import { NextRequest, NextResponse } from "next/server";
import { db, ensureDatabase } from "@/lib/db";
import { execFileSync } from "child_process";
import path from "path";
import fs from "fs";
import {
  extractPSSH,
  getWidevineKeys,
  parseMPD,
  httpGet,
  downloadInitAndMedia,
  downloadSegmentBase,
  mp4Decrypt,
} from "@/lib/widevine";

// ─── Temp directory for Netlify serverless ─────────────────────────────────
function getTmpDir(): string {
  const isServerless = !!(process.env.NETLIFY || process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME);
  const base = isServerless ? "/tmp" : process.cwd();
  const dir = path.join(base, "downloads");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// ─── Background processor ─────────────────────────────────────────────────
async function processJob(jobId: string, mpdUrl: string, licenseUrl: string, manualKeys?: Record<string, string>) {
  const tmpDir = getTmpDir();
  const jobDir = path.join(tmpDir, jobId);
  fs.mkdirSync(jobDir, { recursive: true });

  try {
    // Step 1: Fetch MPD
    await updateJob(jobId, 5, "Fetching MPD...", "processing");
    const mpdResp = await fetch(mpdUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
      },
    });
    if (!mpdResp.ok) throw new Error(`Failed to fetch MPD: HTTP ${mpdResp.status}`);
    const mpdXml = await mpdResp.text();

    // Step 2: Extract PSSH
    await updateJob(jobId, 8, "Extracting PSSH...", "processing");
    const psshB64 = extractPSSH(mpdXml);
    if (!psshB64) throw new Error("No PSSH found in MPD - content may not be DRM-protected");

    // Step 3: Get Widevine Keys
    await updateJob(jobId, 10, "Getting decryption keys...", "processing");
    let contentKeys: Record<string, string>;

    // Try the keys API (which tries Python first, then TS)
    try {
      const keysResp = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL || ''}/api/wv/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mpdUrl, licenseUrl }),
      });
      if (keysResp.ok) {
        const keysData = await keysResp.json();
        if (keysData.keys && Object.keys(keysData.keys).length > 0) {
          contentKeys = keysData.keys;
        }
      }
    } catch {}

    // Fallback: Try Python directly
    if (!contentKeys || Object.keys(contentKeys).length === 0) {
      try {
        const scriptDir = path.join(process.cwd(), "scripts", "widevine_termux");
        const getKeysScript = path.join(scriptDir, "get_keys.py");
        const wvdPath = path.join(scriptDir, "my_device.wvd");

        if (fs.existsSync(getKeysScript) && fs.existsSync(wvdPath)) {
          const result = execFileSync("python3", [getKeysScript, mpdUrl, licenseUrl, wvdPath], {
            timeout: 30000, encoding: "utf-8",
          });
          const keysLine = result.split("\n").find(l => l.startsWith("KEYS:"));
          if (keysLine) {
            contentKeys = {};
            for (const pair of keysLine.replace("KEYS:", "").split(",")) {
              const [kid, key] = pair.split(":");
              if (kid && key) contentKeys[kid] = key;
            }
          }
        }
      } catch {}
    }

    // Fallback: Try TypeScript CDM
    if (!contentKeys || Object.keys(contentKeys).length === 0) {
      try {
        contentKeys = await getWidevineKeys(psshB64, licenseUrl);
      } catch {}
    }

    // Fallback: Use manually provided keys
    if ((!contentKeys || Object.keys(contentKeys).length === 0) && manualKeys && Object.keys(manualKeys).length > 0) {
      contentKeys = manualKeys;
    }

    if (!contentKeys || Object.keys(contentKeys).length === 0) {
      throw new Error("Key extraction failed - no CDM available. Provide keys manually (KID:KEY format) or deploy on a server with Python3 + pywidevine.");
    }

    await updateJob(jobId, 15, `Got ${Object.keys(contentKeys).length} keys. Parsing MPD...`, "processing");

    // Step 4: Parse MPD
    const mpdInfo = parseMPD(mpdUrl, mpdXml);
    const videoReps = mpdInfo.adaptations.filter(a => a.type === 'video');
    const audioReps = mpdInfo.adaptations.filter(a => a.type === 'audio');
    const bestVideo = videoReps.length > 0 ? videoReps.reduce((a, b) => (a.height > b.height ? a : b)) : null;
    const bestAudio = audioReps.length > 0 ? audioReps.reduce((a, b) => (a.bandwidth > b.bandwidth ? a : b)) : null;

    if (!bestVideo) throw new Error("No video representation found in MPD");

    // Step 5: Download Segments
    const onProgress = async (pct: number, msg: string) => {
      await updateJob(jobId, pct, msg, "processing");
    };

    const downloaded: { video?: { encPath: string; keyHex: string; kidHex: string }; audio?: { encPath: string; keyHex: string; kidHex: string } } = {};

    // Download video (progress 20-60)
    if (bestVideo) {
      await updateJob(jobId, 20, "Downloading video segments...", "processing");

      if (bestVideo.initTemplate && bestVideo.mediaTemplate) {
        // SegmentTemplate - multi-segment
        const { initData, segments } = await downloadInitAndMedia(
          mpdInfo.baseUrl, bestVideo.initTemplate, bestVideo.mediaTemplate,
          bestVideo.repId, bestVideo.bandwidth, bestVideo.numSegments,
          bestVideo.startNumber, onProgress, 20, 40
        );
        const encPath = path.join(jobDir, "video_encrypted.mp4");
        const allParts = [initData, ...segments];
        fs.writeFileSync(encPath, Buffer.concat(allParts));
        downloaded.video = findKeyForRep(bestVideo.defaultKid, contentKeys, encPath);
      } else {
        // SegmentBase - single file
        const data = await downloadSegmentBase(mpdInfo.baseUrl, bestVideo.baseURL, onProgress, 20, 40);
        const encPath = path.join(jobDir, "video_encrypted.mp4");
        fs.writeFileSync(encPath, data);
        downloaded.video = findKeyForRep(bestVideo.defaultKid, contentKeys, encPath);
      }
    }

    // Download audio (progress 60-80)
    if (bestAudio) {
      await updateJob(jobId, 60, "Downloading audio segments...", "processing");

      if (bestAudio.initTemplate && bestAudio.mediaTemplate) {
        const { initData, segments } = await downloadInitAndMedia(
          mpdInfo.baseUrl, bestAudio.initTemplate, bestAudio.mediaTemplate,
          bestAudio.repId, bestAudio.bandwidth, bestAudio.numSegments,
          bestAudio.startNumber, onProgress, 60, 20
        );
        const encPath = path.join(jobDir, "audio_encrypted.mp4");
        fs.writeFileSync(encPath, Buffer.concat([initData, ...segments]));
        downloaded.audio = findKeyForRep(bestAudio.defaultKid, contentKeys, encPath);
      } else {
        const data = await downloadSegmentBase(mpdInfo.baseUrl, bestAudio.baseURL, onProgress, 60, 20);
        const encPath = path.join(jobDir, "audio_encrypted.mp4");
        fs.writeFileSync(encPath, data);
        downloaded.audio = findKeyForRep(bestAudio.defaultKid, contentKeys, encPath);
      }
    }

    // Step 6: Decrypt
    await updateJob(jobId, 80, "Decrypting video...", "decrypting");

    const decFiles: Record<string, string> = {};
    for (const [repType, info] of Object.entries(downloaded)) {
      if (!info) continue;
      const encPath = info.encPath;
      const decPath = encPath.replace('_encrypted.mp4', '_decrypted.mp4');

      // Try TypeScript mp4decrypt first
      try {
        const size = mp4Decrypt(encPath, decPath, contentKeys);
        if (size === 0) throw new Error("TS mp4decrypt produced empty file");
        decFiles[repType] = decPath;
      } catch (tsErr: any) {
        const tsErrMsg = tsErr?.message || String(tsErr);
        console.error(`TS mp4decrypt failed for ${repType}:`, tsErrMsg);

        // Fallback: Python mp4decrypt.py
        const scriptDir = path.join(process.cwd(), "scripts", "widevine_termux");
        const pyMp4dec = path.join(scriptDir, "mp4decrypt.py");

        if (fs.existsSync(pyMp4dec)) {
          const keyArgs: string[] = [];
          for (const [kid, key] of Object.entries(contentKeys)) {
            keyArgs.push("--key", `${kid}:${key}`);
          }
          try {
            execFileSync("python3", [pyMp4dec, ...keyArgs, encPath, decPath], { timeout: 120000 });
            decFiles[repType] = decPath;
          } catch (pyErr: any) {
            throw new Error(`Decryption failed for ${repType}: TS(${tsErrMsg}), Python(${pyErr?.message || 'err'})`);
          }
        } else {
          throw new Error(`Decryption failed for ${repType}: TS error: ${tsErrMsg}. Python fallback not available.`);
        }
      }
    }

    // Step 7: Merge
    await updateJob(jobId, 90, "Merging video + audio...", "merging");
    const finalPath = path.join(jobDir, "final_video.mp4");

    if (decFiles.video && decFiles.audio) {
      // Try ffmpeg merge
      try {
        execFileSync("ffmpeg", [
          "-i", decFiles.video, "-i", decFiles.audio,
          "-c:v", "copy", "-c:a", "copy", "-y", finalPath
        ], { timeout: 60000 });
      } catch {
        // Fallback: just use video
        fs.copyFileSync(decFiles.video, finalPath);
      }
    } else if (decFiles.video) {
      fs.copyFileSync(decFiles.video, finalPath);
    }

    // Step 8: Done!
    const videoSize = fs.existsSync(finalPath) ? fs.statSync(finalPath).size : 0;
    const duration = mpdInfo.periodDuration;
    const resolution = bestVideo ? `${bestVideo.width}x${bestVideo.height}` : null;

    await db.videoJob.update({
      where: { id: jobId },
      data: {
        status: "done",
        progress: 100,
        message: "Complete! Video ready to play.",
        videoPath: finalPath,
        videoSize,
        duration,
        resolution,
        keysJson: JSON.stringify(contentKeys),
      },
    });
  } catch (error) {
    console.error("Processing error:", error);
    try {
      await db.videoJob.update({
        where: { id: jobId },
        data: {
          status: "error",
          message: error instanceof Error ? error.message : "Unknown processing error",
        },
      });
    } catch { /* DB update failed */ }
  }
}

