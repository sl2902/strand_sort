from decimal import Decimal
import sqlite3
import json
import boto3
from abc import ABC, abstractmethod
from typing import Any, Optional
import botocore
from boto3.dynamodb.conditions import Key, Attr

from strand_sort.config import settings


class InventoryRepository(ABC):
    @abstractmethod
    def save_item(self, item_data: dict[str, Any]) -> None:
        pass

    @abstractmethod
    def find_by_hash(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        """Checks if this exact package hash has already been processed (Idempotency)"""
        pass

    @abstractmethod
    def check_duplicate_active_inventory(self, product_name: str, expiration_date: str) -> Optional[dict[str, Any]]:
        """Checks if an identical active item exists in inventory"""
        pass

    @abstractmethod
    def increment_quantity(
        self,
        item_id: str,
        additional_qty: int,
        image_urls: Optional[list[str]] = None,
        thumbnail_urls: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Increments quantity of an existing item, updates image_urls/
        thumbnail_urls if provided and not already set, and returns the
        updated record"""
        pass

    @abstractmethod
    def decrement_quantity(self, item_id: str, qty_to_remove: int) -> dict[str, Any]:
        """Decrements quantity of an existing item and handles stock depletion."""
        pass

    @abstractmethod
    def list_all(self) -> list[dict[str, Any]]:
        """Returns all items currently in inventory."""
        pass

    @abstractmethod
    def update_item(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merges the given fields into an existing item's stored data"""
        pass

    def delete_item(self, item_id: str) -> None:
        pass


class SQLiteRepository(InventoryRepository):
    def __init__(self, db_path: str = settings.sqlite_db_path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode once at startup
            conn.execute("PRAGMA synchronous=NORMAL;") # Reduce fsync overhead safely
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    item_id TEXT PRIMARY KEY,
                    product_name TEXT,
                    expiration_date TEXT,
                    idempotency_key TEXT,
                    quantity INTEGER DEFAULT 1,
                    payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def list_all(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload FROM inventory")
            return [json.loads(row[0]) for row in cursor.fetchall()]

    def save_item(self, item_data: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO inventory 
                (item_id, product_name, expiration_date, idempotency_key, quantity, payload) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item_data["item_id"],           # 1. Extracted for fast SQL Indexing
                    item_data["product_name"],       # 2. Extracted for fast SQL Indexing
                    item_data.get("expiration_date"),# 3. Extracted for fast SQL Indexing
                    item_data.get("idempotency_key"),# 4. Extracted for fast SQL Indexing
                    item_data.get("quantity", 1),    # 5. Extracted for Atomic Math
                    json.dumps(item_data)            # 6. EVERYTHING (all fields) saved in JSON
                )
            )
            conn.commit()

    def save_items_bulk(self, items_data: list[dict[str, Any]]) -> None:
        """Inserts or updates thousands of items in a single disk flush"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO inventory 
                (item_id, product_name, expiration_date, idempotency_key, quantity, payload) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["item_id"],
                        item["product_name"],
                        item.get("expiration_date"),
                        item.get("idempotency_key"),
                        item.get("quantity", 1),
                        json.dumps(item)
                    )
                    for item in items_data
                ]
            )

    def get_by_id(self, item_id: str) -> Optional[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload FROM inventory WHERE item_id = ?", (item_id,))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def search_by_name(self, product_name: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Case-insensitive substring search in SQLite
            cursor.execute(
                "SELECT payload FROM inventory WHERE product_name LIKE ?",
                (f"%{product_name}%",),
            )
            rows = cursor.fetchall()
            return [json.loads(row[0]) for row in rows]

    def find_by_hash(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload FROM inventory WHERE idempotency_key = ?", (idempotency_key,))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def check_duplicate_active_inventory(self, product_name: str, expiration_date: str) -> Optional[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT payload FROM inventory WHERE LOWER(product_name) = LOWER(?) AND expiration_date = ?",
                (product_name.strip(), expiration_date.strip())
            )
            # Pending-review rows share this table now (see save_item calls in
            # scan_package_batch) — a row still awaiting review isn't "active
            # inventory" yet and must never match here, so skip past it to
            # find a genuinely committed duplicate, if any.
            for (payload_json,) in cursor.fetchall():
                payload = json.loads(payload_json)
                if not payload.get("requires_human_review"):
                    return payload
            return None

    def increment_quantity(
        self,
        item_id: str,
        additional_qty: int,
        image_urls: Optional[list[str]] = None,
        thumbnail_urls: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload FROM inventory WHERE item_id = ?", (item_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Item {item_id} not found")

            payload = json.loads(row[0])
            payload["quantity"] = payload.get("quantity", 1) + additional_qty

            if image_urls and not payload.get("image_urls"):
                payload["image_urls"] = image_urls
            if thumbnail_urls and not payload.get("thumbnail_urls"):
                payload["thumbnail_urls"] = thumbnail_urls

            cursor.execute(
                "UPDATE inventory SET payload = ?, quantity = ? WHERE item_id = ?",
                (json.dumps(payload), payload["quantity"], item_id)
            )
            return payload

    def decrement_quantity(self, item_id: str, qty_to_remove: int) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload FROM inventory WHERE item_id = ?", (item_id,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Item ID {item_id} not found in inventory.")
            
            payload = json.loads(row[0])
            current_qty = int(payload.get("quantity", 1))

            if qty_to_remove > current_qty:
                raise ValueError(
                    f"Insufficient stock! Requested to remove {qty_to_remove}, "
                    f"but only {current_qty} unit(s) available."
                )

            new_qty = current_qty - qty_to_remove
            payload["quantity"] = new_qty

            if new_qty == 0:
                # Option A: Delete row or mark status as 'exhausted'
                payload["status"] = "exhausted"
                cursor.execute(
                    "UPDATE inventory SET payload = ?, quantity = ? WHERE item_id = ?",
                    (json.dumps(payload), new_qty, item_id)
                )
            else:
                cursor.execute(
                    "UPDATE inventory SET payload = ?, quantity = ? WHERE item_id = ?",
                    (json.dumps(payload), new_qty, item_id)
                )

            return payload

    def update_item(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload FROM inventory WHERE item_id = ?", (item_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Item {item_id} not found")
            payload = json.loads(row[0])
            payload.update(updates)
            cursor.execute(
                "UPDATE inventory SET payload = ?, product_name = ?, expiration_date = ?, quantity = ? WHERE item_id = ?",
                (json.dumps(payload), payload.get("product_name"), payload.get("expiration_date"), payload.get("quantity", 1), item_id),
            )
            return payload

    def delete_item(self, item_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM inventory WHERE item_id = ?", (item_id,))

class DynamoDBRepository(InventoryRepository):
    def __init__(self, table_name: str = settings.dynamodb_table_name):
        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = dynamodb.Table(table_name)

    def list_all(self) -> list[dict[str, Any]]:
        response = self.table.scan()
        return [convert_decimals_to_native(item) for item in response.get("Items", [])]

    def save_item(self, item_data: dict[str, Any]) -> None:
        """
        Saves the entire item_data dict directly as a DynamoDB item.
        Top-level fields (item_id, product_name, expiration_date, idempotency_key, quantity)
        are automatically available for GSI indexing and queries
        """
        # Ensure quantity defaults to int if missing
        sanitized_item = convert_floats_to_decimals(item_data)
        sanitized_item["quantity"] = int(sanitized_item.get("quantity", 1))
        self.table.put_item(Item=sanitized_item)

    def save_items_bulk(self, items_data: list[dict[str, Any]]) -> None:
        """
        Bulk inserts or replaces items in DynamoDB using batch_writer.
        Automatically chunks requests into batches of 25 and handles retries
        """
        with self.table.batch_writer() as batch:
            for item in items_data:
                # Convert floats to Decimal for DynamoDB compliance
                sanitized_item = convert_floats_to_decimals(item)
                
                # Ensure quantity defaults to integer
                sanitized_item["quantity"] = int(sanitized_item.get("quantity", 1))
                
                # Queue item into the batch buffer
                batch.put_item(Item=sanitized_item)

    def get_by_id(self, item_id: str) -> Optional[dict[str, Any]]:
        response = self.table.get_item(Key={"item_id": item_id})
        item = response.get("Item")
        return convert_decimals_to_native(item) if item is not None else None

    def search_by_name(self, product_name: str) -> list[dict[str, Any]]:
        """
        Uses a Global Secondary Index (ProductNameExpirationIndex, composite
        product_name HASH + expiration_date RANGE) for exact/prefix matches.
        Querying with only the HASH key condition is valid DynamoDB
        behavior on a composite-key index — returns every item sharing that
        product_name regardless of expiration_date, which is what this
        method's callers (search_inventory tool, GET /inventory?name=) want.
        Falls back to Attr().contains() Scan if partial matching across values is needed
        """
        # Search via GSI for exact or begins_with product name
        response = self.table.query(
            IndexName="ProductNameExpirationIndex",
            KeyConditionExpression=Key("product_name").eq(product_name)
        )
        items = response.get("Items", [])

        # Fallback to Scan with filter if query yields no exact match
        if not items:
            scan_response = self.table.scan(
                FilterExpression=Attr("product_name").contains(product_name)
            )
            items = scan_response.get("Items", [])

        return [convert_decimals_to_native(item) for item in items]

    def find_by_hash(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        # IdempotencyKeyIndex GSI query
        response = self.table.query(
            IndexName="IdempotencyKeyIndex",
            KeyConditionExpression=Key("idempotency_key").eq(idempotency_key)
        )
        items = response.get("Items", [])
        return convert_decimals_to_native(items[0]) if items else None

    def check_duplicate_active_inventory(self, product_name: str, expiration_date: str) -> Optional[dict[str, Any]]:
        # ProductNameExpirationIndex is a composite key (product_name HASH +
        # expiration_date RANGE) — both belong in KeyConditionExpression,
        # not a FilterExpression, now that the index actually has a range
        # key to match against. requires_human_review isn't part of the key
        # schema, so it stays a filter: pending-review rows share this table
        # now and must be excluded from "active inventory" matches.
        # not_exists() covers rows saved before this attribute was
        # consistently present.
        response = self.table.query(
            IndexName="ProductNameExpirationIndex",
            KeyConditionExpression=Key("product_name").eq(product_name) & Key("expiration_date").eq(expiration_date),
            FilterExpression=Attr("requires_human_review").eq(False) | Attr("requires_human_review").not_exists()
        )
        items = response.get("Items", [])
        return convert_decimals_to_native(items[0]) if items else None

    def increment_quantity(
        self,
        item_id: str,
        additional_qty: int,
        image_urls: Optional[list[str]] = None,
        thumbnail_urls: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        # Previously branched into two separate update_item calls, only
        # assigning the result to `response` in the else branch — taking the
        # if branch (existing item had no image_urls yet, new ones provided)
        # raised UnboundLocalError on the return below. Single call covers
        # every combination of image_urls/thumbnail_urls being newly set.
        existing = self.get_by_id(item_id) or {}
        set_clauses = []
        expr_values: dict[str, Any] = {":q": additional_qty}

        if image_urls and not existing.get("image_urls"):
            set_clauses.append("image_urls = :image_urls")
            expr_values[":image_urls"] = image_urls
        if thumbnail_urls and not existing.get("thumbnail_urls"):
            set_clauses.append("thumbnail_urls = :thumbnail_urls")
            expr_values[":thumbnail_urls"] = thumbnail_urls

        update_expression = "ADD quantity :q"
        if set_clauses:
            update_expression += " SET " + ", ".join(set_clauses)

        response = self.table.update_item(
            Key={"item_id": item_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expr_values,
            ReturnValues="ALL_NEW",
        )
        return convert_decimals_to_native(response.get("Attributes", {}))

    def decrement_quantity(self, item_id: str, qty_to_remove: int) -> dict[str, Any]:
        """Atomically decrements quantity with a condition check to prevent negative stock"""
        try:
            response = self.table.update_item(
                Key={"item_id": item_id},
                UpdateExpression="ADD quantity :dec",
                ConditionExpression="attribute_exists(item_id) AND quantity >= :req_qty",
                ExpressionAttributeValues={
                    ":dec": -qty_to_remove,
                    ":req_qty": qty_to_remove
                },
                ReturnValues="ALL_NEW"
            )
            return convert_decimals_to_native(response.get("Attributes", {}))
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError(f"Insufficient stock for item ID {item_id}.")
            raise

    def update_item(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_by_id(item_id)  # already Decimal-free, see get_by_id
        if not existing:
            raise ValueError(f"Item {item_id} not found")
        existing.update(updates)
        self.save_item(existing)  # put_item overwrite, same item_id
        return existing

    def delete_item(self, item_id: str) -> None:
        self.table.delete_item(Key={"item_id": item_id})

# Factory function to return active engine based on config switch
def get_inventory_repository() -> InventoryRepository:
    if settings.db_engine == "dynamodb":
        return DynamoDBRepository()
    return SQLiteRepository()

def convert_floats_to_decimals(obj: Any) -> Any:
    """Recursively converts float types to Decimal for DynamoDB compatibility"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_floats_to_decimals(v) for v in obj]
    return obj

def convert_decimals_to_native(obj: Any) -> Any:
    """Inverse of convert_floats_to_decimals — boto3's DynamoDB resource API
    always returns Decimal for Number-type attributes (quantity, any float
    field), regardless of what was originally stored. json.dumps() can't
    serialize Decimal at all; this is what silently broke the Strands @tool
    boundary's json.dumps(result) call for any tool returning a DynamoDB
    dict once it happened to contain one (falls back to str(result),
    producing single-quoted, unparseable "JSON" — the exact
    "Could not parse ... result" symptom). Call this on every value read
    back from DynamoDB, not just ones a tool might return — every read
    path shares the same repository methods."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: convert_decimals_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_decimals_to_native(v) for v in obj]
    return obj