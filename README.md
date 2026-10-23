# Widevine DRM Downloader

A full-stack web application for downloading and decrypting Widevine DRM-protected DASH content. Paste an MPD URL, the server fetches and decrypts the content using your CDM device, and you can stream or download the decrypted video directly from the browser.

## Features

- **Web UI** — Dark-themed single-page app with URL input, real-time progress bar, and inline video player
- **API Endpoints** — RESTful API for processing MPD URLs, polling status, and streaming decrypted video
- **Widevine CDM** — Uses `pywidevine` with your own `.wvd` device file (Security Level 3)
- **CENC Decryption** — Bento4 `mp4decrypt` binary (x86_64) with Python fallback for ARM
- **DASH Support** — Parses MPD manifests, handles SegmentTemplate with `$RepresentationID$` and `$Number$` variables
- **Background Processing** — Python processor runs as a detached child process; progress polled via JSON file
- **Job Tracking** — Prisma + SQLite database stores all download jobs with status, progress, resolution, and file info
- **Video Streaming** — HTTP Range request support (206 Partial Content) for efficient browser playback
- **yt-dlp Compatible** — Direct URL + yt-dlp command shown after processing for external downloads
- **Netlify Deployable** — Pre-configured `netlify.toml` with `@netlify/plugin-nextjs`

## Architecture

```
Browser (page.tsx)
  │
  ├── POST /api/wv/process   → Start processing (spawns Python in background)
  ├── GET  /api/wv/status    → Poll progress (% + status message)
  ├── GET  /api/wv/video     → Stream decrypted video (206 Partial Content)
  └── GET  /api/wv/jobs      → List recent jobs

API Route (process/route.ts)
  │
  └── spawns: python3 wv_processor.py <jobId> <mpdUrl> <licenseUrl> <wvdPath> <outputDir> <progressFile>

Python Processor (wv_processor.py)
  │
  ├── get_keys.py      → Extract PSSH from MPD, get decryption keys via CDM
  ├── wv_download.py   → Download segments, decrypt with mp4decrypt, merge with ffmpeg
  └── mp4decrypt.py    → Python CENC AES-CTR decryptor (fallback if Bento4 unavailable)

Database (Prisma + SQLite)
  └── VideoJob model — id, mpdUrl, licenseUrl, status, progress, message, videoPath, videoSize, duration, resolution, keysJson
```

## Quick Start

### Prerequisites

- **Node.js** 20+ and **Bun** (or npm/yarn)
- **Python 3** with `pywidevine`, `requests`, `lxml`
- **ffmpeg** — for merging audio + video
- **Bento4 mp4decrypt** — for CENC decryption (auto-installed by `setup.sh` on x86_64)
- **A Widevine CDM device file** (`.wvd`) — place it at `scripts/widevine_termux/my_device.wvd`

### 1. Clone & Install

```bash
git clone https://github.com/Adarshbhai781/widevine-drm-downloader.git
cd widevine-drm-downloader

# Install Node dependencies
bun install

# Generate Prisma client
bun run db:generate

# Push database schema
bun run db:push
```

### 2. Install Python Dependencies

```bash
pip install pywidevine requests lxml
```

### 3. Setup Bento4 (one-time)

```bash
cd scripts/widevine_termux
chmod +x setup.sh
./setup.sh
```

This downloads the Bento4 `mp4decrypt` binary for x86_64. On ARM/Termux, the Python fallback (`mp4decrypt.py`) is used automatically.

### 4. Place Your CDM Device File

Put your `.wvd` file at:
```
scripts/widevine_termux/my_device.wvd
```

> **Important**: The `.wvd` file contains your Widevine CDM private keys. **Never commit this file to a public repository.** It is included in `.gitignore` by default.

### 5. Start the Development Server

```bash
bun run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Usage

### Web Interface

1. Open the app in your browser
2. Paste a DASH MPD URL (e.g., `https://cdn.bitmovin.com/content/assets/art-of-motion_drm/mpds/11331.mpd`)
3. Optionally change the License URL (default: Shaka proxy no-auth)
4. Click **Process & Play**
5. Watch the progress bar — downloading, decrypting, merging
6. When done, the video plays inline. Use the download button or copy the yt-dlp command.

