import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const jobs = await db.videoJob.findMany({
      orderBy: { createdAt: "desc" },
      take: 20,
      select: {
        id: true,
        mpdUrl: true,
        status: true,
        progress: true,
        message: true,
        videoSize: true,
        duration: true,
        resolution: true,
        createdAt: true,
      },
    });

    return NextResponse.json({ jobs });
  } catch (error) {
    console.error("Jobs API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}
