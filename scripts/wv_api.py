#!/usr/bin/env python3
"""
Widevine DRM CLI Helper for Next.js API routes.
Called via: python3 wv_api.py <command> <args_json>

Commands:
  keys      - Get DRM keys: {"mpd": "url", "lic": "url"}
  stream    - Get stream info + keys + download cmd: {"fetchstreamurl": "url", "lic": "url"}
  health    - Health check: {}
  pssh      - Extract PSSH only: {"mpd": "url"}
"""

import sys
import json
import os

# Add flask_api dir to path so we can import from app.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_api"))

from app import (
    generate_drm_keys,
    extract_pssh_from_mpd,
    parse_pssh_info,
    get_ytdlp_info,
    build_ytdlp_download_cmd,
    build_mp4decrypt_cmd,
    wvd_check,
    KNOWN_MPDS,
    DEFAULT_LICENSE_URL,
)


def cmd_health(args):
    """Health check."""
    try:
        wvd_path = wvd_check()
        wvd_ok = True
    except FileNotFoundError:
        wvd_ok = False
        wvd_path = None

    import shutil
    return {
        "status": "ok" if wvd_ok else "degraded",
        "wvd_available": wvd_ok,
        "wvd_path": wvd_path,
        "yt_dlp": bool(shutil.which("yt-dlp") or os.path.exists(os.path.expanduser("~/.local/bin/yt-dlp"))),
    }


def cmd_keys(args):
    """Generate DRM keys."""
    mpd_url = args.get("mpd")
    license_url = args.get("lic") or DEFAULT_LICENSE_URL

    if not mpd_url:
        return {"error": "mpd URL is required"}

    result = generate_drm_keys(mpd_url, license_url)
    return {
        "keys": result["key_strings"],
        "content_keys": result["content_keys"],
        "pssh": result["pssh"],
        "pssh_info": result["pssh_info"],
        "device_security_level": result["device_security_level"],
    }


def cmd_pssh(args):
    """Extract, only PSSH."""
    mpd_url = args.get("mpd")
    if not mpd_url:
        return {"error": "mpd URL is required"}

    pssh_b64, mpd_xml = extract_pssh_from_mpd(mpd_url)
    pssh_info = parse_pssh_info(pssh_b64)
    return {
        "pssh": pssh_b64,
        "pssh_info": pssh_info,
    }


def cmd_stream(args):
    """Stream endpoint - Get playable/downloadable URL from MPD."""
    stream_url = args.get("fetchstreamurl") or args.get("mpd")
    license_url = args.get("lic") or None
    quality = args.get("quality", "best")

    if not stream_url:
        return {"error": "fetchstreamurl is required", "preconfigured": list(KNOWN_MPDS.keys())}

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

            if is_video:
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
        "download_command": ytdlp_download_cmd,
        "mp4decrypt_keys": mp4decrypt_keys_str,
        "mp4decrypt_command": f"mp4decrypt {mp4decrypt_keys_str} encrypted.mp4 decrypted.mp4",
        "best_video_url": best_video_url,
        "best_audio_url": best_audio_url,
        "formats": video_formats,
        "keys": key_strings,
        "content_keys": content_keys,
        "how_to_download": {
            "method_1_ytdlp": "Copy the download_command and run it in terminal",
            "method_2_manual": f"1. Download encrypted segments\n2. Run: mp4decrypt {mp4decrypt_keys_str} encrypted.mp4 decrypted.mp4\n3. Play decrypted.mp4",
        },
    }

    if preset_name:
        response["preset_name"] = preset_name

    return response


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: wv_api.py <command> [args_json]"}))
        sys.exit(1)

    command = sys.argv[1]
    args = {}

    if len(sys.argv) > 2:
        try:
            args = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            args = {"raw": sys.argv[2]}

    commands = {
        "health": cmd_health,
        "keys": cmd_keys,
        "pssh": cmd_pssh,
        "stream": cmd_stream,
    }

    if command not in commands:
        print(json.dumps({"error": f"Unknown command: {command}", "available": list(commands.keys())}))
        sys.exit(1)

    try:
        result = commands[command](args)
        print(json.dumps(result, indent=2))
    except Exception as e:
        import traceback
        print(json.dumps({
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
