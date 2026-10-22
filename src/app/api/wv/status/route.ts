import { NextRequest, NextResponse } from "next/server";
import { db, ensureDatabase } from "@/lib/db";

export async function GET(req: NextRequest) {
  try {
    await ensureDatabase();
    const jobId = req.nextUrl.searchParams.get("jobId");

    if (!jobId) {
      return NextResponse.json({ error: "jobId is required" }, { status: 400 });
    }

    const job = await db.videoJob.findUnique({
      where: { id: jobId },
    });

    if (!job) {
      return NextResponse.json({ error: "Job not found" }, { status: 404 });
    }

    return NextResponse.json({
      jobId: job.id,
      status: job.status,
      progress: job.progress,
      message: job.message,
      videoSize: job.videoSize,
      duration: job.duration,
      resolution: job.resolution,
      mpdUrl: job.mpdUrl,
    });
  } catch (error) {
    console.error("Status API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}
