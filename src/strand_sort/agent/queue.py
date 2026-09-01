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
        """Resolves an item. If approved, returns the item for inventory commit"""
        item = self._pending_reviews.pop(item_id, None)
        if not item:
            return None

        if approved:
            item.requires_human_review = False
            if corrected_date:
                item.expiration_date = corrected_date
                item.is_expired = False  # Override based on human date correction
            return item
        return None  # Item rejected/discarded


# Global singleton instance
review_queue = ExceptionReviewQueue()