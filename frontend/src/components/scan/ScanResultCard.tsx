import { useEffect, useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  XCircle,
  Image as ImageIcon,
  Video,
  Trash2,
  ChevronDown,
  RefreshCw,
} from "lucide-react";
import clsx from "clsx";
import { Spinner } from "../Spinner";
import { Badge } from "../Badge";
import { DietaryBadgeRow } from "../DietaryBadges";
import { ImageLightbox } from "../ImageLightbox";
import { expiryBadgeContent } from "../../lib/format";
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

function ToggleChevron({ expanded }: { expanded: boolean }) {
  return (
    <ChevronDown
      size={15}
      className={clsx("ml-auto shrink-0 text-ink-700/40 transition-transform", expanded && "rotate-180")}
    />
  );
}

export function ScanResultCard({
  entry,
  onDelete,
  onImageRetry,
}: {
  entry: ScanLogEntry;
  onDelete: () => void;
  /** Re-resolves this entry's image_urls/thumbnail_urls fresh from the
   * backend (GET /inventory/:id, falling back to the review queue for a
   * still-pending item) and updates the persisted entry with the result.
   * Undefined when there's no item_id to resolve against (e.g. a run that
   * never reached a settled item) — the placeholder then has no Refresh
   * affordance, matching there being nothing to refresh. Needed because
   * entry.item.image_urls/thumbnail_urls are presigned S3 URLs, snapshotted
   * at scan-completion time and persisted to localStorage — any such URL
   * left to sit past its ~1hr expiry 403s on the next page load, same
   * class of bug the Inventory/Review pages already solve by never
   * persisting a presigned URL, only resolving fresh on every read. */
  onImageRetry?: () => void;
}) {
  // previewUrl starts as a URL.createObjectURL(...) blob reference, which only
  // survives the page session that created it — ScanPage swaps it for a real
  // server URL once the scan completes and item.image_urls is available, but
  // pending/errored entries (and old localStorage entries from before that
  // swap happened) can still be dead blob refs. Fall back gracefully rather
  // than showing a broken <img>/<video> — there's nothing to retry against.
  const [previewFailed, setPreviewFailed] = useState(false);

  // A successful onImageRetry swaps entry.previewUrl for a freshly-resolved
  // one — reset the failed flag so the new URL gets a real chance to load
  // instead of staying stuck on the placeholder from the old one.
  useEffect(() => {
    setPreviewFailed(false);
  }, [entry.previewUrl]);

  // Set once, from whatever entry.status is at mount — deliberately NOT
  // recomputed on every render/status change. A card that's open because
  // it's still pending must stay open across the pending -> done/error
  // transition, even if that happens while the user is away on another tab;
  // otherwise the card appears to collapse "on its own" the moment they
  // return, with no action from them to explain it. Entries that are already
  // settled at mount time (e.g. reloaded from the store) start collapsed.
  const [isExpanded, setIsExpanded] = useState(entry.status === "pending");

  // Only opened when there are real server-side images to show (see
  // canEnlarge below) — a client-only blob preview isn't worth wiring
  // through resolveImageUrl, which doesn't handle blob: URLs.
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const hasPreview = !!entry.previewUrl && !previewFailed;
  // entry.kind records what the user originally captured, not what
  // entry.previewUrl currently points at — once a video scan completes,
  // runScan swaps previewUrl for a server-resolved frame thumbnail (an
  // IMAGE), but entry.kind stays "video" forever. Rendering that through
  // a <video> tag always fails (browsers can't decode a JPEG as video),
  // regardless of how fresh the URL is — which is why the Refresh button
  // never actually fixed this: a fresh image URL through a <video> tag
  // still fails the same way. Only a still-live blob: reference (the
  // original recorded clip, before the scan resolves) is an actual video.
  const isVideoPreview = entry.kind === "video" && !!entry.previewUrl?.startsWith("blob:");

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
      <div className="relative rounded-2xl border border-danger-400/50 bg-danger-100/60 px-4 py-3.5 pr-9 shadow-soft">
        <button
          type="button"
          onClick={() => setIsExpanded((v) => !v)}
          className="flex w-full items-start gap-3 text-left"
        >
          <XCircle size={20} className="mt-0.5 shrink-0 text-danger-600" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-danger-600">Couldn't scan {entry.label}</p>
            {!isExpanded && <p className="truncate text-xs text-ink-800/60">{entry.errorText}</p>}
          </div>
          <ToggleChevron expanded={isExpanded} />
        </button>
        {isExpanded && <p className="mt-1.5 pl-8 text-sm text-ink-800/80">{entry.errorText}</p>}
        <DeleteButton onDelete={onDelete} label={entry.label} />
      </div>
    );
  }

  const item = entry.item;
  const outcome =
    item?.requires_human_review === true ? "flagged" : item?.requires_human_review === false ? "committed" : "unknown";
  const style = outcomeStyles[outcome];
  const Icon = style.icon;
  const collapsedSubtitle = item?.product_name ?? entry.summary;
  const expiryBadge = item ? expiryBadgeContent(item.expiry_status, item.expiration_date) : null;
  // The server's own images (extracted frames, for video too) are what's
  // worth enlarging — the local blob preview is only ever a stand-in for
  // those until they're available.
  const enlargeableImages = item?.image_urls ?? [];
  const canEnlarge = hasPreview && enlargeableImages.length > 0;

  return (
    <div className={clsx("relative flex gap-3 rounded-2xl border px-4 py-3.5 pr-9 shadow-soft", style.ring)}>
      {hasPreview ? (
        isVideoPreview ? (
          <video
            src={entry.previewUrl}
            muted
            playsInline
            preload="metadata"
            onError={() => setPreviewFailed(true)}
            onClick={canEnlarge ? () => setLightboxIndex(0) : undefined}
            className={clsx(
              "h-14 w-14 shrink-0 rounded-xl border border-cream-300 object-cover",
              canEnlarge && "cursor-pointer"
            )}
          />
        ) : (
          <img
            src={entry.previewUrl}
            alt=""
            onError={() => setPreviewFailed(true)}
            onClick={canEnlarge ? () => setLightboxIndex(0) : undefined}
            className={clsx(
              "h-14 w-14 shrink-0 rounded-xl object-cover border border-cream-300",
              canEnlarge && "cursor-pointer"
            )}
          />
        )
      ) : (
        <div className="flex h-14 w-14 shrink-0 flex-col items-center justify-center gap-0.5 rounded-xl border border-cream-300 bg-cream-100 px-1 text-center text-ink-700/50">
          {entry.kind === "video" ? <Video size={16} /> : <ImageIcon size={16} />}
          {previewFailed && (
            <>
              <span className="text-[8px] leading-none">expired</span>
              {onImageRetry && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onImageRetry();
                  }}
                  className="flex items-center gap-0.5 text-[9px] font-medium text-terracotta-600 hover:text-terracotta-700"
                >
                  <RefreshCw size={9} />
                  Refresh
                </button>
              )}
            </>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="min-w-0 flex-1 text-left"
      >
        <div className="flex items-center gap-1.5">
          <Icon size={16} className={clsx("shrink-0", style.iconClass)} />
          <p className={clsx("text-sm font-semibold", style.iconClass)}>{style.heading}</p>
          <ToggleChevron expanded={isExpanded} />
        </div>

        {!isExpanded && collapsedSubtitle && (
          <p className="mt-0.5 truncate text-sm text-ink-800/80">{collapsedSubtitle}</p>
        )}

        {isExpanded &&
          (item ? (
            <div className="mt-1.5 space-y-1.5">
              <p className="font-display text-sm font-semibold leading-snug text-ink-900">{item.product_name}</p>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="neutral">{CATEGORY_LABELS[item.category]}</Badge>
                {expiryBadge && <Badge tone={expiryBadge.tone}>{expiryBadge.label}</Badge>}
                <Badge tone="neutral">×{item.quantity}</Badge>
              </div>
              {item.requires_human_review && item.review_reason && (
                <p className="text-xs text-saffron-700">{item.review_reason}</p>
              )}
              <DietaryBadgeRow flags={item.dietary_flags} fssaiSymbol={item.nutrition_facts.fssai_symbol_found} category={item.category} />
            </div>
          ) : (
            <p className="mt-1 whitespace-pre-wrap text-sm leading-snug text-ink-800/90">{entry.summary}</p>
          ))}
      </button>

      <DeleteButton onDelete={onDelete} label={entry.label} />

      {lightboxIndex !== null && enlargeableImages.length > 0 && (
        <ImageLightbox
          images={enlargeableImages}
          index={lightboxIndex}
          alt={item?.product_name ?? entry.label}
          onIndexChange={setLightboxIndex}
          onClose={() => setLightboxIndex(null)}
        />
      )}
    </div>
  );
}
