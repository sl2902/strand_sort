import { useState } from "react";
import { CheckCircle2, AlertTriangle, HelpCircle, XCircle, Image as ImageIcon, Video, Trash2 } from "lucide-react";
import clsx from "clsx";
import { Spinner } from "../Spinner";
import { Badge } from "../Badge";
import { DietaryBadgeRow } from "../DietaryBadges";
import { formatDate, expiryUrgency } from "../../lib/format";
import { CATEGORY_LABELS, type DonationItem } from "../../lib/types";

export interface ScanLogEntry {
  id: string;
  kind: "photo" | "video";
  label: string;
  previewUrl?: string;
  status: "pending" | "done" | "error";
  /** Agent's prose summary — only shown as a fallback when `item` is null
   * (a "done" run that never reached a settled item). */
  summary?: string;
  /** Full structured result, once available. Null if the run never reached
   * a settled item (e.g. a hard failure before extraction completed). */
  item?: DonationItem | null;
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

function DeleteButton({ onDelete, label }: { onDelete: () => void; label: string }) {
  return (
    <button
      onClick={onDelete}
      aria-label={`Remove ${label} from log`}
      title="Remove from log"
      className="absolute right-2 top-2 rounded-full p-1.5 text-ink-700/40 transition-colors hover:bg-cream-200 hover:text-ink-900"
    >
      <Trash2 size={13} />
    </button>
  );
}

export function ScanResultCard({ entry, onDelete }: { entry: ScanLogEntry; onDelete: () => void }) {
  // previewUrl starts as a URL.createObjectURL(...) blob reference, which only
  // survives the page session that created it — ScanPage swaps it for a real
  // server URL once the scan completes and item.image_urls is available, but
  // pending/errored entries (and old localStorage entries from before that
  // swap happened) can still be dead blob refs. Fall back gracefully rather
  // than showing a broken <img>/<video> — there's nothing to retry against.
  const [previewFailed, setPreviewFailed] = useState(false);
  const hasPreview = !!entry.previewUrl && !previewFailed;

  if (entry.status === "pending") {
    return (
      <div className="relative flex items-center gap-3 rounded-2xl border border-cream-300 bg-cream-50 px-4 py-3.5 shadow-soft">
        <Spinner className="text-terracotta-500" />
        <div>
          <p className="text-sm font-medium text-ink-800">Scanning {entry.label}…</p>
          <p className="text-xs text-ink-700/60">
            {entry.kind === "video" ? "Sampling frames and reading the label" : "Analyzing packaging"}
          </p>
        </div>
        <DeleteButton onDelete={onDelete} label={entry.label} />
      </div>
    );
  }

  if (entry.status === "error") {
    return (
      <div className="relative flex items-start gap-3 rounded-2xl border border-danger-400/50 bg-danger-100/60 px-4 py-3.5 pr-9 shadow-soft animate-pop-in">
        <XCircle size={20} className="mt-0.5 shrink-0 text-danger-600" />
        <div>
          <p className="text-sm font-semibold text-danger-600">Couldn't scan {entry.label}</p>
          <p className="mt-0.5 text-sm text-ink-800/80">{entry.errorText}</p>
        </div>
        <DeleteButton onDelete={onDelete} label={entry.label} />
      </div>
    );
  }

  const item = entry.item;
  const outcome =
    item?.requires_human_review === true ? "flagged" : item?.requires_human_review === false ? "committed" : "unknown";
  const style = outcomeStyles[outcome];
  const Icon = style.icon;
  const urgency = item ? expiryUrgency(item.expiration_date) : "unknown";

  return (
    <div className={clsx("relative flex gap-3 rounded-2xl border px-4 py-3.5 pr-9 shadow-soft animate-pop-in", style.ring)}>
      {hasPreview ? (
        entry.kind === "video" ? (
          <video
            src={entry.previewUrl}
            muted
            playsInline
            preload="metadata"
            onError={() => setPreviewFailed(true)}
            className="h-14 w-14 shrink-0 rounded-xl border border-cream-300 object-cover"
          />
        ) : (
          <img
            src={entry.previewUrl}
            alt=""
            onError={() => setPreviewFailed(true)}
            className="h-14 w-14 shrink-0 rounded-xl object-cover border border-cream-300"
          />
        )
      ) : (
        <div className="flex h-14 w-14 shrink-0 flex-col items-center justify-center gap-0.5 rounded-xl border border-cream-300 bg-cream-100 text-ink-700/50">
          {entry.kind === "video" ? <Video size={18} /> : <ImageIcon size={18} />}
          {previewFailed && <span className="text-[8px] leading-none">expired</span>}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <Icon size={16} className={clsx("shrink-0", style.iconClass)} />
          <p className={clsx("text-sm font-semibold", style.iconClass)}>{style.heading}</p>
        </div>

        {item ? (
          <div className="mt-1.5 space-y-1.5">
            <p className="font-display text-sm font-semibold leading-snug text-ink-900">{item.product_name}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone="neutral">{CATEGORY_LABELS[item.category]}</Badge>
              <Badge tone={urgency === "expired" ? "danger" : urgency === "soon" ? "saffron" : "neutral"}>
                {urgency === "expired" ? "Expired" : "Expires"} {formatDate(item.expiration_date)}
              </Badge>
              <Badge tone="neutral">×{item.quantity}</Badge>
            </div>
            {item.requires_human_review && item.review_reason && (
              <p className="text-xs text-saffron-700">{item.review_reason}</p>
            )}
            <DietaryBadgeRow flags={item.dietary_flags} />
          </div>
        ) : (
          <p className="mt-1 whitespace-pre-wrap text-sm leading-snug text-ink-800/90">{entry.summary}</p>
        )}
      </div>
      <DeleteButton onDelete={onDelete} label={entry.label} />
    </div>
  );
}
