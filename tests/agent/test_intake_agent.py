from strand_sort.agent.intake_agent import format_intake_summary


def _base_item(**overrides):
    item = {
        "item_id": "abc",
        "product_name": "10on10 Whole Wheat Atta",
        "category": "grains_pulses",
        "quantity": 2,
        "expiration_date": "2026-11-20",
        "date_confidence": "high",
        "requires_human_review": False,
        "review_reason": None,
        "dietary_flags": {},
    }
    item.update(overrides)
    return item


def test_committed_item_summary_mentions_quantity_product_category_and_expiry():
    summary = format_intake_summary(_base_item())
    assert "2 x 10on10 Whole Wheat Atta" in summary
    assert "grains pulses" in summary
    assert "2026-11-20" in summary
    assert "flagged" not in summary.lower()


def test_low_date_confidence_adds_a_note():
    summary = format_intake_summary(_base_item(date_confidence="low"))
    assert "low" in summary.lower()


def test_high_date_confidence_has_no_confidence_note():
    summary = format_intake_summary(_base_item(date_confidence="high"))
    assert "confidence" not in summary.lower()


def test_dietary_highlights_are_listed_when_present():
    summary = format_intake_summary(
        _base_item(dietary_flags={"is_vegan": True, "is_gluten_free": True, "is_low_sodium": True})
    )
    assert "vegan" in summary
    assert "gluten-free" in summary
    assert "low sodium" in summary


def test_no_dietary_clause_when_nothing_is_flagged():
    summary = format_intake_summary(_base_item(dietary_flags={"is_vegan": False}))
    assert "Dietary flags" not in summary


def test_vegetarian_false_is_not_treated_as_a_highlight():
    """is_vegetarian is tri-state (True/False/None) — only an explicit True counts."""
    summary = format_intake_summary(_base_item(dietary_flags={"is_vegetarian": False}))
    assert "vegetarian" not in summary.lower()


def test_flagged_item_summary_mentions_review_and_reason():
    summary = format_intake_summary(
        _base_item(requires_human_review=True, review_reason="low-confidence date read")
    )
    assert "flagged for human review" in summary
    assert "low-confidence date read" in summary
    assert "committed to inventory" not in summary


def test_flagged_item_without_reason_still_produces_a_sentence():
    summary = format_intake_summary(_base_item(requires_human_review=True, review_reason=None))
    assert "flagged for human review" in summary


def test_missing_product_name_falls_back_gracefully():
    item = _base_item()
    del item["product_name"]
    summary = format_intake_summary(item)
    assert "This item" in summary
