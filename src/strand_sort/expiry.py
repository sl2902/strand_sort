from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo

NEAR_EXPIRY_THRESHOLD_DAYS = 7

# Anchored explicitly rather than relying on the server process's ambient
# timezone (date.today() would use whatever that happens to be — UTC by
# default on Lambda, with no TZ env var set). India is UTC+5:30, so for the
# first ~5.5 hours of every IST calendar day, a UTC-based "today" is still
# on the previous day — silently delaying every item's near_expiry ->
# expired flip by however much of that window remained. This is an India
# food bank app; expiry must be computed against India's calendar day
# regardless of which region/timezone the server itself happens to run in.
_TIMEZONE = ZoneInfo("Asia/Kolkata")


class ExpiryStatus(str, Enum):
    FINE = "fine"
    NEAR_EXPIRY = "near_expiry"
    EXPIRED = "expired"


def today_ist() -> date:
    """India-anchored "today" — see this module's own comment above for
    why this isn't just date.today()."""
    return datetime.now(_TIMEZONE).date()


def compute_expiry_status(expiration_date: str | None) -> ExpiryStatus | None:
    """
    Computes expiry status fresh from a stored/extracted YYYY-MM-DD date
    string, relative to *today in IST* — call this on every read, never
    trust a status value computed and stored at some earlier point (e.g.
    at intake time). "Today" keeps moving; a value frozen at scan time
    doesn't, so an item scanned weeks ago with a since-passed date would
    otherwise sit in inventory silently showing as fine forever.
    """
    if not expiration_date:
        return None
    try:
        parsed = datetime.strptime(expiration_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    days_remaining = (parsed - today_ist()).days
    if days_remaining < 0:
        return ExpiryStatus.EXPIRED
    if days_remaining <= NEAR_EXPIRY_THRESHOLD_DAYS:
        return ExpiryStatus.NEAR_EXPIRY
    return ExpiryStatus.FINE
