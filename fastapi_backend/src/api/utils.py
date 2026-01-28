from __future__ import annotations

from datetime import datetime, timezone


# PUBLIC_INTERFACE
def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


# PUBLIC_INTERFACE
def utc_now_iso_z() -> str:
    """Return current UTC timestamp as ISO-8601 string with 'Z' suffix."""
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
