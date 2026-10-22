import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { mpdUrl, licenseUrl } = body;

    if (!mpdUrl) {
      return NextResponse.json({ error: "MPD URL is required" }, { status: 400 });
    }

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
      return NextResponse.json({ error: "WVD file not found" }, { status: 500 });
    }

    // Spawn Python processor in background
    const pythonProcess = spawn("python3", [
      processorScript,
      job.id,
      mpdUrl,
      license,
      wvdPath,
      outputDir,
      progressFile,
    ], {
      detached: true,
      stdio: "ignore",
    });

    pythonProcess.unref();

    // Start polling progress file and updating DB
    pollProgress(job.id, progressFile, outputDir);

    return NextResponse.json({
      jobId: job.id,
      status: "pending",
      message: "Processing started",
    });
  } catch (error) {
    console.error("Process API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}

function pollProgress(jobId: string, progressFile: string, outputDir: string) {
  let pollCount = 0;
  const maxPolls = 600; // 10 minutes at 1s interval

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

      await db.videoJob.update({
        where: { id: jobId },
        data: updateData,
      });
    } catch {
      // Ignore read errors during polling
    }
  }, 1000);
}
