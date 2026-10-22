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

from flask import Flask, request, jsonify, send_file, Response
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
import threading
import time
import math
import urllib.request
import urllib.error
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


# ─── /play Endpoint (Download + Decrypt + Serve Video) ────────────────────

# Storage for play jobs
PLAY_JOBS = {}
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def http_download(url, headers=None):
    """Download a URL with proper headers."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    hdrs.setdefault("Referer", url.rsplit("/", 1)[0] + "/")
    resp = requests.get(url, headers=hdrs, timeout=60)
    resp.raise_for_status()
    return resp.content


def download_and_decrypt_video(job_id, mpd_url, license_url, quality="best"):
    """Background task: Download encrypted DASH segments + decrypt + merge.
    
    Steps:
    1. Get Widevine keys
    2. Parse MPD for segment URLs
    3. Download init + media segments (video + audio)
    4. Decrypt with mp4decrypt
    5. Merge with ffmpeg
    6. Save final video
    """
    job = PLAY_JOBS[job_id]
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    try:
        # Step 1: Get Widevine keys
        job["status"] = "getting_keys"
        job["progress"] = 5
        job["message"] = "Getting Widevine decryption keys..."
        
        drm_result = generate_drm_keys(mpd_url, license_url)
        content_keys = drm_result["content_keys"]
        job["pssh"] = drm_result["pssh"]
        job["keys"] = [f"{kid}:{key}" for kid, key in content_keys.items()]
        
        # Step 2: Fetch and parse MPD
        job["status"] = "parsing_mpd"
        job["progress"] = 10
        job["message"] = "Parsing MPD manifest..."
        
        mpd_resp = requests.get(mpd_url, headers={"User-Agent": USER_AGENT}, timeout=30)
        mpd_resp.raise_for_status()
        mpd_xml = mpd_resp.text
        
        # Parse MPD - extract base URL and segment templates
        # Base URL = directory containing the MPD file
        base_url = mpd_url.rsplit('/', 1)[0] + '/'
        
        # Parse period duration
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
            
            # SegmentTemplate
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
            
            # Representations
            for rep_match in re.finditer(r'<Representation[^>]*id="([^"]*)"[^>]*>', as_block, re.DOTALL):
                rep_id = rep_match.group(1)
                rep_tag = rep_match.group(0)
                bw = re.search(r'bandwidth="(\d+)"', rep_tag)
                w = re.search(r' width="(\d+)"', rep_tag)
                h = re.search(r' height="(\d+)"', rep_tag)
                
                # BaseURL per representation
                rep_block = rep_match.group(0)
                # Get the full representation block (from <Representation to </Representation>)
                rep_full_match = re.search(r'<Representation[^>]*id="' + re.escape(rep_id) + r'\"[^>]*>(.*?)</Representation>', as_block, re.DOTALL)
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
            raise Exception("No video representation found in MPD")
        
        # Step 3: Download segments
        downloaded = {}
        
        for rep_type, rep in [("video", best_video), ("audio", best_audio)]:
            if rep is None:
                continue
            
            # Skip if no segment templates (uses SegmentBase/SegmentList instead)
            if not rep.get('init_template') or not rep.get('media_template'):
                # Try direct BaseURL download for SegmentBase content
                rep_bu = rep.get('base_url')
                if rep_bu:
                    if not rep_bu.startswith('http'):
                        direct_url = base_url + rep_bu
                    else:
                        direct_url = rep_bu
                    job["status"] = f"downloading_{rep_type}"
                    job["message"] = f"Downloading {rep_type} ({direct_url[:60]}...)"
                    job["progress"] = 25 if rep_type == "video" else 60
                    
                    enc_data = http_download(direct_url)
                    enc_path = os.path.join(job_dir, f"{rep_type}_encrypted.mp4")
                    with open(enc_path, 'wb') as f:
                        f.write(enc_data)
                    
                    default_kid = rep.get('default_kid') or ''
                    if default_kid:
                        default_kid = default_kid.replace('-', '')
                    
                    key_hex = kid_hex = None
                    if default_kid and default_kid in content_keys:
                        key_hex, kid_hex = content_keys[default_kid], default_kid
                    else:
                        for kid, kv in content_keys.items():
                            key_hex, kid_hex = kv, kid
                            break
                    
                    downloaded[rep_type] = {"enc_path": enc_path, "key_hex": key_hex, "kid_hex": kid_hex}
                continue
            
            job["status"] = f"downloading_{rep_type}"
            job["message"] = f"Downloading {rep_type} segments ({rep.get('height', 'audio')})..."
            
            def resolve(tmpl, rid, num, bw):
                return tmpl.replace('$RepresentationID$', rid) \
                           .replace('$Bandwidth$', str(bw)) \
                           .replace('$Number$', str(num)) \
                           .replace('$Time$', str(num))
            
            # Download init
            init_url = base_url + resolve(rep['init_template'], rep['rep_id'], 0, rep['bandwidth'])
            init_data = http_download(init_url)
            
            # Download media segments
            segments = []
            seg_num = rep['start_number']
            max_seg = rep['num_segments'] + 5 if rep['num_segments'] > 0 else 300
            progress_base = 20 if rep_type == "video" else 60
            progress_range = 35 if rep_type == "video" else 15
            
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
                job["progress"] = int(progress_base + progress_range * pct / 100)
                job["message"] = f"Downloading {rep_type}: segment {done}/{total}"
                seg_num += 1
                
                if rep['num_segments'] > 0 and done >= rep['num_segments']:
                    break
            
            # Save encrypted file
            enc_path = os.path.join(job_dir, f"{rep_type}_encrypted.mp4")
            with open(enc_path, 'wb') as f:
                f.write(init_data)
                for seg in segments:
                    f.write(seg)
            
            # Find matching key
            default_kid = rep.get('default_kid') or ''
            if default_kid:
                default_kid = default_kid.replace('-', '')
            
            key_hex = kid_hex = None
            if default_kid and default_kid in content_keys:
                key_hex, kid_hex = content_keys[default_kid], default_kid
            else:
                for kid, kv in content_keys.items():
                    key_hex, kid_hex = kv, kid
                    break
            
            downloaded[rep_type] = {"enc_path": enc_path, "key_hex": key_hex, "kid_hex": kid_hex}
        
        # Step 4: Decrypt
        job["status"] = "decrypting"
        job["progress"] = 80
        job["message"] = "Decrypting video..."
        
        # Find mp4decrypt binary
        mp4decrypt_bin = shutil.which("mp4decrypt") or "/usr/local/bin/mp4decrypt"
        
        # Build key args for ALL keys
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
                # Try Python fallback
                py_mp4dec = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "widevine_termux", "mp4decrypt.py")
                if os.path.exists(py_mp4dec):
                    cmd = [sys.executable, py_mp4dec] + key_args + [enc_path, dec_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    raise Exception(f"mp4decrypt failed for {rep_type}: {result.stderr[:200]}")
            
            dec_files[rep_type] = dec_path
            job["message"] = f"Decrypted {rep_type}"
        
        # Step 5: Merge
        job["status"] = "merging"
        job["progress"] = 90
        job["message"] = "Merging video + audio..."
        
        final_path = os.path.join(job_dir, "final_video.mp4")
        
        if 'video' in dec_files and 'audio' in dec_files:
            result = subprocess.run([
                "ffmpeg", "-i", dec_files['video'], "-i", dec_files['audio'],
                "-c:v", "copy", "-c:a", "copy", "-y", final_path
            ], capture_output=True, timeout=120)
            if result.returncode != 0:
                # Fallback: try with audio re-encode
                result = subprocess.run([
                    "ffmpeg", "-i", dec_files['video'], "-i", dec_files['audio'],
                    "-c:v", "copy", "-c:a", "aac", "-y", final_path
                ], capture_output=True, timeout=120)
            if result.returncode != 0:
                shutil.copy2(dec_files['video'], final_path)
        elif 'video' in dec_files:
            shutil.copy2(dec_files['video'], final_path)
        
        # Done!
        video_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
        duration = period_dur
        resolution = f"{best_video['width']}x{best_video['height']}" if best_video else None
        
        job["status"] = "done"
        job["progress"] = 100
        job["message"] = "Video ready!"
        job["video_path"] = final_path
        job["video_size"] = video_size
        job["video_size_mb"] = round(video_size / (1024*1024), 2)
        job["duration"] = duration
        job["resolution"] = resolution
        job["title"] = os.path.basename(mpd_url).replace('.mpd', '')
        
    except Exception as e:
        job["status"] = "error"
        job["progress"] = 0
        job["message"] = str(e)
        job["traceback"] = traceback.format_exc()


@app.route('/play', methods=['GET'])
def play():
    """Play endpoint - Download + Decrypt DRM video and serve for browser playback.
    
    GET /play?fetchstreamurl=<MPD_URL>&lic=<LICENSE_URL>&quality=<best|worst>
    
    This starts the download+decrypt process in the background and returns
    an HTML page with a video player. The player polls /play/status/<job_id>
    and when ready, plays the video from /play/video/<job_id>.
    
    You can also use pre-configured names:
    GET /play?fetchstreamurl=tears
    """
    stream_url = request.args.get('fetchstreamurl') or request.args.get('mpd')
    license_url = request.args.get('lic') or request.args.get('license') or None
    quality = request.args.get('quality', 'best')
    
    if not stream_url:
        return jsonify({
            "error": "fetchstreamurl is required",
            "usage": "GET /play?fetchstreamurl=<MPD_URL>&lic=<LICENSE_URL>",
            "preconfigured": list(KNOWN_MPDS.keys()),
        }), 400
    
    # Check if it's a pre-configured name
    if stream_url in KNOWN_MPDS:
        preset = KNOWN_MPDS[stream_url]
        mpd_url = preset["mpd"]
        license_url = license_url or preset["lic"]
    else:
        mpd_url = stream_url
        license_url = license_url or DEFAULT_LICENSE_URL
    
    # Create job
    job_id = _uuid.uuid4().hex[:12]
    PLAY_JOBS[job_id] = {
        "id": job_id,
        "status": "starting",
        "progress": 0,
        "message": "Starting...",
        "mpd_url": mpd_url,
        "license_url": license_url,
        "created_at": datetime.utcnow().isoformat(),
    }
    
    # Start background processing
    thread = threading.Thread(
        target=download_and_decrypt_video,
        args=(job_id, mpd_url, license_url, quality),
        daemon=True
    )
    thread.start()
    
    # Return HTML page with video player
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Widevine DRM Player</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0a0a0a; color: #fff; font-family: -apple-system, sans-serif; min-height: 100vh; display: flex; flex-direction: column; align-items: center; }}
  .container {{ max-width: 960px; width: 100%; padding: 20px; }}
  h1 {{ font-size: 24px; margin-bottom: 8px; color: #e50914; }}
  .meta {{ color: #888; font-size: 14px; margin-bottom: 20px; }}
  .player-box {{ background: #000; border-radius: 12px; overflow: hidden; margin-bottom: 20px; aspect-ratio: 16/9; display: flex; align-items: center; justify-content: center; position: relative; }}
  video {{ width: 100%; height: 100%; object-fit: contain; }}
  .progress-box {{ background: #1a1a1a; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
  .progress-bar {{ background: #333; border-radius: 4px; height: 8px; overflow: hidden; margin: 10px 0; }}
  .progress-fill {{ background: #e50914; height: 100%; width: 0$; transition: width 0.3s; border-radius: 4px; }}
  .status {{ font-size: 14px; color: #aaa; }}
  .keys-box {{ background: #1a1a1a; border-radius: 8px; padding: 16px; margin-top: 20px; font-size: 12px; }}
  .keys-box h3 {{ color: #e50914; margin-bottom: 8px; }}
  .key {{ color: #0f0; font-family: monospace; margin: 4px 0; word-break: break-all; }}
  .download-btn {{ background: #e50914; color: #fff; border: none; padding: 12px 24px; border-radius: 8px; font-size: 16px; cursor: pointer; margin-top: 12px; display: none; text-decoration: none; }}
  .download-btn:hover {{ background: #b2070f; }}
  .spinner {{ width: 60px; height: 60px; border: 4px solid #333; border-top-color: #e50914; border-radius: 50%; animation: spin 1s linear infinite; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .loading-text {{ color: #aaa; margin-top: 12px; font-size: 16px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Widevine DRM Player</h1>
  <div class="meta" id="meta">MPD: {mpd_url[:80]}...</div>
  
  <div class="player-box" id="playerBox">
    <div id="loadingArea">
      <div class="spinner"></div>
      <div class="loading-text" id="loadingText">Processing video...</div>
    </div>
    <video id="videoPlayer" controls style="display:none"></video>
  </div>
  
  <div class="progress-box" id="progressBox">
    <div class="status" id="statusText">Starting...</div>
    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
    <div class="status" id="progressText">0%</div>
  </div>
  
  <a class="download-btn" id="downloadBtn" download>Download Video</a>
  
  <div class="keys-box" id="keysBox" style="display:none">
    <h3>Decryption Keys</h3>
    <div id="keysList"></div>
  </div>
</div>

<script>
const jobId = "{job_id}";
let pollInterval;

function pollStatus() {{
  fetch('/play/status/' + jobId)
    .then(r => r.json())
    .then(data => {{
      document.getElementById('statusText').textContent = data.message || data.status;
      document.getElementById('progressFill').style.width = data.progress + '%';
      document.getElementById('progressText').textContent = data.progress + '%';
      document.getElementById('loadingText').textContent = data.message || data.status;
      
      if (data.keys && data.keys.length > 0) {{
        document.getElementById('keysBox').style.display = 'block';
        document.getElementById('keysList').innerHTML = data.keys.map(k => '<div class="key">' + k + '</div>').join('');
      }}
      
      if (data.status === 'done') {{
        clearInterval(pollInterval);
        document.getElementById('loadingArea').style.display = 'none';
        const video = document.getElementById('videoPlayer');
        video.style.display = 'block';
        video.src = '/play/video/' + jobId;
        video.play().catch(() => {{}});
        
        if (data.resolution) document.getElementById('meta').textContent = data.title + ' | ' + data.resolution + ' | ' + data.video_size_mb + ' MB';
        
        const btn = document.getElementById('downloadBtn');
        btn.style.display = 'inline-block';
        btn.href = '/play/video/' + jobId;
        btn.textContent = 'Download (' + data.video_size_mb + ' MB)';
      }}
      
      if (data.status === 'error') {{
        clearInterval(pollInterval);
        document.getElementById('loadingText').textContent = 'Error: ' + data.message;
      }}
    }})
    .catch(err => console.error(err));
}}

pollInterval = setInterval(pollStatus, 1500);
pollStatus();
</script>
</body>
</html>"""
    return Response(html, mimetype='text/html')


