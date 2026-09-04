import { useEffect } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle } from "lucide-react";
import { Spinner } from "./Spinner";

/**
 * Shared confirmation modal for destructive, irreversible actions — deleting
 * an item, at minimum. Portaled to document.body, same pattern as
 * ImageLightbox, so it always sits above whatever card/layout it's
 * triggered from.
 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  isConfirming = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isConfirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isConfirming) onCancel();
    };
    window.addEventListener("keydown", onKeyDown);

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [isConfirming, onCancel]);

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-ink-900/80 p-4 backdrop-blur-sm animate-fade-up"
      onClick={(e) => {
        // Root of the portaled subtree — see ImageLightbox's backdrop for
        // why this needs its own stopPropagation rather than relying on the
        // inner content div's.
        e.stopPropagation();
        if (!isConfirming) onCancel();
      }}
      role="alertdialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-cream-300 bg-cream-50 p-5 shadow-lift"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-danger-100 text-danger-600">
            <AlertTriangle size={18} />
          </div>
          <div className="min-w-0">
            <h3 className="font-display text-base font-semibold text-ink-900">{title}</h3>
            {description && <p className="mt-1 text-sm text-ink-700/70">{description}</p>}
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={isConfirming}
            className="rounded-xl border border-cream-300 bg-cream-50 px-4 py-2 text-sm font-medium text-ink-800 hover:bg-cream-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={isConfirming}
            className="inline-flex items-center gap-2 rounded-xl bg-danger-500 px-4 py-2 text-sm font-semibold text-cream-50 shadow-soft hover:bg-danger-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isConfirming && <Spinner size={14} />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
