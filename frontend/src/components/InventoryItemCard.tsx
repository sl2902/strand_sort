import { Link } from "react-router-dom";
import { Badge } from "./Badge";
import { DietaryBadgeRow } from "./DietaryBadges";
import { ImageThumbnail } from "./ItemImages";
import { expiryBadgeContent } from "../lib/format";
import type { DonationItem } from "../lib/types";

/** Shared item card — Inventory list (grouped or sorted) and Expiring Soon. */
export function InventoryItemCard({ item, onImageRetry }: { item: DonationItem; onImageRetry: () => void }) {
  const expiryBadge = expiryBadgeContent(item.expiry_status, item.expiration_date);
  return (
    <Link
      to={`/inventory/${item.item_id}`}
      className="group flex min-w-0 gap-3 rounded-2xl border border-cream-300 bg-cream-50 p-4 shadow-soft transition-all hover:-translate-y-0.5 hover:shadow-lift"
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
    </Link>
  );
}
