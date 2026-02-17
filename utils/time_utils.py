"""
Time and date utilities. Timezone from config (system.timezone).
"""
from datetime import datetime
from zoneinfo import ZoneInfo


def get_timezone(config: dict) -> str:
    """Get timezone from config, default Asia/Shanghai."""
    return (config.get("system") or {}).get("timezone", "Asia/Shanghai")


def get_now(tz: str | None = None) -> datetime:
    """Current datetime in given timezone (default Asia/Shanghai)."""
    tz = tz or "Asia/Shanghai"
    return datetime.now(ZoneInfo(tz))


def format_date(dt: datetime) -> str:
    """Format datetime as YYYY-MM-DD."""
    return dt.strftime("%Y-%m-%d")


def format_datetime(dt: datetime) -> str:
    """Format datetime as ISO-like string."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_published_at(value: str | None) -> datetime | None:
    """Parse published_at string to datetime (ISO or YYYY-MM-DD)."""
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def hours_ago(dt: datetime, from_dt: datetime | None = None) -> float:
    """Hours between dt and from_dt (default now). Normalize naive/aware for subtraction."""
    from_dt = from_dt or get_now()
    if dt.tzinfo is None and from_dt.tzinfo is not None:
        dt = dt.replace(tzinfo=from_dt.tzinfo)
    elif dt.tzinfo is not None and from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=dt.tzinfo)
    delta = from_dt - dt
    return delta.total_seconds() / 3600.0
