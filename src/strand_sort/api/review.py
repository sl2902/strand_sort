from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from strand_sort.agent.queue import review_queue
from strand_sort.agent.tools import commit_to_inventory
from strand_sort.models import DonationItem
from strand_sort.storage.image_storage import resolve_image_urls

router = APIRouter()


class ReviewResolutionRequest(BaseModel):
    approved: bool
    corrected_date: Optional[str] = None
    notes: Optional[str] = None


@router.get("/review/pending", response_model=List[DonationItem])
def get_pending_reviews():
    """Retrieve all flagged items awaiting human verification"""
    items = review_queue.get_pending()
    for item in items:
        item.image_urls = resolve_image_urls(item.image_urls)
    return items


@router.post("/review/resolve/{item_id}")
def resolve_review(item_id: str, request: ReviewResolutionRequest):
    """
    Approve or reject a flagged item. Approved items are automatically
    committed to inventory
    """
    try:
        resolved_item = review_queue.resolve_item(
            item_id=item_id,
            approved=request.approved,
            corrected_date=request.corrected_date,
            notes=request.notes,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found in review queue")

    if request.approved:
        commit_result = commit_to_inventory(resolved_item.model_dump())
        return {"status": "approved_and_committed", "item": commit_result}

    return {"status": "rejected_and_discarded", "item_id": item_id}