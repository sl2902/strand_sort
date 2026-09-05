import base64
from typing import Any

from loguru import logger
from strands import tool
from strand_sort.models import DonationItem, NO_EXPIRATION_DATE
from strand_sort.vision.extract import get_extractor
from strand_sort.db.repository import get_inventory_repository
from strand_sort.vision.extract import generate_idempotency_key
from strand_sort.storage.image_storage import get_image_storage
from strand_sort.storage.pending_uploads import get_bytes as get_pending_upload_bytes


def _encode_image_from_s3(s3_key: str) -> str:
    return base64.b64encode(get_pending_upload_bytes(s3_key)).decode("utf-8")


@tool
def scan_package_batch(image_sources: list[str]) -> dict[str, Any]:
    """
    Scans a batch of packaging images (S3 keys under pending-uploads/,
    already there via the browser's presigned-upload flow) for a single
    donation item, extracts product/date/dietary info, and flags whether
    human review is needed
    """
    logger.info(f"scan_package_batch starting | sources={image_sources}")

    images_base64 = [_encode_image_from_s3(key) for key in image_sources]
    item: DonationItem = get_extractor(images_base64)

    storage = get_image_storage()
    item.image_urls = storage.save_images_from_s3(item.item_id, image_sources)

    if item.requires_human_review:
        # Persisted straight to the inventory table with
        # requires_human_review=True — that flag is the single source of
        # truth for "pending review" vs "committed" (see api/review.py and
        # api/inventory.py, which filter on it). No separate in-memory
        # queue: that was wiped on every dev-server reload.
        repo = get_inventory_repository()
        repo.save_item(item.model_dump())
        result = {
            "status": "flagged_for_review",
            "item_id": item.item_id,
            "product_name": item.product_name,
            "reason": item.review_reason,
            "needs_review": True,
            "item": item.model_dump(),
        }
        logger.info(f"scan_package_batch result | status={result['status']} | needs_review={result['needs_review']}")
        return result

    result = {
        "status": "ready_for_commit",
        "item": item.model_dump(),
        "needs_review": False,
    }
    logger.info(f"scan_package_batch result | status={result['status']} | needs_review={result['needs_review']}")
    return result


