import { NextRequest, NextResponse } from "next/server";

// Reuse the global session store from the drm route
declare global {
  var sessionStore: Record<string, {
    mpd_url: string;
    clearkeys: Record<string, string>;
    keys: { kid: string; key: string }[];
    license_url: string;
    created: number;
  }>;
}

export async function GET(req: NextRequest) {
  const sessionId = req.nextUrl.searchParams.get("id");

  if (!sessionId) {
    return NextResponse.json({ status: "error", message: "Missing session id" }, { status: 400 });
  }

  const store = globalThis.sessionStore || {};
  const session = store[sessionId];

  if (!session) {
    return NextResponse.json({ status: "error", message: "Session not found or expired" }, { status: 404 });
  }

  return NextResponse.json({
    status: "ok",
    mpd_url: session.mpd_url,
    clearkeys: session.clearkeys,
    keys: session.keys,
    license_url: session.license_url,
  });
}
