import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from strand_sort.agent.tools import commit_to_inventory, scan_package_batch
from strand_sort.db.repository import DynamoDBRepository
from strand_sort.models import NO_EXPIRATION_DATE, DietaryFlags, DonationItem, NutritionFacts, VisionExtraction
from strand_sort.vision.extract import _to_donation_item


def _fake_item(**overrides) -> DonationItem:
    defaults = dict(
        item_id="abc",
        product_name="Milk",
        category="dairy_liquid",
        raw_date_text_found="NONE",
        expiration_date=None,
        requires_human_review=False,
    )
    defaults.update(overrides)
    return DonationItem(**defaults)


class TestScanPackageBatchReadsFromS3:
    """image_sources are S3 keys under pending-uploads/ (the presigned
    browser-upload flow) — scan_package_batch must fetch bytes for
    extraction from S3, not local disk, and persist final images via the
    S3-sourced storage method."""

    @patch("strand_sort.agent.tools.get_image_storage")
    @patch("strand_sort.agent.tools.get_extractor")
    @patch("strand_sort.agent.tools._encode_image_from_s3")
    def test_fetches_each_source_from_s3_for_extraction(self, mock_encode, mock_extractor, mock_get_storage):
        mock_encode.return_value = "ZmFrZQ=="
        mock_extractor.return_value = _fake_item()
        mock_get_storage.return_value = MagicMock(save_images_from_s3=MagicMock(return_value=[]))

        scan_package_batch(image_sources=["pending-uploads/a.jpg", "pending-uploads/b.jpg"])

        assert mock_encode.call_args_list == [
            (("pending-uploads/a.jpg",),),
            (("pending-uploads/b.jpg",),),
        ]
        mock_extractor.assert_called_once_with(["ZmFrZQ==", "ZmFrZQ=="])

    @patch("strand_sort.agent.tools.get_image_storage")
    @patch("strand_sort.agent.tools.get_extractor")
    @patch("strand_sort.agent.tools._encode_image_from_s3")
    def test_persists_final_images_via_save_images_from_s3(self, mock_encode, mock_extractor, mock_get_storage):
        mock_encode.return_value = "ZmFrZQ=="
        mock_extractor.return_value = _fake_item()
        mock_storage = MagicMock()
        mock_storage.save_images_from_s3.return_value = ["abc/0.jpg"]
        mock_get_storage.return_value = mock_storage

        result = scan_package_batch(image_sources=["pending-uploads/a.jpg"])

        mock_storage.save_images_from_s3.assert_called_once_with("abc", ["pending-uploads/a.jpg"])
        assert result["item"]["image_urls"] == ["abc/0.jpg"]

    @patch("strand_sort.agent.tools.get_inventory_repository")
    @patch("strand_sort.agent.tools.get_image_storage")
    @patch("strand_sort.agent.tools.get_extractor")
    @patch("strand_sort.agent.tools._encode_image_from_s3")
    def test_flagged_item_is_saved_to_repository(
        self, mock_encode, mock_extractor, mock_get_storage, mock_get_repo
    ):
        mock_encode.return_value = "ZmFrZQ=="
        mock_extractor.return_value = _fake_item(requires_human_review=True, review_reason="unreadable date")
        mock_get_storage.return_value = MagicMock(save_images_from_s3=MagicMock(return_value=[]))
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        result = scan_package_batch(image_sources=["pending-uploads/a.jpg"])

        assert result["status"] == "flagged_for_review"
        mock_repo.save_item.assert_called_once()
        saved = mock_repo.save_item.call_args[0][0]
        assert saved["requires_human_review"] is True


class TestVisibilityLogging:
    """Added to close a gap where a request completed cleanly (no exception
    anywhere in CloudWatch) but returned an empty summary and null item,
    with no log trace of whether either tool actually ran or what it
    returned."""

    @patch("strand_sort.agent.tools.logger")
    @patch("strand_sort.agent.tools.get_image_storage")
    @patch("strand_sort.agent.tools.get_extractor")
    @patch("strand_sort.agent.tools._encode_image_from_s3")
    def test_scan_package_batch_logs_start_and_result(self, mock_encode, mock_extractor, mock_get_storage, mock_logger):
        mock_encode.return_value = "ZmFrZQ=="
        mock_extractor.return_value = _fake_item(requires_human_review=False)
        mock_get_storage.return_value = MagicMock(save_images_from_s3=MagicMock(return_value=[]))

        scan_package_batch(image_sources=["pending-uploads/a.jpg"])

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("scan_package_batch starting" in msg and "pending-uploads/a.jpg" in msg for msg in logged)
        assert any("scan_package_batch result" in msg and "ready_for_commit" in msg for msg in logged)

    @patch("strand_sort.agent.tools.logger")
    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_commit_to_inventory_logs_start_and_result(self, mock_get_repo, mock_logger):
        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = None
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({"item_id": "abc123", "product_name": "Milk", "expiration_date": "2026-10-01"})

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("commit_to_inventory starting" in msg and "abc123" in msg for msg in logged)
        assert any("commit_to_inventory result" in msg and "committed" in msg for msg in logged)


