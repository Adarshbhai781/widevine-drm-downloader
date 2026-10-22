'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Textarea } from '@/components/ui/textarea';
import {
  Play,
  Download,
  Loader2,
  CheckCircle2,
  XCircle,
  Link,
  Video,
  Clock,
  HardDrive,
  Copy,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';

type JobStatus = 'pending' | 'processing' | 'decrypting' | 'merging' | 'done' | 'error';

interface JobInfo {
  jobId: string;
  status: JobStatus;
  progress: number;
  message: string | null;
  videoSize: number | null;
  duration: number | null;
  resolution: string | null;
  mpdUrl: string;
}

export default function WvDownloaderPage() {
  const [mpdUrl, setMpdUrl] = useState('');
  const [licenseUrl, setLicenseUrl] = useState('https://cwip-shaka-proxy.appspot.com/no_auth');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [job, setJob] = useState<JobInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recentJobs, setRecentJobs] = useState<JobInfo[]>([]);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Poll job status
  useEffect(() => {
    if (!job || job.status === 'done' || job.status === 'error') return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/wv/status?jobId=${job.jobId}`);
        const data = await res.json();
        setJob((prev) => ({
          ...prev!,
          status: data.status,
          progress: data.progress,
          message: data.message,
          videoSize: data.videoSize,
          duration: data.duration,
          resolution: data.resolution,
        }));
      } catch {
        // ignore poll errors
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [job?.jobId, job?.status]);

  // Load recent jobs on mount
  useEffect(() => {
    loadRecentJobs();
  }, []);

  const loadRecentJobs = async () => {
    try {
      const res = await fetch('/api/wv/jobs');
      const data = await res.json();
      if (data.jobs) {
        setRecentJobs(
          data.jobs.map((j: JobInfo & { createdAt: string }) => ({
            jobId: j.jobId ?? j.id,
            status: j.status,
            progress: j.progress,
            message: j.message,
            videoSize: j.videoSize,
            duration: j.duration,
            resolution: j.resolution,
            mpdUrl: j.mpdUrl,
          }))
        );
      }
    } catch {
      // ignore
    }
  };

  const handleSubmit = useCallback(async () => {
    if (!mpdUrl.trim()) return;
    setIsSubmitting(true);
    setError(null);
    setJob(null);

    try {
      const res = await fetch('/api/wv/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mpdUrl: mpdUrl.trim(),
          licenseUrl: licenseUrl.trim() || undefined,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || 'Failed to start processing');
        return;
      }

      setJob({
        jobId: data.jobId,
        status: 'pending',
        progress: 0,
        message: 'Processing started...',
        videoSize: null,
        duration: null,
        resolution: null,
        mpdUrl: mpdUrl.trim(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setIsSubmitting(false);
    }
  }, [mpdUrl, licenseUrl]);

  const videoStreamUrl = job?.status === 'done' ? `/api/wv/video?jobId=${job.jobId}` : null;
  const ytdlCommand = job?.status === 'done' ? `yt-dlp "${videoStreamUrl}" -o video.mp4` : '';

  const statusColors: Record<JobStatus, string> = {
    pending: 'bg-yellow-500',
    processing: 'bg-blue-500',
    decrypting: 'bg-purple-500',
    merging: 'bg-orange-500',
    done: 'bg-green-500',
    error: 'bg-red-500',
  };

  const statusLabels: Record<JobStatus, string> = {
    pending: 'Pending',
    processing: 'Downloading',
    decrypting: 'Decrypting',
    merging: 'Merging',
    done: 'Complete',
    error: 'Error',
  };

  const formatSize = (bytes: number | null) => {
    if (!bytes) return '-';
    if (bytes > 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
    if (bytes > 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / 1024).toFixed(0)} KB`;
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '-';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 text-white">
      <div className="mx-auto max-w-4xl px-4 py-8">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
            Widevine DRM Downloader
          </h1>
          <p className="mt-2 text-gray-400">
            Paste DASH MPD URL → Video plays → Download via yt-dlp
          </p>
        </div>

        {/* URL Input Card */}
        <Card className="border-gray-800 bg-gray-900/80 backdrop-blur mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-emerald-400">
              <Link className="h-5 w-5" />
              MPD URL
            </CardTitle>
            <CardDescription className="text-gray-400">
              Enter the DASH manifest URL of the DRM-protected content
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm text-gray-300">MPD URL</label>
              <Input
                placeholder="https://cdn.example.com/content/manifest.mpd"
                value={mpdUrl}
                onChange={(e) => setMpdUrl(e.target.value)}
                className="bg-gray-800 border-gray-700 text-white placeholder-gray-500 focus:border-emerald-500"
                onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-gray-300">License URL (optional)</label>
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
              {isSubmitting ? 'Starting...' : 'Process & Play'}
            </Button>
            {error && (
              <div className="flex items-center gap-2 text-red-400 text-sm mt-2">
                <XCircle className="h-4 w-4 flex-shrink-0" />
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Progress Card */}
        {job && (
          <Card className="border-gray-800 bg-gray-900/80 backdrop-blur mb-6">
            <CardContent className="pt-6 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`h-3 w-3 rounded-full ${statusColors[job.status]} ${job.status !== 'done' && job.status !== 'error' ? 'animate-pulse' : ''}`} />
                  <span className="font-medium">{statusLabels[job.status]}</span>
                </div>
                <Badge variant="outline" className="text-gray-400 border-gray-700">
                  {job.progress}%
                </Badge>
              </div>
              <Progress value={job.progress} className="h-2 bg-gray-800 [&>div]:bg-emerald-500" />
              {job.message && (
                <p className="text-sm text-gray-400">{job.message}</p>
              )}

              {/* Video Info */}
              {job.status === 'done' && (
                <div className="grid grid-cols-3 gap-4 mt-4 p-4 rounded-lg bg-gray-800/50">
                  <div className="text-center">
                    <Video className="h-5 w-5 mx-auto mb-1 text-emerald-400" />
                    <p className="text-xs text-gray-400">Resolution</p>
                    <p className="text-sm font-medium">{job.resolution || '-'}</p>
                  </div>
                  <div className="text-center">
                    <Clock className="h-5 w-5 mx-auto mb-1 text-cyan-400" />
                    <p className="text-xs text-gray-400">Duration</p>
                    <p className="text-sm font-medium">{formatDuration(job.duration)}</p>
                  </div>
                  <div className="text-center">
                    <HardDrive className="h-5 w-5 mx-auto mb-1 text-purple-400" />
                    <p className="text-xs text-gray-400">Size</p>
                    <p className="text-sm font-medium">{formatSize(job.videoSize)}</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Video Player */}
        {job?.status === 'done' && videoStreamUrl && (
          <Card className="border-gray-800 bg-gray-900/80 backdrop-blur mb-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-cyan-400">
                <Video className="h-5 w-5" />
                Video Player
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg overflow-hidden bg-black aspect-video">
                <video
                  ref={videoRef}
                  src={videoStreamUrl}
                  controls
                  autoPlay
                  className="w-full h-full"
                />
              </div>

              {/* Download Commands */}
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-gray-800/80">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-gray-300 font-medium">yt-dlp Command</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-gray-400 hover:text-white h-7"
                      onClick={() => navigator.clipboard.writeText(ytdlCommand)}
                    >
                      <Copy className="h-3.5 w-3.5 mr-1" />
                      Copy
                    </Button>
                  </div>
                  <code className="text-xs text-emerald-400 font-mono break-all">{ytdlCommand}</code>
                </div>

                <div className="p-3 rounded-lg bg-gray-800/80">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-gray-300 font-medium">Direct URL</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-gray-400 hover:text-white h-7"
                      onClick={() => navigator.clipboard.writeText(window.location.origin + videoStreamUrl)}
                    >
                      <Copy className="h-3.5 w-3.5 mr-1" />
                      Copy
                    </Button>
                  </div>
                  <code className="text-xs text-cyan-400 font-mono break-all">
                    {window.location.origin}{videoStreamUrl}
                  </code>
                </div>

                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    className="flex-1 border-gray-700 text-gray-300 hover:text-white hover:border-emerald-500"
                    onClick={() => {
                      const a = document.createElement('a');
                      a.href = videoStreamUrl;
                      a.download = 'video.mp4';
                      a.click();
                    }}
                  >
                    <Download className="mr-2 h-4 w-4" />
                    Download
                  </Button>
                  <Button
                    variant="outline"
                    className="flex-1 border-gray-700 text-gray-300 hover:text-white hover:border-cyan-500"
                    onClick={() => window.open(videoStreamUrl, '_blank')}
                  >
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Open in New Tab
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Recent Jobs */}
        {recentJobs.length > 0 && (
          <Card className="border-gray-800 bg-gray-900/80 backdrop-blur">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-gray-300 text-base">
                  <Clock className="h-4 w-4" />
                  Recent Jobs
                </CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-gray-400 hover:text-white h-7"
                  onClick={loadRecentJobs}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {recentJobs.map((j) => (
                  <div
                    key={j.jobId}
                    className="flex items-center gap-3 p-2 rounded-md hover:bg-gray-800/50 cursor-pointer transition-colors"
                    onClick={() => {
                      setJob(j);
                      setMpdUrl(j.mpdUrl);
                    }}
                  >
                    <div className={`h-2.5 w-2.5 rounded-full flex-shrink-0 ${statusColors[j.status]}`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-300 truncate">{j.mpdUrl}</p>
                      <p className="text-xs text-gray-500">
                        {j.status === 'done' && j.resolution ? `${j.resolution} • ` : ''}
                        {formatSize(j.videoSize)}
                      </p>
                    </div>
                    <Badge variant="outline" className="text-xs border-gray-700 text-gray-500">
                      {statusLabels[j.status]}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Footer */}
        <div className="mt-8 text-center text-xs text-gray-600">
          Widevine DRM Downloader • Requires CDM (.wvd) device file
        </div>
      </div>
    </div>
  );
}
