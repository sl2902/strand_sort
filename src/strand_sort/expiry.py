from datetime import date, datetime
from enum import Enum

NEAR_EXPIRY_THRESHOLD_DAYS = 7


class ExpiryStatus(str, Enum):
    FINE = "fine"
    NEAR_EXPIRY = "near_expiry"
    EXPIRED = "expired"


def compute_expiry_status(expiration_date: str | None) -> ExpiryStatus | None:
    """
    Computes expiry status fresh from a stored/extracted YYYY-MM-DD date
    string, relative to *today* — call this on every read, never trust a
    status value computed and stored at some earlier point (e.g. at intake
    time). "Today" keeps moving; a value frozen at scan time doesn't, so an
    item scanned weeks ago with a since-passed date would otherwise sit in
    inventory silently showing as fine forever.
    """
    if not expiration_date:
        return None
    try:
        parsed = datetime.strptime(expiration_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    days_remaining = (parsed - date.today()).days
    if days_remaining < 0:
        return ExpiryStatus.EXPIRED
    if days_remaining <= NEAR_EXPIRY_THRESHOLD_DAYS:
        return ExpiryStatus.NEAR_EXPIRY
    return ExpiryStatus.FINE
