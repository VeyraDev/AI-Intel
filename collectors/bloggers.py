"""
Bloggers collector (ContentCollector).
Reads active bloggers from bloggers.json, fetches latest updates (e.g. RSS/Atom), returns Update list.
"""
import logging
import time
from collectors.base import ContentCollector
from models.blogger import Blogger
from models.update import Update
from storage.json_store import JSONStore
from utils.hashing import generate_id

logger = logging.getLogger("ai_intel")

try:
    import feedparser
except ImportError:
    feedparser = None


def _published_to_str(published) -> str:
    """Convert feedparser published/updated (struct_time or str) to ISO-like string."""
    if not published:
        return ""
    if isinstance(published, str):
        return published
    if hasattr(published, "timetuple"):  # datetime
        return published.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        # time.struct_time from feedparser
        return time.strftime("%Y-%m-%dT%H:%M:%S", published)
    except (TypeError, ValueError):
        return str(published)


class BloggersCollector(ContentCollector):
    def __init__(self, config: dict, storage: JSONStore):
        self.config = config
        self.storage = storage

    def collect(self, context: dict) -> None:
        raw = self.storage.read_json("bloggers.json")
        if not raw:
            raw = {"bloggers": []}
        bloggers_list = raw.get("bloggers") if isinstance(raw, dict) else raw
        if not isinstance(bloggers_list, list):
            bloggers_list = []
        active = [b for b in bloggers_list if isinstance(b, dict) and b.get("active", True)]
        max_count = (self.config.get("bloggers") or {}).get("max_count", 100)
        active = active[:max_count]

        updates = context.setdefault("updates", [])
        if not feedparser:
            logger.warning("feedparser not installed; skip bloggers feed")
            return

        added = 0
        for b in active:
            blogger = Blogger.from_dict(b) if isinstance(b, dict) else None
            if not blogger or not blogger.source:
                continue
            # Assume source is RSS URL
            try:
                feed = feedparser.parse(blogger.source, request_headers={"User-Agent": "AI-Intel-System/1.0"})
            except Exception as e:
                logger.debug("Feed %s error: %s", blogger.source, e)
                continue
            for entry in getattr(feed, "entries", [])[:10]:
                title = entry.get("title") or ""
                link = entry.get("link") or ""
                if not link:
                    continue
                published = ""
                for k in ("published", "updated"):
                    if entry.get(k):
                        published = entry[k]
                        break
                published_at_str = _published_to_str(published)
                uid = generate_id(link)
                updates.append(
                    Update(
                        id=uid,
                        title=title,
                        url=link,
                        source=blogger.name,
                        published_at=published_at_str,
                        score=0.0,
                        tags=[],
                    )
                )
                added += 1
        logger.info("Bloggers collector: added %d updates from %d bloggers", added, len(active))
