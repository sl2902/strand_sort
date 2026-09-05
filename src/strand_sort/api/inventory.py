from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from strand_sort.db.repository import get_inventory_repository
from strand_sort.models import NO_EXPIRATION_DATE
from strand_sort.storage.image_storage import resolve_image_urls
from strand_sort.expiry import ExpiryStatus, compute_expiry_status

router = APIRouter()


def _decorate_item(item: dict[str, Any]) -> dict[str, Any]:
    """Applied on every read — nothing here should ever be trusted from what
    got persisted at intake/commit time, both can silently go stale:
    presigned S3 URLs expire, and "is this expired" changes daily even
    though the stored date doesn't."""
    item["image_urls"] = resolve_image_urls(item.get("image_urls", []))
    item["thumbnail_urls"] = resolve_image_urls(item.get("thumbnail_urls", []))
    status = compute_expiry_status(item.get("expiration_date"))
    item["expiry_status"] = status
    item["is_expired"] = status == ExpiryStatus.EXPIRED
    return item


@router.get("/inventory")
def list_inventory(name: Optional[str] = Query(None, description="Filter by product name")) -> list[dict[str, Any]]:
    """List all stock items, or search by product name. Items still awaiting
    human review live in the same table but are excluded here — they only
    surface via /review/pending until resolved."""
    repo = get_inventory_repository()
    items = repo.search_by_name(name) if name else repo.list_all()
    committed = [item for item in items if not item.get("requires_human_review")]
    return [_decorate_item(item) for item in committed]


@router.get("/inventory/{item_id}")
def get_item(item_id: str) -> dict[str, Any]:
    """Retrieve complete item metadata including nutrition and dietary flags.
    404s for items still pending review — from Inventory's perspective they
    don't exist yet (e.g. checking out unverified stock shouldn't be
    possible), only /review/pending exposes them."""
    repo = get_inventory_repository()
    item = repo.get_by_id(item_id)
    if not item or item.get("requires_human_review"):
        raise HTTPException(status_code=404, detail="Item not found")
    return _decorate_item(item)


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
    if "expiration_date" in updates and not updates["expiration_date"]:
        # e.g. the item-edit form's "clear date" action sends None here.
        # Never persist None/"" — DynamoDB's expiration_date GSI range key
        # rejects both outright (see NO_EXPIRATION_DATE in models.py).
        updates["expiration_date"] = NO_EXPIRATION_DATE

    repo = get_inventory_repository()
    try:
        return repo.update_item(item_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/inventory/{item_id}")
def delete_item(item_id: str) -> dict[str, Any]:
    """Permanently removes an item from inventory — no soft-delete, no undo."""
    repo = get_inventory_repository()
    existing = repo.get_by_id(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    repo.delete_item(item_id)
    return {"status": "deleted", "item_id": item_id}