#!/usr/bin/env python3
"""
Widevine DASH Video Processor - API Backend
=============================================
Processes a DASH MPD URL: extracts PSSH, gets keys, downloads, decrypts, merges.
Writes progress to a JSON file for the Node.js API to poll.

Usage:
    python3 wv_processor.py <job_id> <mpd_url> <license_url> <wvd_path> <output_dir> <progress_file>
"""

import sys
import os
import re
import json
import base64
import struct
import math
import urllib.request
import urllib.error
import subprocess
import shutil
import time
from pathlib import Path
from datetime import datetime

# ─── Progress Writer ─────────────────────────────────────────────────────
class ProgressWriter:
    def __init__(self, filepath, job_id):
        self.filepath = filepath
        self.job_id = job_id
        self._write(status="processing", progress=0, message="Starting...")
    
    def _write(self, status, progress, message, **extra):
        data = {
            "jobId": self.job_id,
            "status": status,
            "progress": progress,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            **extra
        }
        with open(self.filepath, 'w') as f:
            json.dump(data, f)
    
    def update(self, progress, message, status="processing"):
        self._write(status=status, progress=progress, message=message)
    
    def done(self, video_path, video_size, duration=None, resolution=None, keys=None):
        self._write(
            status="done", progress=100, message="Complete!",
            videoPath=video_path, videoSize=video_size,
            duration=duration, resolution=resolution,
            keysJson=keys
        )
    
    def error(self, message):
        self._write(status="error", progress=0, message=message)

# ─── HTTP Helper ─────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

def http_get(url, extra_headers=None):
    hdrs = dict(HEADERS)
    if extra_headers:
        hdrs.update(extra_headers)
    hdrs.setdefault("Referer", url.rsplit("/", 1)[0] + "/")
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()

# ─── PSSH Extraction ─────────────────────────────────────────────────────
def extract_pssh(mpd_xml):
    pssh_list = []
    for match in re.finditer(r'<cenc:pssh[^>]*>(.*?)</cenc:pssh>', mpd_xml, re.DOTALL):
        val = match.group(1).strip()
        if val and len(val) > 20:
            pssh_list.append(val)
    if not pssh_list:
        for match in re.finditer(r'[A-Za-z0-9+/]{40,}={0,2}', mpd_xml):
            try:
                raw = base64.b64decode(match.group(0))
                if len(raw) > 8 and raw[4:8] == b'pssh':
                    pssh_list.append(match.group(0))
            except Exception:
                continue
    return max(pssh_list, key=len) if pssh_list else None

