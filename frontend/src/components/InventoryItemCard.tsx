import { useState } from "react";
import { Link } from "react-router-dom";
import { X, Check } from "lucide-react";
import { Badge } from "./Badge";
import { DietaryBadgeRow } from "./DietaryBadges";
import { ImageThumbnail } from "./ItemImages";
import { ConfirmDialog } from "./ConfirmDialog";
import { Spinner } from "./Spinner";
import { expiryBadgeContent } from "../lib/format";
import { rejectItem, ApiError } from "../lib/api";
import { useToast } from "./Toast";
import type { DonationItem } from "../lib/types";

/** Shared item card — Inventory list (grouped or sorted) and Expiring Soon. */
export function InventoryItemCard({
  item,
  onImageRetry,
  onReject,
  linkTo,
  readOnly = false,
}: {
  item: DonationItem;
  onImageRetry: () => void;
  /** Called after a successful reject (expired items only) — the caller
   * owns re-fetching its own list so the removed item doesn't linger in a
   * stale cached view. */
  onReject?: () => void;
  /** Overrides the click-through target. Defaults to the live
   * /inventory/:id detail route; pass null to render a fully static,
   * non-interactive card instead (no Link at all). */
  linkTo?: string | null;
  /** True for read-only contexts that must never touch the live backend —
   * e.g. the /demo walkthrough, which reuses this same component to
   * display static fixture data. Hides Reject/Keep even for an item whose
   * expiry_status happens to be "expired" in the fixture. */
  readOnly?: boolean;
}) {
  const expiryBadge = expiryBadgeContent(item.expiry_status, item.expiration_date);
  const [confirmingReject, setConfirmingReject] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  // "Keep" has nothing to persist (no acknowledged-state field exists on
  // DonationItem) — this is a pure local dismiss of the action prompt, not
  // a change to the item itself. Resets on next fetch/remount, which is
  // fine: it's just clearing today's prompt, not recording a decision.
  const [kept, setKept] = useState(false);
  const { show } = useToast();

  const resolvedLinkTo = linkTo === undefined ? `/inventory/${item.item_id}` : linkTo;
  const showExpiredActions = item.expiry_status === "expired" && !readOnly && !kept;

  const handleReject = async () => {
    setRejecting(true);
    try {
      await rejectItem(item.item_id);
      show(`${item.product_name} rejected.`, "success");
      setConfirmingReject(false);
      onReject?.();
    } catch (err) {
      show(err instanceof ApiError ? err.message : "Couldn't reject this item.", "error");
    } finally {
      setRejecting(false);
    }
  };

  const cardBody = (
    <>
      <ImageThumbnail
        url={item.thumbnail_urls[0] ?? item.image_urls[0]}
        images={item.image_urls}
        alt={item.product_name}
        onRetry={onImageRetry}
        size="h-16 w-16 sm:h-20 sm:w-20"
      />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-2 min-w-0 font-display text-base font-semibold leading-snug text-ink-900 group-hover:text-terracotta-600">
            {item.product_name}
          </h3>
          <span className="shrink-0 rounded-full bg-cream-200 px-2.5 py-1 text-xs font-bold text-ink-800">
            ×{item.quantity}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={expiryBadge.tone}>{expiryBadge.label}</Badge>
          {item.requires_human_review && <Badge tone="danger">Needs review</Badge>}
        </div>
        <DietaryBadgeRow flags={item.dietary_flags} fssaiSymbol={item.nutrition_facts.fssai_symbol_found} />
      </div>

      {showExpiredActions && (
        <div className="absolute right-2 top-2 flex items-center gap-1">
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setKept(true);
            }}
            aria-label={`Keep ${item.product_name} despite expiry`}
            title="Keep — dismiss this prompt"
            className="rounded-full p-1.5 text-ink-700/40 transition-colors hover:bg-success-100 hover:text-success-600"
          >
            <Check size={13} />
          </button>
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setConfirmingReject(true);
            }}
            aria-label={`Reject ${item.product_name}`}
            title="Reject — remove from inventory"
            className="rounded-full p-1.5 text-ink-700/40 transition-colors hover:bg-danger-100 hover:text-danger-600"
          >
            {rejecting ? <Spinner size={13} /> : <X size={13} />}
          </button>
        </div>
      )}

      {confirmingReject && showExpiredActions && (
        <ConfirmDialog
          title={`Reject ${item.product_name}?`}
          description="This item is expired. Rejecting removes it from inventory — this can't be undone."
          confirmLabel="Reject"
          isConfirming={rejecting}
          onConfirm={handleReject}
          onCancel={() => setConfirmingReject(false)}
        />
      )}
    </>
  );

  const className =
    "group relative flex min-w-0 gap-3 rounded-2xl border border-cream-300 bg-cream-50 p-4 pr-9 shadow-soft transition-all hover:-translate-y-0.5 hover:shadow-lift";

  if (resolvedLinkTo === null) {
    return <div className={className}>{cardBody}</div>;
  }

  return (
    <Link to={resolvedLinkTo} className={className}>
      {cardBody}
    </Link>
  );
}
