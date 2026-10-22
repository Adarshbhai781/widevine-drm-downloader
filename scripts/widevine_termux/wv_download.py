#!/usr/bin/env python3
"""
Widevine DASH Video Downloader - Complete Solution
===================================================
Downloads DRM-protected DASH video using Widevine CDM keys.

Steps:
  1. Fetch MPD
  2. Extract PSSH from MPD
  3. Get decryption keys via CDM
  4. Parse MPD for segment URLs
  5. Download init + media segments
  6. Decrypt using Python mp4decrypt
  7. Merge video+audio with ffmpeg

Usage:
    python3 wv_download.py <mpd_url> [license_url] [wvd_path]
"""

import sys
import os
import re
import base64
import struct
import json
import math
import urllib.request
import urllib.error
import subprocess
import shutil
from pathlib import Path

# ─── Colors ────────────────────────────────────────────────────────────────
R = "\033[1;31m"; G = "\033[1;32m"; Y = "\033[1;33m"; B = "\033[1;34m"; C = "\033[1;36m"; W = "\033[1;37m"; N = "\033[0m"

def log(level, msg):
    icons = {"info": f"{B}[*]{N}", "ok": f"{G}[+]{N}", "warn": f"{Y}[!]{N}", "err": f"{R}[-]{N}", "key": f"{C}[K]{N}", "dl": f"{G}↓{N}"}
    print(f"  {icons.get(level, icons['info'])} {msg}")

def header(text):
    print(f"\n  {Y}▸ {text}{N}\n")

# ─── HTTP Helper ───────────────────────────────────────────────────────────
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

# ─── PSSH Extraction ───────────────────────────────────────────────────────
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

# ─── Widevine Key Extraction ──────────────────────────────────────────────
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

# ─── MPD Parser ────────────────────────────────────────────────────────────
def parse_mpd(mpd_url, mpd_xml):
    """Parse MPD and return segment download info per adaptation."""
    
    # Base URL for relative paths (the directory containing the MPD)
    base_url = mpd_url.rsplit('/', 1)[0] + '/'
    
    # Also check for BaseURL
    base_url_match = re.search(r'<BaseURL>(.*?)</BaseURL>', mpd_xml)
    if base_url_match:
        bu = base_url_match.group(1).strip()
        if bu.startswith('http'):
            base_url = bu
        elif not bu.startswith('/'):
            base_url = base_url + bu
    
    # Period duration
    period_dur = None
    m = re.search(r'mediaPresentationDuration="PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+\.?\d*)S)?"', mpd_xml)
    if m:
        hrs = int(m.group(1) or 0)
        mins = int(m.group(2) or 0)
        secs = float(m.group(3) or 0)
        period_dur = hrs * 3600 + mins * 60 + secs
    
    if not period_dur:
        m = re.search(r'<Period[^>]*duration="PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+\.?\d*)S)?"', mpd_xml)
        if m:
            hrs = int(m.group(1) or 0)
            mins = int(m.group(2) or 0)
            secs = float(m.group(3) or 0)
            period_dur = hrs * 3600 + mins * 60 + secs
    
    # Parse AdaptationSets with their own SegmentTemplate
    adaptations = []
    for as_match in re.finditer(r'<AdaptationSet[^>]*>(.*?)</AdaptationSet>', mpd_xml, re.DOTALL):
        as_block = as_match.group(0)
        
        # Determine type
        if 'contentType="audio"' in as_block or 'mimeType="audio' in as_block:
            content_type = "audio"
        else:
            content_type = "video"
        
        # Default KID
        kid_match = re.search(r'default_KID="([0-9a-f-]+)"', as_block, re.IGNORECASE)
        default_kid = kid_match.group(1).replace("-", "") if kid_match else None
        
        # Per-AdaptationSet SegmentTemplate
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
        
        # Calculate number of segments for this adaptation
        as_num_segments = 0
        if as_seg_duration and period_dur:
            seg_dur_sec = as_seg_duration / as_timescale
            as_num_segments = math.ceil(period_dur / seg_dur_sec)
        
        # Representations
        for rep_match in re.finditer(r'<Representation[^>]*id="([^"]*)"[^>]*>', as_block, re.DOTALL):
            rep_id = rep_match.group(1)
            rep_tag = rep_match.group(0)
            
            bw = re.search(r'bandwidth="(\d+)"', rep_tag)
            w = re.search(r' width="(\d+)"', rep_tag)
            h = re.search(r' height="(\d+)"', rep_tag)
            
            adaptations.append({
                "type": content_type,
                "rep_id": rep_id,
                "bandwidth": int(bw.group(1)) if bw else 0,
                "width": int(w.group(1)) if w else 0,
                "height": int(h.group(1)) if h else 0,
                "default_kid": default_kid,
                "init_template": as_init_tmpl,
                "media_template": as_media_tmpl,
                "timescale": as_timescale,
                "segment_duration": as_seg_duration,
                "start_number": as_start_num,
                "num_segments": as_num_segments,
            })
    
    return {
        "base_url": base_url,
        "period_duration": period_dur,
        "adaptations": adaptations,
    }

