from unittest.mock import MagicMock, patch

from strand_sort.agent.tools import commit_to_inventory


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
