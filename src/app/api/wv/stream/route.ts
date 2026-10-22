import { NextRequest, NextResponse } from "next/server";
import { execFileSync } from "child_process";
import path from "path";

const WV_API_SCRIPT = path.join(process.cwd(), "scripts", "wv_api.py");

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const fetchstreamurl = url.searchParams.get("fetchstreamurl") || url.searchParams.get("mpd");
    const lic = url.searchParams.get("lic") || "";
    const quality = url.searchParams.get("quality") || "best";

    if (!fetchstreamurl) {
      return NextResponse.json(
        {
          error: "fetchstreamurl is required",
          usage: "GET /api/wv/stream?fetchstreamurl=<MPD_URL>&lic=<LICENSE_URL>&quality=<best|worst>",
          preconfigured: ["tears", "tears_uhd", "tears_vp9", "tears_cbcs", "bitmovin"],
          example: "/api/wv/stream?fetchstreamurl=tears",
        },
        { status: 400 }
      );
    }

    const args = JSON.stringify({ fetchstreamurl, lic: lic || undefined, quality });

    const result = execFileSync("python3", [WV_API_SCRIPT, "stream", args], {
      timeout: 120000,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024, // 10MB buffer for large responses
    });

    const data = JSON.parse(result);
    return NextResponse.json(data);
  } catch (error: any) {
    const errMsg = error.message || "Unknown error";
    // Try to parse Python error output
    try {
      const stderr = error.stderr || "";
      if (stderr) {
        const pyError = JSON.parse(stderr);
        return NextResponse.json(pyError, { status: 500 });
      }
    } catch {}
    return NextResponse.json({ error: errMsg }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const fetchstreamurl = body.fetchstreamurl || body.mpd;
    const lic = body.lic || body.license || "";
    const quality = body.quality || "best";

    if (!fetchstreamurl) {
      return NextResponse.json(
        { error: "fetchstreamurl is required", preconfigured: ["tears", "tears_uhd", "tears_vp9", "tears_cbcs", "bitmovin"] },
        { status: 400 }
      );
    }

    const args = JSON.stringify({ fetchstreamurl, lic: lic || undefined, quality });

    const result = execFileSync("python3", [WV_API_SCRIPT, "stream", args], {
      timeout: 120000,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024,
    });

    const data = JSON.parse(result);
    return NextResponse.json(data);
  } catch (error: any) {
    return NextResponse.json({ error: error.message || "Unknown error" }, { status: 500 });
  }
}
