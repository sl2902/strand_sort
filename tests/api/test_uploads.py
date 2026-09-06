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


# ---- Extension validation ----


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_defaults_to_image_kind(mock_presign, client):
    """kind defaults to "image" when the caller omits it — existing
    callers that predate the kind field still get image validation."""
    mock_presign.return_value = ("pending-uploads/a.jpg", "https://example.com/a")
    response = client.post("/api/v1/uploads/presign", json={"filenames": ["photo.jpg"]})
    assert response.status_code == 200


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_rejects_disallowed_image_extension(mock_presign, client):
    response = client.post("/api/v1/uploads/presign", json={"filenames": ["malware.exe"], "kind": "image"})
    assert response.status_code == 400
    assert ".exe" in response.json()["detail"]
    mock_presign.assert_not_called()


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_rejects_pdf_for_image_kind(mock_presign, client):
    response = client.post("/api/v1/uploads/presign", json={"filenames": ["document.pdf"], "kind": "image"})
    assert response.status_code == 400
    assert ".pdf" in response.json()["detail"]
    mock_presign.assert_not_called()


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_accepts_every_allowed_image_extension(mock_presign, client):
    mock_presign.side_effect = lambda filename: (f"pending-uploads/x{filename}", "https://example.com/x")
    for filename in ["photo.jpg", "photo.JPEG", "photo.png", "photo.webp"]:
        response = client.post("/api/v1/uploads/presign", json={"filenames": [filename], "kind": "image"})
        assert response.status_code == 200, f"{filename} should be allowed"


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_rejects_image_extension_for_video_kind(mock_presign, client):
    """The two allowlists are genuinely separate — a valid image extension
    must not slip through when the caller says kind="video"."""
    response = client.post("/api/v1/uploads/presign", json={"filenames": ["photo.jpg"], "kind": "video"})
    assert response.status_code == 400
    mock_presign.assert_not_called()


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_accepts_every_allowed_video_extension(mock_presign, client):
    mock_presign.side_effect = lambda filename: (f"pending-uploads/x{filename}", "https://example.com/x")
    for filename in ["clip.mp4", "clip.MOV", "clip.webm"]:
        response = client.post("/api/v1/uploads/presign", json={"filenames": [filename], "kind": "video"})
        assert response.status_code == 200, f"{filename} should be allowed"


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_rejects_extensionless_filename(mock_presign, client):
    response = client.post("/api/v1/uploads/presign", json={"filenames": ["noextension"], "kind": "image"})
    assert response.status_code == 400
    assert "(none)" in response.json()["detail"]
    mock_presign.assert_not_called()


@patch("strand_sort.api.uploads.presign_put_url")
def test_presign_stops_at_first_disallowed_filename_in_a_batch(mock_presign, client):
    """One bad file in a multi-file request must reject the whole batch
    rather than silently presigning the good ones and dropping the bad."""
    response = client.post(
        "/api/v1/uploads/presign", json={"filenames": ["good.jpg", "bad.exe"], "kind": "image"}
    )
    assert response.status_code == 400
    mock_presign.assert_not_called()
