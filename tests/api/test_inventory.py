from datetime import date, timedelta
from unittest.mock import patch, MagicMock


def _iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


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
    mock_repo.decrement_quantity.return_value = {"item_id": "abc", "quantity": 1}
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/checkout?quantity=1")
    assert response.status_code == 200
    mock_repo.decrement_quantity.assert_called_once_with("abc", 1)


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_checkout_insufficient_stock_returns_400(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.decrement_quantity.side_effect = ValueError("Insufficient stock!")
    mock_get_repo.return_value = mock_repo

    response = client.post("/api/v1/inventory/abc/checkout?quantity=99")
    assert response.status_code == 400


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