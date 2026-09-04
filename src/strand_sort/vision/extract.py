import base64
import uuid
import hashlib
from abc import ABC, abstractmethod
from typing import Literal

import boto3
import botocore.exceptions
from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field

from strand_sort.config import settings, BEDROCK_FALLBACK_ERROR_CODES
from strand_sort.expiry import ExpiryStatus, compute_expiry_status
from strand_sort.models import (
    Category,
    DonationItem,
    VisionExtraction,
    DietaryFlags,
    NutritionFacts,
)

SYSTEM_PROMPT = """
You are an expert industrial OCR vision parser for a food bank donation intake system in India.
Analyze the provided image(s) of a single item from all angles given.

CRITICAL CONTEXT & ANCHORS:
- CURRENT YEAR ANCHOR: The current year is 2026. Items packaged recently will have expiration dates in 2026, 2027, or beyond. Past years like 2023 or 2025 are unlikely unless explicitly legible.

Extract:
- product_name: the product's name as printed on the package
- category: pick exactly one from the allowed category list
- raw_date_text_found: exact verbatim text string near 'USE BY', 'EXP', or 'Date of Expiry' (e.g., "23/01/2027" or "USE BY 30/08/26")
- expiration_date_raw: normalized ISO 8601 (YYYY-MM-DD) date derived from raw_date_text_found
- date_confidence: "high" only if you are certain the date is genuine and correctly identified; "low" for anything uncertain
- is_damaged: whether the packaging shows visible physical damage
- damage_description: brief description, only if is_damaged is true
- label_readable: whether the label is legible enough to extract from

INDIAN PACKAGING & DOT-MATRIX RULES:
1. FSSAI DIETARY SYMBOL & VEGETARIAN RULES:
  - Scan packaging visually for mandatory FSSAI vegetarian/non-vegetarian symbols:
    * GREEN DOT inside a green square = Vegetarian product (set is_vegetarian=True, fssai_symbol_found="green_dot").
    * BROWN/RED DOT inside a square or RED TRIANGLE = Non-Vegetarian / contains meat, fish, or egg (set is_vegetarian=False, fssai_symbol_found="brown_dot" or "red_triangle").
    * A green stylized "V" with a sprouting leaf and the word "VEGAN" below it
  - Inherent Rules:
    * Fresh dairy (milk, butter, paneer) and plant products (wheat, pulses) with a green dot are Vegetarian (is_vegetarian=True) but milk/butter are NOT Vegan (is_vegan=False).
    * Whole eggs in India generally carry the brown/red dot symbol (is_vegetarian=False under strict Indian veg standards).
2. DATE FORMAT: Indian packaged goods use DD/MM/YY or DD/MM/YYYY (Day/Month/Year).
   - "23/01/2027" -> Day=23, Month=01, Year=2027 -> ISO: "2027-01-23"
   - "30/08/26" -> Day=30, Month=08, Year=2026 -> ISO: "2026-08-30"
3. DUAL-DATE HANDLING (PACKING vs. EXPIRY):
   - Packaging often prints both 'Date of Packing' (MFG/PKD) and 'Date of Expiry' (EXP/USE BY) near each other.
   - NEVER set 'expiration_date_raw' or 'raw_date_text_found' using the manufacturing/packing date. 
   - Always ensure the date mapped to 'raw_date_text_found' corresponds explicitly to the expiry or best-before stamp.
4. DOT-MATRIX OCR SANITY CHECKS:
   - Carefully inspect every single dot in dot-matrix text:
     * Do NOT misread dot-matrix '26' (as in /26) for '23'.
     * Do NOT misread dot-matrix '2027' (as in /2027) for '2025'.
5. Unlabeled/Separate Dates:
   - If "DATE OF EXPIRY:" is printed as a field header but the numbers are printed on a separate line (near MRP or batch number), use spatial proximity to associate them. If inferring, set date_confidence to "low".
6. If you cannot identify an expiration date, return null for expiration_date_raw and raw_date_text_found.
7. Always transcribe the exact text string found near the date header into raw_date_text_found (e.g., '23/01/2027' or 'USE BY 30/08/26') BEFORE parsing it into ISO format for expiration_date_raw.
8. NUTRITION & DIETARY EXTRACTION RULES:
   - Use both visible package labels AND inherent nutritional facts of single-ingredient whole foods:
    * is_low_sugar: True if total sugars <= 5g per 100g or explicitly labeled "Low Sugar" / "Zero Sugar". (True for raw eggs, butter, plain milk, pure grains).
    * is_low_sodium: True if sodium <= 140mg per serving or explicitly labeled "Low Sodium". (True for fresh eggs (~70mg/egg), unsalted butter, milk, and whole grains).
    * is_gluten_free: True if explicitly labeled "Gluten-Free" OR if the item is naturally gluten-free single-ingredient food (e.g., fresh eggs, dairy milk, butter, rice). Set False for wheat/atta products.
    * is_vegan: True if explicitly labeled "Vegan" OR if the item contains zero animal ingredients/byproducts (e.g., 100% whole wheat atta, grains, pulses, fruits, vegetables). Set False for eggs, milk, butter, or honey.
   - Before extracting sugar/sodium/protein numbers, first transcribe the exact raw text of those rows verbatim into raw_nutrition_text_found (e.g.,"Sugars 0.67g, Sodium 142mg, Protein 13.3g"). 
   - Set nutrition_confidence to "high" only if the panel numbers are sharp and unambiguous. If small, blurry, or uncertain, set "low" rather than guessing.
   - For is_low_sugar and is_low_sodium, additionally report:
    * is_low_sugar_source: "printed_panel" if read from an actual visible sugar value; "inferred" if using general category knowledge with no visible panel value.
    * is_low_sodium_source: same logic, for sodium.

Return ONLY valid JSON matching the requested schema.
"""

