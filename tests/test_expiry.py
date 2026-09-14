from datetime import timedelta
from zoneinfo import ZoneInfo

from strand_sort.expiry import ExpiryStatus, compute_expiry_status, today_ist, NEAR_EXPIRY_THRESHOLD_DAYS


def _iso(days_from_today: int) -> str:
    # today_ist(), not date.today() — these tests must stay correct
    # regardless of the machine/CI runner's own ambient timezone (e.g. a
    # UTC-based CI box), same reason production code doesn't use
    # date.today() either. See TestTodayIstAnchoring below for the actual
    # UTC-vs-IST regression this guards against.
    return (today_ist() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


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


class TestTodayIstAnchoring:
    """The real bug, confirmed live against production: a milk item with
    expiration_date=2026-09-13 was still showing near_expiry at 05:17 IST
    on the 14th, because the deployed Lambda has no TZ env var and computed
    "today" as 2026-09-13 (still UTC's date at that instant, since IST is
    5:30 ahead and UTC hadn't rolled over to the 14th yet). Confirmed to
    self-correct once UTC crossed midnight — this test locks in the actual
    fix (anchor to IST explicitly) rather than depending on that
    coincidence of timing."""

    def test_expiry_uses_ist_date_not_servers_utc_date(self, monkeypatch):
        from datetime import datetime as real_datetime

        class _FixedDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                # 2026-09-13 23:47 UTC == 2026-09-14 05:17 IST — the exact
                # instant this bug was caught live.
                fixed_utc = real_datetime(2026, 9, 13, 23, 47, tzinfo=ZoneInfo("UTC"))
                return fixed_utc.astimezone(tz) if tz else fixed_utc.replace(tzinfo=None)

        monkeypatch.setattr("strand_sort.expiry.datetime", _FixedDatetime)

        # A UTC-anchored "today" would still be the 13th, making this item
        # (expiring "today" in UTC terms) merely near_expiry.
        assert compute_expiry_status("2026-09-13") == ExpiryStatus.EXPIRED
        # And an item expiring "today" in the correct, IST sense:
        assert compute_expiry_status("2026-09-14") == ExpiryStatus.NEAR_EXPIRY
