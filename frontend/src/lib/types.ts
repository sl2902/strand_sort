// Mirrors strand_sort/models.py — keep in sync with the backend Pydantic models.

export const CATEGORIES = [
  "canned_protein",
  "grains_pasta",
  "dairy_eggs",
  "produce",
  "dairy_fats",
  "grains_pulses",
  "dairy_liquid",
  "beverages",
  "snacks",
  "baby_items",
  "hygiene",
  "condiments_sauces",
  "boxed_meals",
  "snacks_confectionery",
  "other_unknown",
] as const;

export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_LABELS: Record<Category, string> = {
  canned_protein: "Canned Protein",
  grains_pasta: "Grains & Pasta",
  dairy_eggs: "Dairy & Eggs",
  produce: "Produce",
  dairy_fats: "Dairy Fats",
  grains_pulses: "Grains & Pulses",
  dairy_liquid: "Milk & Dairy Liquid",
  beverages: "Beverages",
  snacks: "Snacks",
  baby_items: "Baby Items",
  hygiene: "Hygiene",
  condiments_sauces: "Condiments & Sauces",
  boxed_meals: "Boxed Meals",
  snacks_confectionery: "Confectionery",
  other_unknown: "Other / Unknown",
};

export type DietarySource = "printed_symbol" | "inferred" | "not_found";
export type PanelSource = "printed_panel" | "inferred" | "unavailable";

export interface DietaryFlags {
  is_vegetarian: boolean | null;
  is_vegetarian_source: DietarySource;
  /** null when unknown — either no nutrition panel at all (source
   * "inferred", falls back to the model's category guess) or a panel
   * exists but this specific value wasn't captured (source
   * "unavailable" — must render as "Unavailable", never a guessed Yes/No). */
  is_low_sugar: boolean | null;
  is_low_sodium: boolean | null;
  is_low_sugar_source: PanelSource;
  is_low_sodium_source: PanelSource;
  is_gluten_free: boolean;
  is_vegan: boolean;
  other_flags_source: "inferred";
}

export type FssaiSymbol = "green_dot" | "brown_dot" | "red_triangle" | "none";

export interface NutritionFacts {
  serving_size: string | null;
  raw_nutrition_text_found: string | null;
  sugars_g: number | null;
  sodium_mg: number | null;
  protein_g: number | null;
  nutrition_confidence: "high" | "low";
  panel_found: boolean;
  fssai_symbol_found: FssaiSymbol;
}

export type ExpiryStatus = "fine" | "near_expiry" | "expired";

export interface DonationItem {
  item_id: string;
  product_name: string;
  category: Category;
  raw_date_text_found: string;
  expiration_date: string | null;
  date_confidence: "high" | "low" | null;
  /** Recomputed by the backend on every read from expiration_date — never
   * stale, unlike a value that was frozen at scan time. Prefer this over
   * client-side date math wherever a DonationItem is already in hand. */
  is_expired: boolean;
  expiry_status: ExpiryStatus | null;
  is_damaged: boolean;
  requires_human_review: boolean;
  review_reason: string | null;
  dietary_flags: DietaryFlags;
  nutrition_facts: NutritionFacts;
  quantity: number;
  /** Full-resolution originals. URLs valid right now — the backend
   * regenerates these (S3 presigned URLs expire) on every read, so never
   * cache one past the response it came in. */
  image_urls: string[];
  /** Resized (max 400px) variants, one per image_urls entry, for card/list
   * display — same regenerate-on-every-read rule as image_urls. Empty for
   * items scanned before this field existed; fall back to image_urls[0]
   * for the card preview in that case. */
  thumbnail_urls: string[];
  [key: string]: unknown; // the backend PATCH endpoint merges arbitrary fields
}

export interface IntakeResponse {
  summary: string;
  /** Null when the run never reached a settled outcome (e.g. a hard failure
   * before extraction completed) — the backend doesn't fabricate one. */
  item: DonationItem | null;
}

export interface ReviewResolutionRequest {
  approved: boolean;
  corrected_date?: string | null;
  notes?: string | null;
}

export interface ReviewResolutionResponse {
  status: "approved_and_committed" | "rejected_and_discarded";
  item?: unknown;
  item_id?: string;
}