@app.route('/play/status/<job_id>', methods=['GET'])
def play_status(job_id):
    """Get the status of a play job."""
    if job_id not in PLAY_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = PLAY_JOBS[job_id]
    result = {
        "id": job["id"],
        "status": job["status"],
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
    }
    
    if job.get("keys"):
        result["keys"] = job["keys"]
    if job.get("video_size_mb"):
        result["video_size_mb"] = job["video_size_mb"]
    if job.get("resolution"):
        result["resolution"] = job["resolution"]
    if job.get("title"):
        result["title"] = job["title"]
    if job.get("duration"):
        result["duration"] = job["duration"]
    
    return jsonify(result)


@app.route('/play/video/<job_id>', methods=['GET'])
def play_video(job_id):
    """Serve the decrypted video file for playback."""
    if job_id not in PLAY_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = PLAY_JOBS[job_id]
    
    if job["status"] != "done":
        return jsonify({"error": "Video not ready yet", "status": job["status"], "progress": job.get("progress", 0)}), 202
    
    video_path = job.get("video_path")
    if not video_path or not os.path.exists(video_path):
        return jsonify({"error": "Video file not found"}), 404
    
    return send_file(video_path, mimetype='video/mp4', as_attachment=False)


@app.route('/play/download/<job_id>', methods=['GET'])
def play_download(job_id):
    """Download the decrypted video file."""
    if job_id not in PLAY_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = PLAY_JOBS[job_id]
    
    if job["status"] != "done":
        return jsonify({"error": "Video not ready yet", "status": job["status"]}), 202
    
    video_path = job.get("video_path")
    if not video_path or not os.path.exists(video_path):
        return jsonify({"error": "Video file not found"}), 404
    
    title = job.get("title", "video") + ".mp4"
    return send_file(video_path, mimetype='video/mp4', as_attachment=True, download_name=title)


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
    print("    GET  /play?fetchstreamurl=<MPD_URL>  <-- PLAY VIDEO IN BROWSER!")
    print("    GET  /stream?fetchstreamurl=<MPD_URL>  <-- Get keys + URLs")
    print("    GET  /api?mpd=<MPD_URL>&lic=<LICENSE_URL>")
    print("    GET  /keys?mpd=<MPD_URL>&lic=<LICENSE_URL>")
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
