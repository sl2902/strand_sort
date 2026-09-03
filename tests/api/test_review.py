from unittest.mock import patch

import pytest

from strand_sort.models import DonationItem


@pytest.fixture
def valid_donation_item():
    return DonationItem(
        item_id="abc123",
        product_name="Fresh Eggs",
        category="dairy_eggs",
        raw_date_text_found="15-09-26",
        expiration_date="2026-09-15",
        date_confidence="high",
        is_expired=False,
        is_damaged=False,
        requires_human_review=True,
        review_reason="low-confidence date read",
        quantity=2,
    )


@pytest.fixture
def no_date_donation_item():
    """Item where the model found no date at all — raw_date_text_found
    stays a real string ("NONE"), expiration_date is None."""
    return DonationItem(
        item_id="def456",
        product_name="10 on 10 Wheat Atta",
        category="grains_pulses",
        raw_date_text_found="NONE",
        expiration_date=None,
        date_confidence="low",
        is_expired=False,
        is_damaged=False,
        requires_human_review=True,
        review_reason="low-confidence date read (unverified: NONE)",
        quantity=1,
    )


@patch("strand_sort.api.review.review_queue")
def test_list_review_queue(mock_queue, client, valid_donation_item):
    mock_queue.get_pending.return_value = [valid_donation_item]

    response = client.get("/api/v1/review/pending")
    assert response.status_code == 200
    assert response.json()[0]["item_id"] == "abc123"


@patch("strand_sort.api.review.commit_to_inventory")
@patch("strand_sort.api.review.review_queue")
def test_resolve_approve_commits_to_inventory(mock_queue, mock_commit, client, valid_donation_item):
    mock_queue.resolve_item.return_value = valid_donation_item
    mock_commit.return_value = {"status": "committed", "item_id": "abc123"}

    response = client.post(
        "/api/v1/review/resolve/abc123",
        json={"approved": True, "corrected_date": "2026-09-15", "notes": "verified manually"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved_and_committed"
    mock_queue.resolve_item.assert_called_once_with(
        item_id="abc123", approved=True, corrected_date="2026-09-15", notes="verified manually"
    )
    mock_commit.assert_called_once()


@patch("strand_sort.api.review.review_queue")
def test_resolve_reject(mock_queue, client):
    mock_queue.resolve_item.return_value = None

    response = client.post(
        "/api/v1/review/resolve/abc123",
        json={"approved": False},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected_and_discarded"


@patch("strand_sort.api.review.review_queue")
def test_resolve_item_not_found(mock_queue, client):
    mock_queue.resolve_item.side_effect = KeyError("Item abc123 not in review queue")

    response = client.post(
        "/api/v1/review/resolve/abc123",
        json={"approved": True},
    )
    assert response.status_code == 404


def test_donation_item_no_date_case_is_valid(no_date_donation_item):
    """Sanity check: 'NONE' as raw_date_text_found + expiration_date=None
    is a valid, expected state — not a validation error."""
    assert no_date_donation_item.raw_date_text_found == "NONE"
    assert no_date_donation_item.expiration_date is None