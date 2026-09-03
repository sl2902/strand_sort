import { useState, useEffect } from "react";
import { Camera, Video as VideoIcon, Trash2 } from "lucide-react";
import clsx from "clsx";
import { PhotoScanPanel } from "../components/scan/PhotoScanPanel";
import { VideoScanPanel } from "../components/scan/VideoScanPanel";
import { ScanResultCard, type ScanLogEntry } from "../components/scan/ScanResultCard";
import { ScanProgress } from "../components/Spinner";
import { intakeImage, intakeVideo, resolveImageUrl, ApiError } from "../lib/api";
import type { IntakeResponse } from "../lib/types";
import { useToast } from "../components/Toast";
import { loadScanLog, saveScanLog, patchScanLogEntry } from "../lib/scanLog";

const PHOTO_MESSAGES = [
  "Reading the label…",
  "Checking the expiry date…",
  "Scanning for dietary symbols…",
  "Cross-checking against existing stock…",
];
const VIDEO_MESSAGES = [
  "Sampling the sharpest frames from your clip…",
  "Reading the label across angles…",
  "Checking the expiry date…",
  "Cross-checking against existing stock…",
];

let nextId = 1;

export function ScanPage({ onScanComplete }: { onScanComplete: () => void }) {
  const [mode, setMode] = useState<"photo" | "video">("photo");
  const [log, setLog] = useState<ScanLogEntry[]>(() => loadScanLog());
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { show } = useToast();

  useEffect(() => {
    saveScanLog(log);
  }, [log]);

  const handleDeleteEntry = (id: string) => {
    setLog((prev) => prev.filter((e) => e.id !== id));
  };

  const runScan = async (
    kind: "photo" | "video",
    label: string,
    previewUrl: string | undefined,
    call: () => Promise<IntakeResponse>
  ) => {
    const id = `scan-${nextId++}`;
    setLog((prev) => [{ id, kind, label, previewUrl, status: "pending" }, ...prev]);
    try {
      const { summary, item } = await call();
      // Prefer the server's persistent URL over the local blob preview — the
      // blob doesn't survive a page reload (see scanLog persistence), but a
      // real image_urls entry does.
      const persistentPreviewUrl = item?.image_urls[0] ? resolveImageUrl(item.image_urls[0]) : undefined;
      if (persistentPreviewUrl && previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
      const patch: Partial<ScanLogEntry> = {
        status: "done",
        summary,
        item,
        ...(persistentPreviewUrl ? { previewUrl: persistentPreviewUrl } : {}),
      };
      // The scan keeps running server-side even if the user navigates away
      // from this page before it resolves — setLog alone would land on an
      // unmounted component and silently no-op, stranding the entry at
      // "pending" forever. Write straight to localStorage so it's durable
      // regardless of whether ScanPage is still mounted when this fires.
      patchScanLogEntry(id, patch);
      setLog((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong during the scan.";
      patchScanLogEntry(id, { status: "error", errorText: message });
      setLog((prev) => prev.map((e) => (e.id === id ? { ...e, status: "error", errorText: message } : e)));
      show(message, "error");
    } finally {
      onScanComplete();
    }
  };

  const handlePhotoSubmit = async (files: File[]) => {
    setIsSubmitting(true);
    const previewUrl = URL.createObjectURL(files[0]);
    const label = files.length === 1 ? files[0].name : `${files.length} photos`;
    await runScan("photo", label, previewUrl, () => intakeImage(files));
    setIsSubmitting(false);
  };

  const handleVideoSubmit = async (blob: Blob, filename: string) => {
    setIsSubmitting(true);
    const previewUrl = URL.createObjectURL(blob);
    await runScan("video", filename, previewUrl, () => intakeVideo(blob, filename));
    setIsSubmitting(false);
  };

  return (
    <div className="space-y-8">
      <div className="animate-fade-up">
        <p className="text-sm font-semibold uppercase tracking-wide text-terracotta-600">Intake</p>
        <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">Scan a donation</h1>
        <p className="mt-2 max-w-xl text-ink-700/70">
          Photograph or film each item — we'll read the label, check the expiry date, and either add it
          straight to stock or flag it for a quick human look.
        </p>
      </div>

      <div className="rounded-3xl border border-cream-300 bg-cream-50/70 p-4 shadow-soft sm:p-6">
        <div className="mb-5 inline-flex rounded-xl bg-cream-200/70 p-1 text-sm">
          {(
            [
              { key: "photo", label: "Photo", icon: Camera },
              { key: "video", label: "Video", icon: VideoIcon },
            ] as const
          ).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setMode(key)}
              className={clsx(
                "flex items-center gap-1.5 rounded-lg px-4 py-1.5 font-medium transition-colors",
                mode === key ? "bg-cream-50 text-ink-900 shadow-soft" : "text-ink-700/70 hover:text-ink-900"
              )}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>

        {isSubmitting ? (
          <ScanProgress messages={mode === "photo" ? PHOTO_MESSAGES : VIDEO_MESSAGES} />
        ) : mode === "photo" ? (
          <PhotoScanPanel disabled={isSubmitting} onSubmit={handlePhotoSubmit} />
        ) : (
          <VideoScanPanel disabled={isSubmitting} onSubmit={handleVideoSubmit} />
        )}
      </div>

      {log.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-700/60">This session</h2>
            <button
              onClick={() => setLog([])}
              className="flex items-center gap-1 text-xs font-medium text-ink-700/50 hover:text-ink-900"
            >
              <Trash2 size={13} />
              Clear
            </button>
          </div>
          <div className="max-h-[32rem] space-y-2.5 overflow-y-auto pr-1">
            {log.map((entry) => (
              <ScanResultCard key={entry.id} entry={entry} onDelete={() => handleDeleteEntry(entry.id)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
