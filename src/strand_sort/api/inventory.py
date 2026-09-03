from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from strand_sort.db.repository import get_inventory_repository
from strand_sort.storage.image_storage import resolve_image_urls

router = APIRouter()


def _with_resolved_images(item: dict[str, Any]) -> dict[str, Any]:
    """Regenerates fetchable image URLs on every read — S3 presigned URLs
    expire, so what's stored on the item is a durable reference, never a URL
    that might already be stale by the time a client sees it."""
    item["image_urls"] = resolve_image_urls(item.get("image_urls", []))
    return item


@router.get("/inventory")
def list_inventory(name: Optional[str] = Query(None, description="Filter by product name")) -> list[dict[str, Any]]:
    """List all stock items, or search by product name."""
    repo = get_inventory_repository()
    items = repo.search_by_name(name) if name else repo.list_all()
    return [_with_resolved_images(item) for item in items]


@router.get("/inventory/{item_id}")
def get_item(item_id: str) -> dict[str, Any]:
    """Retrieve complete item metadata including nutrition and dietary flags."""
    repo = get_inventory_repository()
    item = repo.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return _with_resolved_images(item)


@router.post("/inventory/{item_id}/checkout")
def checkout_item(item_id: str, quantity: int = 1) -> dict[str, Any]:
    """Decrement stock when items are distributed."""
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero.")

    repo = get_inventory_repository()
    try:
        return repo.decrement_quantity(item_id, quantity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/inventory/{item_id}")
def update_item(item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Corrects fields on an existing item — e.g. manually verified nutrition values."""
    repo = get_inventory_repository()
    try:
        return repo.update_item(item_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))