from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from strand_sort.models import DonationItem


def _iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


def _pending_item(**overrides):
    item = {
        "item_id": "abc123",
        "product_name": "Fresh Eggs",
        "category": "dairy_eggs",
        "expiration_date": "2026-09-15",
        "requires_human_review": True,
        "review_reason": "low-confidence date read",
        "quantity": 2,
        "image_urls": [],
    }
    item.update(overrides)
    return item


@patch("strand_sort.api.review.get_inventory_repository")
def test_list_review_queue_filters_to_pending_only(mock_get_repo, client):
    """Pending and committed rows live in the same table now — /review/pending
    must only surface requires_human_review=True ones, or resolved items
    would show up here forever too."""
    mock_repo = MagicMock()
    mock_repo.list_all.return_value = [
        _pending_item(item_id="abc123"),
        {"item_id": "already-committed", "product_name": "Milk", "requires_human_review": False, "image_urls": []},
    ]
    mock_get_repo.return_value = mock_repo

    response = client.get("/api/v1/review/pending")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["item_id"] == "abc123"


@patch("strand_sort.api.review.get_inventory_repository")
def test_pending_review_overrides_stale_is_expired(mock_get_repo, client):
    """Flagged items sit pending for however long a volunteer takes to get to
    them — a date that was fine when scanned can pass while it's still
    pending. is_expired/expiry_status must reflect today, not whatever was
    stored when the item was flagged."""
    mock_repo = MagicMock()
    mock_repo.list_all.return_value = [
        _pending_item(item_id="stale123", expiration_date=_iso(-3), is_expired=False)
    ]
    mock_get_repo.return_value = mock_repo

    body = client.get("/api/v1/review/pending").json()[0]
    assert body["is_expired"] is True
    assert body["expiry_status"] == "expired"


@patch("strand_sort.api.review.commit_to_inventory")
@patch("strand_sort.api.review.get_inventory_repository")
def test_resolve_approve_commits_in_place(mock_get_repo, mock_commit, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = _pending_item()
    mock_get_repo.return_value = mock_repo
    mock_commit.return_value = {"status": "committed", "item_id": "abc123"}

    response = client.post(
        "/api/v1/review/resolve/abc123",
        json={"approved": True, "corrected_date": "2026-09-20", "notes": "verified manually"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved_and_committed"

    committed_payload = mock_commit.call_args[0][0]
    assert committed_payload["requires_human_review"] is False
    assert committed_payload["expiration_date"] == "2026-09-20"
    mock_repo.delete_item.assert_not_called()


@patch("strand_sort.api.review.get_inventory_repository")
def test_resolve_reject_deletes_the_row(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = _pending_item()
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/review/resolve/abc123", json={"approved": False})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected_and_discarded"
    mock_repo.delete_item.assert_called_once_with("abc123")


@patch("strand_sort.api.review.get_inventory_repository")
def test_resolve_item_not_found(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = None
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/review/resolve/abc123", json={"approved": True})
    assert response.status_code == 404


@patch("strand_sort.api.review.get_inventory_repository")
def test_resolve_already_committed_item_returns_404(mock_get_repo, client):
    """Item exists but isn't pending review (already resolved, or never
    flagged) — resolving it again isn't a valid action."""
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = _pending_item(requires_human_review=False)
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/review/resolve/abc123", json={"approved": True})
    assert response.status_code == 404


def test_donation_item_no_date_case_is_valid():
    """Sanity check: 'NONE' as raw_date_text_found + expiration_date=None
    is a valid, expected state — not a validation error."""
    item = DonationItem(
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
    assert item.raw_date_text_found == "NONE"
    assert item.expiration_date is None
