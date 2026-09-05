from unittest.mock import patch

from strand_sort.models import NO_EXPIRATION_DATE, DietaryFlags, NutritionFacts, VisionExtraction
from strand_sort.vision.extract import (
    VisionExtractor,
    _recompute_low_sodium,
    _recompute_low_sugar,
    _to_donation_item,
)


def _nutrition_facts(**overrides) -> NutritionFacts:
    defaults = dict(panel_found=True, sugars_g=None, sodium_mg=None)
    defaults.update(overrides)
    return NutritionFacts(**defaults)


class TestRecomputeLowSugar:
    def test_high_sugar_is_not_low(self):
        assert _recompute_low_sugar(_nutrition_facts(sugars_g=51.84)) == (False, "printed_panel")

    def test_low_sugar_below_threshold(self):
        assert _recompute_low_sugar(_nutrition_facts(sugars_g=0.67)) == (True, "printed_panel")

    def test_boundary_value_is_low(self):
        assert _recompute_low_sugar(_nutrition_facts(sugars_g=5.0)) == (True, "printed_panel")

    def test_no_panel_found_returns_none(self):
        assert _recompute_low_sugar(_nutrition_facts(panel_found=False, sugars_g=51.84)) is None

    def test_missing_value_returns_none(self):
        assert _recompute_low_sugar(_nutrition_facts(sugars_g=None)) is None


class TestRecomputeLowSodium:
    def test_high_sodium_is_not_low(self):
        """The reported bug: 222mg sodium must not compute as low."""
        assert _recompute_low_sodium(_nutrition_facts(sodium_mg=222)) == (False, "printed_panel")

    def test_low_sodium_below_threshold(self):
        assert _recompute_low_sodium(_nutrition_facts(sodium_mg=124)) == (True, "printed_panel")

    def test_boundary_value_is_low(self):
        assert _recompute_low_sodium(_nutrition_facts(sodium_mg=140.0)) == (True, "printed_panel")

    def test_no_panel_found_returns_none(self):
        assert _recompute_low_sodium(_nutrition_facts(panel_found=False, sodium_mg=222)) is None

    def test_missing_value_returns_none(self):
        assert _recompute_low_sodium(_nutrition_facts(sodium_mg=None)) is None


def _vision_extraction(**overrides) -> VisionExtraction:
    # raw_date_text_found deliberately isn't "NONE"/"NULL" here — that value
    # gets normalized to Python None by _to_donation_item, which conflicts
    # with DonationItem's non-nullable field type. Pre-existing, unrelated to
    # the nutrition-flag fix under test here.
    defaults = dict(
        product_name="Test Item",
        category="snacks_confectionery",
        raw_date_text_found="15/09/2027",
        expiration_date_raw="2027-09-15",
        dietary_flags=DietaryFlags(),
        nutrition_facts=_nutrition_facts(),
    )
    defaults.update(overrides)
    return VisionExtraction(**defaults)


class TestToDonationItemOverridesModelAssertion:
    def test_snickers_bug_high_sodium_no_longer_flagged_low(self):
        """The model asserted is_low_sugar/is_low_sodium=True despite 222mg
        sodium and 51.84g sugar being extracted. Both must come out False."""
        result = _vision_extraction(
            product_name="Snickers",
            nutrition_facts=_nutrition_facts(sugars_g=51.84, sodium_mg=222),
            dietary_flags=DietaryFlags(
                is_low_sugar=True,
                is_low_sodium=True,
                is_low_sugar_source="inferred",
                is_low_sodium_source="inferred",
            ),
        )
        item = _to_donation_item(result)

        assert item.dietary_flags.is_low_sugar is False
        assert item.dietary_flags.is_low_sodium is False
        assert item.dietary_flags.is_low_sugar_source == "printed_panel"
        assert item.dietary_flags.is_low_sodium_source == "printed_panel"

    def test_genuinely_low_sodium_item_still_correct(self):
        """Regression guard: fixing the false positive must not introduce a
        false negative on data that was already correct (eggs case)."""
        result = _vision_extraction(
            product_name="Fresh Eggs",
            nutrition_facts=_nutrition_facts(sugars_g=0.67, sodium_mg=124),
            dietary_flags=DietaryFlags(
                is_low_sugar=True,
                is_low_sodium=True,
                is_low_sugar_source="printed_panel",
                is_low_sodium_source="printed_panel",
            ),
        )
        item = _to_donation_item(result)

        assert item.dietary_flags.is_low_sugar is True
        assert item.dietary_flags.is_low_sodium is True

    def test_no_nutrition_panel_keeps_model_inference(self):
        """A whole, unlabeled fruit: no panel to check against — the model's
        own category-level inference should pass through untouched."""
        result = _vision_extraction(
            product_name="Fresh Banana",
            nutrition_facts=_nutrition_facts(panel_found=False, sugars_g=None, sodium_mg=None),
            dietary_flags=DietaryFlags(
                is_low_sugar=False,
                is_low_sodium=True,
                is_low_sugar_source="inferred",
                is_low_sodium_source="inferred",
            ),
        )
        item = _to_donation_item(result)

        assert item.dietary_flags.is_low_sugar is False
        assert item.dietary_flags.is_low_sodium is True
        assert item.dietary_flags.is_low_sugar_source == "inferred"
        assert item.dietary_flags.is_low_sodium_source == "inferred"

    def test_partial_panel_overrides_only_the_field_with_a_real_number(self):
        """Sodium was read but sugar wasn't — is_low_sodium should still get
        corrected even though is_low_sugar has nothing real to check against."""
        result = _vision_extraction(
            nutrition_facts=_nutrition_facts(sugars_g=None, sodium_mg=222),
            dietary_flags=DietaryFlags(
                is_low_sugar=True,  # model's own guess — left alone, no real sugar number
                is_low_sodium=True,  # wrong — must be corrected from the real 222mg reading
                is_low_sugar_source="inferred",
                is_low_sodium_source="inferred",
            ),
        )
        item = _to_donation_item(result)

        assert item.dietary_flags.is_low_sugar is True
        assert item.dietary_flags.is_low_sugar_source == "inferred"
        assert item.dietary_flags.is_low_sodium is False
        assert item.dietary_flags.is_low_sodium_source == "printed_panel"


