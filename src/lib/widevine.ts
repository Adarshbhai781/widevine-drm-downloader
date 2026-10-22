/**
 * Pure TypeScript Widevine CDM + DASH Processor
 * No Python dependency - works on Netlify serverless
 */
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import protobuf from 'protobufjs';

// ─── WVD Device Data (embedded) ────────────────────────────────────────────
const CLIENT_ID_B64 = "CAESgQoKwQIIAhIgkHnqJnbkglh2wzXNtwlJnbt8YuMBCAUUFAZsyQmYIgQY1o63rAYijgIwggEKAoIBAQDBbwWBLa1XgQN+4u1adLFGd6UjLNlbOI3+lf4H6hEWzd6rPIzCgvK7J958h1VFcKTVrR34Y1rZNMkTkrpEBuw50O5WdvYjcUGjrqVN6ShyK6WY61XEMQ2TeDJZJJ2cUAIyCcUQydPTI0ax8lMYAbtWel2i0V9PQ6egMTZZRQNoY5jfTl39f9uKLSxX3lxAZ9U0wjQHMldIxjIxkKdXQjM7vui+SyuDJnoN2QcgnzfLuQfL1CyPW+G5Hb+1eOuKCTR+GAI0rWvtv48dJInVUW9TQTLcX5SpgFzVip6S2ekazRB/VRMISfygpS//hLn1z0E3yOeVo6Hq0SLShOWBs0kRAgMBAAEourABSAESgAIgJaXi+qWdd1sweG1ikJlgWBL3kXo70a/xFEm4SI7832sHaLZEsvwUZSusu7/2oSYQks32ym7pJ4QfOrEeXzTU96k14Gcm64SttA/d+kBaCnh5kah6yqOYGu16OyyaOTRBpvm+KJ2Ub06/29q82PGo/4xCg1d6tLWtM1OaH65O0SrNpu0x9Vk2X2Vk98wOhuHzkJka0piwRKsyWPGccPqKCABp9+8hJaDcUKf+W344TZ8pSgxuZBrCWPRHjVDjy/ZdDldbAl8Q5oocpnxEBNzO2UfEyuzJwxrNqdLPlb0DifKcqT/kpUGpPJp4vPFlzPycxDbRaHPbCRdSeB72RNSvGrcFCrECCAESEGJSHlLT3g6XNAe8gmjAADwY0OHthAYijgIwggEKAoIBAQC5GwNJZows2imnGqXv1uZOorrtX0cZtsFmXBwTz0v8krkO6gw/g5elg8ErxJqBudRn11l54OofnatmxWvLh0gnIAnNvIbwRNg1E7pPhKg9mRFzhEB1kE8YQDq21W3018v8vfJRKA1b15QVqw1slkz2h+OV7ZUSOLbLjctP258kSMDekjGLzD4IfBloNyquKjGW89Xqs6/GXndaACQh+if2Xv/Hq0g1gTEWJtDv74Qtf66pPdsXJ8ZVKWcE6fluiphs8MlffBUCiA3DYK0/92phfoKbDcSBSRz4VmK8YpMak+KGcHDj0/QXzEPdT88DL1tTNrrFfurqcHSzHJWeVuUlAgMBAAEourABSAESgAOeaZbX4hHAEo6dpnXOJKFTcvl78CuHz3B7JG8/W31Fe9hZWUD/FaOIRYw3altgBUlnvKWTN9jtvMo1LBLfmx3MB3AUxKframIIQdiLm7q5zLI2K8Poj8PqqTO8PA0YMLN+ztK3mvPK4ryGTFXnMZ1Z0xwkgHUtY/yLXcWJ6WWVy6mCRMv5aYBy5p5FIEiN41JDEbOD6nRNxiXN9A/9Fl80U42SzIx6Wss1jqHcXdxDivZL0ppL51sDZJ63D6A207GAurzx7lLBy8Lv9EM+KavuYZYpFsPywbV7rYcfgwhcbs72g/NyiTw7bncgtQw5Zz3f3ENHoa75fu7wB+DYEYz0+UyzJKrUR/mKIOXixrRTzoKNLSunQU2JXlab64umvHrD4DWiyWmOAQ3zojI+hm4Fh3Fn5DnT0EjBD728CT4BzBu6nS9bWpXVwCOsV5YeaTy0mUsoXECY67GKyjnowXAbwI0QG6Cug124pkklbjIEet733T/qospChLI7j5ScbOEaFgoMY29tcGFueV9uYW1lEgZYaWFvbWkaEwoKbW9kZWxfbmFtZRIFTWkgQTIaHgoRYXJjaGl0ZWN0dXJlX25hbWUSCWFybTY0LXY4YRodCgtkZXZpY2VfbmFtZRIOamFzbWluZV9zcHJvdXQaJgoMcHJvZHVjdF9uYW1lEhZsaW5lYWdlX2phc21pbmVfc3Byb3V0GmUKCmJ1aWxkX2luZm8SV3hpYW9taS9qYXNtaW5lL2phc21pbmVfc3Byb3V0OjguMS4wL09QTTEuMTcxMDE5LjAxMS9WOS42LjE3LjAuT0RJTUlGRTp1c2VyL3JlbGVhc2Uta2V5cxoeChR3aWRldmluZV9jZG1fdmVyc2lvbhIGMTUuMC4wGiQKH29lbV9jcnlwdG9fc2VjdXJpdHlfcGF0Y2hfbGV2ZWwSATAaUAocb2VtX2NyeXB0b19idWlsZF9pbmZvcm1hdGlvbhIwT0VNQ3J5cHRvIExldmVsMyBDb2RlIDIyNTg2IE1heCAxMiAyMDIxIDIzOjQ4OjA3MhQIARABIAAoDzAAQABIAFABWABgAQ==";
const PRIVATE_KEY_DER_B64 = "MIIEpAIBAAKCAQEAwW8FgS2tV4EDfuLtWnSxRnelIyzZWziN/pX+B+oRFs3eqzyMwoLyuyfefIdVRXCk1a0d+GNa2TTJE5K6RAbsOdDuVnb2I3FBo66lTekociulmOtVxDENk3gyWSSdnFACMgnFEMnT0yNGsfJTGAG7VnpdotFfT0OnoDE2WUUDaGOY305d/X/bii0sV95cQGfVNMI0BzJXSMYyMZCnV0IzO77ovksrgyZ6DdkHIJ83y7kHy9Qsj1vhuR2/tXjrigk0fhgCNK1r7b+PHSSJ1VFvU0Ey3F+UqYBc1YqektnpGs0Qf1UTCEn8oKUv/4S59c9BN8jnlaOh6tEi0oTlgbNJEQIDAQABAoIBADAqdAVxmUtDvdoXqaCvlAEHA+DZZxo23+y37rSLzUuPYdXj0u0QbF68E8OQc2RCI1ltrRvPqaySX0t3athLnQDcjKyNHMdAiWa3s0POPhsH0UlduFKNIGNLN8ZIvtJQfet10VNX3l4h15Wx0I0WyU5EVBKZ7hCvuQrDllPuQmX4kB/c1UI+/HWWUHqfTE0VcLq0NMNMHwEjuVZrlaRxVJ/Ish+T9cFL5TZ8Xs5z+QmIg/f322nGjPNIoWsQLaZ/Vf98KgojVi2q+rUaWiUQUz0jjR350Yytmi2CGgyYOns2kf1SIhpgytYD8Xg8WWJSeqPCom+q46e2TOqUF73Bfc0CgYEA4b3gT74XX+elY6S71thAAxjMOeZOUmScp74HeEBiGl3EPknZgj25qZRiScFYY34VmCxClN5yeoedWerbkREXH3w/GH7jfUVdmkxpTdxnQpIR3jfbcO83A49KfyCBvKpkTfZ5qXQ1ST1NCLSHt5/bR00QcY2roVBkVmoz+7nd5WsCgYEA21yGPlPsVrrBSteQaVIadUkcFvgrH+aNDZwqwvDtqmFOxD2JkDbzgz1/gRrGI6QxIYZQpDMVwVW22koogPFQYs2TLMizor9EkXeAXzMHUSRI0YE4jNsSCaz3U0g0Q6o7R4hebPFz80T+NgE2zo6uIyOhKZUeDfWVj0q61BJkLnMCgYEAneRgE4aC9OqiTLq5Q4GH7GKY3dqPZ6PFyrHoqZxmwchZ7bNbtnQT+1+1C593gkd7NS+n9lZMvhVC4tSZdLL+eGBABZMi7MjqunS9pt8FPpPKeaKaEzjOQugjlB2ZgOuxMrK1z+dfKfX9fpw+3Rmrlwh4+uO7ax4+wA6Sg3wyjzcCgYEA2K4sbKS5b3JKPINyQpa3S+NLu+SntHsoGamJE8ao/QPhqjafC7U8FQdKS10HG220mkjynz9W3gKs/DMEj1nO7cni9vnJd5k3Qfmo9GCTebM9urTKB1jeGHCiXcGU3sHojGBH5ZUb09DyyqWoXaDSoiMvrsN9TIypj0FiCtmf28ECgYBuMBKFsH4OWnUGnIMBdFIOcWvQmTQwvgVt3qyqvTzbVkiOPI0RumOayMj0hlpmq5OVvEFQz8lfGOQfm/mcPHnvLJO4bpEGCdI/od0ooULMe1h1SNR9sK3AO0fGHYqh0TKUKx00HKncwzyyuNm07oL/DOJ/D2wFLkkFvtWDTznpmQ==";

