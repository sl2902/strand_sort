import { useState } from "react";
import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { Badge } from "./Badge";
import { DietaryBadgeRow } from "./DietaryBadges";
import { ImageThumbnail } from "./ItemImages";
import { ConfirmDialog } from "./ConfirmDialog";
import { Spinner } from "./Spinner";
import { expiryBadgeContent } from "../lib/format";
import { deleteItem, ApiError } from "../lib/api";
import { useToast } from "./Toast";
import type { DonationItem } from "../lib/types";

/** Shared item card — Inventory list (grouped or sorted) and Expiring Soon. */
export function InventoryItemCard({
  item,
  onImageRetry,
  onDelete,
}: {
  item: DonationItem;
  onImageRetry: () => void;
  /** Called after a successful delete — the caller owns re-fetching its own
   * list so the removed item doesn't linger in a stale cached view. */
  onDelete?: () => void;
}) {
  const expiryBadge = expiryBadgeContent(item.expiry_status, item.expiration_date);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { show } = useToast();

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteItem(item.item_id);
      show(`${item.product_name} deleted.`, "success");
      setConfirmingDelete(false);
      onDelete?.();
    } catch (err) {
      show(err instanceof ApiError ? err.message : "Couldn't delete this item.", "error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Link
      to={`/inventory/${item.item_id}`}
      className="group relative flex min-w-0 gap-3 rounded-2xl border border-cream-300 bg-cream-50 p-4 pr-9 shadow-soft transition-all hover:-translate-y-0.5 hover:shadow-lift"
    >
      <ImageThumbnail
        url={item.image_urls[0]}
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

      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setConfirmingDelete(true);
        }}
        aria-label={`Delete ${item.product_name}`}
        title="Delete from inventory"
        className="absolute right-2 top-2 rounded-full p-1.5 text-ink-700/40 transition-colors hover:bg-danger-100 hover:text-danger-600"
      >
        {deleting ? <Spinner size={13} /> : <Trash2 size={13} />}
      </button>

      {confirmingDelete && (
        <ConfirmDialog
          title={`Delete ${item.product_name}?`}
          description="This can't be undone — the item and its record will be permanently removed from inventory."
          confirmLabel="Delete"
          isConfirming={deleting}
          onConfirm={handleDelete}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </Link>
  );
}