LOW_SUGAR_THRESHOLD_G = 5.0       # per 100g/serving, matching the system prompt's own stated rule
LOW_SODIUM_THRESHOLD_MG = 140.0   # per serving, matching the system prompt's own stated rule


def _recompute_low_sugar(nf: NutritionFacts) -> tuple[bool, str] | None:
    """Returns (is_low_sugar, source) computed from the extracted sugars_g, or
    None when there's no real number to check (no panel found, or sugars_g
    wasn't extracted) — callers should leave the model's own inferred value
    untouched in that case rather than guessing."""
    if not nf.panel_found or nf.sugars_g is None:
        return None
    return nf.sugars_g <= LOW_SUGAR_THRESHOLD_G, "printed_panel"


def _recompute_low_sodium(nf: NutritionFacts) -> tuple[bool, str] | None:
    """Same as _recompute_low_sugar, for sodium_mg."""
    if not nf.panel_found or nf.sodium_mg is None:
        return None
    return nf.sodium_mg <= LOW_SODIUM_THRESHOLD_MG, "printed_panel"


def _to_donation_item(result: VisionExtraction) -> DonationItem:
    raw_text = result.raw_date_text_found

    has_real_date = raw_text.strip().upper() not in ("NONE", "NULL", "")
    expiration_date_raw = result.expiration_date_raw if has_real_date else None

    if raw_text and raw_text.strip().upper() in ("NONE", "NULL", ""):
        raw_text = None

    # This is the intake-time snapshot only, used below to decide whether to
    # flag/route the item for review right now — it is NOT what callers
    # should trust later. expiry_status (and is_expired) get recomputed
    # fresh from expiration_date on every API read (see strand_sort/api/
    # inventory.py, review.py), since "is this expired" changes daily even
    # though the stored date doesn't; a value frozen here would silently go
    # stale the moment the item sits in inventory past today.
    intake_expiry_status = compute_expiry_status(expiration_date_raw)
    if expiration_date_raw and intake_expiry_status is None:
        logger.warning(f"Unparseable expiration date: {expiration_date_raw!r}")
    is_expired = intake_expiry_status == ExpiryStatus.EXPIRED

    # Optional validation
    suspect_packing_date = False
    if has_real_date and any(kw in raw_text.upper() for kw in ["MFG", "PKD", "PACKED"]):
        logger.warning(f"Possible packing date detected instead of expiry: {raw_text}")
        suspect_packing_date = True

    requires_review = (
        result.is_damaged
        or is_expired
        or not result.label_readable
        or result.date_confidence == "low"
        or suspect_packing_date
    )
    reason = None
    if requires_review:
        reasons = []
        if result.is_damaged:
            reasons.append(f"damaged: {result.damage_description or 'unspecified'}")
        if is_expired:
            reasons.append(f"EXPIRED item detected ({expiration_date_raw})")
        if result.date_confidence == "low":
            reasons.append(f"low-confidence date read (unverified: {expiration_date_raw or raw_text})")
        # if result.expiration_date_raw is not None:
        #     label = "expired" if is_expired else "expiry date detected"
        #     reasons.append(f"{label} (unverified, confidence={result.date_confidence}: {result.expiration_date_raw})")
        if not result.label_readable:
            reasons.append("label unreadable")
        if suspect_packing_date:
            reasons.append(f"suspected packing date extracted ({raw_text})")
        reason = "; ".join(reasons)

    # Never trust the model's own is_low_sugar/is_low_sodium booleans when a
    # real printed number is already in hand — same failure mode as
    # is_expired above: the model can misapply its own stated threshold, or
    # fall back on a category-level assumption that contradicts a number it
    # already extracted (e.g. "snacks are usually low sodium" overriding an
    # actual 222mg reading). Recompute deterministically and override;
    # only fall back to the model's own inference when there's no real
    # number to check it against.
    dietary_flags = result.dietary_flags.model_copy()
    low_sugar = _recompute_low_sugar(result.nutrition_facts)
    if low_sugar is not None:
        dietary_flags.is_low_sugar, dietary_flags.is_low_sugar_source = low_sugar
    low_sodium = _recompute_low_sodium(result.nutrition_facts)
    if low_sodium is not None:
        dietary_flags.is_low_sodium, dietary_flags.is_low_sodium_source = low_sodium

    return DonationItem(
        item_id=generate_idempotency_key(result.product_name, result.expiration_date_raw or ""),
        product_name=result.product_name,
        category=result.category,
        raw_date_text_found=raw_text or "NONE",
        expiration_date=expiration_date_raw,
        date_confidence=result.date_confidence,
        is_expired=is_expired,
        expiry_status=intake_expiry_status,
        is_damaged=result.is_damaged,
        requires_human_review=requires_review,
        review_reason=reason,
        dietary_flags=dietary_flags,
        nutrition_facts=result.nutrition_facts,
    )