const CLIENT_ID_BYTES = Buffer.from(CLIENT_ID_B64, 'base64');
const PRIVATE_KEY_DER = Buffer.from(PRIVATE_KEY_DER_B64, 'base64');

// ─── Widevine Protobuf Schema ──────────────────────────────────────────────
// This is a minimal subset of the full Widevine CDM protocol
const WV_SCHEMA = `
syntax = "proto2";

message SignedMessage {
  enum Type {
    LICENSE_REQUEST = 1;
    LICENSE = 2;
    ERROR_RESPONSE = 3;
    SERVICE_CERTIFICATE_REQUEST = 4;
    SERVICE_CERTIFICATE = 5;
  }
  required Type type = 1;
  optional bytes msg = 2;
  optional bytes signature = 3;
  optional bytes session_key = 4;
}

message ClientIdentification {
  required bytes client_id = 1;
  optional bytes client_token = 2;
}

message LicenseRequest {
  message Content {
    enum Type {
      STREAMING = 1;
      OFFLINE = 2;
    }
    required bytes id = 1;
    optional uint32 source = 2;
    optional bytes key_control = 3;
    optional Type type = 4;
  }
  required uint32 protocol_version = 1;
  optional Content content = 2;
  optional ClientIdentification client_id = 3;
}

message License {
  message Key {
    enum KeyType {
      SIGNING = 1;
      CONTENT = 2;
      KEY_CONTROL = 3;
      OPERATOR_SESSION = 4;
    }
    required bytes id = 1;
    required KeyType type = 2;
    required bytes key = 3;
    optional string level = 4;
    optional uint32 required_protection_level = 5;
  }
  required uint32 protocol_version = 1;
  repeated Key key = 2;
}
`;

