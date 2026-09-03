from unittest.mock import patch
from io import BytesIO


def test_intake_rejects_non_image_file(client):
    response = client.post(
        "/api/v1/intake",
        files=[("files", ("notes.txt", BytesIO(b"hello"), "text/plain"))],
    )
    assert response.status_code == 400
    assert "must be images" in response.json()["detail"]


@patch("strand_sort.api.intake.run_intake_workflow")
def test_intake_success(mock_workflow, client):
    mock_workflow.return_value = (
        "Item processed and committed.",
        {"item_id": "abc123", "requires_human_review": False, "review_reason": None, "image_urls": []},
    )
    response = client.post(
        "/api/v1/intake",
        files=[("files", ("egg.jpg", BytesIO(b"fake-image-bytes"), "image/jpeg"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Item processed and committed."
    assert body["item"]["item_id"] == "abc123"
    assert body["item"]["requires_human_review"] is False
    mock_workflow.assert_called_once()
    # Confirms the fix from earlier: called with image_paths=[...], not image_path=
    _, kwargs = mock_workflow.call_args
    assert "image_paths" in kwargs
    assert isinstance(kwargs["image_paths"], list)


@patch("strand_sort.api.intake.run_intake_workflow")
def test_intake_success_with_null_item(mock_workflow, client):
    """A run that never reaches a settled outcome (e.g. crashes mid-extraction
    before either tool commits) reports item as null rather than fabricating one."""
    mock_workflow.return_value = ("Something went wrong before extraction finished.", None)
    response = client.post(
        "/api/v1/intake",
        files=[("files", ("egg.jpg", BytesIO(b"fake-image-bytes"), "image/jpeg"))],
    )
    assert response.status_code == 200
    assert response.json() == {
        "summary": "Something went wrong before extraction finished.",
        "item": None,
    }


@patch("strand_sort.api.intake.run_intake_workflow")
def test_intake_flagged_item_reports_requires_review_true(mock_workflow, client):
    mock_workflow.return_value = (
        "This item has been flagged for human review due to a low-confidence expiry date.",
        {
            "item_id": "xyz789",
            "requires_human_review": True,
            "review_reason": "low-confidence date read",
            "image_urls": [],
        },
    )
    response = client.post(
        "/api/v1/intake",
        files=[("files", ("mystery.jpg", BytesIO(b"fake-image-bytes"), "image/jpeg"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["item"]["requires_human_review"] is True
    assert body["item"]["review_reason"] == "low-confidence date read"


@patch("strand_sort.api.intake.run_intake_workflow")
def test_intake_workflow_failure_returns_500(mock_workflow, client):
    mock_workflow.side_effect = RuntimeError("model unavailable")
    response = client.post(
        "/api/v1/intake",
        files=[("files", ("egg.jpg", BytesIO(b"fake-image-bytes"), "image/jpeg"))],
    )
    assert response.status_code == 500
    assert "Intake workflow failed" in response.json()["detail"]


def test_intake_video_rejects_non_video_file(client):
    response = client.post(
        "/api/v1/intake/video",
        files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 400
    assert "must be a video" in response.json()["detail"]


@patch("strand_sort.api.intake.run_intake_workflow")
@patch("strand_sort.api.intake.extract_frames")
def test_intake_video_success(mock_extract_frames, mock_workflow, client):
    mock_extract_frames.return_value = [b"fake-jpeg-1", b"fake-jpeg-2"]
    mock_workflow.return_value = (
        "Item processed and committed.",
        {"item_id": "abc123", "requires_human_review": False, "review_reason": None, "image_urls": []},
    )

    response = client.post(
        "/api/v1/intake/video",
        files={"file": ("scan.mp4", BytesIO(b"fake-video-bytes"), "video/mp4")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Item processed and committed."
    assert body["item"]["requires_human_review"] is False
    mock_extract_frames.assert_called_once()
    mock_workflow.assert_called_once()
    _, kwargs = mock_workflow.call_args
    assert "image_paths" in kwargs
    assert len(kwargs["image_paths"]) == 2


@patch("strand_sort.api.intake.extract_frames")
def test_intake_video_frame_extraction_failure_returns_400(mock_extract_frames, client):
    mock_extract_frames.side_effect = ValueError("No frames found in video")

    response = client.post(
        "/api/v1/intake/video",
        files={"file": ("scan.mp4", BytesIO(b"fake-video-bytes"), "video/mp4")},
    )

    assert response.status_code == 400
    assert "Could not process video" in response.json()["detail"]


@patch("strand_sort.api.intake.run_intake_workflow")
@patch("strand_sort.api.intake.extract_frames")
def test_intake_video_workflow_failure_returns_500(mock_extract_frames, mock_workflow, client):
    mock_extract_frames.return_value = [b"fake-jpeg-1"]
    mock_workflow.side_effect = RuntimeError("model unavailable")

    response = client.post(
        "/api/v1/intake/video",
        files={"file": ("scan.mp4", BytesIO(b"fake-video-bytes"), "video/mp4")},
    )

    assert response.status_code == 500
    assert "Intake workflow failed" in response.json()["detail"]
