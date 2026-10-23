"use client";

import { useState } from "react";

const PRESETS = [
  { id: "bitmovin", label: "Bitmovin Art of Motion", desc: "H264 CENC 1080p" },
  { id: "tears", label: "Tears of Steel (HD)", desc: "H264 CENC 1080p" },
  { id: "tears_uhd", label: "Tears of Steel (4K)", desc: "H264 CENC UHD" },
  { id: "tears_vp9", label: "Tears of Steel (VP9)", desc: "WebM CENC" },
  { id: "tears_cbcs", label: "Tears of Steel (CBCS)", desc: "H264 AES-CBCS" },
];

export default function WVPage() {
  const [processurl, setProcessurl] = useState("");
  const [licUrl, setLicUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  const handleProcess = async () => {
    if (!processurl) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const params = new URLSearchParams({ processurl });
      if (licUrl) params.set("license_url", licUrl);
      const res = await fetch(`/api/wv/drm?${params}`);
      const data = await res.json();
      if (data.status === "error") {
        setError(data.message || "Unknown error");
      } else {
        setResult(data);
      }
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const copy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(""), 2000);
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-red-500 mb-2">
            Widevine DRM API
          </h1>
          <p className="text-gray-400">
            One endpoint: <code className="text-yellow-400">/api/wv/drm?processurl=&lt;MPD_URL&gt;</code>
            {" "}
            → Get keys + playable stream URL
          </p>
        </div>

        {/* Input */}
        <div className="bg-[#1a1a1a] rounded-xl p-6 mb-6">
          <div className="grid gap-4 mb-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                processurl <span className="text-gray-600">(MPD URL or preset name)</span>
              </label>
              <input
                type="text"
                value={processurl}
                onChange={(e) => setProcessurl(e.target.value)}
                placeholder="bitmovin  or  https://storage.googleapis.com/wvmedia/cenc/h264/tears/tears.mpd"
                className="w-full bg-[#111] border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:border-red-500 focus:outline-none font-mono text-sm"
                onKeyDown={(e) => e.key === "Enter" && handleProcess()}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                license_url <span className="text-gray-600">(optional)</span>
              </label>
              <input
                type="text"
                value={licUrl}
                onChange={(e) => setLicUrl(e.target.value)}
                placeholder="https://cwip-shaka-proxy.appspot.com/no_auth"
                className="w-full bg-[#111] border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:border-red-500 focus:outline-none font-mono text-sm"
              />
            </div>
          </div>

          {/* Presets */}
          <div className="mb-4">
            <p className="text-sm text-gray-500 mb-2">Quick presets:</p>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    setProcessurl(p.id);
                    setLicUrl("");
                  }}
                  className="bg-[#222] hover:bg-red-900/30 border border-gray-700 hover:border-red-500/50 rounded-lg px-3 py-2 text-sm transition-colors"
                >
                  <span className="text-white">{p.label}</span>
                  <span className="text-gray-500 ml-1">({p.desc})</span>
                </button>
              ))}
            </div>
          </div>

          {/* Submit */}
          <button
            onClick={handleProcess}
            disabled={loading || !processurl}
            className="bg-red-600 hover:bg-red-700 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold rounded-lg px-8 py-3 transition-colors text-lg"
          >
            {loading ? "Processing..." : "Process URL"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 mb-6 text-red-400">
            {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-4">
            {/* Status bar */}
            <div className="bg-green-900/20 border border-green-800 rounded-xl p-4 flex items-center justify-between">
              <div>
                <p className="text-green-400 font-semibold">
                  Status: {result.status} | Keys: {result.keys?.length || 0} | Session: {result.session_id}
                </p>
                <p className="text-gray-500 text-xs mt-1 font-mono break-all">
                  {result.mpd_url}
                </p>
              </div>
            </div>

            {/* Play URL — THE MAIN THING */}
            {result.play_url && (
              <div className="bg-[#1a1a1a] rounded-xl p-5 border-2 border-green-600/50">
                <h3 className="text-green-500 font-bold mb-3 text-lg">
                  Playable Stream URL (Open in Chrome)
                </h3>
                <div className="bg-[#111] rounded px-4 py-3 font-mono text-sm text-green-400 break-all flex items-start justify-between gap-3">
                  <span className="select-all">{result.play_url}</span>
                  <button
                    onClick={() => copy(result.play_url, "play")}
                    className="bg-green-600 hover:bg-green-700 text-white text-xs px-3 py-1 rounded shrink-0"
                  >
                    {copied === "play" ? "Copied!" : "Copy"}
                  </button>
                </div>
                <p className="text-gray-500 text-xs mt-2">
                  Open this URL in Chrome browser to play the video directly with Shaka Player
                </p>
                <a
                  href={result.play_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block mt-3 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-semibold"
                >
                  Open Player
                </a>
              </div>
            )}

            {/* Keys */}
            {result.keys_hex && result.keys_hex.length > 0 && (
              <div className="bg-[#1a1a1a] rounded-xl p-5">
                <h3 className="text-red-500 font-semibold mb-3">
                  Decryption Keys (KID:KEY)
                </h3>
                <div className="space-y-1 font-mono text-sm">
                  {result.keys_hex.map((k: string, i: number) => (
                    <div
                      key={i}
                      className="bg-[#111] rounded px-3 py-2 text-green-400 break-all flex items-start justify-between gap-2"
                    >
                      <span>{k}</span>
                      <button
                        onClick={() => copy(k, `key-${i}`)}
                        className="text-gray-500 hover:text-white shrink-0 text-xs"
                      >
                        {copied === `key-${i}` ? "Done" : "copy"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Download Command */}
            {result.download_cmd && (
              <div className="bg-[#1a1a1a] rounded-xl p-5">
                <h3 className="text-red-500 font-semibold mb-3">
                  yt-dlp Download Command
                </h3>
                <div className="bg-[#111] rounded px-3 py-3 font-mono text-sm text-yellow-400 break-all relative">
                  {result.download_cmd}
                  <button
                    onClick={() => copy(result.download_cmd, "dl")}
                    className="absolute top-2 right-2 bg-red-600 hover:bg-red-700 text-white text-xs px-2 py-1 rounded"
                  >
                    {copied === "dl" ? "Done" : "Copy"}
                  </button>
                </div>
              </div>
            )}

            {/* PSSH & License */}
            <div className="bg-[#1a1a1a] rounded-xl p-5">
              <h3 className="text-gray-400 font-semibold mb-3 text-sm">
                Debug Info
              </h3>
              <div className="space-y-2 text-xs font-mono">
                <div className="text-gray-500">
                  PSSH: <span className="text-gray-400 break-all">{result.pssh}</span>
                </div>
                <div className="text-gray-500">
                  License: <span className="text-gray-400">{result.license_url}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* API Reference */}
        <div className="mt-8 bg-[#1a1a1a] rounded-xl p-5">
          <h3 className="text-red-500 font-semibold mb-3">API Reference</h3>
          <div className="space-y-2 font-mono text-sm text-gray-400">
            <p>
              GET{" "}
              <span className="text-yellow-400">
                /api/wv/drm?processurl=&lt;MPD_URL&gt;
              </span>
            </p>
            <p>
              GET{" "}
              <span className="text-yellow-400">
                /api/wv/drm?processurl=bitmovin
              </span>
            </p>
            <p>
              POST{" "}
              <span className="text-yellow-400">
                /api/wv/drm
              </span>{" "}
              body: {"{ processurl, license_url, pssh }"}
            </p>
          </div>
          <div className="mt-3 text-xs text-gray-600">
            Returns: status, session_id, keys, clearkeys, play_url, download_cmd
          </div>
        </div>
      </div>
    </div>
  );
}
