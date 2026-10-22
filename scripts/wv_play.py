#!/usr/bin/env python3
"""
Widevine DRM Download + Decrypt + Merge script.
Called by Next.js /api/wv/play endpoint.

Usage: python3 wv_play.py <job_id> <job_dir> <mpd_url> <license_url> <quality>

Outputs JSON progress lines to stdout:
  {"status": "getting_keys", "progress": 5, "message": "..."}
  {"status": "done", "progress": 100, "video_path": "...", ...}
"""

import sys
import json
import os
import subprocess
import shutil
import math
import re
import base64
import struct
import requests
import traceback
import uuid as _uuid

# Add flask_api dir to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_api"))

from app import (
    generate_drm_keys,
    extract_pssh_from_mpd,
    parse_pssh_info,
    KNOWN_MPDS,
    DEFAULT_LICENSE_URL,
    USER_AGENT,
)


def emit(data):
    """Print JSON progress line."""
    print(json.dumps(data), flush=True)


def http_download(url):
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*", "Referer": url.rsplit("/", 1)[0] + "/"}
    resp = requests.get(url, headers=hdrs, timeout=60)
    resp.raise_for_status()
    return resp.content


def main():
    job_id = sys.argv[1]
    job_dir = sys.argv[2]
    mpd_url = sys.argv[3]
    license_url = sys.argv[4]
    quality = sys.argv[5] if len(sys.argv) > 5 else "best"

    os.makedirs(job_dir, exist_ok=True)

    try:
        # Step 1: Get keys
        emit({"status": "getting_keys", "progress": 5, "message": "Getting Widevine keys..."})
        drm = generate_drm_keys(mpd_url, license_url)
        content_keys = drm["content_keys"]
        emit({"status": "got_keys", "progress": 15, "message": f"Got {len(content_keys)} keys",
              "keys": [f"{k}:{v}" for k, v in content_keys.items()]})

        # Step 2: Fetch MPD
        emit({"status": "parsing_mpd", "progress": 10, "message": "Parsing MPD..."})
        mpd_resp = requests.get(mpd_url, headers={"User-Agent": USER_AGENT}, timeout=30)
        mpd_resp.raise_for_status()
        mpd_xml = mpd_resp.text
        base_url = mpd_url.rsplit('/', 1)[0] + '/'

        # Parse duration
        period_dur = None
        m = re.search(r'mediaPresentationDuration="PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+\.?\d*)S)?"', mpd_xml)
        if m:
            period_dur = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)

        # Parse AdaptationSets
        adaptations = []
        for as_match in re.finditer(r'<AdaptationSet[^>]*>(.*?)</AdaptationSet>', mpd_xml, re.DOTALL):
            as_block = as_match.group(0)
            content_type = "audio" if ('contentType="audio"' in as_block or 'mimeType="audio' in as_block) else "video"
            kid_match = re.search(r'default_KID="([0-9a-f-]+)"', as_block, re.IGNORECASE)
            default_kid = kid_match.group(1).replace("-", "") if kid_match else None

            seg_tmpl = re.search(r'<SegmentTemplate[^>]*>', as_block, re.DOTALL)
            init_tmpl = media_tmpl = None
            timescale = 1
            seg_duration = None
            start_num = 1

            if seg_tmpl:
                tag = seg_tmpl.group(0)
                m2 = re.search(r'initialization="([^"]*)"', tag)
                if m2: init_tmpl = m2.group(1)
                m2 = re.search(r'media="([^"]*)"', tag)
                if m2: media_tmpl = m2.group(1)
                m2 = re.search(r'timescale="(\d+)"', tag)
                if m2: timescale = int(m2.group(1))
                m2 = re.search(r'duration="(\d+)"', tag)
                if m2: seg_duration = int(m2.group(1))
                m2 = re.search(r'startNumber="(\d+)"', tag)
                if m2: start_num = int(m2.group(1))

            num_segments = 0
            if seg_duration and period_dur:
                num_segments = math.ceil(period_dur / (seg_duration / timescale))

            for rep_match in re.finditer(r'<Representation[^>]*id="([^"]*)"[^>]*>', as_block, re.DOTALL):
                rep_id = rep_match.group(1)
                rep_tag = rep_match.group(0)
                bw = re.search(r'bandwidth="(\d+)"', rep_tag)
                w = re.search(r' width="(\d+)"', rep_tag)
                h = re.search(r' height="(\d+)"', rep_tag)

                rep_full_match = re.search(r'<Representation[^>]*id="' + re.escape(rep_id) + r'"[^>]*>(.*?)</Representation>', as_block, re.DOTALL)
                rep_content = rep_full_match.group(1) if rep_full_match else ""
                rep_bu_match = re.search(r'<BaseURL>(.*?)</BaseURL>', rep_content)
                rep_base_url = rep_bu_match.group(1).strip() if rep_bu_match else None

                adaptations.append({
                    "type": content_type, "rep_id": rep_id,
                    "bandwidth": int(bw.group(1)) if bw else 0,
                    "width": int(w.group(1)) if w else 0,
                    "height": int(h.group(1)) if h else 0,
                    "default_kid": default_kid,
                    "init_template": init_tmpl, "media_template": media_tmpl,
                    "timescale": timescale, "segment_duration": seg_duration,
                    "start_number": start_num, "num_segments": num_segments,
                    "base_url": rep_base_url,
                })

        # Select best video and audio
        video_reps = [a for a in adaptations if a['type'] == 'video']
        audio_reps = [a for a in adaptations if a['type'] == 'audio']

        if quality == "worst":
            best_video = min(video_reps, key=lambda x: x.get('height', 99999)) if video_reps else None
        else:
            best_video = max(video_reps, key=lambda x: x.get('height', 0)) if video_reps else None
        best_audio = max(audio_reps, key=lambda x: x.get('bandwidth', 0)) if audio_reps else None

        if not best_video:
            raise Exception("No video representation found")

        # Step 3: Download
        downloaded = {}
        for rep_type, rep in [("video", best_video), ("audio", best_audio)]:
            if rep is None:
                continue

            if not rep.get('init_template') or not rep.get('media_template'):
                rep_bu = rep.get('base_url')
                if rep_bu:
                    direct_url = base_url + rep_bu if not rep_bu.startswith('http') else rep_bu
                    emit({"status": f"downloading_{rep_type}", "progress": 25 if rep_type == "video" else 60,
                          "message": f"Downloading {rep_type}..."})
                    enc_data = http_download(direct_url)
                    enc_path = os.path.join(job_dir, f"{rep_type}_encrypted.mp4")
                    with open(enc_path, 'wb') as f:
                        f.write(enc_data)
                    dk = rep.get('default_kid', '').replace('-', '')
                    key_hex = content_keys.get(dk) if dk and dk in content_keys else (list(content_keys.values())[0] if content_keys else None)
                    kid_hex = dk if dk and dk in content_keys else (list(content_keys.keys())[0] if content_keys else None)
                    downloaded[rep_type] = {"enc_path": enc_path, "key_hex": key_hex, "kid_hex": kid_hex}
                continue

            emit({"status": f"downloading_{rep_type}", "progress": 20 if rep_type == "video" else 55,
                  "message": f"Downloading {rep_type} segments ({rep.get('height', 'audio')})..."})

            def resolve(tmpl, rid, num, bw):
                return tmpl.replace('$RepresentationID$', rid).replace('$Bandwidth$', str(bw)).replace('$Number$', str(num)).replace('$Time$', str(num))

            init_url = base_url + resolve(rep['init_template'], rep['rep_id'], 0, rep['bandwidth'])
            init_data = http_download(init_url)

            segments = []
            seg_num = rep['start_number']
            max_seg = rep['num_segments'] + 5 if rep['num_segments'] > 0 else 300
            pb = 20 if rep_type == "video" else 55
            pr = 35 if rep_type == "video" else 15

            while seg_num < rep['start_number'] + max_seg:
                seg_url = base_url + resolve(rep['media_template'], rep['rep_id'], seg_num, rep['bandwidth'])
                try:
                    seg_data = http_download(seg_url)
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code in (404, 410):
                        break
                    raise
                if len(seg_data) < 10:
                    break
                segments.append(seg_data)
                done = seg_num - rep['start_number'] + 1
                total = rep['num_segments'] if rep['num_segments'] > 0 else done + 1
                pct = min(100, done / total * 100)
                emit({"progress": int(pb + pr * pct / 100), "message": f"Downloading {rep_type}: seg {done}/{total}"})
                seg_num += 1
                if rep['num_segments'] > 0 and done >= rep['num_segments']:
                    break

            enc_path = os.path.join(job_dir, f"{rep_type}_encrypted.mp4")
            with open(enc_path, 'wb') as f:
                f.write(init_data)
                for seg in segments:
                    f.write(seg)

            dk = rep.get('default_kid', '').replace('-', '')
            key_hex = content_keys.get(dk) if dk and dk in content_keys else (list(content_keys.values())[0] if content_keys else None)
            kid_hex = dk if dk and dk in content_keys else (list(content_keys.keys())[0] if content_keys else None)
            downloaded[rep_type] = {"enc_path": enc_path, "key_hex": key_hex, "kid_hex": kid_hex}

        # Step 4: Decrypt
        emit({"status": "decrypting", "progress": 80, "message": "Decrypting..."})
        mp4decrypt_bin = shutil.which("mp4decrypt") or "/usr/local/bin/mp4decrypt"
        key_args = []
        for kid_hex, key_hex in content_keys.items():
            key_args.extend(["--key", f"{kid_hex}:{key_hex}"])

        dec_files = {}
        for rep_type, info in downloaded.items():
            enc_path = info['enc_path']
            dec_path = enc_path.replace('_encrypted.mp4', '_decrypted.mp4')
            cmd = [mp4decrypt_bin] + key_args + [enc_path, dec_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                py_mp4dec = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widevine_termux", "mp4decrypt.py")
                if os.path.exists(py_mp4dec):
                    cmd = [sys.executable, py_mp4dec] + key_args + [enc_path, dec_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise Exception(f"mp4decrypt failed for {rep_type}: {result.stderr[:200]}")
            dec_files[rep_type] = dec_path

        # Step 5: Merge
        emit({"status": "merging", "progress": 90, "message": "Merging video + audio..."})
        final_path = os.path.join(job_dir, "final_video.mp4")

        if 'video' in dec_files and 'audio' in dec_files:
            result = subprocess.run(["ffmpeg", "-i", dec_files['video'], "-i", dec_files['audio'],
                                   "-c:v", "copy", "-c:a", "copy", "-y", final_path],
                                  capture_output=True, timeout=120)
            if result.returncode != 0:
                result = subprocess.run(["ffmpeg", "-i", dec_files['video'], "-i", dec_files['audio'],
                                       "-c:v", "copy", "-c:a", "aac", "-y", final_path],
                                      capture_output=True, timeout=120)
            if result.returncode != 0:
                shutil.copy2(dec_files['video'], final_path)
        elif 'video' in dec_files:
            shutil.copy2(dec_files['video'], final_path)

        video_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
        resolution = f"{best_video['width']}x{best_video['height']}" if best_video else None

        emit({
            "status": "done", "progress": 100, "message": "Video ready!",
            "video_path": final_path, "video_size": video_size,
            "video_size_mb": round(video_size / (1024*1024), 2),
            "resolution": resolution,
            "title": os.path.basename(mpd_url).replace('.mpd', ''),
            "duration": period_dur
        })

    except Exception as e:
        emit({"status": "error", "progress": 0, "message": str(e), "traceback": traceback.format_exc()})


if __name__ == "__main__":
    main()
