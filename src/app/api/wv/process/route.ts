import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

async function startProcessing(mpdUrl: string, licenseUrl: string) {
  const license = licenseUrl || "https://cwip-shaka-proxy.appspot.com/no_auth";

  // Create job in database
  const job = await db.videoJob.create({
    data: {
      mpdUrl,
      licenseUrl: license,
      status: "pending",
      progress: 0,
      message: "Job created",
    },
  });

  // Paths
  const scriptDir = path.join(process.cwd(), "scripts", "widevine_termux");
  const wvdPath = path.join(scriptDir, "my_device.wvd");
  const outputDir = path.join(process.cwd(), "downloads", job.id);
  const progressFile = path.join(outputDir, "progress.json");
  const processorScript = path.join(scriptDir, "wv_processor.py");

  // Ensure output dir exists
  fs.mkdirSync(outputDir, { recursive: true });

  // Check WVD exists
  if (!fs.existsSync(wvdPath)) {
    await db.videoJob.update({
      where: { id: job.id },
      data: { status: "error", message: "WVD file not found" },
    });
    return { error: "WVD file not found" };
  }

  // Spawn Python processor in background
  const pythonProcess = spawn(
    "python3",
    [processorScript, job.id, mpdUrl, license, wvdPath, outputDir, progressFile],
    { detached: true, stdio: "ignore" }
  );
  pythonProcess.unref();

  // Start polling progress file and updating DB
  pollProgress(job.id, progressFile);

  return {
    jobId: job.id,
    status: "pending",
    message: "Processing started",
    // URLs for convenience
    statusUrl: `/api/wv/status?jobId=${job.id}`,
    videoUrl: `/api/wv/video?jobId=${job.id}`,
  };
}

// GET: /api/wv/process?url=<mpdUrl>&license=<licenseUrl>
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
    if ("error" in result) {
      return NextResponse.json(result, { status: 500 });
    }
    return NextResponse.json(result);
  } catch (error) {
    console.error("Process API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}

// POST: body = { mpdUrl, licenseUrl }
export async function POST(req: NextRequest) {
  try {
    // Try JSON body first, fall back to query params
    let mpdUrl = "";
    let licenseUrl = "";

    try {
      const body = await req.json();
      mpdUrl = body.mpdUrl || "";
      licenseUrl = body.licenseUrl || "";
    } catch {
      // Not JSON - check query params
      mpdUrl = req.nextUrl.searchParams.get("url") || req.nextUrl.searchParams.get("mpdUrl") || "";
      licenseUrl = req.nextUrl.searchParams.get("license") || "";
    }

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
    if ("error" in result) {
      return NextResponse.json(result, { status: 500 });
    }
    return NextResponse.json(result);
  } catch (error) {
    console.error("Process API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}

function pollProgress(jobId: string, progressFile: string) {
  let pollCount = 0;
  const maxPolls = 600;

  const interval = setInterval(async () => {
    pollCount++;
    if (pollCount > maxPolls) {
      clearInterval(interval);
      return;
    }

    try {
      if (!fs.existsSync(progressFile)) return;
      const data = JSON.parse(fs.readFileSync(progressFile, "utf-8"));

      const updateData: Record<string, unknown> = {
        status: data.status,
        progress: data.progress,
        message: data.message,
      };

      if (data.status === "done") {
        updateData.videoPath = data.videoPath;
        updateData.videoSize = data.videoSize;
        updateData.duration = data.duration;
        updateData.resolution = data.resolution;
        updateData.keysJson = data.keysJson;
        clearInterval(interval);
      } else if (data.status === "error") {
        clearInterval(interval);
      }

      await db.videoJob.update({ where: { id: jobId }, data: updateData });
    } catch {
      // Ignore
    }
  }, 1000);
}
