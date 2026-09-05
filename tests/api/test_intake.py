from unittest.mock import patch


def test_intake_rejects_empty_key_list(client):
    response = client.post("/api/v1/intake", json={"s3_keys": []})
    assert response.status_code == 400
    assert "At least one image is required" in response.json()["detail"]


@patch("strand_sort.api.intake.run_intake_workflow")
def test_intake_success(mock_workflow, client):
    mock_workflow.return_value = (
        "Item processed and committed.",
        {"item_id": "abc123", "requires_human_review": False, "review_reason": None, "image_urls": []},
    )
    response = client.post("/api/v1/intake", json={"s3_keys": ["pending-uploads/egg.jpg"]})
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Item processed and committed."
    assert body["item"]["item_id"] == "abc123"
    assert body["item"]["requires_human_review"] is False
    mock_workflow.assert_called_once()
    # The request body is just S3 keys now — no local files, no 6MB limit
    # regardless of how large the actual images are.
    _, kwargs = mock_workflow.call_args
    assert kwargs["image_sources"] == ["pending-uploads/egg.jpg"]


@patch("strand_sort.api.intake.run_intake_workflow")
def test_intake_success_with_null_item(mock_workflow, client):
    """A run that never reaches a settled outcome (e.g. crashes mid-extraction
    before either tool commits) reports item as null rather than fabricating one."""
    mock_workflow.return_value = ("Something went wrong before extraction finished.", None)
    response = client.post("/api/v1/intake", json={"s3_keys": ["pending-uploads/egg.jpg"]})
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
    response = client.post("/api/v1/intake", json={"s3_keys": ["pending-uploads/mystery.jpg"]})
    assert response.status_code == 200
    body = response.json()
    assert body["item"]["requires_human_review"] is True
    assert body["item"]["review_reason"] == "low-confidence date read"


@patch("strand_sort.api.intake.logger")
@patch("strand_sort.api.intake.run_intake_workflow")
def test_intake_workflow_failure_returns_500(mock_workflow, mock_logger, client):
    mock_workflow.side_effect = RuntimeError("model unavailable")
    response = client.post("/api/v1/intake", json={"s3_keys": ["pending-uploads/egg.jpg"]})
    assert response.status_code == 500
    assert "Intake workflow failed" in response.json()["detail"]
    # .exception() (not .error()) is what actually captures the stack trace —
    # this was the whole point of the fix (CloudWatch previously showed only
    # the final error string, no traceback, no indication of which line/
    # branch raised it).
    mock_logger.exception.assert_called_once()
    assert "model unavailable" in mock_logger.exception.call_args[0][0]


@patch("strand_sort.api.intake.logger")
@patch("strand_sort.api.intake.download_to_file")
def test_intake_video_fetch_failure_returns_400(mock_download, mock_logger, client):
    mock_download.side_effect = RuntimeError("no such key")
    response = client.post("/api/v1/intake/video", json={"s3_key": "pending-uploads/clip.mp4"})
    assert response.status_code == 400
    assert "Could not fetch uploaded video" in response.json()["detail"]
    mock_logger.exception.assert_called_once()


@patch("strand_sort.api.intake.run_intake_workflow")
@patch("strand_sort.api.intake.put_bytes")
@patch("strand_sort.api.intake.extract_frames")
@patch("strand_sort.api.intake.download_to_file")
def test_intake_video_success(mock_download, mock_extract_frames, mock_put_bytes, mock_workflow, client):
    mock_download.return_value = None
    mock_extract_frames.return_value = [b"fake-jpeg-1", b"fake-jpeg-2"]
    mock_put_bytes.side_effect = ["pending-uploads/frame-0.jpg", "pending-uploads/frame-1.jpg"]
    mock_workflow.return_value = (
        "Item processed and committed.",
        {"item_id": "abc123", "requires_human_review": False, "review_reason": None, "image_urls": []},
    )

    response = client.post("/api/v1/intake/video", json={"s3_key": "pending-uploads/clip.mp4"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Item processed and committed."
    assert body["item"]["requires_human_review"] is False
    mock_download.assert_called_once()
    mock_extract_frames.assert_called_once()
    # Each sampled frame gets re-uploaded to pending-uploads/ so the rest of
    # the pipeline can treat video and photo intake identically (a list of
    # S3 keys) from this point on.
    assert mock_put_bytes.call_count == 2
    mock_workflow.assert_called_once()
    _, kwargs = mock_workflow.call_args
    assert kwargs["image_sources"] == ["pending-uploads/frame-0.jpg", "pending-uploads/frame-1.jpg"]


@patch("strand_sort.api.intake.extract_frames")
@patch("strand_sort.api.intake.download_to_file")
def test_intake_video_frame_extraction_failure_returns_400(mock_download, mock_extract_frames, client):
    mock_download.return_value = None
    mock_extract_frames.side_effect = ValueError("No frames found in video")

    response = client.post("/api/v1/intake/video", json={"s3_key": "pending-uploads/clip.mp4"})

    assert response.status_code == 400
    assert "Could not process video" in response.json()["detail"]


@patch("strand_sort.api.intake.logger")
@patch("strand_sort.api.intake.run_intake_workflow")
@patch("strand_sort.api.intake.put_bytes")
@patch("strand_sort.api.intake.extract_frames")
@patch("strand_sort.api.intake.download_to_file")
def test_intake_video_workflow_failure_returns_500(
    mock_download, mock_extract_frames, mock_put_bytes, mock_workflow, mock_logger, client
):
    mock_download.return_value = None
    mock_extract_frames.return_value = [b"fake-jpeg-1"]
    mock_put_bytes.return_value = "pending-uploads/frame-0.jpg"
    mock_workflow.side_effect = RuntimeError("model unavailable")

    response = client.post("/api/v1/intake/video", json={"s3_key": "pending-uploads/clip.mp4"})

    assert response.status_code == 500
    assert "Intake workflow failed" in response.json()["detail"]
    mock_logger.exception.assert_called_once()
