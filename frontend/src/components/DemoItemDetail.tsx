import type { ReactNode } from "react";
import { PackageMinus, X, Check, Info } from "lucide-react";
import { CATEGORY_LABELS, type DonationItem } from "../lib/types";
import { Badge } from "./Badge";
import { DietaryDetailList } from "./DietaryBadges";
import { SourceTag } from "./SourceTag";
import { FssaiMark } from "./FssaiMark";
import { ImageGallery } from "./ItemImages";
import { formatDate, expiryBadgeContent } from "../lib/format";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-cream-300 bg-cream-50 p-5 shadow-soft">
      <h2 className="mb-4 font-display text-base font-semibold text-ink-900">{title}</h2>
      {children}
    </section>
  );
}

function StatRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 text-sm">
      <span className="text-ink-700/70">{label}</span>
      <span className="font-medium text-ink-900">{value}</span>
    </div>
  );
}

/**
 * Full item-detail rendering, shared by two demo-only call sites:
 * DemoItemPage (the standalone /demo/item/:itemId route, reached by
 * manually clicking a card) and DemoPage's own "inventory-detail" step
 * (rendered inline during Play's auto-advance, no navigation involved —
 * same fixture object already held in memory, no re-fetch). Both feed it
 * a DonationItem that's already fixture data with zero live API calls;
 * this component itself never fetches anything.
 *
 * Every action button here is visible but permanently disabled — this is
 * a read-only view of a static fixture, not live inventory, so nothing
 * should be wired to a real (or fake) mutation. Mirrors whichever actions
 * the real detail view would show for this item's actual expiry_status —
 * Checkout always, Reject/Commit only if the fixture happens to be
 * "expired" — so a viewer sees the same UI shape the real app would show,
 * just inert.
 */
export function DemoItemDetail({ item }: { item: DonationItem }) {
  const expiryBadge = expiryBadgeContent(item.expiry_status, item.expiration_date);
  const isExpired = item.expiry_status === "expired";
  const { dietary_flags, nutrition_facts } = item;

  return (
    <div className="space-y-6">
      <div className="animate-fade-up flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-terracotta-600">
            {CATEGORY_LABELS[item.category]}
          </p>
          <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">{item.product_name}</h1>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge tone={expiryBadge.tone}>{expiryBadge.label}</Badge>
            <Badge tone="neutral">×{item.quantity} in stock</Badge>
          </div>
        </div>
      </div>

      {isExpired && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-danger-400/50 bg-danger-100/60 px-4 py-3.5 text-sm text-danger-700">
          <span>This item is expired. Disabled in demo mode — reject/commit aren't wired to any action here.</span>
          <div className="flex items-center gap-2">
            <button
              disabled
              title="Disabled in demo mode"
              className="inline-flex items-center gap-1.5 rounded-xl border border-cream-300 bg-cream-50 px-3 py-1.5 text-xs font-medium text-ink-800 shadow-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Check size={13} />
              Commit
            </button>
            <button
              disabled
              title="Disabled in demo mode"
              className="inline-flex items-center gap-1.5 rounded-xl border border-danger-400/50 bg-danger-100/60 px-3 py-1.5 text-xs font-medium text-danger-600 shadow-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              <X size={13} />
              Reject
            </button>
          </div>
        </div>
      )}

      {item.requires_human_review && item.review_reason && (
        <div className="flex items-start gap-2 rounded-2xl border border-saffron-400/50 bg-saffron-100/70 px-4 py-3 text-sm text-saffron-700">
          <Info size={16} className="mt-0.5 shrink-0" />
          <p>{item.review_reason}</p>
        </div>
      )}

      <div className="animate-fade-up">
        <ImageGallery urls={item.image_urls} thumbnailUrls={item.thumbnail_urls} alt={item.product_name} />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Section title="Dates">
          <StatRow label="Raw text on package" value={item.raw_date_text_found || "—"} />
          <StatRow label="Parsed expiry" value={formatDate(item.expiration_date)} />
          <StatRow
            label="Date confidence"
            value={
              <Badge tone={item.date_confidence === "high" ? "success" : "saffron"}>
                {item.date_confidence ?? "unknown"}
              </Badge>
            }
          />
        </Section>

        <Section title="Dietary flags">
          <DietaryDetailList flags={dietary_flags} fssaiSymbol={nutrition_facts.fssai_symbol_found} />
        </Section>

        <Section title="Nutrition facts">
          <StatRow label="Serving size" value={nutrition_facts.serving_size ?? "—"} />
          <StatRow label="Sugars" value={nutrition_facts.sugars_g != null ? `${nutrition_facts.sugars_g} g` : "—"} />
          <StatRow label="Sodium" value={nutrition_facts.sodium_mg != null ? `${nutrition_facts.sodium_mg} mg` : "—"} />
          <StatRow label="Protein" value={nutrition_facts.protein_g != null ? `${nutrition_facts.protein_g} g` : "—"} />
          <div className="flex items-center justify-between gap-3 py-2 text-sm">
            <span className="text-ink-700/70">Confidence</span>
            <span className="flex items-center gap-2">
              <Badge tone={nutrition_facts.nutrition_confidence === "high" ? "success" : "saffron"}>
                {nutrition_facts.nutrition_confidence}
              </Badge>
              <SourceTag source={nutrition_facts.panel_found ? "printed_panel" : "inferred"} />
            </span>
          </div>
          {nutrition_facts.raw_nutrition_text_found && (
            <p className="mt-3 rounded-lg bg-cream-100 px-3 py-2 font-mono text-xs text-ink-700/80">
              “{nutrition_facts.raw_nutrition_text_found}”
            </p>
          )}
          <StatRow
            label="FSSAI symbol"
            value={
              <span className="flex items-center gap-2">
                <FssaiMark symbol={nutrition_facts.fssai_symbol_found} size={20} />
                {nutrition_facts.fssai_symbol_found.replace("_", " ")}
              </span>
            }
          />
        </Section>

        <Section title="Distribute">
          <div className="flex items-center gap-3">
            <PackageMinus size={18} className="text-ink-700/50" />
            <input
              type="number"
              value={1}
              disabled
              className="w-24 rounded-lg border border-cream-300 bg-cream-100 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            />
            <button
              disabled
              title="Disabled in demo mode"
              className="inline-flex items-center gap-2 rounded-xl bg-terracotta-500 px-4 py-2 text-sm font-semibold text-cream-50 shadow-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              <PackageMinus size={15} />
              Check out
            </button>
          </div>
          <p className="mt-3 flex items-start gap-1.5 text-xs text-ink-700/60">
            <Info size={13} className="mt-0.5 shrink-0" />
            Disabled in demo mode — this is a static fixture, not live inventory.
          </p>
        </Section>

        <div className="flex items-center gap-2 text-xs text-ink-700/40 lg:col-span-2">
          Item ID: <span className="font-mono">{item.item_id}</span>
        </div>
      </div>
    </div>
  );
}
