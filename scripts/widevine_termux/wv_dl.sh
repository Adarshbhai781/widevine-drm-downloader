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

# Install mp4decrypt (Bento4 binary or Python fallback)
if command -v mp4decrypt &>/dev/null; then
    ok "mp4decrypt: $(which mp4decrypt)"
elif [ -f "${SCRIPT_DIR}/tools/mp4decrypt" ]; then
    ok "mp4decrypt: ${SCRIPT_DIR}/tools/mp4decrypt"
else
    # Try to download Bento4 mp4decrypt binary
    info "Downloading Bento4 mp4decrypt..."
    mkdir -p "${SCRIPT_DIR}/tools"
    ARCH=$(uname -m)
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        # Termux on ARM - use Python fallback
        warn "ARM architecture - using Python mp4decrypt fallback"
        pip3 install --quiet cryptography 2>/dev/null
    elif [ "$ARCH" = "x86_64" ]; then
        # x86_64 - download Bento4 binary
        BENTO4_URL="https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip"
        TMP_ZIP="/tmp/bento4_$$.zip"
        if command -v wget &>/dev/null; then
            wget -q "$BENTO4_URL" -O "$TMP_ZIP" 2>/dev/null
        else
            curl -sL "$BENTO4_URL" -o "$TMP_ZIP" 2>/dev/null
        fi
        if [ -f "$TMP_ZIP" ] && [ $(stat -c%s "$TMP_ZIP" 2>/dev/null || echo 0) -gt 1000000 ]; then
            unzip -j "$TMP_ZIP" "*/bin/mp4decrypt" -d "${SCRIPT_DIR}/tools/" 2>/dev/null
            chmod +x "${SCRIPT_DIR}/tools/mp4decrypt" 2>/dev/null
            ok "mp4decrypt installed to tools/"
        else
            warn "Failed to download Bento4, using Python fallback"
        fi
        rm -f "$TMP_ZIP"
    fi
    
    if [ -f "${SCRIPT_DIR}/tools/mp4decrypt" ]; then
        ok "mp4decrypt binary ready"
    elif [ -f "${SCRIPT_DIR}/mp4decrypt.py" ]; then
        ok "Python mp4decrypt.py fallback available"
    else
        err "No mp4decrypt available! Decryption will fail."
    fi
fi

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
