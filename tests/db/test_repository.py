import os
import sqlite3
import pytest
import boto3
from decimal import Decimal
from moto import mock_aws

from strand_sort.db.repository import (
    SQLiteRepository,
    DynamoDBRepository,
    get_inventory_repository,
)


@pytest.fixture
def sample_item():
    """Sample donation item data structure extracted by vision workflow."""
    return {
        "item_id": "test-uuid-1234",
        "product_name": "Organic Milk",
        "expiration_date": "2026-10-15",
        "quantity": 5,
        "idempotency_key": "hash_milk_20261015",
        "requires_human_review": False,
        "dietary_flags": {"gluten_free": True, "vegan": False},
        "nutrition_facts": {"protein_g": 8.0, "sugars_g": 12.0},
    }


# ============================================================================
# SQLiteRepository Tests (6 Tests)
# ============================================================================

class TestSQLiteRepository:

    @pytest.fixture
    def sqlite_repo(self, tmp_path):
        db_file = tmp_path / "test_inventory.db"
        return SQLiteRepository(db_path=str(db_file))

    def test_save_and_get_by_id(self, sqlite_repo, sample_item):
        sqlite_repo.save_item(sample_item)
        fetched = sqlite_repo.get_by_id(sample_item["item_id"])

        assert fetched is not None
        assert fetched["item_id"] == sample_item["item_id"]
        assert fetched["product_name"] == "Organic Milk"
        assert fetched["expiration_date"] == "2026-10-15"
        assert fetched["quantity"] == 5

    def test_get_by_id_not_found(self, sqlite_repo):
        result = sqlite_repo.get_by_id("non-existent-id")
        assert result is None

    def test_search_by_name(self, sqlite_repo, sample_item):
        sqlite_repo.save_item(sample_item)
        results = sqlite_repo.search_by_name("Organic Milk")
        assert len(results) == 1

    def test_check_duplicate_active_inventory(self, sqlite_repo, sample_item):
        sqlite_repo.save_item(sample_item)
        existing = sqlite_repo.check_duplicate_active_inventory("Organic Milk", "2026-10-15")
        assert existing is not None
        assert existing["item_id"] == sample_item["item_id"]

    def test_check_duplicate_active_inventory_skips_pending_review_rows(self, sqlite_repo, sample_item):
        """A row still awaiting human review shares this table now but isn't
        'active inventory' yet — must not match as a duplicate to increment
        against (this would also cause a resolved review item to spuriously
        match itself)."""
        pending = dict(sample_item, item_id="pending-id", requires_human_review=True)
        sqlite_repo.save_item(pending)

        existing = sqlite_repo.check_duplicate_active_inventory("Organic Milk", "2026-10-15")
        assert existing is None

    def test_check_duplicate_active_inventory_finds_committed_past_pending(self, sqlite_repo, sample_item):
        """Both a pending-review row and a committed row exist for the same
        product/date — the committed one must be the match, regardless of
        SQL row ordering."""
        pending = dict(sample_item, item_id="pending-id", requires_human_review=True)
        committed = dict(sample_item, item_id="committed-id", requires_human_review=False)
        sqlite_repo.save_item(pending)
        sqlite_repo.save_item(committed)

        existing = sqlite_repo.check_duplicate_active_inventory("Organic Milk", "2026-10-15")
        assert existing is not None
        assert existing["item_id"] == "committed-id"

    def test_increment_quantity(self, sqlite_repo, sample_item):
        sqlite_repo.save_item(sample_item)
        updated = sqlite_repo.increment_quantity(sample_item["item_id"], additional_qty=3)
        assert updated["quantity"] == 8

    def test_decrement_quantity_success(self, sqlite_repo, sample_item):
        sqlite_repo.save_item(sample_item)
        updated = sqlite_repo.decrement_quantity(sample_item["item_id"], qty_to_remove=2)
        assert updated["quantity"] == 3

    def test_increment_quantity_updates_column_not_just_payload(self, sqlite_repo, sample_item):
        sqlite_repo.save_item(sample_item)
        sqlite_repo.increment_quantity(sample_item["item_id"], additional_qty=3)

        with sqlite3.connect(sqlite_repo.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (sample_item["item_id"],))
            column_value = cursor.fetchone()[0]

        assert column_value == 8  # will currently FAIL — column stays at 5


