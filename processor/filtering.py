"""
Filtering processor: by score threshold, top_n, and days_window (drop too old).
"""
import logging
from processor.base import BaseProcessor
from utils.time_utils import get_timezone, parse_published_at, get_now

logger = logging.getLogger("ai_intel")


class FilteringProcessor(BaseProcessor):
    def __init__(self, config: dict):
        self.config = config
        limits = config.get("limits") or {}
        self.top_n = int(limits.get("top_n", 5))
        self.days_window = int(limits.get("days_window", 7))

    def process(self, context: dict) -> None:
        updates = context.get("updates", [])
        tz = get_timezone(self.config)
        now = get_now(tz)

        # Drop older than days_window
        within_window = []
        for u in updates:
            published_at = getattr(u, "published_at", None) or (u.get("published_at") if isinstance(u, dict) else "")
            dt = parse_published_at(published_at) if published_at else None
            if not dt:
                within_window.append(u)
                continue
            try:
                now_date = now.date() if hasattr(now, "date") else now
                dt_date = dt.date() if hasattr(dt, "date") else dt
                days_ago = (now_date - dt_date).days
            except (TypeError, ValueError):
                within_window.append(u)
                continue
            if days_ago <= self.days_window:
                within_window.append(u)

        # Sort by score desc, take top_n
        def score_key(u):
            return getattr(u, "score", None) or (u.get("score") if isinstance(u, dict) else 0) or 0

        within_window.sort(key=score_key, reverse=True)
        context["updates"] = within_window[: self.top_n]
        logger.info("Filtering: %d -> %d (top_n=%d, days_window=%d)", len(updates), len(context["updates"]), self.top_n, self.days_window)
