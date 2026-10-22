#!/usr/bin/env python3
"""
Widevine DRM Key Generator - Flask API
=======================================
Flask API endpoint that:
1. Takes MPD URL + License URL as input
2. Fetches MPD, extracts PSSH
3. Uses pywidevine CDM to generate decryption keys (KID:KEY)
4. Optionally uses yt-dlp to create downloadable URL
5. Returns keys, PSSH, and downloadable URL

Usage:
    python3 app.py

Endpoints:
    GET /api?mpd=<MPD_URL>&lic=<LICENSE_URL>
    POST /api  (JSON body: {"mpd": "<MPD_URL>", "lic": "<LICENSE_URL>"})
    GET /keys?mpd=<MPD_URL>&lic=<LICENSE_URL>  (keys only, minimal)
    GET /download?mpd=<MPD_URL>&lic=<LICENSE_URL>  (yt-dlp download URL)
    GET /health  (health check)
"""

from flask import Flask, request, jsonify
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
import requests
from bs4 import BeautifulSoup
import os
import glob
import re
import base64
import struct
import json
import uuid as _uuid
import subprocess
import shutil
import traceback
from datetime import datetime

app = Flask(__name__)

# ─── Configuration ────────────────────────────────────────────────────────
WVD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WVDs")
DEFAULT_LICENSE_URL = "https://cwip-shaka-proxy.appspot.com/no_auth"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# ─── WVD Device Check ────────────────────────────────────────────────────
def wvd_check():
    """Find the first .wvd file in the WVDs directory."""
    wvd_files = glob.glob(os.path.join(WVD_DIR, "*.wvd"))
    if not wvd_files:
        raise FileNotFoundError(
            f"No .wvd file found in {WVD_DIR}. "
            "Place your Widevine CDM device (.wvd) file in the WVDs/ directory."
        )
    return wvd_files[0]


