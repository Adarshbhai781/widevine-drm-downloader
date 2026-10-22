import { NextRequest, NextResponse } from "next/server";
import { execFileSync } from "child_process";
import path from "path";
import fs from "fs";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { mpdUrl, licenseUrl } = body;

    if (!mpdUrl) {
      return NextResponse.json({ error: "mpdUrl is required" }, { status: 400 });
    }

    const license = licenseUrl || "https://cwip-shaka-proxy.appspot.com/no_auth";
    const scriptDir = path.join(process.cwd(), "scripts", "widevine_termux");
    const wvdPath = path.join(scriptDir, "my_device.wvd");
    const getKeysScript = path.join(scriptDir, "get_keys.py");

    // Try Python pywidevine
    if (fs.existsSync(getKeysScript) && fs.existsSync(wvdPath)) {
      try {
        const result = execFileSync("python3", [getKeysScript, mpdUrl, license, wvdPath], {
          timeout: 30000,
          encoding: "utf-8",
        });
        // Find KEYS: line in output
        const keysLine = result.split("\n").find(l => l.startsWith("KEYS:"));
        if (keysLine) {
          const keyPairs = keysLine.replace("KEYS:", "").split(",");
          const keys: Record<string, string> = {};
          for (const pair of keyPairs) {
            const [kid, key] = pair.split(":");
            if (kid && key) keys[kid] = key;
          }
          if (Object.keys(keys).length > 0) {
            return NextResponse.json({ source: "python", keys, keyCount: Object.keys(keys).length });
          }
        }
      } catch (pyErr: any) {
        return NextResponse.json({ error: `Python failed: ${pyErr.message}` }, { status: 500 });
      }
    }

    // Try TypeScript CDM
    try {
      const { extractPSSH, getWidevineKeys } = await import("@/lib/widevine");
      const mpdResp = await fetch(mpdUrl);
      const mpdXml = await mpdResp.text();
      const pssh = extractPSSH(mpdXml);
      if (pssh) {
        const keys = await getWidevineKeys(pssh, license);
        if (Object.keys(keys).length > 0) {
          return NextResponse.json({ source: "typescript", keys, keyCount: Object.keys(keys).length });
        }
      }
    } catch (tsErr: any) {
      // TS CDM failed
    }

    return NextResponse.json({ error: "No CDM method available on this server" }, { status: 500 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Unknown error" }, { status: 500 });
  }
}
