import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import crypto from "crypto";

const WV_PLAY_SCRIPT = path.join(process.cwd(), "scripts", "wv_play.py");
const WV_API_SCRIPT = path.join(process.cwd(), "scripts", "wv_api.py");
const OUTPUT_DIR = path.join(process.cwd(), "scripts", "flask_api", "output");

// Global job store
if (!(globalThis as any).__wvPlayJobs) {
  (globalThis as any).__wvPlayJobs = {};
}
const PLAY_JOBS = (globalThis as any).__wvPlayJobs as Record<string, any>;

const KNOWN_MPDS: Record<string, { mpd: string; lic: string }> = {
  tears: { mpd: "https://storage.googleapis.com/wvmedia/cenc/h264/tears/tears.mpd", lic: "https://cwip-shaka-proxy.appspot.com/no_auth" },
  tears_uhd: { mpd: "https://storage.googleapis.com/wvmedia/cenc/h264/tears/tears_uhd.mpd", lic: "https://cwip-shaka-proxy.appspot.com/no_auth" },
  tears_vp9: { mpd: "https://storage.googleapis.com/wvmedia/cenc/vp9/tears/tears.mpd", lic: "https://cwip-shaka-proxy.appspot.com/no_auth" },
  tears_cbcs: { mpd: "https://storage.googleapis.com/wvmedia/cbcs/h264/tears/tears_aes_cbcs.mpd", lic: "https://cwip-shaka-proxy.appspot.com/no_auth" },
  bitmovin: { mpd: "https://cdn.bitmovin.com/content/assets/art-of-motion_drm/mpds/11331.mpd", lic: "https://cwip-shaka-proxy.appspot.com/no_auth" },
};
const DEFAULT_LIC = "https://cwip-shaka-proxy.appspot.com/no_auth";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const streamUrl = url.searchParams.get("fetchstreamurl") || url.searchParams.get("mpd") || "";
  const lic = url.searchParams.get("lic") || "";
  const quality = url.searchParams.get("quality") || "best";

  if (!streamUrl) {
    return NextResponse.json(
      {
        error: "fetchstreamurl is required",
        usage: "GET /api/wv/play?fetchstreamurl=<MPD_URL>&lic=<LICENSE_URL>",
        preconfigured: Object.keys(KNOWN_MPDS),
        example: "/api/wv/play?fetchstreamurl=tears",
      },
      { status: 400 }
    );
  }

  return startPlayJob(streamUrl, lic, quality);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const streamUrl = body.fetchstreamurl || body.mpd || "";
  const lic = body.lic || body.license || "";
  const quality = body.quality || "best";

  if (!streamUrl) {
    return NextResponse.json({ error: "fetchstreamurl is required" }, { status: 400 });
  }

  return startPlayJob(streamUrl, lic, quality);
}

function startPlayJob(streamUrl: string, lic: string, quality: string) {
  // Resolve preset
  let mpdUrl = streamUrl;
  let licenseUrl = lic || DEFAULT_LIC;
  if (KNOWN_MPDS[streamUrl]) {
    mpdUrl = KNOWN_MPDS[streamUrl].mpd;
    licenseUrl = lic || KNOWN_MPDS[streamUrl].lic;
  }

  const jobId = crypto.randomBytes(6).toString("hex");
  const jobDir = path.join(OUTPUT_DIR, jobId);

  PLAY_JOBS[jobId] = {
    id: jobId,
    status: "starting",
    progress: 0,
    message: "Starting...",
    mpd_url: mpdUrl,
    created: new Date().toISOString(),
  };

  // Start Python process in background
  const proc = spawn("python3", ["-u", WV_PLAY_SCRIPT, jobId, jobDir, mpdUrl, licenseUrl, quality], {
    stdio: ["pipe", "pipe", "pipe"],
    detached: false,
  });

  proc.stdout.on("data", (data: Buffer) => {
    const lines = data.toString().split("\n").filter(Boolean);
    for (const line of lines) {
      try {
        const update = JSON.parse(line);
        Object.assign(PLAY_JOBS[jobId], update);
      } catch {}
    }
  });

  proc.stderr.on("data", (data: Buffer) => {
    console.error(`[wv/play/${jobId}]`, data.toString().slice(0, 200));
  });

  proc.on("close", (code) => {
    if (code !== 0 && PLAY_JOBS[jobId]?.status !== "done" && PLAY_JOBS[jobId]?.status !== "error") {
      PLAY_JOBS[jobId].status = "error";
      PLAY_JOBS[jobId].message = `Process exited with code ${code}`;
    }
  });

  return NextResponse.json({
    jobId,
    status: "processing",
    message: "Video processing started",
    pollUrl: `/api/wv/play/status/${jobId}`,
    playUrl: `/api/wv/play/video/${jobId}`,
    downloadUrl: `/api/wv/play/download/${jobId}`,
  });
}
