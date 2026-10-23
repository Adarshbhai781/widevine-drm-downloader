import { NextRequest, NextResponse } from "next/server";
import { execFileSync } from "child_process";
import path from "path";

const WV_SCRIPT = path.join(process.cwd(), "scripts", "wv_process.py");
const PYTHON3 = "/home/z/.venv/bin/python3";

// ─── In-memory session store for player ─────────────────────────────
declare global {
  var wvSessions: Record<string, {
    mpd_url: string;
    clearkeys: Record<string, string>;
    keys: { kid: string; key: string }[];
    created: number;
  }>;
}
if (!globalThis.wvSessions) globalThis.wvSessions = {};
const sessions = globalThis.wvSessions;

// ─── Shaka Player HTML (inline, self-contained) ─────────────────────
function playerHtml(mpdUrl: string, clearkeys: Record<string, string>): string {
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>WV Player</title>
<script src="https://cdn.jsdelivr.net/npm/shaka-player@4.11/dist/shaka-player.compiled.min.js"></script>
<style>*{margin:0;padding:0}body{background:#000}video{width:100vw;height:100vh}</style>
</head><body>
<video id="v" controls autoplay></video>
<script>
(async()=>{
  try{
    shaka.polyfill.installAll();
    const p=new shaka.Player();
    await p.attach(document.getElementById('v'));
    p.configure({drm:{clearKeys:${JSON.stringify(clearkeys)}},streaming:{bufferingGoal:30,bufferBehind:10}});
    await p.load("${mpdUrl}");
  }catch(e){document.body.innerHTML='<pre style="color:red;padding:20px">'+e+'</pre>'}
})();
</script></body></html>`;
}

export async function GET(req: NextRequest) {
  const url = new URL(req.url);

  // ── /api/wv?play=<sessionId> → serve Shaka Player HTML ────────
  const playId = url.searchParams.get("play");
  if (playId && sessions[playId]) {
    const s = sessions[playId];
    return new Response(playerHtml(s.mpd_url, s.clearkeys), {
      headers: { "Content-Type": "text/html" },
    });
  }

  // ── /api/wv?processurl=<MPD> → MAIN ENDPOINT ──────────────────
  const processurl = (url.searchParams.get("processurl") || "").trim();
  const license_url = (url.searchParams.get("license_url") || "").trim();

  if (!processurl) {
    return NextResponse.json({
      error: "processurl is required",
      usage: "/api/wv?processurl=<MPD_URL or preset>",
      presets: ["bitmovin", "tears", "tears_vp9"],
    }, { status: 400 });
  }

  try {
    const args = JSON.stringify({ processurl, license_url: license_url || undefined });
    const result = execFileSync(PYTHON3, [WV_SCRIPT, args], {
      timeout: 60000, encoding: "utf-8", maxBuffer: 10 * 1024 * 1024,
    });
    const data = JSON.parse(result);

    if (data.status === "success" && data.session_id) {
      // Build play_url using request origin (works behind proxies)
      const fwdHost = req.headers.get("x-forwarded-host");
      const fwdProto = req.headers.get("x-forwarded-proto");
      const proto = (fwdProto || url.protocol || "http").replace(/:$/, "");
      const host = fwdHost || url.host;
      const origin = `${proto}://${host}`;
      data.play_url = `${origin}/api/wv?play=${data.session_id}`;
      sessions[data.session_id] = {
        mpd_url: data.mpd_url,
        clearkeys: data.clearkeys,
        keys: data.keys,
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

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const processurl = (body.processurl || "").trim();
    const license_url = (body.license_url || "").trim();

    if (!processurl) {
      return NextResponse.json({ error: "processurl is required" }, { status: 400 });
    }

    const args = JSON.stringify({
      processurl,
      license_url: license_url || undefined,
      pssh: body.pssh || undefined,
    });

    const result = execFileSync(PYTHON3, [WV_SCRIPT, args], {
      timeout: 60000, encoding: "utf-8", maxBuffer: 10 * 1024 * 1024,
    });
    const data = JSON.parse(result);
    const url = new URL(req.url);

    if (data.status === "success" && data.session_id) {
      const fwdHost = req.headers.get("x-forwarded-host");
      const fwdProto = req.headers.get("x-forwarded-proto");
      const proto = (fwdProto || url.protocol || "http").replace(/:$/, "");
      const host = fwdHost || url.host;
      const origin = `${proto}://${host}`;
      data.play_url = `${origin}/api/wv?play=${data.session_id}`;
      sessions[data.session_id] = {
        mpd_url: data.mpd_url,
        clearkeys: data.clearkeys,
        keys: data.keys,
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
