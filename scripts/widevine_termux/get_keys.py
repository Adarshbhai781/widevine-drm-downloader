#!/usr/bin/env python3
"""
Widevine Key Extractor for Termux
==================================
Automatically extracts PSSH from MPD, gets license, and returns decryption keys.

Usage:
    python3 get_keys.py <mpd_url> [license_url] [wvd_path]

Defaults:
    license_url = https://cwip-shaka-proxy.appspot.com/no_auth
    wvd_path    = ./my_device.wvd
"""

import sys
import os
import re
import base64
import struct
import json
import urllib.request
import urllib.error
from pathlib import Path

# ─── Colors ────────────────────────────────────────────────────────────────
R = "\033[1;31m"
G = "\033[1;32m"
Y = "\033[1;33m"
B = "\033[1;34m"
C = "\033[1;36m"
W = "\033[1;37m"
N = "\033[0m"

def log(level, msg):
    icons = {"info": f"{B}[*]{N}", "ok": f"{G}[+]{N}", "warn": f"{Y}[!]{N}", "err": f"{R}[-]{N}", "key": f"{C}[K]{N}"}
    print(f"  {icons.get(level, icons['info'])} {msg}")

# ─── PSSH Extraction ───────────────────────────────────────────────────────
def extract_pssh_from_mpd(mpd_url):
    """Fetch MPD and extract PSSH box(es) from it."""
    log("info", f"Fetching MPD from:\n       {mpd_url}")
    
    req = urllib.request.Request(mpd_url, headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Termux) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": mpd_url.rsplit("/", 1)[0] + "/"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            mpd_xml = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log("err", f"Failed to fetch MPD: {e}")
        sys.exit(1)
    
    log("ok", f"MPD fetched ({len(mpd_xml)} bytes)")
    
    # Method 1: Find <cenc:pssh> elements
    pssh_list = []
    pssh_pattern = re.compile(r'<cenc:pssh[^>]*>(.*?)</cenc:pssh>', re.DOTALL)
    for match in pssh_pattern.finditer(mpd_xml):
        pssh_b64 = match.group(1).strip()
        if pssh_b64 and len(pssh_b64) > 20:
            pssh_list.append(pssh_b64)
            log("info", f"Found PSSH in <cenc:pssh> tag ({len(pssh_b64)} chars)")
    
    # Method 2: Find base64 PSSH boxes in ContentProtection
    if not pssh_list:
        b64_pattern = re.compile(r'[A-Za-z0-9+/]{40,}={0,2}')
        for match in b64_pattern.finditer(mpd_xml):
            candidate = match.group(0)
            try:
                raw = base64.b64decode(candidate)
                if len(raw) > 8 and raw[4:8] == b'pssh':
                    pssh_list.append(candidate)
                    log("info", f"Found PSSH box in base64 ({len(candidate)} chars)")
            except Exception:
                continue
    
    if not pssh_list:
        log("err", "No PSSH found in MPD!")
        sys.exit(1)
    
    best_pssh = max(pssh_list, key=len)
    log("ok", f"Using PSSH ({len(best_pssh)} chars)")
    return best_pssh

# ─── PSSH Info ─────────────────────────────────────────────────────────────
def parse_pssh_info(pssh_b64):
    """Parse PSSH box and show KIDs."""
    try:
        raw = base64.b64decode(pssh_b64)
        if raw[4:8] != b'pssh':
            return
        version = raw[8]
        sys_id = raw[12:28]
        sys_id_hex = sys_id.hex()
        
        if version > 0:
            kid_count = struct.unpack('>I', raw[28:32])[0]
            offset = 32
            for i in range(kid_count):
                kid = raw[offset:offset+16]
                kid_uuid = f"{kid[0:4].hex()}-{kid[4:6].hex()}-{kid[6:8].hex()}-{kid[8:10].hex()}-{kid[10:16].hex()}"
                log("info", f"KID from PSSH: {kid_uuid}")
                offset += 16
    except Exception:
        pass

