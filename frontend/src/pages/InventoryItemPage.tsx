import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Pencil, X, Check, PackageMinus, AlertTriangle, CalendarClock, Info } from "lucide-react";
import { getItem, updateItem, checkoutItem, rejectItem, ApiError } from "../lib/api";
import { CATEGORY_LABELS, type DonationItem } from "../lib/types";
import { Badge } from "../components/Badge";
import { DietaryDetailList } from "../components/DietaryBadges";
import { SourceTag } from "../components/SourceTag";
import { FssaiMark } from "../components/FssaiMark";
import { ImageGallery } from "../components/ItemImages";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { formatDate, expiryBadgeContent } from "../lib/format";
import { ItemEditForm } from "../components/ItemEditForm";
import { Spinner } from "../components/Spinner";
import { useToast } from "../components/Toast";

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

export function InventoryItemPage() {
  const { itemId } = useParams<{ itemId: string }>();
  const navigate = useNavigate();
  const { show } = useToast();

  const [item, setItem] = useState<DonationItem | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [checkoutQty, setCheckoutQty] = useState(1);
  const [checkingOut, setCheckingOut] = useState(false);
  const [confirmingReject, setConfirmingReject] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  // "Commit" has nothing to persist (no acknowledged-state field exists on
  // DonationItem) — a pure local dismiss of the reject/commit prompt, not
  // a change to the item. Resets on next load, which is fine: it's only
  // clearing today's prompt, not recording a decision.
  const [expiredDismissed, setExpiredDismissed] = useState(false);

  const load = () => {
    if (!itemId) return;
    getItem(itemId)
      .then((data) => {
        setItem(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Couldn't load this item."));
  };

  useEffect(load, [itemId]);

  const handleSave = async (updates: Record<string, unknown>) => {
    if (!itemId) return;
    setSaving(true);
    try {
      const updated = await updateItem(itemId, updates);
      setItem(updated);
      setIsEditing(false);
      show("Item updated.", "success");
    } catch (err) {
      show(err instanceof ApiError ? err.message : "Couldn't save changes.", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleCheckout = async () => {
    if (!itemId || checkoutQty <= 0) return;
    setCheckingOut(true);
    try {
      const updated = await checkoutItem(itemId, checkoutQty);
      setItem(updated);
      setCheckoutQty(1);
      show(`Checked out ${checkoutQty} unit${checkoutQty === 1 ? "" : "s"}.`, "success");
    } catch (err) {
      show(err instanceof ApiError ? err.message : "Checkout failed.", "error");
    } finally {
      setCheckingOut(false);
    }
  };

  const handleReject = async () => {
    if (!itemId) return;
    setRejecting(true);
    try {
      await rejectItem(itemId);
      show(`${item?.product_name ?? "Item"} rejected.`, "success");
      // The item no longer exists — nothing to stay on this page for, and
      // the Inventory list re-fetches on its own mount, so it won't show
      // the rejected item stale.
      navigate("/inventory");
    } catch (err) {
      show(err instanceof ApiError ? err.message : "Couldn't reject this item.", "error");
      setRejecting(false);
      setConfirmingReject(false);
    }
  };

  if (loadError) {
    return (
      <div className="space-y-4">
        <BackLink />
        <div className="rounded-2xl border border-danger-400/40 bg-danger-100/60 px-5 py-4 text-sm text-danger-600">
          {loadError}
        </div>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="space-y-4">
        <BackLink />
        <div className="flex items-center gap-2 text-ink-700/60">
          <Spinner /> Loading item…
        </div>
      </div>
    );
  }

  const expiryBadge = expiryBadgeContent(item.expiry_status, item.expiration_date);
  const { dietary_flags, nutrition_facts } = item;

  return (
    <div className="space-y-6">
      <BackLink />

      <div className="animate-fade-up flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-terracotta-600">
            {CATEGORY_LABELS[item.category]}
          </p>
          <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">{item.product_name}</h1>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge tone={expiryBadge.tone}>{expiryBadge.label}</Badge>
            {item.is_damaged && <Badge tone="danger">Damaged</Badge>}
            {item.requires_human_review && <Badge tone="danger">Needs review</Badge>}
            <Badge
              tone={item.quantity === 0 ? "danger" : "neutral"}
              className={item.quantity === 0 ? "animate-pulse" : undefined}
            >
              {item.quantity === 0 ? "Out of stock" : `×${item.quantity} in stock`}
            </Badge>
          </div>
        </div>
        {!isEditing && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsEditing(true)}
              className="inline-flex items-center gap-2 rounded-xl border border-cream-300 bg-cream-50 px-4 py-2 text-sm font-medium text-ink-800 shadow-soft hover:bg-cream-100"
            >
              <Pencil size={15} />
              Edit
            </button>
          </div>
        )}
      </div>

      {item.expiry_status === "expired" && !isEditing && !expiredDismissed && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-danger-400/50 bg-danger-100/60 px-4 py-3.5 text-sm text-danger-700">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <p>
              This item is expired ({formatDate(item.expiration_date)}). Reject to remove it from inventory, or
              commit to keep it as-is.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setExpiredDismissed(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-cream-300 bg-cream-50 px-3 py-1.5 text-xs font-medium text-ink-800 shadow-soft hover:bg-cream-100"
            >
              <Check size={13} />
              Commit
            </button>
            <button
              onClick={() => setConfirmingReject(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-danger-400/50 bg-danger-100 px-3 py-1.5 text-xs font-medium text-danger-600 shadow-soft hover:bg-danger-200/60"
            >
              <X size={13} />
              Reject
            </button>
          </div>
        </div>
      )}

      {confirmingReject && (
        <ConfirmDialog
          title={`Reject ${item.product_name}?`}
          description="This item is expired. Rejecting removes it from inventory — this can't be undone."
          confirmLabel="Reject"
          isConfirming={rejecting}
          onConfirm={handleReject}
          onCancel={() => setConfirmingReject(false)}
        />
      )}

      {item.requires_human_review && item.review_reason && (
        <div className="flex items-start gap-2 rounded-2xl border border-saffron-400/50 bg-saffron-100/70 px-4 py-3 text-sm text-saffron-700">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <p>{item.review_reason}</p>
        </div>
      )}

      <div className="animate-fade-up">
        <ImageGallery urls={item.image_urls} alt={item.product_name} onRetry={load} />
      </div>

      {isEditing ? (
        <ItemEditForm item={item} saving={saving} onCancel={() => setIsEditing(false)} onSave={handleSave} />
      ) : (
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
                min={1}
                max={item.quantity}
                value={checkoutQty}
                onChange={(e) => setCheckoutQty(Number(e.target.value))}
                disabled={item.quantity === 0}
                className="w-24 rounded-lg border border-cream-300 bg-cream-100 px-3 py-2 text-sm focus:border-terracotta-400 focus:outline-none focus:ring-2 focus:ring-terracotta-300/40 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <button
                onClick={handleCheckout}
                disabled={checkingOut || item.quantity === 0 || checkoutQty <= 0 || checkoutQty > item.quantity}
                className="inline-flex items-center gap-2 rounded-xl bg-terracotta-500 px-4 py-2 text-sm font-semibold text-cream-50 shadow-soft hover:bg-terracotta-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {checkingOut ? <Spinner size={15} /> : <PackageMinus size={15} />}
                Check out
              </button>
            </div>
            <p className="mt-3 flex items-start gap-1.5 text-xs text-ink-700/60">
              <Info size={13} className="mt-0.5 shrink-0" />
              {item.quantity === 0
                ? "Out of stock — nothing left to distribute."
                : `Decrements stock when items are handed out to distribution. ${item.quantity} unit${
                    item.quantity === 1 ? "" : "s"
                  } currently on hand.`}
            </p>
          </Section>

          <div className="flex items-center gap-2 text-xs text-ink-700/40 lg:col-span-2">
            <CalendarClock size={13} />
            Item ID: <span className="font-mono">{item.item_id}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/inventory" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-700/70 hover:text-ink-900">
      <ArrowLeft size={15} />
      Back to inventory
    </Link>
  );
}
