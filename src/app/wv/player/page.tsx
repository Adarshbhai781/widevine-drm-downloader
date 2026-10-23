"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

// Load Shaka Player from CDN via script tag
function loadShaka(): Promise<any> {
  return new Promise((resolve, reject) => {
    if ((window as any).shaka) {
      resolve((window as any).shaka);
      return;
    }
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/shaka-player@4.11/dist/shaka-player.compiled.min.js";
    script.onload = () => {
      resolve((window as any).shaka);
    };
    script.onerror = () => reject(new Error("Failed to load Shaka Player"));
    document.head.appendChild(script);
  });
}

export default function PlayerPage() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session") || "";
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState("Loading...");
  const [error, setError] = useState("");
  const [mpdUrl, setMpdUrl] = useState("");
  const [keyCount, setKeyCount] = useState(0);

  useEffect(() => {
    if (!sessionId) {
      setError("No session ID provided. Usage: /wv/player?session=<SESSION_ID>");
      return;
    }

    const initPlayer = async () => {
      try {
        setStatus("Fetching session data...");

        // Get session data from our API
        const res = await fetch(`/api/wv/session?id=${sessionId}`);
        const data = await res.json();

        if (data.status !== "ok") {
          setError(data.message || "Failed to get session data");
          return;
        }

        setMpdUrl(data.mpd_url);
        setKeyCount(Object.keys(data.clearkeys).length);
        setStatus("Loading Shaka Player...");

        // Load Shaka Player from CDN
        const shaka = await loadShaka();
        shaka.polyfill.installAll();

        setStatus("Initializing player...");
        const player = new shaka.Player();
        await player.attach(videoRef.current);

        // Configure with ClearKeys - this bypasses the Widevine license server
        // and uses the pre-computed keys directly for decryption
        player.configure({
          drm: {
            clearKeys: data.clearkeys,
          },
          streaming: {
            bufferingGoal: 30,
            bufferBehind: 10,
          },
        });

        setStatus("Loading stream...");
        await player.load(data.mpd_url);
        setStatus("Playing");
      } catch (e: any) {
        console.error("Player error:", e);
        setError(e.message || "Failed to initialize player");
        setStatus("Error");
      }
    };

    initPlayer();
  }, [sessionId]);

  return (
    <div className="min-h-screen bg-black flex flex-col items-center justify-center p-4">
      {/* Header */}
      <div className="w-full max-w-4xl mb-4">
        <div className="flex items-center gap-3 mb-2">
          <div
            className={`w-3 h-3 rounded-full ${
              status === "Playing"
                ? "bg-green-500 animate-pulse"
                : status === "Error"
                ? "bg-red-500"
                : "bg-yellow-500 animate-pulse"
            }`}
          />
          <h1 className="text-xl font-bold text-white">
            Widevine Stream Player
          </h1>
        </div>
        <div className="flex gap-4 text-sm text-gray-400">
          <span>
            Status:{" "}
            <span
              className={
                status === "Playing"
                  ? "text-green-400"
                  : status === "Error"
                  ? "text-red-400"
                  : "text-yellow-400"
              }
            >
              {status}
            </span>
          </span>
          {keyCount > 0 && <span>Keys: {keyCount}</span>}
        </div>
        {mpdUrl && (
          <p className="text-xs text-gray-600 mt-1 break-all font-mono">
            {mpdUrl}
          </p>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="w-full max-w-4xl mb-4 bg-red-900/30 border border-red-800 rounded-lg p-4 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Video */}
      <div className="w-full max-w-4xl bg-black rounded-xl overflow-hidden border border-gray-800">
        <video
          ref={videoRef}
          controls
          autoPlay
          className="w-full max-h-[70vh]"
        />
      </div>

      {/* Info */}
      <div className="w-full max-w-4xl mt-4 text-center text-gray-600 text-xs">
        Session: {sessionId} | Shaka Player + ClearKey Decryption
      </div>
    </div>
  );
}
