import { NextRequest, NextResponse } from "next/server";

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

  return NextResponse.json({
    id: job.id,
    status: job.status,
    progress: job.progress || 0,
    message: job.message || "",
    ...(job.keys ? { keys: job.keys } : {}),
    ...(job.video_size_mb ? { video_size_mb: job.video_size_mb } : {}),
    ...(job.resolution ? { resolution: job.resolution } : {}),
    ...(job.title ? { title: job.title } : {}),
    ...(job.duration ? { duration: job.duration } : {}),
  });
}
