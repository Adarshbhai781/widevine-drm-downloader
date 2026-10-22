"use client";

import { useState } from "react";

const PRESETS = [
  { id: "tears", label: "Tears of Steel (HD)", desc: "H264 CENC 1080p" },
  { id: "tears_uhd", label: "Tears of Steel (4K)", desc: "H264 CENC UHD" },
  { id: "tears_vp9", label: "Tears of Steel (VP9)", desc: "WebM CENC" },
  { id: "tears_cbcs", label: "Tears of Steel (CBCS)", desc: "H264 AES CBCS" },
];

type Tab = "stream" | "play";

export default function WVPage() {
  const [mpdUrl, setMpdUrl] = useState("");
  const [licUrl, setLicUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("stream");

  // Play state
  const [jobId, setJobId] = useState("");
  const [jobStatus, setJobStatus] = useState<any>(null);
  const [polling, setPolling] = useState(false);

  const handleStream = async () => {
    if (!mpdUrl) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const params = new URLSearchParams({ fetchstreamurl: mpdUrl });
      if (licUrl) params.set("lic", licUrl);
      const res = await fetch(`/api/wv/stream?${params}`);
      const data = await res.json();
      if (data.error) setError(data.error);
      else setResult(data);
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const handlePlay = async () => {
    if (!mpdUrl) return;
    setLoading(true);
    setError("");
    setJobId("");
    setJobStatus(null);
    try {
      const params = new URLSearchParams({ fetchstreamurl: mpdUrl });
      if (licUrl) params.set("lic", licUrl);
      const res = await fetch(`/api/wv/play?${params}`);
      const data = await res.json();
      if (data.error) {
        setError(data.error);
        setLoading(false);
      } else {
        setJobId(data.jobId);
        setPolling(true);
        pollStatus(data.jobId);
      }
    } catch (e: any) {
      setError(e.message);
      setLoading(false);
    }
  };

  const pollStatus = async (jid: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/wv/play/status/${jid}`);
        const data = await res.json();
        setJobStatus(data);
        if (data.status === "done" || data.status === "error") {
          clearInterval(interval);
          setPolling(false);
          setLoading(false);
        }
      } catch {
        clearInterval(interval);
        setPolling(false);
        setLoading(false);
      }
    }, 2000);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-red-500 mb-2">Widevine DRM API</h1>
          <p className="text-gray-400">
            Enter an MPD URL to get decryption keys, stream URLs, and download commands
          </p>
        </div>

        {/* Input Section */}
        <div className="bg-[#1a1a1a] rounded-xl p-6 mb-6">
          <div className="grid gap-4 mb-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">MPD URL / Preset Name</label>
              <input
                type="text"
                value={mpdUrl}
                onChange={(e) => setMpdUrl(e.target.value)}
                placeholder="https://storage.googleapis.com/wvmedia/cenc/h264/tears/tears.mpd"
                className="w-full bg-[#111] border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:border-red-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                License URL <span className="text-gray-600">(optional - defaults to Shaka proxy)</span>
              </label>
              <input
                type="text"
                value={licUrl}
                onChange={(e) => setLicUrl(e.target.value)}
                placeholder="https://cwip-shaka-proxy.appspot.com/no_auth"
                className="w-full bg-[#111] border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:border-red-500 focus:outline-none"
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
                  onClick={() => { setMpdUrl(p.id); setLicUrl(""); }}
                  className="bg-[#222] hover:bg-red-900/30 border border-gray-700 hover:border-red-500/50 rounded-lg px-3 py-2 text-sm transition-colors"
                >
                  <span className="text-white">{p.label}</span>
                  <span className="text-gray-500 ml-1">({p.desc})</span>
                </button>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3">
            <button
              onClick={tab === "stream" ? handleStream : handlePlay}
              disabled={loading || !mpdUrl}
              className="bg-red-600 hover:bg-red-700 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold rounded-lg px-6 py-3 transition-colors"
            >
              {loading ? "Processing..." : tab === "stream" ? "Get Stream Keys" : "Download & Play"}
            </button>
            <div className="flex bg-[#111] rounded-lg overflow-hidden border border-gray-700">
              <button
                onClick={() => setTab("stream")}
                className={`px-4 py-3 text-sm ${tab === "stream" ? "bg-red-600 text-white" : "text-gray-400 hover:text-white"}`}
              >
                Stream API
              </button>
              <button
                onClick={() => setTab("play")}
                className={`px-4 py-3 text-sm ${tab === "play" ? "bg-red-600 text-white" : "text-gray-400 hover:text-white"}`}
              >
                Play Video
              </button>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 mb-6 text-red-400">
            {error}
          </div>
        )}

        {/* Stream Result */}
        {tab === "stream" && result && (
          <div className="space-y-4">
            {/* Status */}
            <div className="bg-green-900/20 border border-green-800 rounded-xl p-4">
              <p className="text-green-400 font-semibold">
                Status: {result.status} | Keys: {result.keys?.length || 0}
                {result.preset_name && ` | ${result.preset_name}`}
              </p>
              {result.title && <p className="text-gray-400 text-sm mt-1">Title: {result.title}</p>}
            </div>

            {/* Keys */}
            {result.keys && result.keys.length > 0 && (
              <div className="bg-[#1a1a1a] rounded-xl p-5">
                <h3 className="text-red-500 font-semibold mb-3">Decryption Keys (KID:KEY)</h3>
                <div className="space-y-1 font-mono text-sm">
                  {result.keys.map((k: string, i: number) => (
                    <div key={i} className="bg-[#111] rounded px-3 py-2 text-green-400 break-all flex justify-between items-start gap-2">
                      <span>{k}</span>
                      <button onClick={() => copyToClipboard(k)} className="text-gray-500 hover:text-white shrink-0 text-xs">copy</button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Download Command */}
            {result.download_command && (
              <div className="bg-[#1a1a1a] rounded-xl p-5">
                <h3 className="text-red-500 font-semibold mb-3">yt-dlp Download Command</h3>
                <div className="bg-[#111] rounded px-3 py-3 font-mono text-sm text-yellow-400 break-all relative">
                  {result.download_command}
                  <button
                    onClick={() => copyToClipboard(result.download_command)}
                    className="absolute top-2 right-2 bg-red-600 hover:bg-red-700 text-white text-xs px-2 py-1 rounded"
                  >
                    Copy
                  </button>
                </div>
              </div>
            )}

            {/* mp4decrypt */}
            {result.mp4decrypt_command && (
              <div className="bg-[#1a1a1a] rounded-xl p-5">
                <h3 className="text-red-500 font-semibold mb-3">mp4decrypt Command</h3>
                <div className="bg-[#111] rounded px-3 py-3 font-mono text-sm text-cyan-400 break-all">
                  {result.mp4decrypt_command}
                </div>
              </div>
            )}

            {/* Formats */}
            {result.formats && result.formats.length > 0 && (
              <div className="bg-[#1a1a1a] rounded-xl p-5">
                <h3 className="text-red-500 font-semibold mb-3">Available Formats</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-gray-500 border-b border-gray-800">
                        <th className="py-2 px-2 text-left">ID</th>
                        <th className="py-2 px-2 text-left">Resolution</th>
                        <th className="py-2 px-2 text-left">Codec</th>
                        <th className="py-2 px-2 text-left">Ext</th>
                        <th className="py-2 px-2 text-left">Bitrate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.formats.map((f: any, i: number) => (
                        <tr key={i} className="border-b border-gray-800/50">
                          <td className="py-2 px-2 text-gray-300">{f.format_id}</td>
                          <td className="py-2 px-2 text-gray-300">{f.resolution}</td>
                          <td className="py-2 px-2 text-gray-300 font-mono text-xs">
                            {f.vcodec !== "none" ? f.vcodec : f.acocodec}
                          </td>
                          <td className="py-2 px-2 text-gray-300">{f.ext}</td>
                          <td className="py-2 px-2 text-gray-300">{f.bandwidth ? `${f.bandwidth}k` : "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Play Result */}
        {tab === "play" && (jobId || jobStatus) && (
          <div className="space-y-4">
            {/* Progress */}
            <div className="bg-[#1a1a1a] rounded-xl p-5">
              <div className="flex justify-between items-center mb-2">
                <span className="text-gray-400">{jobStatus?.message || "Processing..."}</span>
                <span className="text-white font-mono">{jobStatus?.progress || 0}%</span>
              </div>
              <div className="bg-[#333] rounded-full h-3 overflow-hidden">
                <div
                  className="bg-red-500 h-full rounded-full transition-all duration-300"
                  style={{ width: `${jobStatus?.progress || 0}%` }}
                />
              </div>
            </div>

            {/* Keys */}
            {jobStatus?.keys && jobStatus.keys.length > 0 && (
              <div className="bg-[#1a1a1a] rounded-xl p-5">
                <h3 className="text-red-500 font-semibold mb-3">Keys Found</h3>
                <div className="space-y-1 font-mono text-sm">
                  {jobStatus.keys.map((k: string, i: number) => (
                    <div key={i} className="bg-[#111] rounded px-3 py-2 text-green-400 break-all">{k}</div>
                  ))}
                </div>
              </div>
            )}

            {/* Video Player */}
            {jobStatus?.status === "done" && (
              <div className="bg-black rounded-xl overflow-hidden">
                <video
                  controls
                  autoPlay
                  className="w-full"
                  src={`/api/wv/play/video/${jobId}`}
                />
                <div className="p-4 bg-[#1a1a1a] flex justify-between items-center">
                  <div>
                    <span className="text-white">{jobStatus.title || "Video"}</span>
                    {jobStatus.resolution && (
                      <span className="text-gray-400 ml-2">{jobStatus.resolution}</span>
                    )}
                    {jobStatus.video_size_mb && (
                      <span className="text-gray-400 ml-2">{jobStatus.video_size_mb} MB</span>
                    )}
                  </div>
                  <a
                    href={`/api/wv/play/download/${jobId}`}
                    download
                    className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm"
                  >
                    Download
                  </a>
                </div>
              </div>
            )}
          </div>
        )}

        {/* API Usage Reference */}
        <div className="mt-8 bg-[#1a1a1a] rounded-xl p-5">
          <h3 className="text-red-500 font-semibold mb-3">API Endpoints</h3>
          <div className="space-y-2 font-mono text-sm text-gray-400">
            <p>GET /api/wv/stream?fetchstreamurl=&lt;MPD_URL&gt;&lic=&lt;LIC_URL&gt;</p>
            <p>GET /api/wv/play?fetchstreamurl=&lt;MPD_URL&gt;</p>
            <p>GET /api/wv/play/status/&lt;jobId&gt;</p>
            <p>GET /api/wv/play/video/&lt;jobId&gt;</p>
            <p>GET /api/wv/keys  (POST: {`{mpdUrl, licenseUrl}`})</p>
          </div>
        </div>
      </div>
    </div>
  );
}
