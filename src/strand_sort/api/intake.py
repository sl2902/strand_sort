import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
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


@router.post("/intake")
async def intake_item(body: ProcessUploadRequest) -> dict[str, Any]:
    """
    Runs vision extraction, idempotency checks, and inventory commitment
    against images already uploaded to S3 (see /uploads/presign) — the
    request body here is just a small list of key strings regardless of how
    large or how many the actual images are, staying well under Lambda's 6MB
    synchronous payload limit.
    """
    if not body.s3_keys:
        raise HTTPException(status_code=400, detail="At least one image is required.")

    rollback_hook = InventoryRollbackHook()
    try:
        # run_intake_workflow is synchronous and blocks on a live Bedrock/Gemini
        # call — running it inline here would stall FastAPI's single event loop
        # for the whole request, starving every other in-flight request (including
        # unrelated GET /inventory, GET /review/pending calls from other tabs).
        summary, item = await asyncio.to_thread(
            run_intake_workflow, image_sources=body.s3_keys, hooks=[rollback_hook]
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


@router.post("/intake/video")
async def intake_video(body: ProcessVideoUploadRequest) -> dict[str, Any]:
    """
    Processes a short donation item video (a volunteer panning around the
    item), already uploaded to S3 (see /uploads/presign). Downloads it
    locally just long enough to sample a handful of sharp, evenly-spaced
    frames (cv2 needs a real file, not an S3 key), re-uploads those frames
    to pending-uploads/, then runs the same intake workflow used for
    still-image uploads — from that point on, video and photo intake are
    identical (a list of S3 keys).
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

        summary, item = await asyncio.to_thread(run_intake_workflow, image_sources=frame_keys)
        return {"summary": summary, "item": _with_resolved_images(item)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Video intake workflow failed: {e}")
        raise HTTPException(status_code=500, detail=f"Intake workflow failed: {e}")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


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
