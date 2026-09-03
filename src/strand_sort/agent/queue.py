from typing import Dict, List, Optional
from strand_sort.models import DonationItem


class ExceptionReviewQueue:
    def __init__(self):
        self._pending_reviews: Dict[str, DonationItem] = {}

    def add_for_review(self, item: DonationItem) -> None:
        """Adds a flagged item to the review queue"""
        self._pending_reviews[item.item_id] = item

    def get_pending(self) -> List[DonationItem]:
        """Returns all items awaiting human intervention"""
        return list(self._pending_reviews.values())

    def resolve_item(
        self,
        item_id: str,
        approved: bool,
        corrected_date: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[DonationItem]:
        """Resolves an item. If approved, returns the item for inventory commit.
        Raises KeyError if the item isn't in the queue (found by neither branch)"""
        if item_id not in self._pending_reviews:
            raise KeyError(f"Item {item_id} not in review queue")

        item = self._pending_reviews.pop(item_id)
        if approved:
            item.requires_human_review = False
            if corrected_date:
                item.expiration_date = corrected_date
                item.is_expired = False
            return item
        return None

    def discard(self, item_id: str) -> None:
        """Removes an item if present; no-op (unlike resolve_item) if it isn't.
        For when a commit supersedes a pending flag outside the normal
        approve/reject flow — e.g. a retried agent run (see the Bedrock→Gemini
        fallback in run_intake_workflow) can flag an item on one attempt and
        commit it on another, since the fallback re-runs the whole prompt with
        no memory of tool calls the failed attempt already made."""
        self._pending_reviews.pop(item_id, None)


# Global singleton instance
review_queue = ExceptionReviewQueue()