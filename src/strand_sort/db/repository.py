# strand_sort/db/repository.py
import sqlite3
import json
import boto3
from abc import ABC, abstractmethod
from typing import Any, Dict
from strand_sort.config import settings

class InventoryRepository(ABC):
    @abstractmethod
    def save_item(self, item_data: Dict[str, Any]) -> None:
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

    def save_item(self, item_data: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO inventory (item_id, product_name, payload) VALUES (?, ?, ?)",
                (item_data["item_id"], item_data["product_name"], json.dumps(item_data))
            )

class DynamoDBRepository(InventoryRepository):
    def __init__(self, table_name: str = settings.dynamodb_table_name):
        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = dynamodb.Table(table_name)

    def save_item(self, item_data: Dict[str, Any]) -> None:
        self.table.put_item(Item=item_data)

# Factory function to return active engine based on config switch
def get_inventory_repository() -> InventoryRepository:
    if settings.db_engine == "dynamodb":
        return DynamoDBRepository()
    return SQLiteRepository()