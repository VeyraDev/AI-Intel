"""
Research feeds collector (ContentCollector).

采集来源：
- arXiv RSS（按分类）
- 研究机构博客 RSS/Atom（按配置 feeds 列表）

设计目标：
- 多分类/多源覆盖，单源收敛（per-source cap）+ 全局 cap（避免日报输入爆炸）
- 输出统一 Update 结构（可选 summary 字段用于日报理解）
"""

from __future__ import annotations

import calendar
import logging
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Tuple

from collectors.base import ContentCollector
from models.update import Update
from storage.json_store import JSONStore
from utils.hashing import generate_id
from utils.time_utils import get_now, get_timezone

logger = logging.getLogger("ai_intel")

try:
    import feedparser  # type: ignore
except ImportError:  # pragma: no cover
    feedparser = None  # type: ignore

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


def _parse_feed(url: str, *, user_agent: str) -> Any:
    """Parse feed with a conservative HTTPS->HTTP fallback for local SSL issues."""
    if not feedparser:
        return None
    feed = feedparser.parse(url, request_headers={"User-Agent": user_agent})
    entries = list(getattr(feed, "entries", []) or [])
    if entries:
        return feed

    bozo = bool(getattr(feed, "bozo", False))
    if not bozo:
        return feed

    exc = getattr(feed, "bozo_exception", None)
    err = str(exc or "").lower()
    ssl_related = ("certificate verify failed" in err) or ("ssl" in err and "verify" in err)
    if not ssl_related:
        return feed

    # 优先用 requests 拉取（requests 使用 certifi，Windows 上比 urllib 更稳定），再由 feedparser 解析内容
    if requests:
        try:
            resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=20)  # type: ignore[arg-type]
            if resp.status_code == 200 and resp.content:
                parsed = feedparser.parse(resp.content)
                if list(getattr(parsed, "entries", []) or []):
                    logger.warning("Feed urllib SSL 校验失败，已改用 requests 抓取并解析：%s", url)
                    return parsed
        except Exception:
            pass

    if url.startswith("https://"):
        alt = "http://" + url[len("https://") :]
        alt_feed = feedparser.parse(alt, request_headers={"User-Agent": user_agent})
        alt_entries = list(getattr(alt_feed, "entries", []) or [])
        if alt_entries:
            logger.warning("Feed HTTPS 证书校验失败，已降级为 HTTP 抓取：%s", alt)
            return alt_feed
    return feed


_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(value: Any, max_len: int = 800) -> str:
    if not value:
        return ""
    s = str(value)
    # RSS summary 常含 HTML，简单去标签 + 反转义
    s = _TAG_RE.sub(" ", s)
    s = unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if max_len > 0 and len(s) > max_len:
        s = s[: max_len].rstrip() + "…"
    return s


