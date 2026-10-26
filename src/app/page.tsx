'use client';

import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  Link as LinkIcon,
  Key,
  Copy,
  ExternalLink,
  Terminal,
} from 'lucide-react';

interface WvResult {
  status: string;
  session_id?: string;
  mpd_url?: string;
  keys?: { kid: string; key: string }[];
  keys_hex?: string[];
  clearkeys?: Record<string, string>;
  download_cmd?: string;
  play_url?: string;
  message?: string;
  error?: string;
}

export default function WvDownloaderPage() {
  const [mpdUrl, setMpdUrl] = useState('');
  const [licenseUrl, setLicenseUrl] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<WvResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!mpdUrl.trim()) return;
    setIsSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch('/api/wv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          processurl: mpdUrl.trim(),
          license_url: licenseUrl.trim() || undefined,
        }),
      });

      const data: WvResult = await res.json();

      if (data.status !== 'success') {
        setError(data.message || data.error || 'Processing failed');
        return;
      }

      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setIsSubmitting(false);
    }
  }, [mpdUrl, licenseUrl]);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  const CopyBtn = ({ text, id }: { text: string; id: string }) => (
    <Button
      variant="ghost"
      size="sm"
      className="text-gray-400 hover:text-white h-7"
      onClick={() => copyToClipboard(text, id)}
    >
      <Copy className="h-3.5 w-3.5 mr-1" />
      {copied === id ? 'Copied!' : 'Copy'}
    </Button>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 text-white">
      <div className="mx-auto max-w-4xl px-4 py-8">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
            Widevine DRM Downloader
          </h1>
          <p className="mt-2 text-gray-400">
            Paste DASH MPD URL → Get decryption keys → Play & Download
          </p>
        </div>

        {/* URL Input Card */}
        <Card className="border-gray-800 bg-gray-900/80 backdrop-blur mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-emerald-400">
              <LinkIcon className="h-5 w-5" />
              MPD URL
            </CardTitle>
            <CardDescription className="text-gray-400">
              Enter the DASH manifest URL of the DRM-protected content (or use a preset: bitmovin,
              tears, tears_vp9, axinom_cbcs)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm text-gray-300">MPD URL or Preset</label>
              <Input
                placeholder="https://cdn.example.com/content/manifest.mpd"
                value={mpdUrl}
                onChange={(e) => setMpdUrl(e.target.value)}
                className="bg-gray-800 border-gray-700 text-white placeholder-gray-500 focus:border-emerald-500"
                onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-gray-300">
                License URL (optional — leave empty for presets)
              </label>
              <Input
                placeholder="https://cwip-shaka-proxy.appspot.com/no_auth"
                value={licenseUrl}
                onChange={(e) => setLicenseUrl(e.target.value)}
                className="bg-gray-800 border-gray-700 text-white placeholder-gray-500 focus:border-emerald-500"
              />
            </div>
            <Button
              onClick={handleSubmit}
              disabled={isSubmitting || !mpdUrl.trim()}
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
            >
              {isSubmitting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              {isSubmitting ? 'Getting keys...' : 'Process & Play'}
            </Button>
            {error && (
              <div className="flex items-start gap-2 text-red-400 text-sm mt-2 p-3 rounded-lg bg-red-950/50 border border-red-900">
                <XCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span className="break-all">{error}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Results */}
        {result?.status === 'success' && (
          <>
            {/* Keys Card */}
            <Card className="border-gray-800 bg-gray-900/80 backdrop-blur mb-6">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-cyan-400">
                  <Key className="h-5 w-5" />
                  Decryption Keys
                  <Badge variant="outline" className="ml-2 text-emerald-400 border-emerald-700">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    Success
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {result.keys_hex?.map((kh, i) => (
                  <div key={i} className="p-3 rounded-lg bg-gray-800/80">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-gray-300 font-medium">KID:KEY #{i + 1}</span>
                      <CopyBtn text={kh} id={`key-${i}`} />
                    </div>
                    <code className="text-xs text-emerald-400 font-mono break-all">{kh}</code>
                  </div>
                ))}

                {/* Download Command */}
                {result.download_cmd && (
                  <div className="p-3 rounded-lg bg-gray-800/80">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-gray-300 font-medium flex items-center gap-1.5">
                        <Terminal className="h-4 w-4 text-cyan-400" />
                        yt-dlp Download Command
                      </span>
                      <CopyBtn text={result.download_cmd} id="ytdl" />
                    </div>
                    <code className="text-xs text-cyan-300 font-mono break-all block">
                      {result.download_cmd}
                    </code>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Player Card */}
            {result.play_url && (
              <Card className="border-gray-800 bg-gray-900/80 backdrop-blur mb-6">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-purple-400">
                    <Play className="h-5 w-5" />
                    DRM Player
                  </CardTitle>
                  <CardDescription className="text-gray-400">
                    Opens a Shaka Player page that decrypts and plays the stream in your browser
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="p-3 rounded-lg bg-gray-800/80">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-gray-300 font-medium">Player URL</span>
                      <CopyBtn text={result.play_url} id="play" />
                    </div>
                    <code className="text-xs text-purple-400 font-mono break-all">
                      {result.play_url}
                    </code>
                  </div>
                  <Button
                    className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold"
                    onClick={() => window.open(result.play_url, '_blank')}
                  >
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Open Player in New Tab
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* MPD Info */}
            {result.mpd_url && (
              <Card className="border-gray-800 bg-gray-900/80 backdrop-blur">
                <CardContent className="pt-6">
                  <div className="p-3 rounded-lg bg-gray-800/80">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-gray-300 font-medium">Source MPD</span>
                      <CopyBtn text={result.mpd_url} id="mpd" />
                    </div>
                    <code className="text-xs text-gray-400 font-mono break-all">
                      {result.mpd_url}
                    </code>
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {/* Footer */}
        <div className="mt-8 text-center text-xs text-gray-600">
          Widevine DRM Downloader • L3 CDM • For educational/testing purposes only
        </div>
      </div>
    </div>
  );
}
