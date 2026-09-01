import base64
from pathlib import Path
from typing import Any

from strands import tool
from strand_sort.models import DonationItem
from strand_sort.vision.extract import get_extractor
from strand_sort.agent.queue import review_queue
from strand_sort.db.repository import get_inventory_repository


def _encode_image(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("utf-8")


@tool
def scan_package_batch(image_paths: list[str]) -> dict[str, Any]:
    """
    Scans a batch of packaging images (file paths) for a single donation item,
    extracts product/date/dietary info, and flags whether human review is needed
    """
    images_base64 = [_encode_image(p) for p in image_paths]
    item: DonationItem = get_extractor(images_base64)
    
    if item.requires_human_review:
        review_queue.add_for_review(item)
        return {
            "status": "flagged_for_review",
            "item_id": item.item_id,
            "product_name": item.product_name,
            "reason": item.review_reason,
            "needs_review": True,
        }

    return {
        "status": "ready_for_commit",
        "item": item.model_dump(),
        "needs_review": False,
    }


@tool
def commit_to_inventory(item_data: dict[str, Any]) -> dict[str, Any]:
    """
    Persists a verified, non-expired DonationItem into the food bank inventory
    """
    repo = get_inventory_repository()
    repo.save_item(item_data)

    return {
        "status": "committed",
        "item_id": item_data.get("item_id"),
        "product_name": item_data.get("product_name"),
        "expiration_date": item_data.get("expiration_date"),
        "dietary_flags": item_data.get("dietary_flags", {}),
    }