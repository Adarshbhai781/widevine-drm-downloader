#!/usr/bin/env python3
"""
Widevine DRM Processor — Single endpoint script
================================================
Usage: python3 wv_process.py <json_args>

Input JSON:
  {
    "processurl": "<MPD_URL or preset name>",
    "license_url": "<optional license URL>",
    "pssh": "<optional PSSH base64>"
  }

Output JSON:
  {
    "status": "success",
    "session_id": "...",
    "mpd_url": "...",
    "license_url": "...",
    "keys": [{"kid": "...", "key": "..."}],
    "keys_hex": ["KID:KEY", ...],
    "clearkeys": {"KID": "KEY", ...},
    "download_cmd": "yt-dlp ..."
  }
"""

import sys
import os
import re
import json
import time
import base64
import hashlib
import requests
from bs4 import BeautifulSoup

# ─── pywidevine ───────────────────────────────────────────────────────
from pywidevine.cdm import Cdm
from pywidevine.device import Device, DeviceTypes
from pywidevine.pssh import PSSH

# ─── CDM FILES ────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CDM_DIR = os.path.join(SCRIPT_DIR, "widevine_termux")
PRIVATE_KEY = os.path.join(CDM_DIR, "private_key.der")
CLIENT_ID = os.path.join(CDM_DIR, "client_id.bin")

# ─── PRESETS ──────────────────────────────────────────────────────────
PRESETS = {
    "bitmovin": {
        "mpd": "https://cdn.bitmovin.com/content/assets/art-of-motion_drm/mpds/11331.mpd",
        "lic": "https://cwip-shaka-proxy.appspot.com/no_auth",
        "pssh": "AAAAW3Bzc2gAAAAA7e+LqXnWSs6jyCfc1R0h7QAAADsIARIQ62dqu8s0Xpa7z2FmMPGj2hoNd2lkZXZpbmVfdGVzdCIQZmtqM2xqYVNkZmFsa3IzaioCSEQyAA==",
    },
    "tears": {
        "mpd": "https://storage.googleapis.com/wvmedia/cenc/h264/tears/tears.mpd",
        "lic": "https://cwip-shaka-proxy.appspot.com/no_auth",
    },
    "tears_vp9": {
        "mpd": "https://storage.googleapis.com/wvmedia/cenc/vp9/tears/tears.mpd",
        "lic": "https://cwip-shaka-proxy.appspot.com/no_auth",
    },
}

DEFAULT_LIC = "https://cwip-shaka-proxy.appspot.com/no_auth"

# ─── CDM SINGLETON ────────────────────────────────────────────────────
_cdm = None

def get_cdm():
    global _cdm
    if _cdm is not None:
        return _cdm
    with open(PRIVATE_KEY, "rb") as f:
        pk = f.read()
    with open(CLIENT_ID, "rb") as f:
        ci = f.read()
    device = Device(type_=DeviceTypes.ANDROID, security_level=3, flags=None,
                    private_key=pk, client_id=ci)
    _cdm = Cdm.from_device(device)
    return _cdm


# ─── MPD FETCHING ─────────────────────────────────────────────────────
def fetch_mpd(mpd_url: str) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://bitmovin.com/demos/drm/",
    }
    # Method 1: standard
    try:
        r = requests.get(mpd_url, headers=headers, timeout=15)
        if r.status_code == 200 and "<MPD" in r.text:
            return r.text
    except Exception:
        pass
    # Method 2: curl_cffi
    try:
        from curl_cffi import requests as cf_req
        r = cf_req.get(mpd_url, impersonate="chrome120", timeout=15)
        if r.status_code == 200 and "<MPD" in r.text:
            return r.text
    except Exception:
        pass
    return None


