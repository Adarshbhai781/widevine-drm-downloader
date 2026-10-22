========================================================
  Widevine DRM Auto Downloader - Termux Edition
========================================================

QUICK START:
------------

1. First time setup (one time only):
   bash setup.sh

2. Download video (just give MPD link!):
   bash wv_dl.sh "<mpd_url>"

3. Video will be saved in: downloads/final_video.mp4


EXAMPLE:
--------
bash wv_dl.sh "https://cdn.bitmovin.com/content/assets/art-of-motion_drm/mpds/11331.mpd"


ADVANCED:
---------
# Custom license URL
bash wv_dl.sh "<mpd_url>" "<license_url>"

# Just get keys (no download)
python3 get_keys.py "<mpd_url>"


FILES:
------
  wv_dl.sh       - Main script (auto everything)
  wv_download.py - Python downloader (called by wv_dl.sh)
  get_keys.py    - Key extractor (standalone)
  mp4decrypt.py  - Python CENC decryptor (replaces Bento4)
  setup.sh       - Termux setup (install deps)
  my_device.wvd  - Your CDM device file


HOW IT WORKS:
-------------
1. Fetches MPD manifest from your URL
2. Extracts PSSH (protection info) from MPD
3. Uses your CDM to get decryption keys from license server
4. Downloads video+audio segments
5. Decrypts using CENC AES-CTR
6. Merges video+audio with ffmpeg
7. Saves to downloads/final_video.mp4


REQUIREMENTS:
-------------
- Termux (Android) or Linux
- Python 3 with: pywidevine, cryptography, pycryptodome
- ffmpeg (for merging)
- Your .wvd CDM file (replace my_device.wvd)
