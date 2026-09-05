from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from strand_sort.agent.tools import commit_to_inventory
from strand_sort.db.repository import get_inventory_repository
from strand_sort.storage.image_storage import resolve_image_urls
from strand_sort.expiry import ExpiryStatus, compute_expiry_status

router = APIRouter()


class ReviewResolutionRequest(BaseModel):
    approved: bool
    corrected_date: Optional[str] = None
    notes: Optional[str] = None


def _decorate_item(item: dict[str, Any]) -> dict[str, Any]:
    """Same freshness rule as api/inventory.py — recomputed on every read,
    never trusted from whatever was set when the item was first flagged."""
    item["image_urls"] = resolve_image_urls(item.get("image_urls", []))
    item["thumbnail_urls"] = resolve_image_urls(item.get("thumbnail_urls", []))
    status = compute_expiry_status(item.get("expiration_date"))
    item["expiry_status"] = status
    item["is_expired"] = status == ExpiryStatus.EXPIRED
    return item


@router.get("/review/pending")
def get_pending_reviews() -> List[dict[str, Any]]:
    """Retrieve all flagged items awaiting human verification. Pending items
    live in the same inventory table as committed stock, distinguished only
    by requires_human_review — there's no separate in-memory queue to wipe
    on a dev-server restart."""
    repo = get_inventory_repository()
    pending = [item for item in repo.list_all() if item.get("requires_human_review")]
    return [_decorate_item(item) for item in pending]


@router.post("/review/resolve/{item_id}")
def resolve_review(item_id: str, request: ReviewResolutionRequest) -> dict[str, Any]:
    """
    Approve or reject a flagged item. Approved items are committed in place
    (same row, requires_human_review flips to False); rejected items are
    deleted outright rather than kept around with a "rejected" status.
    """
    repo = get_inventory_repository()
    existing = repo.get_by_id(item_id)
    if not existing or not existing.get("requires_human_review"):
        raise HTTPException(status_code=404, detail="Item not found in review queue")

    if not request.approved:
        repo.delete_item(item_id)
        return {"status": "rejected_and_discarded", "item_id": item_id}

    existing["requires_human_review"] = False
    if request.corrected_date:
        existing["expiration_date"] = request.corrected_date
        existing["is_expired"] = False

    commit_result = commit_to_inventory(existing)
    return {"status": "approved_and_committed", "item": commit_result}
