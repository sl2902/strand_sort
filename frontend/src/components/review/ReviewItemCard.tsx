import { useState } from "react";
import { AlertTriangle, CalendarCheck, Check, X, MessageSquarePlus } from "lucide-react";
import clsx from "clsx";
import type { DonationItem } from "../../lib/types";
import { CATEGORY_LABELS } from "../../lib/types";
import { Badge } from "../Badge";
import { DietaryBadgeRow } from "../DietaryBadges";
import { Spinner } from "../Spinner";
import { ImageGallery } from "../ItemImages";
import { formatDate } from "../../lib/format";

export function ReviewItemCard({
  item,
  isResolving,
  isLeaving,
  onApprove,
  onReject,
  onImageRetry,
}: {
  item: DonationItem;
  isResolving: boolean;
  isLeaving: boolean;
  onApprove: (correctedDate: string | null, notes: string | null) => void;
  onReject: (notes: string | null) => void;
  onImageRetry: () => void;
}) {
  const [correctingDate, setCorrectingDate] = useState(false);
  const [correctedDate, setCorrectedDate] = useState(item.expiration_date ?? "");
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState("");
  const [confirmingReject, setConfirmingReject] = useState(false);

  return (
    <div
      className={clsx(
        "overflow-hidden rounded-2xl border border-cream-300 bg-cream-50 p-5 shadow-soft transition-all",
        isLeaving && "animate-fade-out-collapse pointer-events-none"
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-terracotta-600">
            {CATEGORY_LABELS[item.category]}
          </p>
          <h3 className="mt-0.5 font-display text-lg font-semibold text-ink-900">{item.product_name}</h3>
        </div>
        <Badge tone="neutral">×{item.quantity}</Badge>
      </div>

      <div className="mt-3">
        <ImageGallery urls={item.image_urls} alt={item.product_name} onRetry={onImageRetry} />
      </div>

      <div className="mt-3 flex items-start gap-2 rounded-xl border border-saffron-400/50 bg-saffron-100/70 px-3.5 py-2.5 text-sm text-saffron-700">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        <p>{item.review_reason || "Flagged for review."}</p>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-700/70">
        <span>Raw date text: “{item.raw_date_text_found || "none"}”</span>
        <span aria-hidden>·</span>
        <span>Parsed: {formatDate(item.expiration_date)}</span>
      </div>

      <div className="mt-3">
        <DietaryBadgeRow flags={item.dietary_flags} fssaiSymbol={item.nutrition_facts.fssai_symbol_found} />
      </div>

      <div className="mt-4 space-y-3 border-t border-cream-200 pt-4">
        {correctingDate && (
          <div className="flex items-center gap-2 animate-fade-up">
            <CalendarCheck size={15} className="text-ink-700/50" />
            <input
              type="date"
              value={correctedDate}
              onChange={(e) => setCorrectedDate(e.target.value)}
              className="rounded-lg border border-cream-300 bg-cream-100 px-3 py-1.5 text-sm focus:border-terracotta-400 focus:outline-none focus:ring-2 focus:ring-terracotta-300/40"
            />
            <span className="text-xs text-ink-700/60">will be used on approval</span>
          </div>
        )}

        {showNotes && (
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional note for this decision…"
            rows={2}
            className="w-full animate-fade-up rounded-lg border border-cream-300 bg-cream-100 px-3 py-2 text-sm focus:border-terracotta-400 focus:outline-none focus:ring-2 focus:ring-terracotta-300/40"
          />
        )}

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => onApprove(correctingDate ? correctedDate || null : null, notes || null)}
            disabled={isResolving}
            className="inline-flex items-center gap-1.5 rounded-xl bg-success-500 px-4 py-2 text-sm font-semibold text-cream-50 shadow-soft hover:bg-success-600 disabled:opacity-60"
          >
            {isResolving ? <Spinner size={14} /> : <Check size={15} />}
            Approve
          </button>

          {!confirmingReject ? (
            <button
              onClick={() => setConfirmingReject(true)}
              disabled={isResolving}
              className="inline-flex items-center gap-1.5 rounded-xl border border-danger-400/50 bg-danger-100/60 px-4 py-2 text-sm font-semibold text-danger-600 hover:bg-danger-100 disabled:opacity-60"
            >
              <X size={15} />
              Reject
            </button>
          ) : (
            <div className="flex items-center gap-2 animate-fade-up">
              <span className="text-xs text-ink-700/70">Discard this item?</span>
              <button
                onClick={() => onReject(notes || null)}
                disabled={isResolving}
                className="rounded-lg bg-danger-500 px-3 py-1.5 text-xs font-semibold text-cream-50 hover:bg-danger-600 disabled:opacity-60"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirmingReject(false)}
                className="text-xs font-medium text-ink-700/60 hover:text-ink-900"
              >
                Cancel
              </button>
            </div>
          )}

          <button
            onClick={() => setCorrectingDate((v) => !v)}
            className="ml-auto text-xs font-medium text-ink-700/60 hover:text-ink-900"
          >
            {correctingDate ? "Cancel date fix" : "Correct date"}
          </button>
          <button
            onClick={() => setShowNotes((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-ink-700/60 hover:text-ink-900"
          >
            <MessageSquarePlus size={13} />
            {showNotes ? "Hide note" : "Add note"}
          </button>
        </div>
      </div>
    </div>
  );
}