function findKeyForRep(defaultKid: string | null, contentKeys: Record<string, string>, encPath: string) {
  let kid = defaultKid?.replace(/-/g, '') || '';
  let keyHex: string | undefined;
  let kidHex: string | undefined;

  if (kid && contentKeys[kid]) {
    keyHex = contentKeys[kid];
    kidHex = kid;
  } else {
    // Try first available key
    for (const [k, v] of Object.entries(contentKeys)) {
      keyHex = v;
      kidHex = k;
      break;
    }
  }

  return { encPath, keyHex: keyHex || '', kidHex: kidHex || '' };
}

async function updateJob(jobId: string, progress: number, message: string, status: string) {
  try {
    await db.videoJob.update({
      where: { id: jobId },
      data: { status, progress, message },
    });
  } catch { /* ignore */ }
}

// ─── API Handler ───────────────────────────────────────────────────────────
async function startProcessing(mpdUrl: string, licenseUrl: string, manualKeys?: Record<string, string>) {
  await ensureDatabase();
  const license = licenseUrl || "https://cwip-shaka-proxy.appspot.com/no_auth";

  const job = await db.videoJob.create({
    data: {
      mpdUrl,
      licenseUrl: license,
      status: "pending",
      progress: 0,
      message: "Job created, processing starting...",
    },
  });

  // Start background processing (non-blocking)
  setImmediate(() => {
    processJob(job.id, mpdUrl, license, manualKeys).catch(err => {
      console.error("Background processing fatal error:", err);
    });
  });

  return {
    jobId: job.id,
    status: "pending",
    message: "Processing started",
    statusUrl: `/api/wv/status?jobId=${job.id}`,
    videoUrl: `/api/wv/video?jobId=${job.id}`,
  };
}