# ─── Widevine Key Extraction ────────────────────────────────────────────
def get_widevine_keys(pssh_b64, license_url, wvd_path):
    import uuid as _uuid
    from pywidevine.device import Device
    from pywidevine.cdm import Cdm
    from pywidevine.pssh import PSSH

    device = Device.load(wvd_path)
    cdm = Cdm.from_device(device)
    sid = cdm.open()
    challenge = cdm.get_license_challenge(sid, PSSH(pssh_b64))

    req = urllib.request.Request(license_url, data=challenge, headers={
        "Content-Type": "application/octet-stream",
        "User-Agent": HEADERS["User-Agent"]
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        lic = resp.read()

    cdm.parse_license(sid, lic)
    keys = cdm.get_keys(sid)
    cdm.close(sid)

    content_keys = {}
    for key in keys:
        kid = key.kid.bytes.hex() if isinstance(key.kid, _uuid.UUID) else str(key.kid).replace("-", "")
        key_val = key.key.hex() if isinstance(key.key, bytes) else str(key.key)
        if str(key.type) == "CONTENT":
            content_keys[kid] = key_val
    return content_keys

# ─── MPD Parser ─────────────────────────────────────────────────────────
def parse_mpd(mpd_url, mpd_xml):
    base_url = mpd_url.rsplit('/', 1)[0] + '/'
    base_url_match = re.search(r'<BaseURL>(.*?)</BaseURL>', mpd_xml)
    if base_url_match:
        bu = base_url_match.group(1).strip()
        if bu.startswith('http'):
            base_url = bu
        elif not bu.startswith('/'):
            base_url = base_url + bu

    period_dur = None
    m = re.search(r'mediaPresentationDuration="PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+\.?\d*)S)?"', mpd_xml)
    if m:
        hrs, mins, secs = int(m.group(1) or 0), int(m.group(2) or 0), float(m.group(3) or 0)
        period_dur = hrs * 3600 + mins * 60 + secs
    if not period_dur:
        m = re.search(r'<Period[^>]*duration="PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+\.?\d*)S)?"', mpd_xml)
        if m:
            hrs, mins, secs = int(m.group(1) or 0), int(m.group(2) or 0), float(m.group(3) or 0)
            period_dur = hrs * 3600 + mins * 60 + secs

    adaptations = []
    for as_match in re.finditer(r'<AdaptationSet[^>]*>(.*?)</AdaptationSet>', mpd_xml, re.DOTALL):
        as_block = as_match.group(0)
        if 'contentType="audio"' in as_block or 'mimeType="audio' in as_block:
            content_type = "audio"
        else:
            content_type = "video"

        kid_match = re.search(r'default_KID="([0-9a-f-]+)"', as_block, re.IGNORECASE)
        default_kid = kid_match.group(1).replace("-", "") if kid_match else None

        as_seg_tmpl = re.search(r'<SegmentTemplate[^>]*>', as_block, re.DOTALL)
        as_init_tmpl = as_media_tmpl = None
        as_timescale = 1
        as_seg_duration = None
        as_start_num = 1

        if as_seg_tmpl:
            tag = as_seg_tmpl.group(0)
            m = re.search(r'initialization="([^"]*)"', tag)
            if m: as_init_tmpl = m.group(1)
            m = re.search(r'media="([^"]*)"', tag)
            if m: as_media_tmpl = m.group(1)
            m = re.search(r'timescale="(\d+)"', tag)
            if m: as_timescale = int(m.group(1))
            m = re.search(r'duration="(\d+)"', tag)
            if m: as_seg_duration = int(m.group(1))
            m = re.search(r'startNumber="(\d+)"', tag)
            if m: as_start_num = int(m.group(1))

        as_num_segments = 0
        if as_seg_duration and period_dur:
            seg_dur_sec = as_seg_duration / as_timescale
            as_num_segments = math.ceil(period_dur / seg_dur_sec)

        for rep_match in re.finditer(r'<Representation[^>]*id="([^"]*)"[^>]*>', as_block, re.DOTALL):
            rep_id = rep_match.group(1)
            rep_tag = rep_match.group(0)
            bw = re.search(r'bandwidth="(\d+)"', rep_tag)
            w = re.search(r' width="(\d+)"', rep_tag)
            h = re.search(r' height="(\d+)"', rep_tag)

            adaptations.append({
                "type": content_type, "rep_id": rep_id,
                "bandwidth": int(bw.group(1)) if bw else 0,
                "width": int(w.group(1)) if w else 0,
                "height": int(h.group(1)) if h else 0,
                "default_kid": default_kid,
                "init_template": as_init_tmpl, "media_template": as_media_tmpl,
                "timescale": as_timescale, "segment_duration": as_seg_duration,
                "start_number": as_start_num, "num_segments": as_num_segments,
            })

    return {"base_url": base_url, "period_duration": period_dur, "adaptations": adaptations}

# ─── Segment Download ───────────────────────────────────────────────────
def download_segments(base_url, init_tmpl, media_tmpl, rep_id, bandwidth, num_segments, start_num, progress, progress_prefix, base_pct, pct_range):
    def resolve(tmpl, rep_id, num, bw):
        return tmpl.replace('$RepresentationID$', rep_id) \
                   .replace('$Bandwidth$', str(bw)) \
                   .replace('$Number$', str(num)) \
                   .replace('$Time$', str(num))

    init_url = base_url + resolve(init_tmpl, rep_id, 0, bandwidth)
    init_data = http_get(init_url)

    segments = []
    seg_num = start_num
    max_attempts = num_segments + 5 if num_segments > 0 else 300

    while seg_num < start_num + max_attempts:
        seg_url = base_url + resolve(media_tmpl, rep_id, seg_num, bandwidth)
        try:
            seg_data = http_get(seg_url)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                break
            raise
        if len(seg_data) < 10:
            break

        segments.append(seg_data)
        done = seg_num - start_num + 1
        total = num_segments if num_segments > 0 else done + 1
        pct = min(100, done / total * 100)
        progress.update(
            int(base_pct + pct_range * pct / 100),
            f"{progress_prefix} segment {done}/{total}"
        )
        seg_num += 1
        if num_segments > 0 and done >= num_segments:
            break

    return init_data, segments

# ─── Main ────────────────────────────────────────────────────────────────
def main():
    job_id = sys.argv[1]
    mpd_url = sys.argv[2]
    license_url = sys.argv[3]
    wvd_path = sys.argv[4]
    output_dir = sys.argv[5]
    progress_file = sys.argv[6]

    os.makedirs(output_dir, exist_ok=True)
    progress = ProgressWriter(progress_file, job_id)

    try:
        # Step 1: Fetch MPD
        progress.update(5, "Fetching MPD...")
        mpd_xml = http_get(mpd_url).decode("utf-8", errors="replace")

        # Step 2: Extract PSSH + Get Keys
        progress.update(10, "Extracting PSSH & getting keys...")
        pssh_b64 = extract_pssh(mpd_xml)
        if not pssh_b64:
            raise Exception("No PSSH found in MPD")

        content_keys = get_widevine_keys(pssh_b64, license_url, wvd_path)
        if not content_keys:
            raise Exception("No content keys obtained")

        # Step 3: Parse MPD
        progress.update(15, "Parsing MPD...")
        mpd_info = parse_mpd(mpd_url, mpd_xml)

        video_reps = [a for a in mpd_info['adaptations'] if a['type'] == 'video']
        audio_reps = [a for a in mpd_info['adaptations'] if a['type'] == 'audio']
        best_video = max(video_reps, key=lambda x: x.get('height', 0)) if video_reps else None
        best_audio = max(audio_reps, key=lambda x: x.get('bandwidth', 0)) if audio_reps else None

        if not best_video:
            raise Exception("No video representation found")

        # Step 4: Download Segments
        base_url = mpd_info['base_url']
        downloaded = {}

        # Download video (progress 20-60)
        if best_video:
            progress.update(20, "Downloading video segments...")
            init_data, segments = download_segments(
                base_url, best_video['init_template'], best_video['media_template'],
                best_video['rep_id'], best_video['bandwidth'], best_video['num_segments'],
                best_video['start_number'], progress, "Video", 20, 40
            )
            enc_path = os.path.join(output_dir, "video_encrypted.mp4")
            with open(enc_path, 'wb') as f:
                f.write(init_data)
                for seg in segments:
                    f.write(seg)
            
            default_kid = best_video.get('default_kid', '')
            if default_kid:
                default_kid = default_kid.replace('-', '')
            key_hex = kid_hex = None
            if default_kid and default_kid in content_keys:
                key_hex, kid_hex = content_keys[default_kid], default_kid
            else:
                for kid, kv in content_keys.items():
                    key_hex, kid_hex = kv, kid
                    break
            downloaded['video'] = {"enc_path": enc_path, "key_hex": key_hex, "kid_hex": kid_hex}

        # Download audio (progress 60-80)
        if best_audio:
            progress.update(60, "Downloading audio segments...")
            init_data, segments = download_segments(
                base_url, best_audio['init_template'], best_audio['media_template'],
                best_audio['rep_id'], best_audio['bandwidth'], best_audio['num_segments'],
                best_audio['start_number'], progress, "Audio", 60, 20
            )
            enc_path = os.path.join(output_dir, "audio_encrypted.mp4")
            with open(enc_path, 'wb') as f:
                f.write(init_data)
                for seg in segments:
                    f.write(seg)
            
            default_kid = best_audio.get('default_kid', '')
            if default_kid:
                default_kid = default_kid.replace('-', '')
            key_hex = kid_hex = None
            if default_kid and default_kid in content_keys:
                key_hex, kid_hex = content_keys[default_kid], default_kid
            else:
                for kid, kv in content_keys.items():
                    key_hex, kid_hex = kv, kid
                    break
            downloaded['audio'] = {"enc_path": enc_path, "key_hex": key_hex, "kid_hex": kid_hex}

        # Step 5: Decrypt
        progress.update(80, "Decrypting...", status="decrypting")
        
        # Find mp4decrypt
        mp4decrypt_bin = None
        for candidate in ["mp4decrypt", "/usr/local/bin/mp4decrypt", "/usr/bin/mp4decrypt"]:
            if shutil.which(candidate):
                mp4decrypt_bin = candidate
                break
        if not mp4decrypt_bin:
            tools_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "mp4decrypt")
            if os.path.exists(tools_path) and os.access(tools_path, os.X_OK):
                mp4decrypt_bin = tools_path
        
        # Build key args
        key_args = []
        for kid_hex, key_hex in content_keys.items():
            key_args.extend(["--key", f"{kid_hex}:{key_hex}"])

        dec_files = {}
        for rep_type, info in downloaded.items():
            enc_path = info['enc_path']
            dec_path = enc_path.replace('_encrypted.mp4', '_decrypted.mp4')
            
            if mp4decrypt_bin:
                cmd = [mp4decrypt_bin] + key_args + [enc_path, dec_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    raise Exception(f"mp4decrypt failed for {rep_type}: {result.stderr[:200]}")
            else:
                # Use Python fallback
                py_mp4dec = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mp4decrypt.py")
                cmd = [sys.executable, py_mp4dec] + key_args + [enc_path, dec_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    raise Exception(f"Python mp4decrypt failed for {rep_type}: {result.stderr[:200]}")
            
            dec_files[rep_type] = dec_path

        # Step 6: Merge
        progress.update(90, "Merging video + audio...", status="merging")
        final_path = os.path.join(output_dir, "final_video.mp4")
        
        if 'video' in dec_files and 'audio' in dec_files:
            if shutil.which('ffmpeg'):
                result = subprocess.run([
                    "ffmpeg", "-i", dec_files['video'], "-i", dec_files['audio'],
                    "-c:v", "copy", "-c:a", "copy", "-y", final_path
                ], capture_output=True, timeout=60)
                if result.returncode != 0:
                    shutil.copy2(dec_files['video'], final_path)
            else:
                shutil.copy2(dec_files['video'], final_path)
        elif 'video' in dec_files:
            shutil.copy2(dec_files['video'], final_path)

        # Get video info
        video_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
        duration = mpd_info.get('period_duration')
        resolution = f"{best_video['width']}x{best_video['height']}" if best_video else None

        # Done!
        progress.done(
            video_path=final_path,
            video_size=video_size,
            duration=duration,
            resolution=resolution,
            keys=json.dumps(content_keys)
        )

    except Exception as e:
        progress.error(str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