def _to_dt(value: Any, tz_name: str) -> Optional[datetime]:
    """Parse feed entry published/updated into timezone-aware datetime."""
    if not value:
        return None
    tzinfo = None
    try:
        from zoneinfo import ZoneInfo

        tzinfo = ZoneInfo(tz_name)
    except Exception:  # pragma: no cover
        tzinfo = None

    # 1) feedparser 的 struct_time 优先（更可靠）
    if isinstance(value, tuple) and len(value) >= 9:
        try:
            ts = calendar.timegm(value)  # treat as UTC
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.astimezone(tzinfo) if tzinfo else dt
        except Exception:
            pass

    # 2) RFC 2822 / RSS 常见日期格式
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            dt = parsedate_to_datetime(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(tzinfo) if tzinfo else dt
        except Exception:
            pass
        # 3) ISO 8601
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(tzinfo) if tzinfo else dt
        except Exception:
            return None

    return None


def _entry_published_dt(entry: Any, tz_name: str) -> Optional[datetime]:
    """Get best-effort published datetime for a feedparser entry."""
    # feedparser 常见：published_parsed / updated_parsed（struct_time）
    for k in ("published_parsed", "updated_parsed"):
        v = entry.get(k) if isinstance(entry, dict) else None
        dt = _to_dt(v, tz_name)
        if dt:
            return dt
    # 字符串：published / updated
    for k in ("published", "updated"):
        v = entry.get(k) if isinstance(entry, dict) else None
        dt = _to_dt(v, tz_name)
        if dt:
            return dt
    return None


def _within_days(dt: Optional[datetime], now: datetime, days_window: int) -> bool:
    if days_window <= 0:
        return True
    if not dt:
        # 无日期：保守放行（后续 FilteringProcessor 仍会兜底）
        return True
    return dt >= (now - timedelta(days=days_window))


def _dedup_merge(updates: Iterable[Update]) -> List[Update]:
    """Deduplicate by id; merge tags and keep latest published_at/summary."""
    by_id: Dict[str, Update] = {}
    for u in updates:
        if not u.id:
            continue
        if u.id not in by_id:
            by_id[u.id] = u
            continue
        prev = by_id[u.id]
        merged_tags = sorted({*(prev.tags or []), *(u.tags or [])})
        # published_at：优先保留更长/更具体的那个（通常带时分秒）
        published_at = prev.published_at if len(prev.published_at or "") >= len(u.published_at or "") else u.published_at
        # summary：优先保留更长的那个
        summary = prev.summary if len(prev.summary or "") >= len(u.summary or "") else u.summary
        by_id[u.id] = replace(prev, tags=merged_tags, published_at=published_at, summary=summary)
    return list(by_id.values())


def _sort_by_published_desc(updates: List[Update], tz_name: str) -> List[Update]:
    def key(u: Update) -> Tuple[int, str]:
        # published_at 可能为空；空的排后
        return (0, u.published_at) if u.published_at else (1, "")

    # ISO 字符串可直接按字典序排序近似等价于时间排序（同一时区格式下）
    return sorted(updates, key=key, reverse=True)


class ResearchFeedsCollector(ContentCollector):
    def __init__(self, config: dict, storage: JSONStore):
        self.config = config
        self.storage = storage

    def collect(self, context: dict) -> None:
        if not feedparser:
            logger.warning("feedparser not installed; skip research_feeds collector")
            return

        cfg = (self.config or {}).get("research_feeds") or {}
        tz = get_timezone(self.config)
        now = get_now(tz)
        updates_out: List[Update] = []

        arxiv_cfg = cfg.get("arxiv") or {}
        if arxiv_cfg.get("enabled", True):
            updates_out.extend(self._collect_arxiv(arxiv_cfg, tz, now))

        blogs_cfg = cfg.get("blogs") or {}
        if blogs_cfg.get("enabled", True):
            updates_out.extend(self._collect_blogs(blogs_cfg, tz, now))

        if not updates_out:
            return

        updates_out = _dedup_merge(updates_out)
        updates_out = _sort_by_published_desc(updates_out, tz)

        updates = context.setdefault("updates", [])
        updates.extend(updates_out)
        logger.info("ResearchFeeds collector: added %d updates (deduped)", len(updates_out))

    def _collect_arxiv(self, arxiv_cfg: dict, tz: str, now: datetime) -> List[Update]:
        base_rss_url = str(arxiv_cfg.get("base_rss_url") or "https://export.arxiv.org/rss").rstrip("/")
        categories = [str(c).strip() for c in (arxiv_cfg.get("categories") or []) if str(c).strip()]
        # 多分类覆盖：默认给一套科研常用分类
        if not categories:
            categories = ["cs.AI", "cs.LG", "cs.CL", "stat.ML", "cs.IR", "cs.CV"]

        per_cat = int(arxiv_cfg.get("max_entries_per_category", 12))
        scan_per_cat = int(arxiv_cfg.get("scan_entries_per_category", max(30, per_cat * 4)))
        max_total = int(arxiv_cfg.get("max_total_entries", 60))
        days_window = int(arxiv_cfg.get("days_window", 1))
        summary_max_len = int(arxiv_cfg.get("summary_max_len", 800))
        user_agent = str(arxiv_cfg.get("user_agent") or "AI-Intel-System/1.0")

        collected: List[Tuple[Optional[datetime], Update]] = []
        parsed_categories = 0
        for cat in categories:
            url = f"{base_rss_url}/{cat}"
            try:
                feed = _parse_feed(url, user_agent=user_agent)
            except Exception as e:  # pragma: no cover
                logger.debug("arXiv feed parse error (%s): %s", url, e)
                continue
            if not feed:
                continue
            parsed_categories += 1

            added_cat = 0
            entries = list(getattr(feed, "entries", []) or [])
            for entry in entries[: max(0, scan_per_cat)]:
                if added_cat >= per_cat:
                    break
                if not isinstance(entry, dict):
                    continue

                link = (entry.get("link") or "").strip()
                if not link:
                    continue
                title = _clean_text(entry.get("title") or "", max_len=200)
                if not title:
                    title = link

                dt = _entry_published_dt(entry, tz)
                if not _within_days(dt, now, days_window):
                    continue

                published_at = dt.isoformat(timespec="seconds") if dt else ""
                summary = _clean_text(entry.get("summary") or entry.get("description") or "", max_len=summary_max_len)

                uid = generate_id("arxiv:" + link)
                tags = ["arxiv", cat]
                u = Update(
                    id=uid,
                    title=title,
                    url=link,
                    source=f"arXiv {cat}",
                    published_at=published_at,
                    score=0.0,
                    tags=tags,
                    summary=summary,
                )
                collected.append((dt, u))
                added_cat += 1

        updates = [u for _, u in collected]
        updates = _dedup_merge(updates)
        updates = _sort_by_published_desc(updates, tz)
        if max_total > 0:
            updates = updates[:max_total]
        if not updates:
            logger.warning(
                "ResearchFeeds arXiv: 0 updates (categories=%d, parsed=%d). "
                "若你在 Windows 遇到 SSL 证书问题，可将 base_rss_url 设为 http://export.arxiv.org/rss",
                len(categories),
                parsed_categories,
            )
        return updates

    def _collect_blogs(self, blogs_cfg: dict, tz: str, now: datetime) -> List[Update]:
        feeds = blogs_cfg.get("feeds") or []
        if not isinstance(feeds, list) or not feeds:
            return []

        per_feed = int(blogs_cfg.get("max_entries_per_feed", 10))
        scan_per_feed = int(blogs_cfg.get("scan_entries_per_feed", max(30, per_feed * 4)))
        max_total = int(blogs_cfg.get("max_total_entries", 40))
        days_window = int(blogs_cfg.get("days_window", 3))
        summary_max_len = int(blogs_cfg.get("summary_max_len", 800))
        user_agent = str(blogs_cfg.get("user_agent") or "AI-Intel-System/1.0")

        collected: List[Tuple[Optional[datetime], Update]] = []
        for f in feeds:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name") or "").strip()
            url = str(f.get("url") or "").strip()
            if not name or not url:
                continue
            extra_tags = [str(t).strip() for t in (f.get("tags") or []) if str(t).strip()]
            tags = ["blog", "research"] + extra_tags

            try:
                feed = _parse_feed(url, user_agent=user_agent)
            except Exception as e:  # pragma: no cover
                logger.debug("Blog feed parse error (%s): %s", url, e)
                continue
            if not feed:
                continue

            added_feed = 0
            entries = list(getattr(feed, "entries", []) or [])
            for entry in entries[: max(0, scan_per_feed)]:
                if added_feed >= per_feed:
                    break
                if not isinstance(entry, dict):
                    continue
                link = (entry.get("link") or "").strip()
                if not link:
                    continue
                title = _clean_text(entry.get("title") or "", max_len=200)
                if not title:
                    title = link

                dt = _entry_published_dt(entry, tz)
                if not _within_days(dt, now, days_window):
                    continue

                published_at = dt.isoformat(timespec="seconds") if dt else ""
                summary = _clean_text(entry.get("summary") or entry.get("description") or "", max_len=summary_max_len)

                uid = generate_id("blog:" + link)
                u = Update(
                    id=uid,
                    title=title,
                    url=link,
                    source=name,
                    published_at=published_at,
                    score=0.0,
                    tags=tags,
                    summary=summary,
                )
                collected.append((dt, u))
                added_feed += 1

        updates = [u for _, u in collected]
        updates = _dedup_merge(updates)
        updates = _sort_by_published_desc(updates, tz)
        if max_total > 0:
            updates = updates[:max_total]
        return updates