let root: protobuf.Root | null = null;
function getProto() {
  if (!root) {
    root = protobuf.parse(WV_SCHEMA, { keepCase: true }).root;
  }
  return root;
}

// ─── PSSH Extraction ──────────────────────────────────────────────────────
export function extractPSSH(mpdXml: string): string | null {
  const psshList: string[] = [];

  // Method 1: <cenc:pssh> tags
  const regex1 = /<cenc:pssh[^>]*>([\s\S]*?)<\/cenc:pssh>/g;
  let match: RegExpExecArray | null;
  while ((match = regex1.exec(mpdXml)) !== null) {
    const val = match[1].trim();
    if (val && val.length > 20) psshList.push(val);
  }

  // Method 2: base64 strings that decode to 'pssh' boxes
  if (psshList.length === 0) {
    const regex2 = /[A-Za-z0-9+/]{40,}={0,2}/g;
    while ((match = regex2.exec(mpdXml)) !== null) {
      try {
        const raw = Buffer.from(match[0], 'base64');
        if (raw.length > 8 && raw.slice(4, 8).toString('ascii') === 'pssh') {
          psshList.push(match[0]);
        }
      } catch { /* skip */ }
    }
  }

  return psshList.length > 0 ? psshList.reduce((a, b) => a.length >= b.length ? a : b) : null;
}