@tool
def commit_to_inventory(item_data: dict[str, Any]) -> dict[str, Any]:
    """
    Checks for idempotency and duplicate items before committing a verified item to inventory
    """
    logger.info(f"commit_to_inventory starting | item_id={item_data.get('item_id')}")

    repo = get_inventory_repository()

    product_name = item_data.get("product_name", "").strip()
    # `.get(..., "")` only substitutes when the key is ABSENT — a present-
    # but-None value (e.g. old data from before the sentinel fix) would
    # still slip through as str(None) == "None", a nonsense literal string
    # that isn't actually a date. `or NO_EXPIRATION_DATE` catches both a
    # missing key and an explicit None/"" the same way _to_donation_item
    # does (vision/extract.py) — defense in depth, not the primary fix.
    expiration_date = str(item_data.get("expiration_date") or NO_EXPIRATION_DATE).strip()
    incoming_qty = int(item_data.get("quantity", 1))

    # Compute idempotency hash and bind top-level attributes
    idempotency_key = generate_idempotency_key(product_name, expiration_date)
    item_data["idempotency_key"] = idempotency_key
    item_data["expiration_date"] = expiration_date  # Ensure normalized string presence
    item_data["quantity"] = incoming_qty
    # A committed item is never pending review, regardless of what the
    # caller passed in — this is what makes it show up in Inventory instead
    # of the Review queue (both read from this same table, filtered on this
    # flag; see api/inventory.py and api/review.py).
    item_data["requires_human_review"] = False

    # Check for existing batch in active stock
    existing_item = repo.check_duplicate_active_inventory(product_name, expiration_date)
    if existing_item:
        updated_item = repo.increment_quantity(
            item_id=existing_item["item_id"],
            additional_qty=incoming_qty,
            image_urls=item_data.get("image_urls"),
        )
        incoming_item_id = item_data.get("item_id")
        if incoming_item_id and incoming_item_id != existing_item["item_id"]:
            # item_data may already have its own row (e.g. it was sitting
            # pending review before being approved, or re-scanned under a
            # fresh item_id) — now merged into existing_item's row above, so
            # the original row would otherwise linger as an orphan (and, if
            # it was still requires_human_review=True, keep showing up in
            # the Review queue forever). No-op if that row never existed.
            repo.delete_item(incoming_item_id)
        result = {
            "status": "quantity_updated",
            "action": "incremented_existing_batch",
            "item_id": existing_item["item_id"],
            "product_name": product_name,
            "expiration_date": expiration_date,
            "added_quantity": incoming_qty,
            "total_quantity": updated_item.get("quantity", existing_item.get("quantity", 1) + incoming_qty),
            "image_urls": updated_item.get("image_urls", []),
            "item": updated_item,
            "message": f"Added {incoming_qty} unit(s) to existing stock of '{product_name}' (Expires: {expiration_date})."
        }
        logger.info(f"commit_to_inventory result | status={result['status']}")
        return result

    # Persist new batch if no match exists. If item_data's item_id already
    # has a row (e.g. this is an approved review item), INSERT OR REPLACE
    # overwrites it in place — same record, now committed.
    repo.save_item(item_data)

    result = {
        "status": "committed",
        "action": "created_new_batch",
        "item_id": item_data.get("item_id"),
        "product_name": product_name,
        "expiration_date": expiration_date,
        "quantity": incoming_qty,
        "item": item_data,
        "message": f"Registered new batch of {incoming_qty} x '{product_name}' (Expires: {expiration_date}) to inventory."
    }
    logger.info(f"commit_to_inventory result | status={result['status']}")
    return result

@tool
def search_inventory(product_name: str) -> list[dict[str, Any]]:
    """
    Searches the food bank inventory for existing items matching a product name
    """
    repo = get_inventory_repository()
    return repo.search_by_name(product_name)

@tool
def fetch_item_details(item_id: str) -> dict[str, Any]:
    """
    Fetches exact inventory details for a specific item using its item_id
    """
    repo = get_inventory_repository()
    item = repo.get_by_id(item_id)
    if not item:
        return {"status": "error", "message": f"Item {item_id} not found."}
    return {"status": "success", "item": item}

@tool
def checkout_from_inventory(item_id: str, quantity_to_remove: int = 1) -> dict[str, Any]:
    """
    Decrements stock quantity when items are distributed or removed from the food bank
    
    Args:
        item_id: The unique identifier of the batch/item in inventory
        quantity_to_remove: The number of units being distributed (default 1)
    """
    if quantity_to_remove <= 0:
        return {
            "status": "error",
            "message": "Quantity to remove must be greater than zero."
        }

    repo = get_inventory_repository()

    try:
        updated_item = repo.decrement_quantity(item_id, quantity_to_remove)
        remaining_qty = updated_item.get("quantity", 0)

        if remaining_qty == 0:
            return {
                "status": "depleted",
                "item_id": item_id,
                "product_name": updated_item.get("product_name"),
                "removed_quantity": quantity_to_remove,
                "remaining_quantity": 0,
                "message": f"Successfully checked out {quantity_to_remove} unit(s). Batch is now completely depleted."
            }

        return {
            "status": "success",
            "item_id": item_id,
            "product_name": updated_item.get("product_name"),
            "removed_quantity": quantity_to_remove,
            "remaining_quantity": remaining_qty,
            "message": f"Successfully checked out {quantity_to_remove} unit(s). {remaining_qty} unit(s) remaining in stock."
        }

    except ValueError as e:
        return {
            "status": "error",
            "item_id": item_id,
            "message": str(e)
        }