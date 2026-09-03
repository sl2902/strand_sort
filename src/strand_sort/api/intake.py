import asyncio
import os
import shutil
import tempfile
from typing import Any

from fastapi import APIRouter, UploadFile, File, HTTPException
from loguru import logger

from strand_sort.agent.intake_agent import run_intake_workflow
from strand_sort.vision.video import extract_frames
from strand_sort.agent.rollback_hook import InventoryRollbackHook
from strand_sort.db.repository import get_inventory_repository
from strand_sort.storage.image_storage import resolve_image_urls

router = APIRouter()


def _with_resolved_images(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Same freshness rule as the inventory/review reads: S3 image references
    captured mid-workflow are durable keys, not presigned URLs — resolve them
    to something actually fetchable right before this response goes out."""
    if item is None:
        return None
    item["image_urls"] = resolve_image_urls(item.get("image_urls", []))
    return item


@router.post("/intake")
async def intake_item(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    """
    Upload a donation item photo to run vision extraction,
    idempotency checks, and inventory commitment
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

    rollback_hook = InventoryRollbackHook()
    try:
        # run_intake_workflow is synchronous and blocks on a live Bedrock/Gemini
        # call — running it inline here would stall FastAPI's single event loop
        # for the whole request, starving every other in-flight request (including
        # unrelated GET /inventory, GET /review/pending calls from other tabs).
        summary, item = await asyncio.to_thread(
            run_intake_workflow, image_paths=tmp_paths, hooks=[rollback_hook]
        )
        # if os.environ.get("STRAND_SORT_TEST_ROLLBACK"):  # TEMPORARY — remove after testing
        #     raise RuntimeError("Simulated post-commit failure for rollback testing")
        return {"summary": summary, "item": _with_resolved_images(item)}
    except Exception as e:
        rollback_count = len(rollback_hook.committed_actions)
        _rollback(rollback_hook.committed_actions)
        detail = (
            f"Intake workflow failed: {e}. Rolled back {rollback_count} action(s)."
            if rollback_count > 0
            else f"Intake workflow failed: {e}. No inventory changes to roll back."
        )
        raise HTTPException(status_code=500, detail=detail)
    finally:
       for p in tmp_paths:
            if os.path.exists(p):
                os.remove(p)


@router.post("/intake/video")
async def intake_video(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Upload a short donation item video (a volunteer panning around the item).
    Samples a handful of sharp, evenly-spaced frames from the clip and runs
    them through the same intake workflow used for still-image uploads.
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

        summary, item = await asyncio.to_thread(run_intake_workflow, image_paths=frame_paths)
        return {"summary": summary, "item": _with_resolved_images(item)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video intake workflow failed: {e}")
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