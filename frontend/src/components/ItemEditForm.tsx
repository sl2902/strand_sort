import { useState, type ReactNode } from "react";
import { Save, X, ChevronDown } from "lucide-react";
import { CATEGORIES, CATEGORY_LABELS, type DonationItem } from "../lib/types";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-700/70">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-cream-300 bg-cream-50 px-3 py-2 text-sm text-ink-900 focus:border-terracotta-400 focus:outline-none focus:ring-2 focus:ring-terracotta-300/40";

export function ItemEditForm({
  item,
  onCancel,
  onSave,
  saving,
}: {
  item: DonationItem;
  onCancel: () => void;
  onSave: (updates: Record<string, unknown>) => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState<DonationItem>(() => JSON.parse(JSON.stringify(item)));
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [rawJson, setRawJson] = useState(() => JSON.stringify(item, null, 2));
  const [rawJsonError, setRawJsonError] = useState<string | null>(null);

  const set = <K extends keyof DonationItem>(key: K, value: DonationItem[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const setFlag = <K extends keyof DonationItem["dietary_flags"]>(key: K, value: DonationItem["dietary_flags"][K]) =>
    setDraft((d) => ({ ...d, dietary_flags: { ...d.dietary_flags, [key]: value } }));

  const setNutrition = <K extends keyof DonationItem["nutrition_facts"]>(
    key: K,
    value: DonationItem["nutrition_facts"][K]
  ) => setDraft((d) => ({ ...d, nutrition_facts: { ...d.nutrition_facts, [key]: value } }));

  const submitStructured = () => {
    onSave({
      product_name: draft.product_name,
      category: draft.category,
      raw_date_text_found: draft.raw_date_text_found,
      expiration_date: draft.expiration_date,
      date_confidence: draft.date_confidence,
      is_expired: draft.is_expired,
      is_damaged: draft.is_damaged,
      quantity: draft.quantity,
      dietary_flags: draft.dietary_flags,
      nutrition_facts: draft.nutrition_facts,
    });
  };

  const submitRawJson = () => {
    try {
      const parsed = JSON.parse(rawJson);
      setRawJsonError(null);
      onSave(parsed);
    } catch {
      setRawJsonError("That isn't valid JSON — check for a stray comma or quote.");
    }
  };

  return (
    <div className="space-y-6 rounded-2xl border border-terracotta-300/50 bg-terracotta-50/40 p-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Product name">
          <input
            className={inputClass}
            value={draft.product_name}
            onChange={(e) => set("product_name", e.target.value)}
          />
        </Field>
        <Field label="Category">
          <select
            className={inputClass}
            value={draft.category}
            onChange={(e) => set("category", e.target.value as DonationItem["category"])}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Quantity">
          <input
            type="number"
            min={0}
            className={inputClass}
            value={draft.quantity}
            onChange={(e) => set("quantity", Number(e.target.value))}
          />
        </Field>
        <Field label="Expiration date (YYYY-MM-DD)">
          <input
            type="date"
            className={inputClass}
            value={draft.expiration_date ?? ""}
            onChange={(e) => set("expiration_date", e.target.value || null)}
          />
        </Field>
        <Field label="Raw date text found">
          <input
            className={inputClass}
            value={draft.raw_date_text_found ?? ""}
            onChange={(e) => set("raw_date_text_found", e.target.value)}
          />
        </Field>
        <Field label="Date confidence">
          <select
            className={inputClass}
            value={draft.date_confidence ?? ""}
            onChange={(e) => set("date_confidence", (e.target.value || null) as DonationItem["date_confidence"])}
          >
            <option value="high">High</option>
            <option value="low">Low</option>
          </select>
        </Field>
      </div>

      <div className="flex flex-wrap gap-5">
        <label className="flex items-center gap-2 text-sm text-ink-800">
          <input type="checkbox" checked={draft.is_damaged} onChange={(e) => set("is_damaged", e.target.checked)} />
          Damaged
        </label>
        <label className="flex items-center gap-2 text-sm text-ink-800">
          <input type="checkbox" checked={draft.is_expired} onChange={(e) => set("is_expired", e.target.checked)} />
          Expired
        </label>
      </div>

      <div>
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-700/60">Dietary flags</h4>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Vegetarian">
            <select
              className={inputClass}
              value={draft.dietary_flags.is_vegetarian === null ? "" : String(draft.dietary_flags.is_vegetarian)}
              onChange={(e) => setFlag("is_vegetarian", e.target.value === "" ? null : e.target.value === "true")}
            >
              <option value="">Unknown</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </Field>
          <div className="flex flex-wrap items-center gap-4 pt-5">
            {(
              [
                ["is_vegan", "Vegan"],
                ["is_gluten_free", "Gluten-free"],
                ["is_low_sugar", "Low sugar"],
                ["is_low_sodium", "Low sodium"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm text-ink-800">
                <input
                  type="checkbox"
                  checked={draft.dietary_flags[key]}
                  onChange={(e) => setFlag(key, e.target.checked)}
                />
                {label}
              </label>
            ))}
          </div>
        </div>
      </div>

      <div>
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-700/60">Nutrition facts</h4>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Serving size">
            <input
              className={inputClass}
              value={draft.nutrition_facts.serving_size ?? ""}
              onChange={(e) => setNutrition("serving_size", e.target.value || null)}
            />
          </Field>
          <Field label="Nutrition confidence">
            <select
              className={inputClass}
              value={draft.nutrition_facts.nutrition_confidence}
              onChange={(e) =>
                setNutrition("nutrition_confidence", e.target.value as DonationItem["nutrition_facts"]["nutrition_confidence"])
              }
            >
              <option value="high">High</option>
              <option value="low">Low</option>
            </select>
          </Field>
          <Field label="Sugars (g)">
            <input
              type="number"
              step="0.1"
              className={inputClass}
              value={draft.nutrition_facts.sugars_g ?? ""}
              onChange={(e) => setNutrition("sugars_g", e.target.value === "" ? null : Number(e.target.value))}
            />
          </Field>
          <Field label="Sodium (mg)">
            <input
              type="number"
              step="1"
              className={inputClass}
              value={draft.nutrition_facts.sodium_mg ?? ""}
              onChange={(e) => setNutrition("sodium_mg", e.target.value === "" ? null : Number(e.target.value))}
            />
          </Field>
          <Field label="Protein (g)">
            <input
              type="number"
              step="0.1"
              className={inputClass}
              value={draft.nutrition_facts.protein_g ?? ""}
              onChange={(e) => setNutrition("protein_g", e.target.value === "" ? null : Number(e.target.value))}
            />
          </Field>
          <Field label="FSSAI symbol">
            <select
              className={inputClass}
              value={draft.nutrition_facts.fssai_symbol_found}
              onChange={(e) =>
                setNutrition("fssai_symbol_found", e.target.value as DonationItem["nutrition_facts"]["fssai_symbol_found"])
              }
            >
              <option value="green_dot">Green dot</option>
              <option value="brown_dot">Brown dot</option>
              <option value="red_triangle">Red triangle</option>
              <option value="none">None</option>
            </select>
          </Field>
          <Field label="Raw nutrition text found">
            <input
              className={inputClass}
              value={draft.nutrition_facts.raw_nutrition_text_found ?? ""}
              onChange={(e) => setNutrition("raw_nutrition_text_found", e.target.value || null)}
            />
          </Field>
          <label className="flex items-center gap-2 pt-5 text-sm text-ink-800">
            <input
              type="checkbox"
              checked={draft.nutrition_facts.panel_found}
              onChange={(e) => setNutrition("panel_found", e.target.checked)}
            />
            Nutrition panel visible on package
          </label>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-terracotta-300/40 pt-4">
        <button
          onClick={submitStructured}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-xl bg-terracotta-500 px-4 py-2 text-sm font-semibold text-cream-50 shadow-soft hover:bg-terracotta-600 disabled:opacity-60"
        >
          <Save size={15} />
          Save changes
        </button>
        <button
          onClick={onCancel}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-xl border border-cream-300 bg-cream-50 px-4 py-2 text-sm font-medium text-ink-800 hover:bg-cream-100"
        >
          <X size={15} />
          Cancel
        </button>
      </div>

      <div>
        <button
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-1 text-xs font-medium text-ink-700/60 hover:text-ink-900"
        >
          <ChevronDown size={13} className={showAdvanced ? "rotate-180 transition-transform" : "transition-transform"} />
          Advanced: edit raw JSON
        </button>
        {showAdvanced && (
          <div className="mt-3 space-y-2">
            <p className="text-xs text-ink-700/60">
              For anything the structured form above doesn't cover — this is sent as-is and merged into the
              stored item.
            </p>
            <textarea
              className={`${inputClass} h-56 font-mono text-xs`}
              value={rawJson}
              onChange={(e) => setRawJson(e.target.value)}
              spellCheck={false}
            />
            {rawJsonError && <p className="text-xs text-danger-600">{rawJsonError}</p>}
            <button
              onClick={submitRawJson}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-xl bg-ink-900 px-4 py-2 text-sm font-semibold text-cream-50 shadow-soft hover:bg-ink-800 disabled:opacity-60"
            >
              <Save size={15} />
              Save raw JSON
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