// ─── Widevine Key Extraction ──────────────────────────────────────────────
export async function getWidevineKeys(psshB64: string, licenseUrl: string): Promise<Record<string, string>> {
  const psshBytes = Buffer.from(psshB64, 'base64');
  const r = getProto();

  const SignedMessage = r.lookupType('SignedMessage');
  const LicenseRequest = r.lookupType('LicenseRequest');

  // Build LicenseRequest manually using protobuf Writer
  // This avoids schema mismatch with ClientIdentification
  const writer = protobuf.Writer.create();

  // Field 1: protocol_version = 21 (VERSION_2_1)
  writer.uint32(/* id 1, wireType 0 = */ 8).uint32(21);

  // Field 2: content (LicenseRequest.Content)
  const contentWriter = protobuf.Writer.create();
  // Content.id = PSSH bytes (field 1, wireType 2 = 10)
  contentWriter.uint32(10).bytes(psshBytes);
  // Content.type = STREAMING = 1 (field 4, wireType 0 = 32)
  contentWriter.uint32(32).uint32(1);
  // Write Content as field 2 (wireType 2 = 18)
  writer.uint32(18).bytes(contentWriter.finish());

  // Field 3: client_id - use raw CLIENT_ID_BYTES directly
  // The client_id.bin is already a serialized ClientIdentification message
  writer.uint32(/* id 3, wireType 2 = */ 26).bytes(CLIENT_ID_BYTES);

  const licenseReqEncoded = writer.finish();

  // Sign the LicenseRequest with RSA-SHA256
  const signature = crypto.sign('sha256', Buffer.from(licenseReqEncoded), {
    key: PRIVATE_KEY_DER,
    type: 'pkcs1',
    format: 'der',
  });

  // Create SignedMessage wrapping the LicenseRequest
  const signedMsg = SignedMessage.create({
    type: 1,  // LICENSE_REQUEST
    msg: Buffer.from(licenseReqEncoded),
    signature: Buffer.from(signature),
  });
  const challenge = Buffer.from(SignedMessage.encode(signedMsg).finish());

  // Send to license server
  const response = await fetch(licenseUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    },
    body: challenge,
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`License server returned ${response.status}: ${errText.substring(0, 200)}`);
  }

  const licenseResponse = Buffer.from(await response.arrayBuffer());

  // Parse the response SignedMessage
  const responseMsg = SignedMessage.decode(licenseResponse);
  const licenseBytes = responseMsg.msg as Uint8Array;

  // Parse License
  const License = r.lookupType('License');
  const license = License.decode(Buffer.from(licenseBytes));

  // Extract CONTENT keys
  const contentKeys: Record<string, string> = {};
  for (const key of (license as any).key) {
    if (key.type === 2) {  // CONTENT
      const kid = Buffer.from(key.id as Uint8Array).toString('hex');
      const keyVal = Buffer.from(key.key as Uint8Array).toString('hex');
      contentKeys[kid] = keyVal;
    }
  }

  if (Object.keys(contentKeys).length === 0) {
    // Fallback: try all non-signing keys
    for (const key of (license as any).key) {
      if (key.type !== 1 && key.type !== 3 && key.type !== 4) {  // not SIGNING/KEY_CONTROL/OPERATOR_SESSION
        const kid = Buffer.from(key.id as Uint8Array).toString('hex');
        const keyVal = Buffer.from(key.key as Uint8Array).toString('hex');
        if (kid !== '0'.repeat(32)) contentKeys[kid] = keyVal;
      }
    }
  }

  return contentKeys;
}

// ─── MPD Parser ───────────────────────────────────────────────────────────
export interface AdaptationInfo {
  type: string;
  repId: string;
  bandwidth: number;
  width: number;
  height: number;
  defaultKid: string | null;
  initTemplate: string | null;
  mediaTemplate: string | null;
  timescale: number;
  segmentDuration: number | null;
  startNumber: number;
  numSegments: number;
  baseURL: string | null;  // Per-representation BaseURL filename
}

export interface MPDInfo {
  baseUrl: string;
  periodDuration: number | null;
  adaptations: AdaptationInfo[];
}