# ─── Segment Download ─────────────────────────────────────────────────────
def download_segments(base_url, init_tmpl, media_tmpl, rep_id, bandwidth, num_segments, start_num, output_dir, prefix):
    """Download init + media segments for a representation."""
    
    # Resolve template
    def resolve(tmpl, rep_id, num, bw):
        return tmpl.replace('$RepresentationID$', rep_id) \
                   .replace('$Bandwidth$', str(bw)) \
                   .replace('$Number$', str(num)) \
                   .replace('$Time$', str(num))
    
    # Download init segment
    init_url = base_url + resolve(init_tmpl, rep_id, 0, bandwidth)
    log("dl", f"Init: {init_url}")
    init_data = http_get(init_url)
    
    # Download media segments
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
        
        # Progress
        done = seg_num - start_num + 1
        total = num_segments if num_segments > 0 else done + 1
        pct = min(100, done / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"\r  {G}↓{N} {prefix} [{bar}] {done}/{total} ({pct:.0f}%)   ", end="", flush=True)
        
        seg_num += 1
        
        if num_segments > 0 and done >= num_segments:
            break
    
    print()  # newline
    return init_data, segments

# ─── Find mp4decrypt ──────────────────────────────────────────────────────
def find_mp4decrypt(script_dir):
    """Find mp4decrypt binary or our Python replacement."""
    # Check for real mp4decrypt
    for candidate in ["mp4decrypt", "/usr/bin/mp4decrypt", "/usr/local/bin/mp4decrypt"]:
        if shutil.which(candidate):
            return ("binary", candidate)
    
    # Check in tools dir
    tools_mp4dec = os.path.join(script_dir, "tools", "mp4decrypt")
    if os.path.exists(tools_mp4dec) and os.access(tools_mp4dec, os.X_OK):
        return ("binary", tools_mp4dec)
    
    # Use our Python mp4decrypt
    py_mp4dec = os.path.join(script_dir, "mp4decrypt.py")
    if os.path.exists(py_mp4dec):
        return ("python", py_mp4dec)
    
    return None

