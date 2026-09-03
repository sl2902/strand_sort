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
export type PanelSource = "printed_panel" | "inferred";

export interface DietaryFlags {
  is_vegetarian: boolean | null;
  is_vegetarian_source: DietarySource;
  is_low_sugar: boolean;
  is_low_sodium: boolean;
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

export interface DonationItem {
  item_id: string;
  product_name: string;
  category: Category;
  raw_date_text_found: string;
  expiration_date: string | null;
  date_confidence: "high" | "low" | null;
  is_expired: boolean;
  is_damaged: boolean;
  requires_human_review: boolean;
  review_reason: string | null;
  dietary_flags: DietaryFlags;
  nutrition_facts: NutritionFacts;
  quantity: number;
  /** URLs valid right now — the backend regenerates these (S3 presigned URLs
   * expire) on every read, so never cache one past the response it came in. */
  image_urls: string[];
  [key: string]: unknown; // the backend PATCH endpoint merges arbitrary fields
}

export interface IntakeResponse {
  result: string;
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