# ============================================================================
# DynamoDBRepository Tests (6 Tests)
# ============================================================================

class TestDynamoDBRepository:

    @pytest.fixture
    def dynamodb_table(self):
        with mock_aws():
            os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
            dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

            table = dynamodb.create_table(
                TableName="foodbank_inventory_test",
                KeySchema=[{"AttributeName": "item_id", "KeyType": "HASH"}],
                AttributeDefinitions=[
                    {"AttributeName": "item_id", "AttributeType": "S"},
                    {"AttributeName": "product_name", "AttributeType": "S"},
                    {"AttributeName": "idempotency_key", "AttributeType": "S"},
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "ProductNameIndex",
                        "KeySchema": [{"AttributeName": "product_name", "KeyType": "HASH"}],
                        "Projection": {"ProjectionType": "ALL"},
                    },
                    {
                        "IndexName": "IdempotencyKeyIndex",
                        "KeySchema": [{"AttributeName": "idempotency_key", "KeyType": "HASH"}],
                        "Projection": {"ProjectionType": "ALL"},
                    },
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            yield table

    @pytest.fixture
    def dynamo_repo(self, dynamodb_table):
        return DynamoDBRepository(table_name="foodbank_inventory_test")

    def test_save_and_get_by_id(self, dynamo_repo, sample_item):
        dynamo_repo.save_item(sample_item)
        fetched = dynamo_repo.get_by_id(sample_item["item_id"])

        assert fetched is not None
        assert fetched["item_id"] == sample_item["item_id"]
        assert fetched["product_name"] == "Organic Milk"

    def test_get_by_id_not_found(self, dynamo_repo):
        result = dynamo_repo.get_by_id("non-existent-id")
        assert result is None

    def test_search_by_name_via_index(self, dynamo_repo, sample_item):
        dynamo_repo.save_item(sample_item)
        results = dynamo_repo.search_by_name("Organic Milk")
        assert len(results) == 1

    def test_check_duplicate_active_inventory(self, dynamo_repo, sample_item):
        dynamo_repo.save_item(sample_item)
        existing = dynamo_repo.check_duplicate_active_inventory("Organic Milk", "2026-10-15")
        assert existing is not None

    def test_check_duplicate_active_inventory_skips_pending_review_rows(self, dynamo_repo, sample_item):
        pending = dict(sample_item, item_id="pending-id", requires_human_review=True)
        dynamo_repo.save_item(pending)

        existing = dynamo_repo.check_duplicate_active_inventory("Organic Milk", "2026-10-15")
        assert existing is None

    def test_increment_quantity(self, dynamo_repo, sample_item):
        dynamo_repo.save_item(sample_item)
        updated = dynamo_repo.increment_quantity(sample_item["item_id"], additional_qty=5)
        assert updated["quantity"] == 10

    def test_decrement_quantity_success(self, dynamo_repo, sample_item):
        dynamo_repo.save_item(sample_item)
        updated = dynamo_repo.decrement_quantity(sample_item["item_id"], qty_to_remove=2)
        assert updated["quantity"] == 3


# ============================================================================
# Factory Method Switching Test (1 Test)
# ============================================================================

def test_get_inventory_repository_factory(monkeypatch, tmp_path):
    monkeypatch.setattr("strand_sort.config.settings.db_engine", "sqlite")
    monkeypatch.setattr("strand_sort.config.settings.sqlite_db_path", str(tmp_path / "factory.db"))
    
    repo = get_inventory_repository()
    assert isinstance(repo, SQLiteRepository)