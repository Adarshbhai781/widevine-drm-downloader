import { NextRequest, NextResponse } from "next/server";
import fs from "fs";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await params;
  const jobs = (globalThis as any).__wvPlayJobs || {};
  const job = jobs[jobId];

  if (!job) {
    return NextResponse.json({ error: "Job not found" }, { status: 404 });
  }

  if (job.status !== "done") {
    return NextResponse.json(
      { error: "Video not ready yet", status: job.status },
      { status: 202 }
    );
  }

  const videoPath = job.video_path;
  if (!videoPath || !fs.existsSync(videoPath)) {
    return NextResponse.json({ error: "Video file not found" }, { status: 404 });
  }

  const videoBuffer = fs.readFileSync(videoPath);
  const title = (job.title || "video") + ".mp4";
  return new NextResponse(videoBuffer, {
    headers: {
      "Content-Type": "video/mp4",
      "Content-Length": String(videoBuffer.length),
      "Content-Disposition": `attachment; filename="${title}"`,
    },
  });
}
