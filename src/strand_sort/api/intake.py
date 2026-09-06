import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from loguru import logger

from strand_sort.agent.intake_agent import run_intake_workflow
from strand_sort.vision.video import extract_frames
from strand_sort.agent.rollback_hook import InventoryRollbackHook
from strand_sort.db.repository import get_inventory_repository
from strand_sort.storage.image_storage import resolve_image_urls
from strand_sort.storage.pending_uploads import download_to_file, put_bytes

router = APIRouter()


class ProcessUploadRequest(BaseModel):
    s3_keys: list[str]  # keys already uploaded to pending-uploads/ via /uploads/presign


class ProcessVideoUploadRequest(BaseModel):
    s3_key: str  # single video, already uploaded to pending-uploads/


def _with_resolved_images(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Same freshness rule as the inventory/review reads: S3 image references
    captured mid-workflow are durable keys, not presigned URLs — resolve them
    to something actually fetchable right before this response goes out."""
    if item is None:
        return None
    item["image_urls"] = resolve_image_urls(item.get("image_urls", []))
    item["thumbnail_urls"] = resolve_image_urls(item.get("thumbnail_urls", []))
    return item


async def _run_workflow_with_rollback(image_sources: list[str]) -> dict[str, Any]:
    """Shared by every intake route (photo/video, local/S3) — same
    rollback/error handling regardless of where image_sources came from."""
    rollback_hook = InventoryRollbackHook()
    try:
        # run_intake_workflow is synchronous and blocks on a live Bedrock/Gemini
        # call — running it inline here would stall FastAPI's single event loop
        # for the whole request, starving every other in-flight request (including
        # unrelated GET /inventory, GET /review/pending calls from other tabs).
        summary, item = await asyncio.to_thread(
            run_intake_workflow, image_sources=image_sources, hooks=[rollback_hook]
        )
        return {"summary": summary, "item": _with_resolved_images(item)}
    except Exception as e:
        # .exception() (not .error()) — captures the full stack trace, the
        # piece missing from CloudWatch when all that survives is the final
        # error string with no indication of which line/branch raised it.
        logger.exception(f"Intake workflow failed: {e}")
        rollback_count = len(rollback_hook.committed_actions)
        _rollback(rollback_hook.committed_actions)
        detail = (
            f"Intake workflow failed: {e}. Rolled back {rollback_count} action(s)."
            if rollback_count > 0
            else f"Intake workflow failed: {e}. No inventory changes to roll back."
        )
        raise HTTPException(status_code=500, detail=detail)


@router.post("/intake")
async def intake_item(body: ProcessUploadRequest) -> dict[str, Any]:
    """
    Used when storage_backend=s3: runs vision extraction, idempotency
    checks, and inventory commitment against images already uploaded to S3
    (see /uploads/presign) — the request body here is just a small list of
    key strings regardless of how large or how many the actual images are,
    staying well under Lambda's 6MB synchronous payload limit.
    """
    if not body.s3_keys:
        raise HTTPException(status_code=400, detail="At least one image is required.")
    return await _run_workflow_with_rollback(body.s3_keys)


@router.post("/intake/local")
async def intake_item_local(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    """
    Used when storage_backend=local: plain multipart upload straight to
    this endpoint, no AWS/S3 dependency at all — the counterpart to
    POST /intake for fully offline local dev.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one image is required.")

    for f in files:
        if not f.content_type or not f.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="All uploaded files must be images.")

    tmp_paths = []
    for f in files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            shutil.copyfileobj(f.file, tmp)
            tmp_paths.append(tmp.name)

    try:
        return await _run_workflow_with_rollback(tmp_paths)
    finally:
        for p in tmp_paths:
            if os.path.exists(p):
                os.remove(p)


@router.post("/intake/video")
async def intake_video(body: ProcessVideoUploadRequest) -> dict[str, Any]:
    """
    Used when storage_backend=s3. Processes a short donation item video (a
    volunteer panning around the item), already uploaded to S3 (see
    /uploads/presign). Downloads it locally just long enough to sample a
    handful of sharp, evenly-spaced frames (cv2 needs a real file, not an
    S3 key), re-uploads those frames to pending-uploads/, then runs the
    same intake workflow used for still-image uploads — from that point
    on, video and photo intake are identical (a list of S3 keys).
    """
    suffix = Path(body.s3_key).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        video_path = tmp.name

    try:
        try:
            download_to_file(body.s3_key, video_path)
        except Exception as e:
            logger.exception(f"Could not fetch uploaded video: {e}")
            raise HTTPException(status_code=400, detail=f"Could not fetch uploaded video: {e}")

        try:
            frames = extract_frames(video_path, max_frames=4)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Could not process video: {e}")

        frame_keys = [put_bytes(frame_bytes) for frame_bytes in frames]
        return await _run_workflow_with_rollback(frame_keys)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Video intake workflow failed: {e}")
        raise HTTPException(status_code=500, detail=f"Intake workflow failed: {e}")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


@router.post("/intake/video/local")
async def intake_video_local(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Used when storage_backend=local — the counterpart to POST /intake/video
    for fully offline local dev. Video arrives as a plain multipart upload;
    sampled frames are written to local temp files instead of re-uploaded
    to S3.
    """
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a video.")

    suffix = os.path.splitext(file.filename or "")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        video_path = tmp.name

    frame_paths: list[str] = []
    try:
        try:
            frames = extract_frames(video_path, max_frames=4)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Could not process video: {e}")

        for frame_bytes in frames:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as frame_tmp:
                frame_tmp.write(frame_bytes)
                frame_paths.append(frame_tmp.name)

        return await _run_workflow_with_rollback(frame_paths)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Video intake workflow failed: {e}")
        raise HTTPException(status_code=500, detail=f"Intake workflow failed: {e}")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)
        for p in frame_paths:
            if os.path.exists(p):
                os.remove(p)


def _rollback(actions: list[dict]) -> None:
    repo = get_inventory_repository()
    for action in reversed(actions):
        try:
            if action["type"] == "increment":
                repo.decrement_quantity(action["item_id"], action["qty"])
            elif action["type"] == "new_batch":
                repo.delete_item(action["item_id"])
            logger.warning(f"Rolled back: {action}")
        except Exception as rollback_err:
            logger.error(f"Rollback FAILED for {action}: {rollback_err}")
