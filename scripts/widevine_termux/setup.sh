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
pip3 install pywidevine yt-dlp

# Verify
echo -e "\n  ${G}[+]${N} Setup complete!\n"
echo -e "  Python:  $(python3 --version 2>&1)"
echo -e "  FFmpeg:  $(ffmpeg -version 2>&1 | head -1)"
echo -e "  yt-dlp:  $(yt-dlp --version 2>&1)"

echo -e "\n${W}  Next step:${N}"
echo -e "  ${C}1.${N} Put your CDM file as: ${Y}my_device.wvd${N}"
echo -e "  ${C}2.${N} Run: ${Y}bash wv_dl.sh \"<mpd_url>\"${N}"
echo -e "  ${C}3.${N} Video will be in: ${Y}downloads/${N}\n"
