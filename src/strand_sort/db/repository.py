# strand_sort/db/repository.py
import sqlite3
import json
import boto3
from abc import ABC, abstractmethod
from typing import Any, Optional
from boto3.dynamodb.conditions import Key, Attr

from strand_sort.config import settings

class InventoryRepository(ABC):
    @abstractmethod
    def save_item(self, item_data: dict[str, Any]) -> None:
        pass

class SQLiteRepository(InventoryRepository):
    def __init__(self, db_path: str = settings.sqlite_db_path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    item_id TEXT PRIMARY KEY,
                    product_name TEXT,
                    payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def save_item(self, item_data: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO inventory (item_id, product_name, payload) VALUES (?, ?, ?)",
                (item_data["item_id"], item_data["product_name"], json.dumps(item_data))
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

class DynamoDBRepository(InventoryRepository):
    def __init__(self, table_name: str = settings.dynamodb_table_name):
        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = dynamodb.Table(table_name)

    def save_item(self, item_data: dict[str, Any]) -> None:
        self.table.put_item(Item=item_data)

    def get_by_id(self, item_id: str) -> Optional[dict[str, Any]]:
        response = self.table.get_item(Key={"item_id": item_id})
        return response.get("Item")

    def search_by_name(self, product_name: str) -> list[dict[str, Any]]:
        """
        Uses a Global Secondary Index (ProductNameIndex) for exact/prefix matches.
        Falls back to Attr().contains() Scan if partial matching across values is needed
        """
        # Search via GSI for exact or begins_with product name
        response = self.table.query(
            IndexName="ProductNameIndex",
            KeyConditionExpression=Key("product_name").eq(product_name)
        )
        items = response.get("Items", [])
        
        # Fallback to Scan with filter if query yields no exact match
        if not items:
            scan_response = self.table.scan(
                FilterExpression=Attr("product_name").contains(product_name)
            )
            items = scan_response.get("Items", [])

        return items

# Factory function to return active engine based on config switch
def get_inventory_repository() -> InventoryRepository:
    if settings.db_engine == "dynamodb":
        return DynamoDBRepository()
    return SQLiteRepository()