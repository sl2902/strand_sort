from datetime import timedelta
from unittest.mock import patch, MagicMock

from strand_sort.expiry import today_ist


def _iso(days_from_today: int) -> str:
    # today_ist(), not date.today() — must match what compute_expiry_status
    # itself anchors to, or these tests go flaky near the IST/UTC day
    # boundary on a non-IST machine (e.g. a UTC CI runner). See
    # tests/test_expiry.py's TestTodayIstAnchoring for the actual bug this
    # guards against.
    return (today_ist() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_list_inventory_overrides_stale_is_expired_false(mock_get_repo, client):
    """The core bug: an item stored with is_expired=False (correct at scan
    time) whose expiration_date has since passed must come back corrected —
    never the stale stored value."""
    mock_repo = MagicMock()
    mock_repo.list_all.return_value = [
        {
            "item_id": "abc",
            "product_name": "Old Eggs",
            "expiration_date": _iso(-5),
            "is_expired": False,  # stale, wrong by the time this is read
        }
    ]
    mock_get_repo.return_value = mock_repo

    body = client.get("/api/v1/inventory").json()[0]
    assert body["is_expired"] is True
    assert body["expiry_status"] == "expired"


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_list_inventory_overrides_stale_is_expired_true(mock_get_repo, client):
    """Same bug, other direction — a stored is_expired=True must not leak
    through if the item is actually still fine."""
    mock_repo = MagicMock()
    mock_repo.list_all.return_value = [
        {
            "item_id": "abc",
            "product_name": "Fresh Eggs",
            "expiration_date": _iso(30),
            "is_expired": True,  # stale/wrong
        }
    ]
    mock_get_repo.return_value = mock_repo

    body = client.get("/api/v1/inventory").json()[0]
    assert body["is_expired"] is False
    assert body["expiry_status"] == "fine"


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_list_inventory_near_expiry_item(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.list_all.return_value = [
        {"item_id": "abc", "product_name": "Soon-expiring Milk", "expiration_date": _iso(3)}
    ]
    mock_get_repo.return_value = mock_repo

    body = client.get("/api/v1/inventory").json()[0]
    assert body["expiry_status"] == "near_expiry"
    assert body["is_expired"] is False


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_list_inventory_no_filter_calls_list_all(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.list_all.return_value = [{"item_id": "abc", "product_name": "Eggs"}]
    mock_get_repo.return_value = mock_repo

    response = client.get("/api/v1/inventory")
    assert response.status_code == 200
    assert response.json() == [
        {
            "item_id": "abc",
            "product_name": "Eggs",
            "image_urls": [],
            "thumbnail_urls": [],
            "expiry_status": None,
            "is_expired": False,
        }
    ]
    mock_repo.list_all.assert_called_once()
    mock_repo.search_by_name.assert_not_called()


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_list_inventory_with_name_filter(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.search_by_name.return_value = [{"item_id": "abc", "product_name": "Eggs"}]
    mock_get_repo.return_value = mock_repo

    response = client.get("/api/v1/inventory?name=Eggs")
    assert response.status_code == 200
    mock_repo.search_by_name.assert_called_once_with("Eggs")
    mock_repo.list_all.assert_not_called()


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_list_inventory_excludes_pending_review_items(mock_get_repo, client):
    """Pending-review items live in the same table now (see api/review.py) —
    they must not leak into the normal Inventory listing, or the item would
    show up both as verified stock AND awaiting review simultaneously."""
    mock_repo = MagicMock()
    mock_repo.list_all.return_value = [
        {"item_id": "committed", "product_name": "Eggs", "requires_human_review": False},
        {"item_id": "pending", "product_name": "Milk", "requires_human_review": True},
    ]
    mock_get_repo.return_value = mock_repo

    response = client.get("/api/v1/inventory")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["item_id"] == "committed"


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_get_item_found(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {"item_id": "abc", "product_name": "Eggs"}
    mock_get_repo.return_value = mock_repo

    response = client.get("/api/v1/inventory/abc")
    assert response.status_code == 200
    assert response.json()["item_id"] == "abc"


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_get_item_not_found(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = None
    mock_get_repo.return_value = mock_repo

    response = client.get("/api/v1/inventory/nonexistent")
    assert response.status_code == 404


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_get_item_pending_review_returns_404(mock_get_repo, client):
    """A pending-review item isn't real inventory yet — direct lookup by id
    must 404 the same as if it didn't exist, so e.g. checkout can't target
    unverified stock."""
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {"item_id": "abc", "product_name": "Eggs", "requires_human_review": True}
    mock_get_repo.return_value = mock_repo

    response = client.get("/api/v1/inventory/abc")
    assert response.status_code == 404


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_checkout_rejects_zero_or_negative_quantity(mock_get_repo, client):
    response = client.post("/api/v1/inventory/abc/checkout?quantity=0")
    assert response.status_code == 400


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_checkout_success(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {"item_id": "abc", "expiration_date": _iso(30)}
    mock_repo.decrement_quantity.return_value = {"item_id": "abc", "quantity": 1}
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/checkout?quantity=1")
    assert response.status_code == 200
    mock_repo.decrement_quantity.assert_called_once_with("abc", 1)


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_checkout_insufficient_stock_returns_400(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {"item_id": "abc", "expiration_date": _iso(30)}
    mock_repo.decrement_quantity.side_effect = ValueError("Insufficient stock!")
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/checkout?quantity=99")
    assert response.status_code == 400


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_checkout_not_found_returns_404(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = None
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/nonexistent/checkout?quantity=1")
    assert response.status_code == 404
    mock_repo.decrement_quantity.assert_not_called()


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_checkout_blocked_for_expired_item(mock_get_repo, client):
    """The reported gap: staff could distribute an expired item through
    the app with no warning or block anywhere. How an expired item
    actually gets disposed of is out of scope — the app just shouldn't
    offer distributing it at all."""
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {"item_id": "abc", "expiration_date": _iso(-1)}
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/checkout?quantity=1")
    assert response.status_code == 400
    mock_repo.decrement_quantity.assert_not_called()


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_checkout_allowed_for_near_expiry_item(mock_get_repo, client):
    """Only actually-expired items are blocked — near_expiry is still a
    legitimate, distributable state (that's the whole point of surfacing
    it early on the Expiring Soon page)."""
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {"item_id": "abc", "expiration_date": _iso(3)}
    mock_repo.decrement_quantity.return_value = {"item_id": "abc", "quantity": 1}
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/checkout?quantity=1")
    assert response.status_code == 200
    mock_repo.decrement_quantity.assert_called_once_with("abc", 1)


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_checkout_blocked_uses_freshly_computed_expiry_not_a_stored_value(mock_get_repo, client):
    """Same "never trust a stored value" rule as everywhere else in this
    file — a stale stored is_expired=False must not let checkout through
    for an item whose date has since actually passed."""
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {
        "item_id": "abc",
        "expiration_date": _iso(-5),
        "is_expired": False,  # stale, wrong by the time this is read
    }
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/checkout?quantity=1")
    assert response.status_code == 400
    mock_repo.decrement_quantity.assert_not_called()


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_update_item_success(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.update_item.return_value = {"item_id": "abc", "product_name": "Corrected Eggs"}
    mock_get_repo.return_value = mock_repo

    response = client.patch("/api/v1/inventory/abc", json={"product_name": "Corrected Eggs"})
    assert response.status_code == 200
    mock_repo.update_item.assert_called_once_with("abc", {"product_name": "Corrected Eggs"})


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_update_item_not_found(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.update_item.side_effect = ValueError("Item xyz not found")
    mock_get_repo.return_value = mock_repo

    response = client.patch("/api/v1/inventory/xyz", json={"product_name": "X"})
    assert response.status_code == 404


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_delete_item_success(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {"item_id": "abc", "product_name": "Eggs"}
    mock_get_repo.return_value = mock_repo

    response = client.delete("/api/v1/inventory/abc")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "item_id": "abc"}
    mock_repo.delete_item.assert_called_once_with("abc")


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_delete_item_not_found(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = None
    mock_get_repo.return_value = mock_repo

    response = client.delete("/api/v1/inventory/nonexistent")
    assert response.status_code == 404
    mock_repo.delete_item.assert_not_called()


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_reject_item_success_when_expired(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {
        "item_id": "abc",
        "product_name": "Old Eggs",
        "expiration_date": _iso(-5),
    }
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/reject")
    assert response.status_code == 200
    assert response.json() == {"status": "rejected", "item_id": "abc"}
    mock_repo.delete_item.assert_called_once_with("abc")


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_reject_item_rejects_when_not_expired(mock_get_repo, client):
    """Gated server-side, not just hidden in the UI — a client can't reject
    an item that isn't actually expired just by hitting this endpoint
    directly."""
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {
        "item_id": "abc",
        "product_name": "Fresh Eggs",
        "expiration_date": _iso(30),
    }
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/reject")
    assert response.status_code == 400
    mock_repo.delete_item.assert_not_called()


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_reject_item_not_found(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = None
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/nonexistent/reject")
    assert response.status_code == 404
    mock_repo.delete_item.assert_not_called()


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_reject_item_hides_pending_review_items(mock_get_repo, client):
    """Same visibility rule as get_item — an item still awaiting review
    doesn't exist from Inventory's perspective yet, expired or not."""
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {
        "item_id": "abc",
        "product_name": "Flagged Milk",
        "expiration_date": _iso(-5),
        "requires_human_review": True,
    }
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/reject")
    assert response.status_code == 404
    mock_repo.delete_item.assert_not_called()