import { useEffect, useMemo, useState } from "react";
import { PartyPopper, AlarmClock } from "lucide-react";
import { listInventory, ApiError } from "../lib/api";
import type { DonationItem } from "../lib/types";
import { byExpirationDateAscending } from "../lib/format";
import { InventoryItemCard } from "../components/InventoryItemCard";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/Toast";

export function ExpiringSoonPage() {
  const [items, setItems] = useState<DonationItem[] | null>(null);
  const { show } = useToast();

  const load = () => {
    listInventory()
      .then(setItems)
      .catch((err) => show(err instanceof ApiError ? err.message : "Couldn't load inventory.", "error"));
  };

  useEffect(load, [show]);

  const urgent = useMemo(() => {
    if (!items) return [];
    return items
      .filter((item) => item.expiry_status === "expired" || item.expiry_status === "near_expiry")
      .sort(byExpirationDateAscending);
  }, [items]);

  const expiredCount = urgent.filter((i) => i.expiry_status === "expired").length;
  const nearExpiryCount = urgent.length - expiredCount;

  return (
    <div className="space-y-6">
      <div className="animate-fade-up">
        <p className="text-sm font-semibold uppercase tracking-wide text-terracotta-600">Inventory</p>
        <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">Expiring soon</h1>
        <p className="mt-2 text-ink-700/70">
          {items === null
            ? "Loading…"
            : urgent.length === 0
              ? "Nothing needs attention right now."
              : `${expiredCount > 0 ? `${expiredCount} expired, ` : ""}${nearExpiryCount} expiring within the week — soonest first.`}
        </p>
      </div>

      {items === null && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton h-32 rounded-2xl" />
          ))}
        </div>
      )}

      {items !== null && urgent.length === 0 && (
        <EmptyState
          icon={<PartyPopper size={24} />}
          title="All clear"
          description="Nothing in stock is expired or expiring within the week — nice work."
        />
      )}

      {items !== null && urgent.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {urgent.map((item) => (
            <InventoryItemCard key={item.item_id} item={item} onImageRetry={load} onReject={load} />
          ))}
        </div>
      )}

      {items !== null && urgent.length === 0 && (
        <div className="flex items-center justify-center gap-2 pt-4 text-xs text-ink-700/40">
          <AlarmClock size={13} />
          Items within a week of their expiry date will show up here automatically.
        </div>
      )}
    </div>
  );
}