# ─── PSSH EXTRACTION ──────────────────────────────────────────────────
def extract_pssh(mpd_xml: str) -> list[str]:
    pssh_list = []
    # <cenc:pssh> tags
    soup = BeautifulSoup(mpd_xml, "xml")
    for tag in soup.find_all("cenc:pssh"):
        val = tag.get_text(strip=True)
        if val and val not in pssh_list:
            pssh_list.append(val)
    # Also check inside ContentProtection
    WV_UUID = "edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"
    for cp in soup.find_all("ContentProtection"):
        if WV_UUID in cp.get("schemeIdUri", "").lower():
            for ptag in cp.find_all("cenc:pssh"):
                val = ptag.get_text(strip=True)
                if val and val not in pssh_list:
                    pssh_list.append(val)
    # Regex fallback
    if not pssh_list:
        for m in re.findall(r"<cenc:pssh[^>]*>(.*?)</cenc:pssh>", mpd_xml, re.DOTALL):
            val = m.strip()
            if val and val not in pssh_list:
                pssh_list.append(val)
    return pssh_list


# ─── DRM KEY GENERATION ──────────────────────────────────────────────
def get_keys(pssh_b64: str, license_url: str) -> list[dict]:
    cdm = get_cdm()
    pssh = PSSH(pssh_b64)
    sid = cdm.open()
    try:
        challenge = cdm.get_license_challenge(sid, pssh)
        resp = requests.post(license_url, data=challenge,
                             headers={"Content-Type": "application/octet-stream"},
                             timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"License server HTTP {resp.status_code}")
        cdm.parse_license(sid, resp.content)
        keys = []
        for key in cdm.get_keys(sid):
            if key.type == "CONTENT":
                keys.append({"kid": key.kid.hex, "key": key.key.hex()})
        return keys
    finally:
        cdm.close(sid)


# ─── MAIN PROCESSOR ──────────────────────────────────────────────────
def process(args: dict) -> dict:
    processurl = args.get("processurl", "").strip()
    license_url = args.get("license_url", "").strip()
    pssh_input = args.get("pssh", "").strip()

    if not processurl:
        return {"status": "error", "message": "Missing processurl"}

    # Resolve preset
    preset = PRESETS.get(processurl.lower())
    if preset:
        mpd_url = preset["mpd"]
        if not license_url:
            license_url = preset.get("lic", DEFAULT_LIC)
        pssh_input = pssh_input or preset.get("pssh", "")
    else:
        mpd_url = processurl

    # Step 1: Get PSSH
    if not pssh_input:
        mpd_xml = fetch_mpd(mpd_url)
        if mpd_xml:
            pssh_list = extract_pssh(mpd_xml)
            if pssh_list:
                pssh_input = pssh_list[0]
        # Bitmovin Cloudflare fallback
        if not pssh_input and "bitmovin.com" in mpd_url:
            bp = PRESETS["bitmovin"]
            pssh_input = bp["pssh"]
            if not license_url:
                license_url = bp["lic"]

    if not pssh_input:
        return {"status": "error", "message": "No PSSH found. Provide pssh parameter directly."}

    if not license_url:
        license_url = DEFAULT_LIC

    # Step 2: Get DRM keys
    content_keys = get_keys(pssh_input, license_url)
    if not content_keys:
        return {"status": "error", "message": "No CONTENT keys from license server.",
                "pssh": pssh_input, "license_url": license_url}

    # Step 3: Build response
    session_id = hashlib.md5(f"{mpd_url}{time.time()}".encode()).hexdigest()[:12]
    keys_hex = [f"{k['kid']}:{k['key']}" for k in content_keys]
    clearkeys = {k["kid"]: k["key"] for k in content_keys}

    # yt-dlp command
    key_args = " ".join([f"--decryption-key {kh}" for kh in keys_hex])
    download_cmd = f'yt-dlp --allow-unplayable-formats {key_args} "{mpd_url}"'

    return {
        "status": "success",
        "session_id": session_id,
        "mpd_url": mpd_url,
        "license_url": license_url,
        "pssh": pssh_input,
        "keys": content_keys,
        "keys_hex": keys_hex,
        "clearkeys": clearkeys,
        "download_cmd": download_cmd,
    }


# ─── CLI ENTRY ────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Usage: wv_process.py '<json_args>'"}))
        sys.exit(1)

    try:
        args = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {e}"}))
        sys.exit(1)

    try:
        result = process(args)
        print(json.dumps(result))
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"status": "error", "message": str(e), "type": type(e).__name__}))
        sys.exit(1)
