import { useEffect, useMemo, useState } from "react";
import { Search, Boxes, PackageSearch, LayoutGrid, ArrowDownWideNarrow } from "lucide-react";
import clsx from "clsx";
import { listInventory, ApiError } from "../lib/api";
import { CATEGORIES, CATEGORY_LABELS, type DonationItem } from "../lib/types";
import { EmptyState } from "../components/EmptyState";
import { InventoryItemCard } from "../components/InventoryItemCard";
import { byExpirationDateAscending } from "../lib/format";
import { useToast } from "../components/Toast";

export function InventoryPage() {
  const [items, setItems] = useState<DonationItem[] | null>(null);
  const [search, setSearch] = useState("");
  const [activeCategories, setActiveCategories] = useState<Set<string>>(new Set());
  const [sortMode, setSortMode] = useState<"category" | "expiry">("category");
  const { show } = useToast();

  const load = () => {
    listInventory()
      .then(setItems)
      .catch((err) => show(err instanceof ApiError ? err.message : "Couldn't load inventory.", "error"));
  };

  useEffect(load, [show]);

  const toggleCategory = (c: string) =>
    setActiveCategories((prev) => {
      const next = new Set(prev);
      next.has(c) ? next.delete(c) : next.add(c);
      return next;
    });

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      const matchesSearch = !q || item.product_name.toLowerCase().includes(q);
      const matchesCategory = activeCategories.size === 0 || activeCategories.has(item.category);
      return matchesSearch && matchesCategory;
    });
  }, [items, search, activeCategories]);

  const grouped = useMemo(() => {
    const byCategory = new Map<string, DonationItem[]>();
    for (const item of filtered) {
      const bucket = byCategory.get(item.category) ?? [];
      bucket.push(item);
      byCategory.set(item.category, bucket);
    }
    for (const bucket of byCategory.values()) {
      bucket.sort(byExpirationDateAscending);
    }
    return CATEGORIES.filter((c) => byCategory.has(c)).map((c) => ({ category: c, items: byCategory.get(c)! }));
  }, [filtered]);

  const sortedByExpiry = useMemo(() => [...filtered].sort(byExpirationDateAscending), [filtered]);

  const presentCategories = useMemo(() => {
    if (!items) return [];
    return CATEGORIES.filter((c) => items.some((i) => i.category === c));
  }, [items]);

  return (
    <div className="space-y-6">
      <div className="animate-fade-up">
        <p className="text-sm font-semibold uppercase tracking-wide text-terracotta-600">Inventory</p>
        <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">Browse stock</h1>
        <p className="mt-2 text-ink-700/70">{items ? `${items.length} item batch${items.length === 1 ? "" : "es"} on hand` : "Loading…"}</p>
      </div>

      <div className="space-y-3">
        <div className="relative">
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-700/40" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by product name…"
            className="w-full rounded-xl border border-cream-300 bg-cream-50 py-2.5 pl-10 pr-4 text-sm focus:border-terracotta-400 focus:outline-none focus:ring-2 focus:ring-terracotta-300/40"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          {presentCategories.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setActiveCategories(new Set())}
                className={clsx(
                  "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  activeCategories.size === 0
                    ? "border-terracotta-500 bg-terracotta-500 text-cream-50"
                    : "border-cream-300 bg-cream-50 text-ink-700 hover:border-terracotta-300"
                )}
              >
                All
              </button>
              {presentCategories.map((c) => (
                <button
                  key={c}
                  onClick={() => toggleCategory(c)}
                  className={clsx(
                    "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    activeCategories.has(c)
                      ? "border-terracotta-500 bg-terracotta-500 text-cream-50"
                      : "border-cream-300 bg-cream-50 text-ink-700 hover:border-terracotta-300"
                  )}
                >
                  {CATEGORY_LABELS[c]}
                </button>
              ))}
            </div>
          ) : (
            <div />
          )}

          <div className="inline-flex shrink-0 rounded-xl bg-cream-200/70 p-1 text-xs">
            <button
              onClick={() => setSortMode("category")}
              className={clsx(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition-colors",
                sortMode === "category" ? "bg-cream-50 text-ink-900 shadow-soft" : "text-ink-700/70 hover:text-ink-900"
              )}
            >
              <LayoutGrid size={13} />
              By category
            </button>
            <button
              onClick={() => setSortMode("expiry")}
              className={clsx(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition-colors",
                sortMode === "expiry" ? "bg-cream-50 text-ink-900 shadow-soft" : "text-ink-700/70 hover:text-ink-900"
              )}
            >
              <ArrowDownWideNarrow size={13} />
              Soonest expiring
            </button>
          </div>
        </div>
      </div>

      {items === null && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton h-32 rounded-2xl" />
          ))}
        </div>
      )}

      {items !== null && items.length === 0 && (
        <EmptyState
          icon={<Boxes size={24} />}
          title="No inventory yet"
          description="Committed donations will show up here once they've been scanned in."
        />
      )}

      {items !== null && items.length > 0 && filtered.length === 0 && (
        <EmptyState
          icon={<PackageSearch size={24} />}
          title="No matches"
          description="Try a different search term or clear the category filters."
        />
      )}

      {items !== null && filtered.length > 0 && sortMode === "expiry" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sortedByExpiry.map((item) => (
            <InventoryItemCard key={item.item_id} item={item} onImageRetry={load} />
          ))}
        </div>
      )}

      {items !== null && filtered.length > 0 && sortMode === "category" && (
        <div className="space-y-8">
          {grouped.map(({ category, items: categoryItems }) => (
            <section key={category} className="animate-fade-up">
              <div className="mb-3 flex items-baseline gap-2">
                <h2 className="font-display text-lg font-semibold text-ink-900">{CATEGORY_LABELS[category]}</h2>
                <span className="text-xs text-ink-700/50">{categoryItems.length}</span>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {categoryItems.map((item) => (
                  <InventoryItemCard key={item.item_id} item={item} onImageRetry={load} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