# ─── Key Extraction via pywidevine ─────────────────────────────────────────
def get_keys(pssh_b64, license_url, wvd_path):
    """Use pywidevine CDM to get decryption keys."""
    
    if not os.path.exists(wvd_path):
        log("err", f"WVD file not found: {wvd_path}")
        log("info", "Place your .wvd CDM file in the script directory as my_device.wvd")
        sys.exit(1)
    
    try:
        from pywidevine.device import Device
        from pywidevine.cdm import Cdm
        from pywidevine.pssh import PSSH
    except ImportError:
        log("err", "pywidevine not installed!")
        log("info", "Run: pip install pywidevine")
        sys.exit(1)
    
    log("info", f"Loading CDM device: {wvd_path}")
    try:
        device = Device.load(wvd_path)
    except Exception as e:
        log("err", f"Failed to load WVD: {e}")
        sys.exit(1)
    
    log("ok", f"Device loaded (Level {device.security_level})")
    
    cdm = Cdm.from_device(device)
    session_id = cdm.open()
    log("ok", f"CDM session opened: {session_id[:16]}...")
    
    try:
        pssh_obj = PSSH(pssh_b64)
    except Exception as e:
        log("err", f"Invalid PSSH: {e}")
        sys.exit(1)
    
    log("info", "Generating license challenge...")
    try:
        challenge = cdm.get_license_challenge(session_id, pssh_obj)
    except Exception as e:
        log("err", f"Challenge generation failed: {e}")
        sys.exit(1)
    
    log("ok", f"Challenge created ({len(challenge)} bytes)")
    
    log("info", f"Sending to license server:\n       {license_url}")
    try:
        req = urllib.request.Request(license_url, data=challenge, headers={
            "Content-Type": "application/octet-stream",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; Termux)"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            license_data = resp.read()
    except Exception as e:
        log("err", f"License request failed: {e}")
        cdm.close(session_id)
        sys.exit(1)
    
    log("ok", f"License received ({len(license_data)} bytes)")
    
    try:
        cdm.parse_license(session_id, license_data)
    except Exception as e:
        log("err", f"License parsing failed: {e}")
        cdm.close(session_id)
        sys.exit(1)
    
    keys = cdm.get_keys(session_id)
    cdm.close(session_id)
    
    import uuid as _uuid
    content_keys = {}
    all_keys = []
    for key in keys:
        # kid is uuid.UUID, key is bytes, type is str
        if isinstance(key.kid, _uuid.UUID):
            kid = key.kid.bytes.hex()
        else:
            kid = str(key.kid).replace("-", "")
        if isinstance(key.key, bytes):
            key_val = key.key.hex()
        else:
            key_val = str(key.key)
        key_type = str(key.type)
        all_keys.append({"kid": kid, "key": key_val, "type": key_type})
        if key_type == "CONTENT":
            content_keys[kid] = key_val
    
    if not content_keys:
        log("warn", "No CONTENT keys found, using all non-signing keys")
        for key in keys:
            if isinstance(key.kid, _uuid.UUID):
                kid = key.kid.bytes.hex()
            else:
                kid = str(key.kid).replace("-", "")
            if isinstance(key.key, bytes):
                key_val = key.key.hex()
            else:
                key_val = str(key.key)
            key_type = str(key.type)
            if kid != "00000000000000000000000000000000" and key_type != "SIGNING":
                content_keys[kid] = key_val
    
    log("ok", f"Got {len(content_keys)} content keys!")
    print()
    
    for kid, key_val in content_keys.items():
        log("key", f"{kid}:{key_val}")
    print()
    
    return content_keys, all_keys

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    print(f"\n{W}{'='*60}{N}")
    print(f"{C}  Widevine Key Extractor{N}")
    print(f"{W}{'='*60}{N}\n")
    
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <mpd_url> [license_url] [wvd_path]")
        print(f"\nDefaults:")
        print(f"  license_url = https://cwip-shaka-proxy.appspot.com/no_auth")
        print(f"  wvd_path    = ./my_device.wvd")
        sys.exit(1)
    
    mpd_url = sys.argv[1]
    license_url = sys.argv[2] if len(sys.argv) > 2 else "https://cwip-shaka-proxy.appspot.com/no_auth"
    wvd_path = sys.argv[3] if len(sys.argv) > 3 else "./my_device.wvd"
    
    # Step 1: Extract PSSH
    print(f"{Y}[STEP 1]{N} Extract PSSH from MPD")
    pssh_b64 = extract_pssh_from_mpd(mpd_url)
    parse_pssh_info(pssh_b64)
    
    # Step 2: Get Keys
    print(f"\n{Y}[STEP 2]{N} Get decryption keys via CDM")
    content_keys, all_keys = get_keys(pssh_b64, license_url, wvd_path)
    
    # Step 3: Save keys
    print(f"{Y}[STEP 3]{N} Save keys")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    keys_file = os.path.join(script_dir, "keys.json")
    output = {
        "mpd_url": mpd_url,
        "pssh": pssh_b64,
        "license_url": license_url,
        "content_keys": content_keys,
        "all_keys": all_keys
    }
    with open(keys_file, "w") as f:
        json.dump(output, f, indent=2)
    log("ok", f"Keys saved to: {keys_file}")
    
    # Output keys for shell script to pick up
    print(f"\n{W}{'='*60}{N}")
    print(f"{G}  KEYS READY{N}")
    print(f"  Format: <kid>:<key> for yt-dlp/ffmpeg")
    key_args = []
    for kid, key_val in content_keys.items():
        key_args.append(f"{kid}:{key_val}")
    print("KEYS:" + ",".join(key_args))
    print(f"{W}{'='*60}{N}")

if __name__ == "__main__":
    main()