# ─── PSSH Extraction ─────────────────────────────────────────────────────
def extract_pssh_from_mpd(mpd_url, custom_headers=None):
    """Fetch MPD and extract PSSH box(es) from it.
    
    Returns:
        tuple: (pssh_b64, mpd_xml) - the PSSH base64 string and full MPD XML
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": mpd_url.rsplit("/", 1)[0] + "/",
    }
    if custom_headers:
        headers.update(custom_headers)

    resp = requests.get(mpd_url, headers=headers, timeout=30)
    resp.raise_for_status()
    mpd_xml = resp.text

    # Method 1: Find <cenc:pssh> elements
    pssh_list = []
    for match in re.finditer(r'<cenc:pssh[^>]*>(.*?)</cenc:pssh>', mpd_xml, re.DOTALL):
        val = match.group(1).strip()
        if val and len(val) > 20:
            pssh_list.append(val)

    # Method 2: Find base64-encoded PSSH boxes in ContentProtection
    if not pssh_list:
        for match in re.finditer(r'[A-Za-z0-9+/]{40,}={0,2}', mpd_xml):
            try:
                raw = base64.b64decode(match.group(0))
                if len(raw) > 8 and raw[4:8] == b'pssh':
                    pssh_list.append(match.group(0))
            except Exception:
                continue

    if not pssh_list:
        raise ValueError("No PSSH found in MPD manifest")

    # Use the longest PSSH (most complete)
    best_pssh = max(pssh_list, key=len)
    return best_pssh, mpd_xml


# ─── PSSH Info Parser ────────────────────────────────────────────────────
def parse_pssh_info(pssh_b64):
    """Parse PSSH box and extract KIDs."""
    try:
        raw = base64.b64decode(pssh_b64)
        if raw[4:8] != b'pssh':
            return {"system_id": None, "kids": []}
        
        version = raw[8]
        system_id = raw[12:28].hex()
        kids = []
        
        if version > 0:
            kid_count = struct.unpack('>I', raw[28:32])[0]
            offset = 32
            for i in range(kid_count):
                kid = raw[offset:offset+16]
                kid_uuid = f"{kid[0:4].hex()}-{kid[4:6].hex()}-{kid[6:8].hex()}-{kid[8:10].hex()}-{kid[10:16].hex()}"
                kids.append(kid_uuid)
                offset += 16
        
        return {"system_id": system_id, "kids": kids, "version": version}
    except Exception:
        return {"system_id": None, "kids": []}


# ─── Widevine Key Generation ─────────────────────────────────────────────
def generate_drm_keys(mpd_url, license_url, custom_headers=None):
    """Generate Widevine DRM decryption keys for a given MPD + License URL.
    
    Args:
        mpd_url: URL of the DASH MPD manifest
        license_url: URL of the Widevine license server
        custom_headers: Optional dict of extra headers for license request
    
    Returns:
        dict with keys, pssh, mpd_url, license_url, etc.
    """
    # Step 1: Find WVD device file
    wvd_path = wvd_check()
    
    # Step 2: Fetch MPD and extract PSSH
    pssh_b64, mpd_xml = extract_pssh_from_mpd(mpd_url)
    pssh_info = parse_pssh_info(pssh_b64)
    
    # Step 3: Load CDM device
    device = Device.load(wvd_path)
    cdm = Cdm.from_device(device)
    session_id = cdm.open()
    
    # Step 4: Generate license challenge
    ipssh = PSSH(pssh_b64)
    challenge = cdm.get_license_challenge(session_id, ipssh)
    
    # Step 5: Send challenge to license server
    lic_headers = {
        "Content-Type": "application/octet-stream",
        "User-Agent": USER_AGENT,
    }
    if custom_headers:
        lic_headers.update(custom_headers)
    
    lic_resp = requests.post(license_url, data=challenge, headers=lic_headers, timeout=30)
    lic_resp.raise_for_status()
    license_data = lic_resp.content
    
    # Step 6: Parse license and extract keys
    cdm.parse_license(session_id, license_data)
    keys = cdm.get_keys(session_id)
    cdm.close(session_id)
    
    # Step 7: Format keys
    content_keys = {}
    all_keys = []
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
        all_keys.append({"kid": kid, "key": key_val, "type": key_type})
        
        if key_type == "CONTENT":
            content_keys[kid] = key_val
    
    # Fallback: if no CONTENT keys, use non-signing keys
    if not content_keys:
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
    
    # Format keys as KID:KEY strings
    key_strings = [f"{kid}:{key}" for kid, key in content_keys.items()]
    
    return {
        "mpd_url": mpd_url,
        "license_url": license_url,
        "pssh": pssh_b64,
        "pssh_info": pssh_info,
        "content_keys": content_keys,
        "key_strings": key_strings,
        "all_keys": all_keys,
        "device_security_level": device.security_level,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─── yt-dlp Integration ──────────────────────────────────────────────────
def get_ytdlp_info(url, keys=None):
    """Use yt-dlp to get download info for a DASH stream.
    
    For DRM-protected content, yt-dlp cannot directly decrypt. We use it to:
    1. Get format info and direct URLs (--allow-unplayable-formats)
    2. Build a yt-dlp command with --decryption-key for the user to run
    
    Args:
        url: MPD URL to process
        keys: dict of {kid: key} for Widevine decryption
    
    Returns:
        dict with download URLs, formats, and yt-dlp command.
    """
    try:
        ytdlp_bin = os.path.expanduser("~/.local/bin/yt-dlp")
        if not os.path.exists(ytdlp_bin):
            ytdlp_bin = shutil.which("yt-dlp") or "yt-dlp"
        
        # Step 1: Get format info with --dump-json --allow-unplayable-formats
        cmd = [
            ytdlp_bin,
            "--dump-json",
            "--no-warnings",
            "--allow-unplayable-formats",
            url,
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr[:500] if result.stderr else "yt-dlp failed",
                "url": url,
            }
        
        info = json.loads(result.stdout)
        
        # Extract useful format info
        formats = []
        for fmt in info.get("formats", []):
            formats.append({
                "format_id": fmt.get("format_id"),
                "ext": fmt.get("ext"),
                "resolution": fmt.get("resolution"),
                "filesize": fmt.get("filesize"),
                "url": fmt.get("url"),
                "vcodec": fmt.get("vcodec"),
                "acodec": fmt.get("acodec"),
                "tbr": fmt.get("tbr"),
                "drm": fmt.get("drm"),
            })
        
        # Step 2: Build yt-dlp download command with decryption keys
        # yt-dlp uses --decryption-key KID:KEY for each key
        download_cmd = [ytdlp_bin]
        if keys:
            for kid, key in keys.items():
                download_cmd.extend(["--decryption-key", f"{kid}:{key}"])
        download_cmd.extend(["-o", "%(title)s.%(ext)s", url])
        
        return {
            "success": True,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "formats": formats,
            "best_url": info.get("url"),
            "requested_url": url,
            "download_command": " ".join(download_cmd),
            "mp4decrypt_keys": " ".join([f"--key {kid}:{key}" for kid, key in (keys or {}).items()]),
        }
        
    except FileNotFoundError:
        return {"success": False, "error": "yt-dlp not installed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "yt-dlp timed out"}
    except json.JSONDecodeError:
        return {"success": False, "error": "yt-dlp output parse failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── API Endpoints ───────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    try:
        wvd_path = wvd_check()
        wvd_ok = True
    except FileNotFoundError:
        wvd_ok = False
    
    return jsonify({
        "status": "ok" if wvd_ok else "degraded",
        "service": "Widevine DRM Key Generator",
        "wvd_available": wvd_ok,
        "wvd_path": wvd_path if wvd_ok else None,
        "pywidevine": True,
        "yt_dlp": os.path.exists(os.path.expanduser("~/.local/bin/yt-dlp")),
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.route('/api', methods=['GET', 'POST'])
def api():
    """Main API endpoint - Generate DRM keys from MPD + License URL.
    
    GET  /api?mpd=<MPD_URL>&lic=<LICENSE_URL>&headers=<JSON_HEADERS>
    POST /api  body: {"mpd": "<MPD_URL>", "lic": "<LICENSE_URL>", "headers": {...}}
    
    Parameters:
        mpd: MPD manifest URL (required)
        lic: License server URL (optional, defaults to Shaka proxy)
        headers: Custom headers for license request (optional, JSON dict)
        ytdlp: Set to "true" to also get yt-dlp download info (optional)
    
    Returns:
        JSON with content_keys, key_strings, pssh, pssh_info, etc.
    """
    # Parse parameters
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        mpd_url = data.get('mpd')
        license_url = data.get('lic') or data.get('license') or DEFAULT_LICENSE_URL
        custom_headers = data.get('headers')
        do_ytdlp = data.get('ytdlp', False)
    else:
        mpd_url = request.args.get('mpd')
        license_url = request.args.get('lic') or request.args.get('license') or DEFAULT_LICENSE_URL
        headers_str = request.args.get('headers')
        custom_headers = json.loads(headers_str) if headers_str else None
        do_ytdlp = request.args.get('ytdlp', 'false').lower() == 'true'
    
    if not mpd_url:
        return jsonify({
            "error": "MPD URL is required",
            "usage": {
                "GET": "/api?mpd=<MPD_URL>&lic=<LICENSE_URL>",
                "POST": {"mpd": "<MPD_URL>", "lic": "<LICENSE_URL>"},
            }
        }), 400
    
    try:
        # Generate keys
        result = generate_drm_keys(mpd_url, license_url, custom_headers)
        
        # Optionally get yt-dlp info
        if do_ytdlp:
            ytdlp_info = get_ytdlp_info(mpd_url, result["content_keys"])
            result["ytdlp"] = ytdlp_info
        
        return jsonify(result)
    
    except FileNotFoundError as e:
        return jsonify({"error": str(e), "type": "wvd_not_found"}), 500
    except ValueError as e:
        return jsonify({"error": str(e), "type": "pssh_error"}), 400
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP error: {e}", "type": "http_error"}), 502
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request timed out", "type": "timeout"}), 504
    except Exception as e:
        return jsonify({
            "error": str(e),
            "type": "internal_error",
            "traceback": traceback.format_exc(),
        }), 500


@app.route('/keys', methods=['GET'])
def keys_only():
    """Minimal endpoint - Returns only KID:KEY pairs.
    
    GET /keys?mpd=<MPD_URL>&lic=<LICENSE_URL>
    
    Returns:
        JSON with just the keys in KID:KEY format.
    """
    mpd_url = request.args.get('mpd')
    license_url = request.args.get('lic') or DEFAULT_LICENSE_URL
    
    if not mpd_url:
        return jsonify({"error": "MPD URL is required"}), 400
    
    try:
        result = generate_drm_keys(mpd_url, license_url)
        return jsonify({
            "keys": result["key_strings"],
            "content_keys": result["content_keys"],
            "pssh": result["pssh"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/download', methods=['GET'])
def download():
    """Get yt-dlp download URL for an MPD with DRM keys.
    
    GET /download?mpd=<MPD_URL>&lic=<LICENSE_URL>
    
    Returns:
        JSON with yt-dlp download info including direct URLs.
    """
    mpd_url = request.args.get('mpd')
    license_url = request.args.get('lic') or DEFAULT_LICENSE_URL
    
    if not mpd_url:
        return jsonify({"error": "MPD URL is required"}), 400
    
    try:
        # First get keys
        result = generate_drm_keys(mpd_url, license_url)
        
        # Then get yt-dlp info with keys
        ytdlp_info = get_ytdlp_info(mpd_url, result["content_keys"])
        
        return jsonify({
            "keys": result["key_strings"],
            "content_keys": result["content_keys"],
            "ytdlp": ytdlp_info,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/pssh', methods=['GET'])
def pssh_endpoint():
    """Extract PSSH from MPD only (no key generation).
    
    GET /pssh?mpd=<MPD_URL>
    """
    mpd_url = request.args.get('mpd')
    if not mpd_url:
        return jsonify({"error": "MPD URL is required"}), 400
    
    try:
        pssh_b64, mpd_xml = extract_pssh_from_mpd(mpd_url)
        pssh_info = parse_pssh_info(pssh_b64)
        return jsonify({
            "pssh": pssh_b64,
            "pssh_info": pssh_info,
            "mpd_length": len(mpd_xml),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── /stream Endpoint ─────────────────────────────────────────────────────

# Pre-configured MPD URLs that are known to work
KNOWN_MPDS = {
    "tears": {
        "mpd": "https://storage.googleapis.com/wvmedia/cenc/h264/tears/tears.mpd",
        "lic": "https://cwip-shaka-proxy.appspot.com/no_auth",
        "name": "Tears of Steel (HD, H264 CENC)",
    },
    "tears_uhd": {
        "mpd": "https://storage.googleapis.com/wvmedia/cenc/h264/tears/tears_uhd.mpd",
        "lic": "https://cwip-shaka-proxy.appspot.com/no_auth",
        "name": "Tears of Steel (4K UHD, H264 CENC)",
    },
    "tears_vp9": {
        "mpd": "https://storage.googleapis.com/wvmedia/cenc/vp9/tears/tears.mpd",
        "lic": "https://cwip-shaka-proxy.appspot.com/no_auth",
        "name": "Tears of Steel (HD, VP9 WebM CENC)",
    },
    "tears_cbcs": {
        "mpd": "https://storage.googleapis.com/wvmedia/cbcs/h264/tears/tears_aes_cbcs.mpd",
        "lic": "https://cwip-shaka-proxy.appspot.com/no_auth",
        "name": "Tears of Steel (HD, H264 CBCS)",
    },
    "bitmovin": {
        "mpd": "https://cdn.bitmovin.com/content/assets/art-of-motion_drm/mpds/11331.mpd",
        "lic": "https://cwip-shaka-proxy.appspot.com/no_auth",
        "name": "Bitmovin Art of Motion (HD, CENC)",
    },
}


def build_ytdlp_download_cmd(mpd_url, keys, quality="best"):
    """Build a complete yt-dlp download command with decryption keys."""
    ytdlp_bin = os.path.expanduser("~/.local/bin/yt-dlp")
    if not os.path.exists(ytdlp_bin):
        ytdlp_bin = shutil.which("yt-dlp") or "yt-dlp"
    
    cmd = [ytdlp_bin]
    
    # Add decryption keys
    for kid, key in keys.items():
        cmd.extend(["--decryption-key", f"{kid}:{key}"])
    
    # Quality selection
    if quality == "best":
        cmd.extend(["-f", "bestvideo+bestaudio"])
    elif quality == "worst":
        cmd.extend(["-f", "worstvideo+worstaudio"])
    
    cmd.extend(["-o", "%(title)s.%(ext)s", mpd_url])
    return " ".join(cmd)


def build_mp4decrypt_cmd(keys):
    """Build mp4decrypt key arguments."""
    args = []
    for kid, key in keys.items():
        args.extend(["--key", f"{kid}:{key}"])
    return " ".join(args)


@app.route('/stream', methods=['GET', 'POST'])
def stream():
    """Stream endpoint - Get playable/downloadable URL from MPD.
    
    This is the ONE endpoint you need. Just pass your MPD URL and get back:
    - Direct video URLs for each quality
    - Ready-to-use yt-dlp download command (with keys)
    - mp4decrypt keys for manual decryption
    - Video title, duration, formats info
    
    GET  /stream?fetchstreamurl=<MPD_URL>&lic=<LICENSE_URL>&quality=<best|worst>
    POST /stream  body: {"fetchstreamurl": "<MPD_URL>", "lic": "<LICENSE_URL>"}
    
    You can also use pre-configured names:
    GET  /stream?fetchstreamurl=tears    (uses pre-configured Tears of Steel)
    GET  /stream?fetchstreamurl=bitmovin (uses pre-configured Bitmovin)
    
    Parameters:
        fetchstreamurl: MPD URL or pre-configured name (required)
        lic: License server URL (optional, defaults to Shaka proxy)
        quality: best / worst (optional, default: best)
    """
    # Parse parameters
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        stream_url = data.get('fetchstreamurl') or data.get('mpd')
        license_url = data.get('lic') or data.get('license') or None
        quality = data.get('quality', 'best')
    else:
        stream_url = request.args.get('fetchstreamurl') or request.args.get('mpd')
        license_url = request.args.get('lic') or request.args.get('license') or None
        quality = request.args.get('quality', 'best')
    
    if not stream_url:
        return jsonify({
            "error": "fetchstreamurl is required",
            "usage": "GET /stream?fetchstreamurl=<MPD_URL>&lic=<LICENSE_URL>",
            "preconfigured": list(KNOWN_MPDS.keys()),
            "example": "/stream?fetchstreamurl=tears",
        }), 400
    
    # Check if it's a pre-configured name
    if stream_url in KNOWN_MPDS:
        preset = KNOWN_MPDS[stream_url]
        mpd_url = preset["mpd"]
        license_url = license_url or preset["lic"]
        preset_name = preset["name"]
    else:
        mpd_url = stream_url
        license_url = license_url or DEFAULT_LICENSE_URL
        preset_name = None
    
    try:
        # Step 1: Get Widevine keys
        drm_result = generate_drm_keys(mpd_url, license_url)
        content_keys = drm_result["content_keys"]
        key_strings = drm_result["key_strings"]
        
        # Step 2: Get video info via yt-dlp
        ytdlp_result = get_ytdlp_info(mpd_url, content_keys)
        
        # Step 3: Build download commands
        ytdlp_download_cmd = build_ytdlp_download_cmd(mpd_url, content_keys, quality)
        mp4decrypt_keys_str = build_mp4decrypt_cmd(content_keys)
        
        # Step 4: Extract best direct URLs
        best_video_url = None
        best_audio_url = None
        video_formats = []
        
        if ytdlp_result.get("success"):
            for fmt in ytdlp_result.get("formats", []):
                vc = fmt.get("vcodec", "none")
                ac = fmt.get("acodec", "none")
                is_video = vc != "none"
                is_audio = ac != "none" and not is_video
                
                entry = {
                    "format_id": fmt.get("format_id"),
                    "resolution": fmt.get("resolution", "audio"),
                    "ext": fmt.get("ext"),
                    "url": fmt.get("url"),
                    "vcodec": vc,
                    "acodec": ac,
                    "bandwidth": fmt.get("tbr"),
                }
                video_formats.append(entry)
                
                # Track best video (highest resolution)
                if is_video and not best_video_url:
                    best_video_url = fmt.get("url")
                elif is_video:
                    # Compare resolutions - pick the last (highest) one
                    best_video_url = fmt.get("url")
                
                if is_audio:
                    best_audio_url = fmt.get("url")
        
        # Step 5: Build complete response
        response = {
            "status": "ready",
            "message": "Stream ready - use download_command to download, or use direct URLs with mp4decrypt",
            "title": ytdlp_result.get("title") if ytdlp_result.get("success") else None,
            "duration": ytdlp_result.get("duration") if ytdlp_result.get("success") else None,
            "mpd_url": mpd_url,
            "license_url": license_url,
            "pssh": drm_result["pssh"],
            
            # Download command - JUST COPY PASTE THIS!
            "download_command": ytdlp_download_cmd,
            
            # mp4decrypt keys - use if you download raw segments
            "mp4decrypt_keys": mp4decrypt_keys_str,
            "mp4decrypt_command": f"mp4decrypt {mp4decrypt_keys_str} encrypted.mp4 decrypted.mp4",
            
            # Direct URLs for each quality
            "best_video_url": best_video_url,
            "best_audio_url": best_audio_url,
            "formats": video_formats,
            
            # DRM Keys
            "keys": key_strings,
            "content_keys": content_keys,
            
            # How to use
            "how_to_download": {
                "method_1_ytdlp": "Copy the download_command and run it in terminal",
                "method_2_manual": "1. Download encrypted segments from best_video_url\n"
                                  "2. Run: mp4decrypt " + mp4decrypt_keys_str + " encrypted.mp4 decrypted.mp4\n"
                                  "3. Play decrypted.mp4",
                "method_3_ffmpeg": "ffmpeg -decryption_key KID:KEY -i encrypted.mp4 -c copy decrypted.mp4",
            },
        }
        
        if preset_name:
            response["preset_name"] = preset_name
        
        return jsonify(response)
    
    except FileNotFoundError as e:
        return jsonify({"error": str(e), "type": "wvd_not_found"}), 500
    except ValueError as e:
        return jsonify({"error": str(e), "type": "pssh_error"}), 400
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"HTTP error: {e}", "type": "http_error"}), 502
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request timed out", "type": "timeout"}), 504
    except Exception as e:
        return jsonify({
            "error": str(e),
            "type": "internal_error",
            "traceback": traceback.format_exc(),
        }), 500


# ─── Main ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("  Widevine DRM Key Generator - Flask API")
    print("=" * 60)
    print(f"  WVD Directory: {WVD_DIR}")
    try:
        wvd = wvd_check()
        print(f"  WVD Device:    {wvd}")
    except FileNotFoundError as e:
        print(f"  WARNING: {e}")
    print(f"  Default License: {DEFAULT_LICENSE_URL}")
    print()
    print("  Endpoints:")
    print("    GET  /stream?fetchstreamurl=<MPD_URL>&lic=<LICENSE_URL>  <-- MAIN")
    print("    GET  /api?mpd=<MPD_URL>&lic=<LICENSE_URL>")
    print("    POST /api  {mpd, lic, headers}")
    print("    GET  /keys?mpd=<MPD_URL>&lic=<LICENSE_URL>")
    print("    GET  /download?mpd=<MPD_URL>&lic=<LICENSE_URL>")
    print("    GET  /pssh?mpd=<MPD_URL>")
    print("    GET  /health")
    print()
    print("  Pre-configured streams:")
    print("    /stream?fetchstreamurl=tears       (Tears of Steel HD)")
    print("    /stream?fetchstreamurl=tears_uhd   (Tears of Steel 4K)")
    print("    /stream?fetchstreamurl=tears_vp9   (VP9 WebM)")
    print("    /stream?fetchstreamurl=bitmovin    (Art of Motion)")
    print()
    print("  Starting server on http://0.0.0.0:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