def decrypt_file(enc_path, dec_path, all_keys, mp4decrypt_info):
    """Decrypt an encrypted MP4 file. all_keys = {kid_hex: key_hex}"""
    # Build --key arguments for ALL keys (mp4decrypt matches KID internally)
    key_args = []
    for kid_hex, key_hex in all_keys.items():
        key_args.extend(["--key", f"{kid_hex}:{key_hex}"])
    
    if mp4decrypt_info[0] == "binary":
        cmd = [mp4decrypt_info[1]] + key_args + [enc_path, dec_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log("err", f"mp4decrypt failed: {result.stderr[:200]}")
            return False
        return True
    
    elif mp4decrypt_info[0] == "python":
        cmd = [sys.executable, mp4decrypt_info[1]] + key_args + [enc_path, dec_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log("err", f"Python mp4decrypt failed: {result.stderr[:200]}")
            return False
        return True
    
    return False

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    print(f"\n{W}{'═'*60}{N}")
    print(f"{C}  Widevine DASH Auto Downloader{N}")
    print(f"{W}{'═'*60}{N}\n")
    
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <mpd_url> [license_url] [wvd_path]")
        print(f"\nDefaults:")
        print(f"  license_url = https://cwip-shaka-proxy.appspot.com/no_auth")
        print(f"  wvd_path    = ./my_device.wvd")
        sys.exit(1)
    
    mpd_url = sys.argv[1]
    license_url = sys.argv[2] if len(sys.argv) > 2 else "https://cwip-shaka-proxy.appspot.com/no_auth"
    wvd_path = sys.argv[3] if len(sys.argv) > 3 else "./my_device.wvd"
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "downloads")
    os.makedirs(output_dir, exist_ok=True)
    
    if not os.path.exists(wvd_path):
        log("err", f"WVD not found: {wvd_path}")
        sys.exit(1)
    
    # ─── STEP 1: Fetch MPD ─────────────────────────────────────────────
    header("STEP 1/5: Fetch MPD")
    log("info", f"URL: {mpd_url}")
    mpd_xml = http_get(mpd_url).decode("utf-8", errors="replace")
    log("ok", f"MPD fetched ({len(mpd_xml)} bytes)")
    
    # ─── STEP 2: Extract PSSH + Get Keys ──────────────────────────────
    header("STEP 2/5: Get Decryption Keys")
    pssh_b64 = extract_pssh(mpd_xml)
    if not pssh_b64:
        log("err", "No PSSH found!")
        sys.exit(1)
    log("ok", f"PSSH extracted ({len(pssh_b64)} chars)")
    
    content_keys = get_widevine_keys(pssh_b64, license_url, wvd_path)
    log("ok", f"Got {len(content_keys)} content keys")
    for kid, key in content_keys.items():
        log("key", f"{kid}:{key}")
    
    # ─── STEP 3: Parse MPD ─────────────────────────────────────────────
    header("STEP 3/5: Parse MPD")
    mpd_info = parse_mpd(mpd_url, mpd_xml)
    log("ok", f"Found {len(mpd_info['adaptations'])} representations")
    
    for adapt in mpd_info['adaptations']:
        label = f"{adapt['width']}x{adapt['height']}" if adapt['type'] == 'video' else "audio"
        log("info", f"  {adapt['type']}: {adapt['rep_id']} {label} @ {adapt['bandwidth']}bps (KID: {adapt.get('default_kid','?')})")
    
    # ─── STEP 4: Download Segments ─────────────────────────────────────
    header("STEP 4/5: Download Encrypted Segments")
    
    video_reps = [a for a in mpd_info['adaptations'] if a['type'] == 'video']
    audio_reps = [a for a in mpd_info['adaptations'] if a['type'] == 'audio']
    
    best_video = max(video_reps, key=lambda x: x['bandwidth']) if video_reps else None
    best_audio = max(audio_reps, key=lambda x: x['bandwidth']) if audio_reps else None
    
    downloaded = {}
    
    for rep_type, rep in [("video", best_video), ("audio", best_audio)]:
        if rep is None:
            continue
        
        log("info", f"Downloading {rep_type}: {rep['rep_id']}")
        
        init_data, segments = download_segments(
            mpd_info['base_url'],
            rep['init_template'],
            rep['media_template'],
            rep['rep_id'],
            rep['bandwidth'],
            rep['num_segments'],
            rep['start_number'],
            output_dir,
            rep_type
        )
        
        log("ok", f"{rep_type}: init ({len(init_data)}B) + {len(segments)} segments")
        
        # Save encrypted
        enc_path = os.path.join(output_dir, f"{rep_type}_encrypted.mp4")
        with open(enc_path, 'wb') as f:
            f.write(init_data)
            for seg in segments:
                f.write(seg)
        log("ok", f"Saved: {enc_path} ({os.path.getsize(enc_path)} bytes)")
        
        # Find matching key
        default_kid = rep.get('default_kid', '')
        if default_kid:
            default_kid = default_kid.replace('-', '')
        
        key_hex = None
        kid_hex = None
        
        if default_kid and default_kid in content_keys:
            key_hex = content_keys[default_kid]
            kid_hex = default_kid
        else:
            # Try all keys - use first one
            for kid, kv in content_keys.items():
                key_hex = kv
                kid_hex = kid
                break
        
        downloaded[rep_type] = {
            "enc_path": enc_path,
            "key_hex": key_hex,
            "kid_hex": kid_hex,
        }
    
    # Store all content keys for mp4decrypt (needs ALL keys for proper KID matching)
    all_content_keys = content_keys
    
    # ─── STEP 5: Decrypt ───────────────────────────────────────────────
    header("STEP 5/5: Decrypt & Merge")
    
    # Find mp4decrypt
    mp4dec_info = find_mp4decrypt(script_dir)
    if mp4dec_info:
        log("ok", f"mp4decrypt: {mp4dec_info[1]}")
    else:
        log("err", "No mp4decrypt found! Need mp4decrypt.py or Bento4 binary")
        log("info", "Install: pip install bento4 or download from https://github.com/niclas-niclas/Bento4/releases")
        # Save keys for manual use
        keys_path = os.path.join(output_dir, "keys.txt")
        with open(keys_path, 'w') as f:
            for kid, key in content_keys.items():
                f.write(f"{kid}:{key}\n")
        log("info", f"Keys saved to: {keys_path}")
        sys.exit(1)
    
    dec_files = {}
    for rep_type, info in downloaded.items():
        enc_path = info['enc_path']
        dec_path = enc_path.replace('_encrypted.mp4', '_decrypted.mp4')
        
        log("info", f"Decrypting {rep_type} (using {len(all_content_keys)} keys)")
        
        if decrypt_file(enc_path, dec_path, all_content_keys, mp4dec_info):
            log("ok", f"Decrypted: {dec_path} ({os.path.getsize(dec_path)} bytes)")
            dec_files[rep_type] = dec_path
        else:
            log("err", f"Decryption failed for {rep_type}")
    
    # Merge with ffmpeg
    if 'video' in dec_files and 'audio' in dec_files:
        final_path = os.path.join(output_dir, "final_video.mp4")
        log("info", "Merging video + audio with ffmpeg...")
        
        if shutil.which('ffmpeg'):
            result = subprocess.run([
                "ffmpeg", "-i", dec_files['video'], "-i", dec_files['audio'],
                "-c:v", "copy", "-c:a", "copy", "-y", final_path
            ], capture_output=True)
            
            if result.returncode == 0:
                log("ok", f"Final: {final_path} ({os.path.getsize(final_path)/(1024*1024):.1f} MB)")
            else:
                log("warn", "ffmpeg merge failed, keeping separate files")
                shutil.copy2(dec_files['video'], final_path)
        else:
            log("warn", "ffmpeg not found, video+audio not merged")
            shutil.copy2(dec_files['video'], os.path.join(output_dir, "final_video.mp4"))
    
    elif 'video' in dec_files:
        final_path = os.path.join(output_dir, "final_video.mp4")
        shutil.copy2(dec_files['video'], final_path)
        log("ok", f"Final (video only): {final_path}")
    
    # Save keys
    keys_path = os.path.join(output_dir, "keys.txt")
    with open(keys_path, 'w') as f:
        for kid, key in content_keys.items():
            f.write(f"{kid}:{key}\n")
    log("ok", f"Keys saved: {keys_path}")
    
    # Summary
    final = os.path.join(output_dir, "final_video.mp4")
    if os.path.exists(final):
        size_mb = os.path.getsize(final) / (1024*1024)
        print(f"\n{W}{'═'*60}{N}")
        print(f"{G}  ✅ DONE! Video: {final} ({size_mb:.1f} MB){N}")
        print(f"{W}{'═'*60}{N}")

if __name__ == "__main__":
    main()