class VisionExtractor(ABC):
    @abstractmethod
    def _extract_raw(self, images_base64: list[str]) -> VisionExtraction:
        ...

    def extract(self, images_base64: list[str]) -> DonationItem:
        raw = self._extract_raw(images_base64)
        return _to_donation_item(raw)


class BedrockExtractor(VisionExtractor):
    def __init__(self, model_id: str | None = None):
        self.bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self.model_id = model_id or settings.bedrock_vision_model_id

    def _extract_raw(self, images_base64: list[str]) -> VisionExtraction:
        content = []
        for img in images_base64:
            content.append({
                "image": {
                    "format": "jpeg",
                    "source": {"bytes": base64.b64decode(img)},
                }
            })
        content.append({
            "text": "Analyze these item angles and output structured metadata "
                     f"matching this JSON schema: {VisionExtraction.model_json_schema()}"
        })

        response = self.bedrock.converse(
            modelId=self.model_id,
            inferenceConfig={"temperature": 0.},
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": content}],
        )
        raw_text = response["output"]["message"]["content"][0]["text"]
        return VisionExtraction.model_validate_json(raw_text)


class GeminiExtractor(VisionExtractor):
    def __init__(self, model_id: str | None = None):
        self.client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location="global" or settings.gcp_location,
        )
        self.model_id = model_id or settings.gemini_model_id

    def _extract_raw(self, images_base64: list[str]) -> VisionExtraction:
        parts = [SYSTEM_PROMPT]
        for img in images_base64:
            parts.append(
                types.Part.from_bytes(data=base64.b64decode(img), mime_type="image/jpeg")
            )

        response = self.client.models.generate_content(
            model=self.model_id,
            contents=parts,
            config={
                "response_mime_type": "application/json",
                "response_schema": VisionExtraction,
                "temperature": 0.,
            },
        )
        return VisionExtraction.model_validate_json(response.text)


def get_extractor(images_base64: list[str]) -> DonationItem:
    logger.info(f"get_extractor called | provider={settings.vision_provider} | images={len(images_base64)}")

    if settings.vision_provider == "bedrock":
        logger.info("Using Bedrock (forced)")
        return BedrockExtractor().extract(images_base64)
    if settings.vision_provider == "gemini":
        logger.info("Using Gemini (forced)")
        return GeminiExtractor().extract(images_base64)

    try:
        logger.info("Auto mode: trying Bedrock first")
        return BedrockExtractor().extract(images_base64)
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")

        if error_code in BEDROCK_FALLBACK_ERROR_CODES:
            logger.warning(f"Bedrock unusable ({error_code}); falling back to Gemini.")
            return GeminiExtractor().extract(images_base64)
        logger.error(f"Bedrock call failed with unhandled error code: {error_code}")
        raise

def generate_idempotency_key(product_name: str, expiration_date: str) -> str:
    """Creates a deterministic hash based on static product traits"""
    raw = f"{product_name.strip().lower()}|{expiration_date.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()