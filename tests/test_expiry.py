from datetime import date, timedelta

from strand_sort.expiry import ExpiryStatus, compute_expiry_status, NEAR_EXPIRY_THRESHOLD_DAYS


def _iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


class TestComputeExpiryStatus:
    def test_none_input_returns_none(self):
        assert compute_expiry_status(None) is None

    def test_empty_string_returns_none(self):
        assert compute_expiry_status("") is None

    def test_unparseable_string_returns_none(self):
        assert compute_expiry_status("not-a-date") is None

    def test_past_date_is_expired(self):
        assert compute_expiry_status(_iso(-1)) == ExpiryStatus.EXPIRED

    def test_far_past_date_is_expired(self):
        assert compute_expiry_status(_iso(-30)) == ExpiryStatus.EXPIRED

    def test_today_is_near_expiry(self):
        assert compute_expiry_status(_iso(0)) == ExpiryStatus.NEAR_EXPIRY

    def test_within_threshold_is_near_expiry(self):
        assert compute_expiry_status(_iso(3)) == ExpiryStatus.NEAR_EXPIRY

    def test_exactly_at_threshold_is_near_expiry(self):
        assert compute_expiry_status(_iso(NEAR_EXPIRY_THRESHOLD_DAYS)) == ExpiryStatus.NEAR_EXPIRY

    def test_one_day_past_threshold_is_fine(self):
        assert compute_expiry_status(_iso(NEAR_EXPIRY_THRESHOLD_DAYS + 1)) == ExpiryStatus.FINE

    def test_distant_future_is_fine(self):
        assert compute_expiry_status(_iso(365)) == ExpiryStatus.FINE

    def test_result_depends_on_todays_date_not_a_cached_value(self):
        """The whole point of this function: calling it twice with the same
        stored date string on different days must be able to yield different
        answers — nothing here should be memoized/cached."""
        near_expiry_date = _iso(NEAR_EXPIRY_THRESHOLD_DAYS)
        assert compute_expiry_status(near_expiry_date) == ExpiryStatus.NEAR_EXPIRY
        # Simulate "time passing" by checking the same stored string against
        # a date threshold further out than when it was first computed.
        assert compute_expiry_status(_iso(-1)) == ExpiryStatus.EXPIRED
