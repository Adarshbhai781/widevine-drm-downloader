#!/data/data/com.termux/files/usr/bin/bash
# ╔════════════════════════════════════════════════════════════════════════╗
# ║        Termux Setup - One Time Install for Widevine Downloader        ║
# ╚════════════════════════════════════════════════════════════════════════╝

R='\033[1;31m' G='\033[1;32m' Y='\033[1;33m' B='\033[1;34m' C='\033[1;36m' W='\033[1;37m' N='\033[0m'

echo -e "\n${W}╔══════════════════════════════════════════════════════╗${N}"
echo -e "${C}║     🔧 Termux Setup - Widevine Downloader            ║${N}"
echo -e "${W}╚══════════════════════════════════════════════════════╝${N}\n"

# Update Termux packages
echo -e "  ${B}[*]${N} Updating Termux packages..."
pkg update -y && pkg upgrade -y

# Install core packages
echo -e "\n  ${B}[*]${N} Installing core packages..."
pkg install -y python python-pip ffmpeg

# Install Python packages
echo -e "\n  ${B}[*]${N} Installing Python packages..."
pip3 install --upgrade pip
pip3 install pywidevine cryptography pycryptodome yt-dlp

# Install Bento4 mp4decrypt
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
    echo -e "\n  ${B}[*]${N} Installing Bento4 mp4decrypt..."
    BENTO4_URL="https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip"
    TMP_ZIP="/tmp/bento4_setup.zip"
    if command -v wget &>/dev/null; then
        wget -q "$BENTO4_URL" -O "$TMP_ZIP"
    else
        curl -sL "$BENTO4_URL" -o "$TMP_ZIP"
    fi
    TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tools"
    mkdir -p "$TOOLS_DIR"
    unzip -j "$TMP_ZIP" "*/bin/mp4decrypt" -d "$TOOLS_DIR/" 2>/dev/null
    chmod +x "$TOOLS_DIR/mp4decrypt" 2>/dev/null
    # Also install system-wide if possible
    if [ -w /usr/local/bin ]; then
        cp "$TOOLS_DIR/mp4decrypt" /usr/local/bin/ 2>/dev/null
    fi
    rm -f "$TMP_ZIP"
    echo -e "  ${G}[+]${N} mp4decrypt installed"
else
    echo -e "\n  ${Y}[!]${N} ARM device - Python mp4decrypt.py will be used as fallback"
fi

# Verify
echo -e "\n  ${G}[+]${N} Setup complete!\n"
echo -e "  Python:  $(python3 --version 2>&1)"
echo -e "  FFmpeg:  $(ffmpeg -version 2>&1 | head -1)"
echo -e "  yt-dlp:  $(yt-dlp --version 2>&1)"

echo -e "\n${W}  Next step:${N}"
echo -e "  ${C}1.${N} Put your CDM file as: ${Y}my_device.wvd${N}"
echo -e "  ${C}2.${N} Run: ${Y}bash wv_dl.sh \"<mpd_url>\"${N}"
echo -e "  ${C}3.${N} Video will be in: ${Y}downloads/${N}\n"