### API Endpoints

#### Start Processing

```bash
# POST with JSON body
curl -X POST http://localhost:3000/api/wv/process \
  -H "Content-Type: application/json" \
  -d '{"mpdUrl": "https://cdn.example.com/manifest.mpd"}'

# GET with query parameter
curl "http://localhost:3000/api/wv/process?url=https://cdn.example.com/manifest.mpd"
```

Response:
```json
{
  "jobId": "clxxxx",
  "status": "pending",
  "statusUrl": "/api/wv/status?jobId=clxxxx",
  "videoUrl": "/api/wv/video?jobId=clxxxx"
}
```

#### Check Status

```bash
curl "http://localhost:3000/api/wv/status?jobId=clxxxx"
```

Response:
```json
{
  "jobId": "clxxxx",
  "status": "done",
  "progress": 100,
  "message": "Complete! Video ready.",
  "videoSize": 52428800,
  "duration": 120.5,
  "resolution": "1920x1080"
}
```

#### Stream Video

```bash
# Browser playback
open "http://localhost:3000/api/wv/video?jobId=clxxxx"

# Download with yt-dlp
yt-dlp "http://localhost:3000/api/wv/video?jobId=clxxxx" -o video.mp4

# Direct download
curl -o video.mp4 "http://localhost:3000/api/wv/video?jobId=clxxxx"
```

#### List Recent Jobs

```bash
curl "http://localhost:3000/api/wv/jobs"
```

### Termux / CLI Usage

You can also run the Python scripts directly without the web server:

```bash
cd scripts/widevine_termux

# One-shot download
chmod +x wv_dl.sh
./wv_dl.sh "https://cdn.example.com/manifest.mpd"
```

## Project Structure

```
├── prisma/
│   └── schema.prisma          # VideoJob model (SQLite)
├── public/
│   ├── logo.svg
│   └── robots.txt
├── scripts/
│   └── widevine_termux/
│       ├── get_keys.py        # PSSH extraction + CDM key retrieval
│       ├── mp4decrypt.py      # Python CENC AES-CTR decryptor (fallback)
│       ├── wv_download.py     # Segment download + decrypt + merge
│       ├── wv_processor.py    # Background processor (writes progress JSON)
│       ├── wv_dl.sh           # Shell wrapper with auto Bento4 download
│       ├── setup.sh           # One-time setup (Bento4 installation)
│       ├── my_device.wvd      # CDM device file (DO NOT COMMIT)
│       └── README.txt         # Termux-specific instructions
├── src/
│   ├── app/
│   │   ├── page.tsx           # Main UI (dark theme, video player, progress)
│   │   ├── layout.tsx         # Root layout
│   │   ├── globals.css        # Tailwind + global styles
│   │   └── api/
│   │       ├── wv/
│   │       │   ├── process/route.ts  # POST/GET: start processing
│   │       │   ├── status/route.ts   # GET: poll job status
│   │       │   ├── video/route.ts    # GET: stream video (206)
│   │       │   └── jobs/route.ts     # GET: list recent jobs
│   │       ├── chat/[id]/route.ts
│   │       └── conversations/
│   │           ├── route.ts
│   │           └── [id]/route.ts
│   ├── components/
│   │   ├── ui/                # shadcn/ui components
│   │   └── chat/              # Chat components
│   ├── lib/
│   │   ├── db.ts              # Prisma client singleton
│   │   ├── utils.ts
│   │   └── agent.ts
│   ├── hooks/
│   └── store/
├── netlify.toml               # Netlify deployment config
├── next.config.ts             # Next.js config (standalone output)
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.mjs
├── eslint.config.mjs
├── components.json            # shadcn/ui config
└── .gitignore
```

## Netlify Deployment

The project is pre-configured for Netlify deployment:

### Configuration (`netlify.toml`)

```toml
[build]
  command = "bun run build"
  publish = ".next"

[[plugins]]
  package = "@netlify/plugin-nextjs"

[build.environment]
  NODE_VERSION = "20"
  BUN_VERSION = "latest"
```