export async function GET(req: NextRequest) {
  try {
    const mpdUrl = req.nextUrl.searchParams.get("url");
    const licenseUrl = req.nextUrl.searchParams.get("license") || "";

    if (!mpdUrl) {
      return NextResponse.json(
        {
          error: "MPD URL is required",
          usage: {
            get: "/api/wv/process?url=<mpdUrl>&license=<licenseUrl>",
            post: 'POST /api/wv/process  body: {"mpdUrl":"...", "licenseUrl":"..."}',
          },
        },
        { status: 400 }
      );
    }

    const result = await startProcessing(mpdUrl, licenseUrl);
    return NextResponse.json(result);
  } catch (error) {
    console.error("Process API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    let mpdUrl = "";
    let licenseUrl = "";

    let manualKeys: Record<string, string> | undefined;
    try {
      const body = await req.json();
      mpdUrl = body.mpdUrl || "";
      licenseUrl = body.licenseUrl || "";
      // Accept keys in format: {"kid1": "key1", "kid2": "key2"} or "kid1:key1,kid2:key2"
      if (body.keys) {
        if (typeof body.keys === 'string') {
          manualKeys = {};
          for (const pair of body.keys.split(',')) {
            const [kid, key] = pair.split(':');
            if (kid && key) manualKeys[kid.trim()] = key.trim();
          }
        } else if (typeof body.keys === 'object') {
          manualKeys = body.keys;
        }
      }
    } catch {
      mpdUrl = req.nextUrl.searchParams.get("url") || req.nextUrl.searchParams.get("mpdUrl") || "";
      licenseUrl = req.nextUrl.searchParams.get("license") || "";
      const keysParam = req.nextUrl.searchParams.get("keys");
      if (keysParam) {
        manualKeys = {};
        for (const pair of keysParam.split(',')) {
          const [kid, key] = pair.split(':');
          if (kid && key) manualKeys[kid.trim()] = key.trim();
        }
      }
    }

    if (!mpdUrl) {
      return NextResponse.json(
        {
          error: "MPD URL is required",
          usage: {
            get: "/api/wv/process?url=<mpdUrl>&license=<licenseUrl>&keys=<kid:key,...>",
            post: 'POST /api/wv/process  body: {"mpdUrl":"...", "licenseUrl":"...", "keys": "kid:key,..."}',
          },
        },
        { status: 400 }
      );
    }

    const result = await startProcessing(mpdUrl, licenseUrl, manualKeys);
    return NextResponse.json(result);
  } catch (error) {
    console.error("Process API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}