class TestCommitToInventoryClearsPendingReview:
    """Flagged items are now persisted straight to the inventory table with
    requires_human_review=True (see scan_package_batch) instead of a
    separate in-memory queue. commit_to_inventory must always leave the
    committed row with requires_human_review=False, and must clean up any
    now-orphaned pending-review row left behind when a commit merges into a
    *different* existing row — otherwise that orphan lingers in
    /review/pending forever."""

    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_new_batch_commit_clears_requires_human_review(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = None
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({
            "item_id": "milk-abc123",
            "product_name": "Milk",
            "expiration_date": "2026-10-01",
            "quantity": 1,
            "requires_human_review": True,  # e.g. an approved review item
        })

        saved = mock_repo.save_item.call_args[0][0]
        assert saved["requires_human_review"] is False

    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_increment_existing_batch_deletes_orphaned_pending_row(self, mock_get_repo):
        """The incoming item_id (e.g. a fresh re-scan, or an approved review
        item) is different from the existing duplicate's item_id — its own
        row, if any, must be deleted so it doesn't linger."""
        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = {"item_id": "existing-id", "quantity": 2}
        mock_repo.increment_quantity.return_value = {"item_id": "existing-id", "quantity": 3, "image_urls": []}
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({
            "item_id": "some-new-scan-id",
            "product_name": "Milk",
            "expiration_date": "2026-10-01",
            "quantity": 1,
        })

        mock_repo.delete_item.assert_called_once_with("some-new-scan-id")

    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_increment_does_not_delete_the_row_it_just_incremented(self, mock_get_repo):
        """Exact re-scan producing the same item_id as the existing duplicate
        — deleting here would destroy the row increment_quantity just
        updated."""
        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = {"item_id": "same-id", "quantity": 2}
        mock_repo.increment_quantity.return_value = {"item_id": "same-id", "quantity": 3, "image_urls": []}
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({
            "item_id": "same-id",
            "product_name": "Milk",
            "expiration_date": "2026-10-01",
            "quantity": 1,
        })

        mock_repo.delete_item.assert_not_called()

    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_commit_new_batch_does_not_call_delete(self, mock_get_repo):
        """No pre-existing duplicate at all — nothing to clean up."""
        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = None
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({
            "item_id": "never-flagged",
            "product_name": "Eggs",
            "expiration_date": "2026-10-01",
            "quantity": 1,
        })

        mock_repo.delete_item.assert_not_called()


class TestCommitToInventoryCoercesRawNoneExpirationDate:
    """str(item_data.get("expiration_date", "")) previously turned a
    present-but-None value into the literal 4-char string "None" (Python's
    str(None)), not an empty string — .get's default only applies when the
    key is ABSENT, never when it's present with value None. Defense in
    depth alongside the primary fix in _to_donation_item/DonationItem's
    own default."""

    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_none_expiration_date_becomes_the_sentinel_not_the_string_none(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = None
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({
            "item_id": "old-data-item",
            "product_name": "Old Stock Item",
            "expiration_date": None,
            "quantity": 1,
        })

        saved = mock_repo.save_item.call_args[0][0]
        assert saved["expiration_date"] == NO_EXPIRATION_DATE
        assert saved["expiration_date"] != "None"


class TestScanPackageBatchNoExpirationDateReachesRealDynamoDB:
    """End-to-end regression for the reported bug, using a real (moto-mocked)
    DynamoDB table with the actual production GSI schema (expiration_date as
    ProductNameExpirationIndex's RANGE key, name confirmed via `aws dynamodb
    describe-table`) — not a MagicMock, so this only passes if the fix
    actually prevents the ValidationException, not just because a mock
    doesn't enforce the constraint. Exercises the specific path that was
    silently losing items: scan_package_batch's direct repo.save_item for a
    flagged item, which had zero string coercion applied to it (unlike
    commit_to_inventory) — a no-date scan always sets date_confidence="low",
    which flags it for review, making this the path that was actually hit
    by the reported bug."""

    @pytest.fixture
    def dynamodb_table(self):
        with mock_aws():
            os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
            dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
            table = dynamodb.create_table(
                TableName="scan_batch_no_date_test",
                KeySchema=[{"AttributeName": "item_id", "KeyType": "HASH"}],
                AttributeDefinitions=[
                    {"AttributeName": "item_id", "AttributeType": "S"},
                    {"AttributeName": "product_name", "AttributeType": "S"},
                    {"AttributeName": "expiration_date", "AttributeType": "S"},
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "ProductNameExpirationIndex",
                        "KeySchema": [
                            {"AttributeName": "product_name", "KeyType": "HASH"},
                            {"AttributeName": "expiration_date", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    },
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            yield table

    @patch("strand_sort.agent.tools.get_inventory_repository")
    @patch("strand_sort.agent.tools.get_image_storage")
    @patch("strand_sort.agent.tools._encode_image_from_s3")
    @patch("strand_sort.agent.tools.get_extractor")
    def test_no_date_scan_persists_instead_of_being_silently_lost(
        self, mock_extractor, mock_encode, mock_get_storage, mock_get_repo, dynamodb_table
    ):
        no_date_extraction = VisionExtraction(
            product_name="10on10 Whole Wheat Atta",
            category="grains_pulses",
            raw_date_text_found="NONE",
            expiration_date_raw=None,
            date_confidence="low",
            dietary_flags=DietaryFlags(),
            nutrition_facts=NutritionFacts(),
        )
        mock_extractor.return_value = _to_donation_item(no_date_extraction)
        mock_encode.return_value = "ZmFrZQ=="
        mock_get_storage.return_value = MagicMock(save_images_from_s3=MagicMock(return_value=[]))

        real_repo = DynamoDBRepository(table_name="scan_batch_no_date_test")
        mock_get_repo.return_value = real_repo

        result = scan_package_batch(image_sources=["pending-uploads/atta.jpg"])

        # A no-date item always gets date_confidence="low", which flags it —
        # confirms this test actually exercises the vulnerable direct-save
        # path, not the (already-safe) commit_to_inventory path.
        assert result["status"] == "flagged_for_review"

        fetched = real_repo.get_by_id(result["item_id"])
        assert fetched is not None, "item was silently lost — exactly the reported bug"
        assert fetched["expiration_date"] == NO_EXPIRATION_DATE