### Deploy Steps

1. Push this repo to GitHub
2. Go to [Netlify](https://netlify.com) → **Add new site** → **Import from Git**
3. Select your GitHub repository
4. Build settings are auto-detected from `netlify.toml`
5. Add environment variables if needed:
   - `DATABASE_URL` — Prisma connection string (default: `file:./dev.db`)
6. Click **Deploy**

### Important Notes for Netlify

- The `@netlify/plugin-nextjs` plugin handles Next.js SSR, API routes, and static optimization
- The project uses `output: "standalone"` in `next.config.ts` for optimal serverless deployment
- **Python runtime**: The Widevine processor requires Python 3 on the server. For Netlify serverless functions, you may need to use a custom build plugin or deploy the Python processor as a separate serverless function. Alternatively, use a VPS/self-hosted deployment for full Python support.
- **CDM device file**: The `.wvd` file must be available on the server. Set it as an environment variable or upload it as a deploy asset.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `file:./dev.db` | Prisma SQLite database path |
| `WV_WVD_PATH` | `scripts/widevine_termux/my_device.wvd` | Path to CDM device file |
| `WV_LICENSE_URL` | `https://cwip-shaka-proxy.appspot.com/no_auth` | Default Widevine license server |
| `WV_OUTPUT_DIR` | `./downloads` | Output directory for decrypted videos |

## How It Works

### Widevine DRM Decryption Flow

1. **Fetch MPD** — The processor downloads the DASH manifest (MPD) from the provided URL
2. **Extract PSSH** — Parses the MPD to find the Protection System Specific Header (PSSH) box containing the Widevine system ID
3. **CDM Challenge** — Using `pywidevine`, creates a license challenge with the PSSH and your CDM device credentials
4. **License Response** — Sends the challenge to the license server, receives the license response containing encrypted content keys
5. **Key Decryption** — The CDM decrypts the content keys from the license response
6. **Segment Download** — Downloads the encrypted audio and video segments based on the MPD SegmentTemplate
7. **CENC Decryption** — Uses Bento4 `mp4decrypt` (or Python fallback) to decrypt the segments with the obtained keys, performing AES-CTR decryption on each subsample
8. **Muxing** — Merges decrypted audio and video into a single MP4 file using `ffmpeg`
9. **Streaming** — The API serves the final file with HTTP Range support for browser playback

### CENC Decryption Details

The Python fallback (`mp4decrypt.py`) implements:
- **tenc box parsing** — Reads default KID from track encryption boxes for proper key matching
- **senc/saiz/saio processing** — Reads sample encryption data, auxiliary info sizes, and offsets
- **Subsample encryption** — Handles clear+encrypted subsample patterns (some bytes clear, rest encrypted)
- **IV extension** — Extends 8-byte IVs to 16 bytes per CENC spec
- **Encryption marker removal** — Strips senc, saiz, saio boxes from moof after decryption so players recognize the file as unencrypted

## Troubleshooting

### Video plays but no audio

This happens when only the first key is used instead of all keys. Ensure `wv_download.py` passes the `all_keys` dictionary to `mp4decrypt` so it can match KIDs correctly.

### Python mp4decrypt fallback not working

The Python fallback is for ARM devices where Bento4 binaries aren't available. For best results on x86_64, install Bento4 via `setup.sh`. The shell wrapper (`wv_dl.sh`) auto-detects the platform.

### "Device file not found" error

Ensure `my_device.wvd` exists at `scripts/widevine_termux/my_device.wvd`. You can also set the `WV_WVD_PATH` environment variable to a custom path.

### Disk full

Decrypted videos can be large. Clean the downloads directory:
```bash
rm -rf downloads/*
```

### Prisma client errors

Regenerate the Prisma client:
```bash
bun run db:generate
```

## License

This project is for educational and personal use only. Widevine is a Google proprietary DRM system. Use responsibly and in compliance with applicable laws and terms of service.

## Disclaimer

This tool is provided for educational purposes only. The authors are not responsible for any misuse of this software. Always ensure you have the right to access and download the content you process with this tool. Respect copyright laws and content protection mechanisms.
