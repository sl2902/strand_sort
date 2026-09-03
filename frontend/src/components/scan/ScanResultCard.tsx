import { CheckCircle2, AlertTriangle, HelpCircle, XCircle, Image as ImageIcon, Video } from "lucide-react";
import clsx from "clsx";
import { Spinner } from "../Spinner";
import { classifyScanResult } from "../../lib/format";

export interface ScanLogEntry {
  id: string;
  kind: "photo" | "video";
  label: string;
  previewUrl?: string;
  status: "pending" | "done" | "error";
  resultText?: string;
  errorText?: string;
}

const outcomeStyles = {
  committed: {
    icon: CheckCircle2,
    ring: "border-success-400/50 bg-success-100/70",
    iconClass: "text-success-600",
    heading: "Committed to inventory",
  },
  flagged: {
    icon: AlertTriangle,
    ring: "border-saffron-400/50 bg-saffron-100/70",
    iconClass: "text-saffron-600",
    heading: "Flagged for review",
  },
  unknown: {
    icon: HelpCircle,
    ring: "border-cream-300 bg-cream-50",
    iconClass: "text-ink-700",
    heading: "Scan complete",
  },
} as const;

export function ScanResultCard({ entry }: { entry: ScanLogEntry }) {
  if (entry.status === "pending") {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-cream-300 bg-cream-50 px-4 py-3.5 shadow-soft">
        <Spinner className="text-terracotta-500" />
        <div>
          <p className="text-sm font-medium text-ink-800">Scanning {entry.label}…</p>
          <p className="text-xs text-ink-700/60">
            {entry.kind === "video" ? "Sampling frames and reading the label" : "Analyzing packaging"}
          </p>
        </div>
      </div>
    );
  }

  if (entry.status === "error") {
    return (
      <div className="flex items-start gap-3 rounded-2xl border border-danger-400/50 bg-danger-100/60 px-4 py-3.5 shadow-soft animate-pop-in">
        <XCircle size={20} className="mt-0.5 shrink-0 text-danger-600" />
        <div>
          <p className="text-sm font-semibold text-danger-600">Couldn't scan {entry.label}</p>
          <p className="mt-0.5 text-sm text-ink-800/80">{entry.errorText}</p>
        </div>
      </div>
    );
  }

  const outcome = classifyScanResult(entry.resultText ?? "");
  const style = outcomeStyles[outcome];
  const Icon = style.icon;

  return (
    <div className={clsx("animate-pop-in flex gap-3 rounded-2xl border px-4 py-3.5 shadow-soft", style.ring)}>
      {entry.previewUrl ? (
        entry.kind === "video" ? (
          <video
            src={entry.previewUrl}
            muted
            playsInline
            preload="metadata"
            className="h-14 w-14 shrink-0 rounded-xl border border-cream-300 object-cover"
          />
        ) : (
          <img
            src={entry.previewUrl}
            alt=""
            className="h-14 w-14 shrink-0 rounded-xl object-cover border border-cream-300"
          />
        )
      ) : (
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl border border-cream-300 bg-cream-100 text-ink-700/50">
          {entry.kind === "video" ? <Video size={20} /> : <ImageIcon size={20} />}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <Icon size={16} className={clsx("shrink-0", style.iconClass)} />
          <p className={clsx("text-sm font-semibold", style.iconClass)}>{style.heading}</p>
        </div>
        <p className="mt-1 whitespace-pre-wrap text-sm leading-snug text-ink-800/90">{entry.resultText}</p>
      </div>
    </div>
  );
}
