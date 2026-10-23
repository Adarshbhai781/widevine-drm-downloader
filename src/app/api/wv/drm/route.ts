import { NextRequest, NextResponse } from "next/server";
import { execFileSync } from "child_process";
import path from "path";

const WV_SCRIPT = path.join(process.cwd(), "scripts", "wv_process.py");
const PYTHON3 = "/home/z/.venv/bin/python3"; // Use venv python3 with all deps

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const processurl = url.searchParams.get("processurl") || "";
    const license_url = url.searchParams.get("license_url") || "";

    if (!processurl) {
      return NextResponse.json(
        {
          status: "error",
          message: "Missing processurl parameter",
          usage: "/api/wv/drm?processurl=<MPD_URL or preset>",
          presets: ["bitmovin", "tears", "tears_uhd", "tears_vp9", "tears_cbcs"],
          example: "/api/wv/drm?processurl=bitmovin",
        },
        { status: 400 }
      );
    }

    const args = JSON.stringify({
      processurl,
      license_url: license_url || undefined,
    });

    const result = execFileSync(PYTHON3, [WV_SCRIPT, args], {
      timeout: 60000,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024,
    });

    const data = JSON.parse(result);

    // Add play_url pointing to our Shaka Player page
    if (data.status === "success" && data.session_id) {
      const baseUrl = `${url.protocol}//${url.host}`;
      data.play_url = `${baseUrl}/wv/player?session=${data.session_id}`;
      // Store session data in a global for the player page to retrieve
      sessionStore[data.session_id] = {
        mpd_url: data.mpd_url,
        clearkeys: data.clearkeys,
        keys: data.keys,
        license_url: data.license_url,
        created: Date.now(),
      };
    }

    return NextResponse.json(data);
  } catch (error: any) {
    // Try to parse Python stderr
    const stderr = error.stderr || "";
    try {
      const pyError = JSON.parse(stderr);
      return NextResponse.json(pyError, { status: 500 });
    } catch {}
    return NextResponse.json(
      { status: "error", message: error.message || "Unknown error" },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const processurl = body.processurl || "";
    const license_url = body.license_url || "";

    if (!processurl) {
      return NextResponse.json(
        { status: "error", message: "Missing processurl", presets: ["bitmovin", "tears"] },
        { status: 400 }
      );
    }

    const args = JSON.stringify({
      processurl,
      license_url: license_url || undefined,
      pssh: body.pssh || undefined,
    });

    const result = execFileSync(PYTHON3, [WV_SCRIPT, args], {
      timeout: 60000,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024,
    });

    const data = JSON.parse(result);
    const url = new URL(req.url);

    if (data.status === "success" && data.session_id) {
      const baseUrl = `${url.protocol}//${url.host}`;
      data.play_url = `${baseUrl}/wv/player?session=${data.session_id}`;
      sessionStore[data.session_id] = {
        mpd_url: data.mpd_url,
        clearkeys: data.clearkeys,
        keys: data.keys,
        license_url: data.license_url,
        created: Date.now(),
      };
    }

    return NextResponse.json(data);
  } catch (error: any) {
    return NextResponse.json(
      { status: "error", message: error.message || "Unknown error" },
      { status: 500 }
    );
  }
}

// ─── In-memory session store ────────────────────────────────────────
// The player page reads session data to configure Shaka Player
declare global {
  var sessionStore: Record<string, {
    mpd_url: string;
    clearkeys: Record<string, string>;
    keys: { kid: string; key: string }[];
    license_url: string;
    created: number;
  }>;
}

if (!globalThis.sessionStore) {
  globalThis.sessionStore = {};
}
const sessionStore = globalThis.sessionStore;

// ─── Session data endpoint ──────────────────────────────────────────
// /api/wv/drm?session=<id> returns session data for the player page
export async function HEAD(req: NextRequest) {
  const sessionId = new URL(req.url).searchParams.get("session");
  if (!sessionId || !sessionStore[sessionId]) {
    return NextResponse.json({ status: "error", message: "Session not found" }, { status: 404 });
  }
  return NextResponse.json({ status: "ok", ...sessionStore[sessionId] });
}
