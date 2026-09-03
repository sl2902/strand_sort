from unittest.mock import MagicMock, patch

import pytest

from strand_sort.agent.queue import review_queue
from strand_sort.agent.tools import commit_to_inventory
from strand_sort.models import DonationItem


@pytest.fixture(autouse=True)
def clean_review_queue():
    """review_queue is a module-level singleton — don't leak state across tests."""
    review_queue._pending_reviews.clear()
    yield
    review_queue._pending_reviews.clear()


def _flagged_item(item_id: str, product_name: str) -> DonationItem:
    return DonationItem(
        item_id=item_id,
        product_name=product_name,
        category="dairy_liquid",
        raw_date_text_found="unreadable",
        expiration_date=None,
        date_confidence="low",
        requires_human_review=True,
        review_reason="low-confidence date read",
    )


class TestCommitClearsReviewQueue:
    """A retried agent run (see the Bedrock->Gemini fallback in
    run_intake_workflow) can flag an item on one attempt and commit it on
    another. commit_to_inventory must always clear any pending review flag
    for the item it just committed, or the item ends up visible in both
    Inventory and the Review queue simultaneously."""

    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_new_batch_commit_clears_pending_review(self, mock_get_repo):
        item_id = "milk-abc123"
        review_queue.add_for_review(_flagged_item(item_id, "Milk"))
        assert review_queue.get_pending()  # sanity: it's actually there first

        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = None
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({
            "item_id": item_id,
            "product_name": "Milk",
            "expiration_date": "2026-10-01",
            "quantity": 1,
        })

        assert review_queue.get_pending() == []

    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_increment_existing_batch_clears_pending_review(self, mock_get_repo):
        item_id = "milk-abc123"
        review_queue.add_for_review(_flagged_item(item_id, "Milk"))

        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = {"item_id": item_id, "quantity": 2}
        mock_repo.increment_quantity.return_value = {"item_id": item_id, "quantity": 3, "image_urls": []}
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({
            "item_id": "some-new-scan-id",  # a fresh scan of the same product/date
            "product_name": "Milk",
            "expiration_date": "2026-10-01",
            "quantity": 1,
        })

        assert review_queue.get_pending() == []

    @patch("strand_sort.agent.tools.get_inventory_repository")
    def test_commit_is_a_no_op_on_review_queue_when_nothing_pending(self, mock_get_repo):
        """discard() must not raise when the item was never flagged."""
        mock_repo = MagicMock()
        mock_repo.check_duplicate_active_inventory.return_value = None
        mock_get_repo.return_value = mock_repo

        commit_to_inventory({
            "item_id": "never-flagged",
            "product_name": "Eggs",
            "expiration_date": "2026-10-01",
            "quantity": 1,
        })

        assert review_queue.get_pending() == []
