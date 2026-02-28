"""
Filtering processor: by score, days_window, and optional source quota (arxiv_rss / github).
When limits.quota_arxiv_rss and limits.quota_github are set, selects up to N from each source
so that updates.json has a guaranteed mix (e.g. 5 arxiv/RSS + 4 GitHub).
"""
import logging
from processor.base import BaseProcessor
from utils.time_utils import get_timezone, parse_published_at, get_now

logger = logging.getLogger("ai_intel")


def _source_bucket(u) -> str:
    """Classify update as 'arxiv_rss' | 'github' | 'other' for quota."""
    src = (getattr(u, "source", None) or (u.get("source") if isinstance(u, dict) else "") or "").lower()
    url = (getattr(u, "url", None) or (u.get("url") if isinstance(u, dict) else "") or "").lower()
    tags = getattr(u, "tags", None) or (u.get("tags") if isinstance(u, dict) else []) or []
    tag_set = {str(t).lower() for t in tags}
    if "arxiv" in src or "arxiv" in tag_set or "arxiv.org" in url:
        return "arxiv_rss"
    if "blog" in tag_set or "research" in tag_set:
        if "github.com" not in url and "trending" not in tag_set:
            return "arxiv_rss"
    if "github" in src or "github.com" in url or "trending" in tag_set:
        return "github"
    return "other"


class FilteringProcessor(BaseProcessor):
    def __init__(self, config: dict):
        self.config = config
        limits = config.get("limits") or {}
        self.top_n = int(limits.get("top_n", 5))
        self.days_window = int(limits.get("days_window", 7))
        self.quota_arxiv_rss = limits.get("quota_arxiv_rss")
        self.quota_github = limits.get("quota_github")

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

        def score_key(u):
            return getattr(u, "score", None) or (u.get("score") if isinstance(u, dict) else 0) or 0

        if self.quota_arxiv_rss is not None and self.quota_github is not None:
            # 按来源保底：先按桶分组，再各取前 N 条
            q_ar = max(0, int(self.quota_arxiv_rss))
            q_gh = max(0, int(self.quota_github))
            by_bucket = {"arxiv_rss": [], "github": [], "other": []}
            for u in within_window:
                by_bucket[_source_bucket(u)].append(u)
            for key in by_bucket:
                by_bucket[key].sort(key=score_key, reverse=True)
            # 仅取 arxiv_rss 与 github 配额，不掺入 other，保证 5:4 比例；视频由 generator 按 quota_video 另加
            selected = by_bucket["arxiv_rss"][:q_ar] + by_bucket["github"][:q_gh]
            selected.sort(key=score_key, reverse=True)
            context["updates"] = selected
            logger.info(
                "Filtering: %d -> %d (quota arxiv_rss=%d, github=%d, days_window=%d)",
                len(updates), len(context["updates"]), q_ar, q_gh, self.days_window,
            )
        else:
            within_window.sort(key=score_key, reverse=True)
            context["updates"] = within_window[: self.top_n]
            logger.info(
                "Filtering: %d -> %d (top_n=%d, days_window=%d)",
                len(updates), len(context["updates"]), self.top_n, self.days_window,
            )
