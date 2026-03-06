import re
from datetime import date, datetime, timezone
from uuid import uuid4


def parse_event_date(ticker_fragment: str) -> date:
    """Parse '26MAR07' → date(2026, 3, 7)."""
    months = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
        "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
        "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    match = re.match(r"(\d{2})([A-Z]{3})(\d{2})", ticker_fragment.upper())
    if not match:
        raise ValueError(f"Cannot parse date fragment: {ticker_fragment}")
    yy, mon_str, dd = int(match.group(1)), match.group(2), int(match.group(3))
    month = months[mon_str]
    return date(2000 + yy, month, dd)


def hours_until(close_time_str: str) -> float:
    """Return hours from now until close_time_str (ISO 8601)."""
    if not close_time_str:
        return 9999.0
    try:
        ct = close_time_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ct)
        now = datetime.now(timezone.utc)
        delta = dt - now
        return max(delta.total_seconds() / 3600, 0.0)
    except Exception:
        return 9999.0


def cents_to_dollars(cents: int) -> str:
    """Convert cent integer to formatted dollar string."""
    return f"${cents / 100:.2f}"


def build_client_order_id() -> str:
    return str(uuid4())
