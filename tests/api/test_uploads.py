from unittest.mock import patch


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_returns_one_result_per_filename(mock_presign, client):
    mock_presign.side_effect = [
        ("pending-uploads/a.jpg", "https://example.com/a"),
        ("pending-uploads/b.png", "https://example.com/b"),
    ]

    response = client.post("/api/v1/uploads/presign", json={"filenames": ["photo.jpg", "photo.png"]})

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {"s3_key": "pending-uploads/a.jpg", "upload_url": "https://example.com/a"},
        {"s3_key": "pending-uploads/b.png", "upload_url": "https://example.com/b"},
    ]
    assert mock_presign.call_count == 2


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_empty_filenames_returns_empty_list(mock_presign, client):
    response = client.post("/api/v1/uploads/presign", json={"filenames": []})
    assert response.status_code == 200
    assert response.json() == []
    mock_presign.assert_not_called()
