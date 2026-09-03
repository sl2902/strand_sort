from unittest.mock import patch, MagicMock


@patch("strand_sort.api.inventory.get_inventory_repository")
def test_list_inventory_no_filter_calls_list_all(mock_get_repo, client):
    mock_repo = MagicMock()
    mock_repo.list_all.return_value = [{"item_id": "abc", "product_name": "Eggs"}]
    mock_get_repo.return_value = mock_repo

    response = client.get("/api/v1/inventory")
    assert response.status_code == 200
    assert response.json() == [{"item_id": "abc", "product_name": "Eggs", "image_urls": []}]
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