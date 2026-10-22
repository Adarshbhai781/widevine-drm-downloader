import { NextResponse } from "next/server";
import { db } from "@/lib/db";

// Auto-ensure database schema on first call (for serverless environments)
let dbInitialized = false;
async function ensureDb() {
  if (dbInitialized) return;
  try {
    // Try a simple query first
    await db.videoJob.count();
    dbInitialized = true;
  } catch {
    // Database doesn't exist yet, create it
    try {
      const { execSync } = await import("child_process");
      execSync("npx prisma db push --accept-data-loss", {
        env: { ...process.env },
        timeout: 30000,
      });
      dbInitialized = true;
    } catch (pushErr) {
      console.error("Failed to initialize database:", pushErr);
      // Even if push fails, mark as initialized to avoid retrying on every request
      dbInitialized = true;
    }
  }
}

export async function GET() {
  try {
    await ensureDb();
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
