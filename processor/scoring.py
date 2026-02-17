"""
Scoring processor: keyword match, trending (stars_today), recency. Weights from config.scoring.
"""
import logging
from processor.base import BaseProcessor
from utils.time_utils import get_now, get_timezone, parse_published_at, hours_ago

logger = logging.getLogger("ai_intel")


class ScoringProcessor(BaseProcessor):
    def __init__(self, config: dict):
        self.config = config
        self.keywords = list(config.get("keywords") or [])
        scoring = config.get("scoring") or {}
        self.keyword_weight = float(scoring.get("keyword_weight", 1))
        self.trending_weight = float(scoring.get("trending_weight", 2))
        self.recency_weight = float(scoring.get("recency_weight", 1))

    def process(self, context: dict) -> None:
        updates = context.get("updates", [])
        tz = get_timezone(self.config)
        now = get_now(tz)
        # Normalize stars for trending: max stars_today in this batch for 0-10 scale
        stars_list = [
            getattr(u, "stars_today", None) or (u.get("stars_today") if isinstance(u, dict) else None)
            for u in updates
        ]
        max_stars = max((s for s in stars_list if s is not None), default=1) or 1

        for u in updates:
            score = self._compute_score(u, now, max_stars)
            if hasattr(u, "score"):
                u.score = score
            elif isinstance(u, dict):
                u["score"] = score
        logger.info("Scoring: computed for %d updates", len(updates))

    def _compute_score(self, u, now, max_stars: float) -> float:
        title = getattr(u, "title", None) or (u.get("title") if isinstance(u, dict) else "") or ""
        # Keyword count
        keyword_count = sum(1 for k in self.keywords if k and (k in title))
        keyword_score = keyword_count * self.keyword_weight

        # Trending: stars_today normalized to 0-10 then * trending_weight
        stars_today = getattr(u, "stars_today", None) or (u.get("stars_today") if isinstance(u, dict) else None)
        if stars_today is not None and stars_today > 0:
            normalized = min(stars_today / 100.0, 10.0)
            trending_score = normalized * self.trending_weight
        else:
            trending_score = 0.0

        # Recency: hours_ago -> max(0, (24 - hours_ago)/24 * 10) * recency_weight
        published_at = getattr(u, "published_at", None) or (u.get("published_at") if isinstance(u, dict) else "")
        dt = parse_published_at(published_at) if published_at else None
        if dt:
            h = hours_ago(dt, now)
            recency_part = max(0.0, (24 - h) / 24.0 * 10.0)
            recency_score = recency_part * self.recency_weight
        else:
            recency_score = 5.0 * self.recency_weight  # unknown date: give middle recency

        return keyword_score + trending_score + recency_score
