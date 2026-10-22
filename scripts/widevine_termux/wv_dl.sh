#!/data/data/com.termux/files/usr/bin/bash
# ╔════════════════════════════════════════════════════════════════════════╗
# ║         Widevine DRM Auto Downloader - Termux Edition                  ║
# ║                                                                        ║
# ║  Usage:  bash wv_dl.sh <mpd_url> [license_url]                        ║
# ║                                                                        ║
# ║  Example:                                                              ║
# ║    bash wv_dl.sh "https://cdn.bitmovin.com/content/assets/             ║
# ║      art-of-motion_drm/mpds/11331.mpd"                                ║
# ║                                                                        ║
# ║  Requirements: my_device.wvd (your CDM) in same folder                ║
# ╚════════════════════════════════════════════════════════════════════════╝

set -e

# ─── Colors ────────────────────────────────────────────────────────────────
R='\033[1;31m' G='\033[1;32m' Y='\033[1;33m' B='\033[1;34m' C='\033[1;36m' W='\033[1;37m' N='\033[0m'

info()  { echo -e "  ${B}[*]${N} $1"; }
ok()    { echo -e "  ${G}[+]${N} $1"; }
warn()  { echo -e "  ${Y}[!]${N} $1"; }
err()   { echo -e "  ${R}[-]${N} $1"; }
header(){ echo -e "\n  ${C}▸ $1${N}\n"; }

# ─── Script Directory ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Config ────────────────────────────────────────────────────────────────
WVD_FILE="${SCRIPT_DIR}/my_device.wvd"
OUTPUT_DIR="${SCRIPT_DIR}/downloads"
DEFAULT_LICENSE="https://cwip-shaka-proxy.appspot.com/no_auth"

# ─── Banner ────────────────────────────────────────────────────────────────
echo ""
echo -e "${W}╔══════════════════════════════════════════════════════╗${N}"
echo -e "${C}║     🔓 Widevine DRM Auto Downloader - Termux        ║${N}"
echo -e "${W}╚══════════════════════════════════════════════════════╝${N}"
echo ""

# ─── Check Args ────────────────────────────────────────────────────────────
if [ -z "$1" ]; then
    err "MPD URL required!"
    echo ""
    echo "Usage: bash wv_dl.sh <mpd_url> [license_url]"
    echo ""
    echo "Example:"
    echo '  bash wv_dl.sh "https://cdn.bitmovin.com/content/assets/art-of-motion_drm/mpds/11331.mpd"'
    echo ""
    echo "Your .wvd CDM file must be in: ${SCRIPT_DIR}/my_device.wvd"
    exit 1
fi

MPD_URL="$1"
LICENSE_URL="${2:-$DEFAULT_LICENSE}"

info "MPD URL    : $MPD_URL"
info "License URL: $LICENSE_URL"
info "WVD File   : $WVD_FILE"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# STEP 0: Install Dependencies
# ═══════════════════════════════════════════════════════════════════════════
header "STEP 0/5: Check & Install Dependencies"

# Check if we're in Termux
if [ -d "/data/data/com.termux" ]; then
    info "Termux environment detected"
    
    # Install core packages
    if ! command -v python3 &>/dev/null; then
        info "Installing Python..."
        pkg install python -y
    fi
    ok "Python: $(python3 --version 2>&1)"
    
    # Install ffmpeg (for merging)
    if ! command -v ffmpeg &>/dev/null; then
        info "Installing FFmpeg..."
        pkg install ffmpeg -y
    fi
    ok "FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    warn "Not in Termux, using system packages"
    if ! command -v python3 &>/dev/null; then
        err "python3 not found!"
        exit 1
    fi
fi

# Install Python packages
info "Installing Python packages..."
pip3 install --quiet pywidevine cryptography pycryptodome 2>/dev/null || \
pip install --quiet pywidevine cryptography pycryptodome 2>/dev/null || {
    err "Failed to install packages"
    exit 1
}
ok "Python packages installed"

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: Check CDM File
# ═══════════════════════════════════════════════════════════════════════════
header "STEP 1/5: Check CDM Device File"

if [ ! -f "$WVD_FILE" ]; then
    err "CDM file not found: $WVD_FILE"
    echo ""
    echo "  Place your Widevine CDM (.wvd) file as: my_device.wvd"
    echo "  in the same directory as this script."
    exit 1
fi

WVD_SIZE=$(stat -c%s "$WVD_FILE" 2>/dev/null || stat -f%z "$WVD_FILE" 2>/dev/null)
ok "CDM found: my_device.wvd (${WVD_SIZE} bytes)"

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2-5: Run the Python downloader (does everything)
# ═══════════════════════════════════════════════════════════════════════════
header "STEP 2-5/5: Extract Keys + Download + Decrypt + Merge"

python3 "${SCRIPT_DIR}/wv_download.py" "$MPD_URL" "$LICENSE_URL" "$WVD_FILE"
DL_EXIT=$?

if [ $DL_EXIT -ne 0 ]; then
    err "Download failed!"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════
# Verify Output
# ═══════════════════════════════════════════════════════════════════════════

# Find the final video file
FINAL_FILE=""
for f in "${OUTPUT_DIR}/final_video.mp4" "${OUTPUT_DIR}/video_decrypted.mp4" "${OUTPUT_DIR}/"*decrypted*.mp4; do
    if [ -f "$f" ]; then
        FINAL_FILE="$f"
        break
    fi
done

if [ -n "$FINAL_FILE" ] && [ -f "$FINAL_FILE" ]; then
    FILE_SIZE=$(stat -c%s "$FINAL_FILE" 2>/dev/null || stat -f%z "$FINAL_FILE" 2>/dev/null)
    FILE_SIZE_MB=$((FILE_SIZE / 1024 / 1024))
    
    echo ""
    echo -e "${W}╔══════════════════════════════════════════════════════╗${N}"
    echo -e "${G}║            ✅ DOWNLOAD COMPLETE!                     ║${N}"
    echo -e "${W}╠══════════════════════════════════════════════════════╣${N}"
    echo -e "${C}║  File: $FINAL_FILE${N}"
    echo -e "${C}║  Size: ${FILE_SIZE_MB} MB${N}"
    echo -e "${W}╚══════════════════════════════════════════════════════╝${N}"
    
    # Show video info
    if command -v ffprobe &>/dev/null; then
        echo ""
        info "Video info:"
        ffprobe -v quiet -show_format -show_streams "$FINAL_FILE" 2>/dev/null | \
            grep -E "^(codec_name|width|height|duration|bit_rate|nb_streams)" | \
            while read line; do
                echo -e "    ${C}$line${N}"
            done
    fi
else
    warn "Final video not found, check downloads/ folder"
    ls -la "${OUTPUT_DIR}/" 2>/dev/null
fi