export function parseMPD(mpdUrl: string, mpdXml: string): MPDInfo {
  // Base URL is the directory containing the MPD
  let baseUrl = mpdUrl.split('/').slice(0, -1).join('/') + '/';

  // Duration
  let periodDur: number | null = null;
  const durMatch = mpdXml.match(/mediaPresentationDuration="PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+\.?\d*)S)?"/);
  if (durMatch) {
    periodDur = (parseInt(durMatch[1] || '0')) * 3600 +
                (parseInt(durMatch[2] || '0')) * 60 +
                (parseFloat(durMatch[3] || '0'));
  }

  // AdaptationSets
  const adaptations: AdaptationInfo[] = [];
  const asRegex = /<AdaptationSet[^>]*>([\s\S]*?)<\/AdaptationSet>/g;
  let asMatch: RegExpExecArray | null;

  while ((asMatch = asRegex.exec(mpdXml)) !== null) {
    const asBlock = asMatch[0];
    const contentType = (asBlock.includes('contentType="audio"') || asBlock.includes('mimeType="audio'))
      ? 'audio' : 'video';

    const kidMatch = asBlock.match(/default_KID="([0-9a-f-]+)"/i);
    const defaultKid = kidMatch ? kidMatch[1].replace(/-/g, '') : null;

    // SegmentTemplate at AdaptationSet level
    const segTmplMatch = asBlock.match(/<SegmentTemplate[^>]*>/);
    let initTmpl: string | null = null;
    let mediaTmpl: string | null = null;
    let timescale = 1;
    let segDuration: number | null = null;
    let startNum = 1;

    if (segTmplMatch) {
      const tag = segTmplMatch[0];
      const im = tag.match(/initialization="([^"]*)"/); if (im) initTmpl = im[1];
      const mm = tag.match(/media="([^"]*)"/); if (mm) mediaTmpl = mm[1];
      const ts = tag.match(/timescale="(\d+)"/); if (ts) timescale = parseInt(ts[1]);
      const sd = tag.match(/duration="(\d+)"/); if (sd) segDuration = parseInt(sd[1]);
      const sn = tag.match(/startNumber="(\d+)"/); if (sn) startNum = parseInt(sn[1]);
    }

    let numSegments = 0;
    if (segDuration && periodDur) {
      numSegments = Math.ceil(periodDur / (segDuration / timescale));
    }

    // Representations - capture full content for BaseURL extraction
    const repRegex = /<Representation[^>]*id="([^"]*)"[^>]*>([\s\S]*?)<\/Representation>/g;
    let repMatch: RegExpExecArray | null;
    while ((repMatch = repRegex.exec(asBlock)) !== null) {
      const repId = repMatch[1];
      const repContent = repMatch[2];
      const repTag = repMatch[0];
      const bw = repTag.match(/bandwidth="(\d+)"/);
      const w = repTag.match(/ width="(\d+)"/);
      const h = repTag.match(/ height="(\d+)"/);

      // Extract per-representation BaseURL
      const repBaseMatch = repContent.match(/<BaseURL>(.*?)<\/BaseURL>/);
      const repBaseURL = repBaseMatch ? repBaseMatch[1].trim() : null;

      // Check for SegmentBase (static MP4)
      const segBaseMatch = asBlock.match(/<SegmentBase[^>]*>/);

      adaptations.push({
        type: contentType,
        repId,
        bandwidth: bw ? parseInt(bw[1]) : 0,
        width: w ? parseInt(w[1]) : 0,
        height: h ? parseInt(h[1]) : 0,
        defaultKid,
        initTemplate: initTmpl,
        mediaTemplate: mediaTmpl,
        timescale,
        segmentDuration: segDuration,
        startNumber: startNum,
        numSegments,
        baseURL: repBaseURL,
      });
    }
  }

  return { baseUrl, periodDuration: periodDur, adaptations };
}