class TestNoDateSentinelDoesNotCrash:
    """DonationItem.raw_date_text_found is a required str, but the model's
    own sentinel for "no date visible" is the literal string "NONE" — not
    Python None (VisionExtraction.raw_date_text_found is itself a required
    str; the system prompt instructs: "Put 'NONE' if no date string is
    visible"). _to_donation_item converts that sentinel to Python None
    internally for its own has_real_date/suspect_packing_date checks, and
    must convert it back to a string ("NONE") before constructing
    DonationItem — `raw_text or "NONE"` — or construction raises a
    pydantic ValidationError."""

    def test_no_date_sentinel_does_not_raise(self):
        result = _vision_extraction(
            raw_date_text_found="NONE",
            expiration_date_raw=None,
            date_confidence="low",
        )
        item = _to_donation_item(result)  # must not raise ValidationError
        assert item.raw_date_text_found == "NONE"

    def test_no_date_item_requires_review(self):
        """No date found means the model can't be high-confidence about a
        date that isn't there, so date_confidence="low" — which routes
        through the existing low-confidence-date review gate, same as any
        other low-confidence date read."""
        result = _vision_extraction(
            raw_date_text_found="NONE",
            expiration_date_raw=None,
            date_confidence="low",
        )
        item = _to_donation_item(result)
        assert item.requires_human_review is True

    def test_real_date_passes_through_unchanged(self):
        """Regression guard: the "NONE" fallback must not clobber a real,
        legitimately-extracted date string."""
        result = _vision_extraction(
            raw_date_text_found="23/01/2027",
            expiration_date_raw="2027-01-23",
            date_confidence="high",
        )
        item = _to_donation_item(result)
        assert item.raw_date_text_found == "23/01/2027"

    def test_no_date_expiration_date_is_the_sentinel_not_none(self):
        """DynamoDB's expiration_date GSI range key rejects both a null
        value and a missing attribute outright — expiration_date must never
        be Python None on a DonationItem that reaches the repository layer,
        or save_item raises ValidationException and the item is silently
        lost (not committed, not sent to review)."""
        result = _vision_extraction(
            raw_date_text_found="NONE",
            expiration_date_raw=None,
            date_confidence="low",
        )
        item = _to_donation_item(result)
        assert item.expiration_date == NO_EXPIRATION_DATE
        assert item.expiration_date is not None

    def test_no_date_item_is_not_marked_expired(self):
        """The sentinel must never be mistaken for an expired real date —
        is_expired/expiry_status must come out exactly as they did when
        expiration_date was None."""
        result = _vision_extraction(
            raw_date_text_found="NONE",
            expiration_date_raw=None,
            date_confidence="low",
        )
        item = _to_donation_item(result)
        assert item.is_expired is False
        assert item.expiry_status is None


class _FakeExtractor(VisionExtractor):
    """Minimal concrete VisionExtractor, no real Bedrock/Gemini client —
    exercises the shared extract() method (where the new "Extraction
    complete" log line lives) without a network call."""

    def __init__(self, raw: VisionExtraction):
        self._raw = raw

    def _extract_raw(self, images_base64):
        return self._raw


class TestExtractionCompleteLogging:
    """Closes a gap where a request completed with no exception anywhere
    but no indication of whether extraction itself ever finished — this
    covers every get_extractor() branch (forced Bedrock/Gemini, both legs
    of auto-mode fallback), since all of them funnel through this one
    extract() method."""

    @patch("strand_sort.vision.extract.logger")
    def test_logs_product_name_and_requires_review_on_success(self, mock_logger):
        raw = _vision_extraction(
            product_name="10on10 Whole Wheat Atta",
            raw_date_text_found="23/01/2027",
            expiration_date_raw="2027-01-23",
            date_confidence="high",
        )
        _FakeExtractor(raw).extract(["ZmFrZQ=="])

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any(
            "Extraction complete" in msg and "10on10 Whole Wheat Atta" in msg and "requires_review=False" in msg
            for msg in logged
        )
