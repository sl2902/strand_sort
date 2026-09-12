from pydantic import BaseModel, Field
from typing import Optional, Literal


from enum import Enum

from strand_sort.expiry import ExpiryStatus

# A real, non-null, non-empty string sentinel for "no expiration date found
# on the package" — never store None or "" for expiration_date. DynamoDB's
# ProductNameExpirationIndex GSI has expiration_date as its RANGE key, which rejects
# both a null value AND an empty string outright (ValidationException); a
# missing attribute doesn't crash the write but silently drops the item
# from that index (invisible to search_by_name/check_duplicate_active_
# inventory). One consistent string sentinel, defined once here and used
# everywhere, avoids all three failure modes. Deliberately not something
# that could parse as a real date (e.g. "9999-12-31") — compute_expiry_status
# and every date-parsing call site must be able to reject it outright as
# "not a date" rather than silently succeeding with a nonsense value.
NO_EXPIRATION_DATE = "no-date"


class Category(str, Enum):
    CANNED_PROTEIN = "canned_protein"       # canned meat, beans, tuna
    GRAINS_PASTA = "grains_pasta"           # rice, pasta, cereal
    DAIRY_EGGS = "dairy_eggs"               # milk, butter, cheese, eggs
    PRODUCE = "produce"                     # fresh fruit/veg, if accepted
    DAIRY_FATS = "dairy_fats"               # butter (and other dairy fats, if you add ghee etc.)
    GRAINS_PULSES = "grains_pulses"         # rice, wheat, pulses/lentils
    DAIRY_LIQUID = "dairy_liquid"           # milk
    BEVERAGES = "beverages"
    SNACKS = "snacks"
    BABY_ITEMS = "baby_items"               # formula, baby food
    HYGIENE = "hygiene"                     # soap, toothpaste, etc.
    CONDIMENTS_SAUCES = "condiments_sauces"
    BOXED_MEALS = "boxed_meals"             # mac & cheese, instant meals
    SNACKS_CONFECTIONERY = "snacks_confectionery"
    OTHER_UNKNOWN = "other_unknown"         # doesn't match any category


# Categories dietary/nutrition concepts don't meaningfully apply to — a
# hygiene product being "vegan" or "gluten-free" isn't a food-safety claim
# the model has any real basis to make, whether from a printed panel or
# from generic category knowledge. OTHER_UNKNOWN is included because it's
# not confirmed to be food either; the safe default for an uncertain
# category is to withhold the claim, not guess it. Used both to instruct
# the extraction prompt and (more reliably) to zero out whatever the model
# returned anyway — see _to_donation_item in vision/extract.py.
NON_FOOD_CATEGORIES = frozenset({Category.HYGIENE, Category.OTHER_UNKNOWN})


def is_food_category(category: Category) -> bool:
    return category not in NON_FOOD_CATEGORIES


class DietaryFlags(BaseModel):
    is_vegetarian: bool | None = None
    is_vegetarian_source: Literal["printed_symbol", "inferred", "not_found"] = "not_found"
    is_low_sugar: bool | None = Field(
        None, description="None when unknown — either no panel at all (falls back to the model's category "
        "inference, source='inferred') or a panel exists but this value wasn't captured (source='unavailable')"
    )
    is_low_sodium: bool | None = Field(None, description="Same tri-state as is_low_sugar")
    is_low_sugar_source: Literal["printed_panel", "inferred", "unavailable"] = "inferred"
    is_low_sodium_source: Literal["printed_panel", "inferred", "unavailable"] = "inferred"
    is_gluten_free: bool = False
    is_vegan: bool = False
    other_flags_source: Literal["inferred"] = "inferred"

class NutritionFacts(BaseModel):
    serving_size: str | None = Field(default=None, description="e.g. '100g' or '1 egg (50g)'")
    raw_nutrition_text_found: str | None = Field(
        default=None,
        description="Verbatim transcription of the sugar/sodium/protein rows as printed, before parsing into numbers (e.g. 'Sugars 0.67g, Sodium 142mg, Protein 13.3g')"
    )
    sugars_g: float | None = Field(default=None, description="Total sugars in grams per serving/100g")
    sodium_mg: float | None = Field(default=None, description="Sodium in milligrams per serving/100g")
    protein_g: float | None = Field(default=None, description="Protein in grams")
    nutrition_confidence: Literal["high", "low"] = Field(
        default="low",
        description="'high' only if the panel numbers were sharp and unambiguous; 'low' for anything blurry or uncertain"
    )
    panel_found: bool = Field(default=False, description="True if a nutrition facts table was visually detected")
    fssai_symbol_found: Literal["green_dot", "brown_dot", "red_triangle", "none"] = Field(
        default="none",
        description="FSSAI dietary indicator symbol detected on packaging"
    )

class DonationItem(BaseModel):
    item_id: str
    product_name: str = Field(..., description="Name and brand of the item")
    category: Category
    raw_date_text_found: str = Field(description="Forces OCR attention step")
    expiration_date: Optional[str] = Field(
        NO_EXPIRATION_DATE,
        description=f"Extracted date string YYYY-MM-DD if present, else the {NO_EXPIRATION_DATE!r} sentinel — "
        "never None/empty, both of which DynamoDB's expiration_date GSI range key rejects",
    )
    date_confidence: Literal["high", "low"] | None = Field(None, description="Categorise confidence in date extraction") 
    is_expired: bool = Field(False, description="True if past safety threshold — recomputed on every API read, never trust a stored value")
    expiry_status: Optional[ExpiryStatus] = Field(
        None, description="fine/near_expiry/expired, recomputed fresh on every API read from expiration_date"
    )
    is_damaged: bool = Field(False, description="True if dents, rust, or leaks are visible")
    requires_human_review: bool = Field(False, description="True if date is unreadable or item is severely damaged")
    review_reason: Optional[str] = Field(None, description="Explanation for human flag")
    dietary_flags: DietaryFlags = Field(default_factory=DietaryFlags)
    nutrition_facts: NutritionFacts = Field(default_factory=NutritionFacts)
    quantity: int = Field(default=1, ge=1, description="Number of units in this intake scan")
    image_urls: list[str] = Field(default_factory=list, description="Full-resolution originals")
    thumbnail_urls: list[str] = Field(
        default_factory=list, description="Resized (max 400px) variants for card/list display, one per image_urls entry"
    )

class VisionExtraction(BaseModel):
    """Raw fields the model is actually qualified to report"""
    product_name: str
    category: Category
    category_other_text: str | None = None
    packing_date_raw: str | None = Field(
        default=None, 
        description="Date of packing/MFG if printed separately (e.g., '24/07/2026')"
    )
    raw_date_text_found: str = Field(
        description="CRITICAL: The exact raw unformatted text string read off the package near the expiry/use-by stamp (e.g. '23/01/2027', '30/08/26', or 'BEST BY 15/09/2026'). Put 'NONE' if no date string is visible."
    )
    expiration_date_raw: str | None = None
    date_confidence: Literal["high", "low"] = "low"
    is_damaged: bool = False
    damage_description: str | None = None
    label_readable: bool = True
    dietary_flags: DietaryFlags = Field(default_factory=DietaryFlags)
    nutrition_facts: NutritionFacts = Field(default_factory=NutritionFacts)