// ─── HTTP Helper ───────────────────────────────────────────────────────────
const HTTP_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Accept': '*/*',
};

export async function httpGet(url: string): Promise<Buffer> {
  const resp = await fetch(url, { headers: { ...HTTP_HEADERS, 'Referer': url.split('/').slice(0, -1).join('/') + '/' } });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${url}`);
  return Buffer.from(await resp.arrayBuffer());
}

// ─── Segment Download ─────────────────────────────────────────────────────
export async function downloadInitAndMedia(
  baseUrl: string,
  initTmpl: string | null,
  mediaTmpl: string | null,
  repId: string,
  bandwidth: number,
  numSegments: number,
  startNum: number,
  onProgress: (pct: number, msg: string) => void,
  basePct: number,
  pctRange: number,
): Promise<{ initData: Buffer; segments: Buffer[] }> {
  if (!initTmpl || !mediaTmpl) {
    throw new Error('No segment templates found - this MPD may use SegmentBase (single file) which is handled differently');
  }

  const resolve = (tmpl: string, repId: string, num: number, bw: number) =>
    tmpl.replace(/\$RepresentationID\$/g, repId)
        .replace(/\$Bandwidth\$/g, String(bw))
        .replace(/\$Number\$/g, String(num))
        .replace(/\$Time\$/g, String(num));

  const initUrl = baseUrl + resolve(initTmpl, repId, 0, bandwidth);
  onProgress(basePct, `Downloading init segment...`);
  const initData = await httpGet(initUrl);

  const segments: Buffer[] = [];
  const maxAttempts = numSegments > 0 ? numSegments + 5 : 300;

  for (let segNum = startNum; segNum < startNum + maxAttempts; segNum++) {
    const segUrl = baseUrl + resolve(mediaTmpl, repId, segNum, bandwidth);
    let segData: Buffer;
    try {
      segData = await httpGet(segUrl);
    } catch (e: any) {
      if (e.message?.includes('404') || e.message?.includes('410')) break;
      throw e;
    }
    if (segData.length < 10) break;

    segments.push(segData);
    const done = segNum - startNum + 1;
    const total = numSegments > 0 ? numSegments : done + 1;
    const pct = Math.min(100, (done / total) * 100);
    onProgress(Math.round(basePct + pctRange * pct / 100), `Segment ${done}/${total}`);
    if (numSegments > 0 && done >= numSegments) break;
  }

  return { initData, segments };
}

// ─── MP4 Decrypt (AES-CTR) ────────────────────────────────────────────────
function aesCtrDecrypt(data: Buffer, key: Buffer, iv8: Buffer): Buffer {
  const iv16 = Buffer.concat([iv8, Buffer.alloc(8, 0)]);
  const decipher = crypto.createDecipheriv('aes-256-ctr', key, iv16);
  return Buffer.concat([decipher.update(data), decipher.final()]);
}

function iterBoxes(data: Buffer, start = 0, end?: number) {
  if (!end) end = data.length;
  const boxes: { type: string; offset: number; size: number; hdrSize: number }[] = [];
  let offset = start;
  while (offset < end - 8) {
    if (offset + 8 > end) break;
    let size = data.readUInt32BE(offset);
    const type = data.slice(offset + 4, offset + 8).toString('ascii');
    let hdrSize = 8;
    if (size === 1) {
      if (offset + 16 > end) break;
      size = Number(data.readBigUInt64BE(offset + 8));
      hdrSize = 16;
    } else if (size === 0) {
      size = end - offset;
    }
    if (size < 8 || offset + size > end) break;
    boxes.push({ type, offset, size, hdrSize });
    offset += size;
  }
  return boxes;
}

function parseSenc(data: Buffer, offset: number, size: number) {
  const hdrSize = 8;
  if (offset + hdrSize + 8 > offset + size) return [];
  const version = data[offset + hdrSize];
  const flags = (data[offset + 9] << 16) | (data[offset + 10] << 8) | data[offset + 11];
  const hasSubsamples = !!(flags & 0x02);
  const sampleCount = data.readUInt32BE(offset + 12);
  const ivSize = version === 0 ? 8 : 16;
  let pos = offset + 16;
  const samples: { iv: Buffer; subsamples: { clear: number; encrypted: number }[] }[] = [];

  for (let i = 0; i < sampleCount; i++) {
    if (pos + ivSize > offset + size) break;
    const iv = data.slice(pos, pos + ivSize);
    pos += ivSize;
    const subsamples: { clear: number; encrypted: number }[] = [];
    if (hasSubsamples) {
      if (pos + 2 > offset + size) break;
      const nSub = data.readUInt16BE(pos);
      pos += 2;
      for (let j = 0; j < nSub; j++) {
        if (pos + 6 > offset + size) break;
        const clear = data.readUInt16BE(pos);
        const encrypted = data.readUInt32BE(pos + 2);
        pos += 6;
        subsamples.push({ clear, encrypted });
      }
    }
    samples.push({ iv: iv.slice(0, 8), subsamples });
  }
  return samples;
}

function findKidFromMoov(data: Buffer): string | null {
  const boxes = iterBoxes(data, 0, data.length);
  for (const box of boxes) {
    if (box.type === 'moov') {
      return findTencRecursive(data, box.offset + box.hdrSize, box.offset + box.size);
    }
  }
  return null;
}

function findTencRecursive(data: Buffer, start: number, end: number): string | null {
  const boxes = iterBoxes(data, start, end);
  const containers = new Set(['moov', 'trak', 'mdia', 'minf', 'stbl', 'stsd', 'sinf', 'schi', 'moof', 'traf', 'encv', 'enca']);
  for (const box of boxes) {
    if (box.type === 'tenc') {
      const hdrSize = 8;
      if (box.offset + hdrSize + 4 > box.offset + box.size) continue;
      const version = data[box.offset + hdrSize];
      let pos = box.offset + hdrSize + 4;
      if (pos + 4 > box.offset + box.size) continue;
      const isProtected = data[pos];
      pos += 4;
      if (isProtected === 0) continue;
      if (pos + 16 > box.offset + box.size) continue;
      return data.slice(pos, pos + 16).toString('hex');
    }
    if (containers.has(box.type)) {
      const result = findTencRecursive(data, box.offset + box.hdrSize, box.offset + box.size);
      if (result) return result;
    }
  }
  return null;
}

export function mp4Decrypt(inputPath: string, outputPath: string, keys: Record<string, string>): number {
  const data = fs.readFileSync(inputPath);
  if (data.length < 16) throw new Error(`Input file too small: ${data.length} bytes`);
  
  const defaultKid = findKidFromMoov(data);
  const lowerKeys: Record<string, string> = {};
  for (const [k, v] of Object.entries(keys)) lowerKeys[k.toLowerCase()] = v.toLowerCase();

  const result: Buffer[] = [];
  const moofMdatPairs: { moofOffset: number; moofSize: number; mdatOffset: number; mdatSize: number }[] = [];

  // First pass: identify moof+mdat pairs and copy other boxes
  let offset = 0;
  const allBoxes = iterBoxes(data, 0, data.length);
  const moofMdatSet = new Set<number>();

  for (let i = 0; i < allBoxes.length; i++) {
    const box = allBoxes[i];
    if (box.type === 'moof' && i + 1 < allBoxes.length && allBoxes[i + 1].type === 'mdat') {
      moofMdatPairs.push({
        moofOffset: box.offset,
        moofSize: box.size,
        mdatOffset: allBoxes[i + 1].offset,
        mdatSize: allBoxes[i + 1].size,
      });
      moofMdatSet.add(box.offset);
      moofMdatSet.add(allBoxes[i + 1].offset);
    }
  }

  // Rebuild file
  offset = 0;
  for (const box of allBoxes) {
    if (moofMdatSet.has(box.offset) && box.type === 'moof') {
      // Find the matching pair
      const pair = moofMdatPairs.find(p => p.moofOffset === box.offset);
      if (!pair) {
        result.push(data.slice(box.offset, box.offset + box.size));
        continue;
      }

      const moofData = data.slice(pair.moofOffset, pair.moofOffset + pair.moofSize);
      const mdatData = data.slice(pair.mdatOffset + 8, pair.mdatOffset + pair.mdatSize);

      // Parse traf for senc
      let samples: any[] = [];
      let trackKid: string | null = null;
      const moofBoxes = iterBoxes(data, pair.moofOffset + 8, pair.moofOffset + pair.moofSize);
      for (const mb of moofBoxes) {
        if (mb.type === 'traf') {
          const trafBoxes = iterBoxes(data, mb.offset + 8, mb.offset + mb.size);
          for (const tb of trafBoxes) {
            if (tb.type === 'senc') {
              samples = parseSenc(data, tb.offset, tb.size);
            }
            if (tb.type === 'tenc') {
              trackKid = findTencRecursive(data, tb.offset, tb.offset + tb.size);
            }
          }
          if (samples.length > 0) break;
        }
      }

      if (samples.length === 0) {
        result.push(data.slice(pair.moofOffset, pair.mdatOffset + pair.mdatSize));
        continue;
      }

      // Find key
      let keyHex: string | null = null;
      if (trackKid && lowerKeys[trackKid]) keyHex = lowerKeys[trackKid];
      else if (defaultKid && lowerKeys[defaultKid]) keyHex = lowerKeys[defaultKid];
      else keyHex = Object.values(lowerKeys)[0] || null;

      if (!keyHex) {
        result.push(data.slice(pair.moofOffset, pair.mdatOffset + pair.mdatSize));
        continue;
      }

      const keyBytes = Buffer.from(keyHex, 'hex');

      // Decrypt mdat
      const decryptedParts: Buffer[] = [];
      let dataOffset = 0;
      for (const sample of samples) {
        const iv = sample.iv;
        if (!sample.subsamples || sample.subsamples.length === 0) {
          const sampleSize = mdatData.length - dataOffset;
          decryptedParts.push(aesCtrDecrypt(mdatData.slice(dataOffset, dataOffset + sampleSize), keyBytes, iv));
          dataOffset += sampleSize;
        } else {
          // Subsample encryption
          const encParts: { offset: number; size: number }[] = [];
          let sampleOffset = dataOffset;
          for (const sub of sample.subsamples) {
            if (sub.clear > 0) sampleOffset += sub.clear;
            if (sub.encrypted > 0) {
              encParts.push({ offset: sampleOffset, size: sub.encrypted });
              sampleOffset += sub.encrypted;
            }
          }
          const allEnc = Buffer.concat(encParts.map(p => mdatData.slice(p.offset, p.offset + p.size)));
          const allDec = aesCtrDecrypt(allEnc, keyBytes, iv);
          let decOffset = 0;
          sampleOffset = dataOffset;
          for (const sub of sample.subsamples) {
            if (sub.clear > 0) {
              decryptedParts.push(mdatData.slice(sampleOffset, sampleOffset + sub.clear));
              sampleOffset += sub.clear;
            }
            if (sub.encrypted > 0) {
              decryptedParts.push(allDec.slice(decOffset, decOffset + sub.encrypted));
              decOffset += sub.encrypted;
              sampleOffset += sub.encrypted;
            }
          }
          dataOffset = sampleOffset;
        }
      }
      if (dataOffset < mdatData.length) {
        decryptedParts.push(mdatData.slice(dataOffset));
      }

      // Strip senc/saiz/saio from moof
      const strippedMoof = stripEncryptionBoxes(moofData);

      result.push(strippedMoof);
      const mdatHeader = Buffer.alloc(8);
      mdatHeader.writeUInt32BE(pair.mdatSize, 0);
      mdatHeader.write('mdat', 4);
      result.push(mdatHeader);
      result.push(Buffer.concat(decryptedParts));

    } else if (moofMdatSet.has(box.offset) && box.type === 'mdat') {
      // Skip - handled with moof
      continue;
    } else {
      result.push(data.slice(box.offset, box.offset + box.size));
    }
  }

  const finalData = Buffer.concat(result);
  fs.writeFileSync(outputPath, finalData);
  return finalData.length;
}

function stripEncryptionBoxes(moofData: Buffer): Buffer {
  const boxesToRemove: { offset: number; size: number }[] = [];
  const removeTypes = new Set(['senc', 'saiz', 'saio']);
  const containerTypes = new Set(['moof', 'traf']);

  function findBoxesToRemove(data: Buffer, start: number, end: number) {
    for (const box of iterBoxes(data, start, end)) {
      if (removeTypes.has(box.type)) {
        boxesToRemove.push({ offset: box.offset, size: box.size });
      } else if (containerTypes.has(box.type)) {
        findBoxesToRemove(data, box.offset + box.hdrSize, box.offset + box.size);
      }
    }
  }

  findBoxesToRemove(moofData, 0, moofData.length);

  if (boxesToRemove.length === 0) return moofData;

  const result = Buffer.from(moofData);
  const arr = Uint8Array.from(result);
  let totalRemoved = 0;
  for (const { offset, size } of boxesToRemove.sort((a, b) => b.offset - a.offset)) {
    arr.copyWithin(offset, offset + size);
    totalRemoved += size;
  }

  const trimmed = Buffer.from(arr.buffer, 0, arr.length - totalRemoved);
  trimmed.writeUInt32BE(trimmed.length, 0); // Update moof box size
  return trimmed;
}

// ─── SegmentBase (single-file) Download ────────────────────────────────────
export async function downloadSegmentBase(
  baseUrl: string,
  repBaseUrl: string | null,
  onProgress: (pct: number, msg: string) => void,
  basePct: number,
  pctRange: number,
): Promise<Buffer> {
  // Construct the file URL from baseUrl + per-rep BaseURL
  let fileUrl = baseUrl;
  if (repBaseUrl) {
    if (repBaseUrl.startsWith('http')) fileUrl = repBaseUrl;
    else fileUrl = baseUrl + repBaseUrl;
  }

  onProgress(basePct, `Downloading: ${fileUrl.split('/').pop()}...`);
  const data = await httpGet(fileUrl);
  onProgress(basePct + pctRange, 'Download complete');
  return data;
}
