"""
GitHub Trending collector (ContentCollector).
Fetches daily trending from base_url, saves to trending.json, and emits Update list.
"""
import re
import logging
from urllib.parse import urljoin

from collectors.base import ContentCollector
from models.update import Update
from models.trending import Trending, TrendingItem
from storage.json_store import JSONStore
from utils.hashing import generate_id
from utils.time_utils import format_date, get_now, get_timezone

logger = logging.getLogger("ai_intel")

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


class GitHubTrendingCollector(ContentCollector):
    def __init__(self, config: dict, storage: JSONStore):
        self.config = config
        self.storage = storage
        self.base_url = (config.get("github") or {}).get("base_url", "https://github.com/trending")

    def collect(self, context: dict) -> None:
        if not requests or not BeautifulSoup:
            logger.warning("requests or beautifulsoup4 not installed; skip GitHub trending")
            return
        tz = get_timezone(self.config)
        today = format_date(get_now(tz))
        updates = context.setdefault("updates", [])

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0"}
            resp = requests.get(self.base_url, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.exception("Failed to fetch GitHub trending: %s", e)
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[TrendingItem] = []
        # GitHub trending: article.Box-row or div.Box-row; h2 a href="/owner/repo"
        for row in soup.select("article.Box-row, div.Box-row"):
            repo_link = row.select_one("h2 a")
            if not repo_link:
                continue
            href = repo_link.get("href", "")
            repo = href.strip("/") if href.startswith("/") else href
            if not repo or "/" not in repo:
                continue
            url = urljoin("https://github.com", href)
            # Stars today: often in a span with "stars today" or number
            stars_today = 0
            for span in row.select("span"):
                text = span.get_text(strip=True)
                if "stars today" in text.lower() or (text.isdigit() and int(text) < 100000):
                    # Sometimes it's just the number in same fragment
                    num = re.sub(r"[^\d]", "", text)
                    if num:
                        stars_today = int(num)
                        break
            # Fallback: look for relative link with "stargazers"
            if stars_today == 0:
                for a in row.select("a[href*='stargazers']"):
                    t = a.get_text(strip=True)
                    n = re.sub(r"[^\d]", "", t)
                    if n:
                        stars_today = int(n)
                        break
            language_el = row.select_one("[itemprop='programmingLanguage']")
            language = language_el.get_text(strip=True) if language_el else ""
            items.append(TrendingItem(repo=repo, url=url, stars_today=stars_today, language=language))

            # One Update per repo for pipeline (scoring will use stars_today)
            uid = generate_id(url)
            updates.append(
                Update(
                    id=uid,
                    title=repo,
                    url=url,
                    source="GitHub Trending",
                    published_at=today,
                    score=0.0,
                    tags=["trending"],
                    stars_today=stars_today,
                )
            )

        trending = Trending(date=today, items=items)
        self.storage.write_json("trending.json", trending.to_dict())
        logger.info("GitHub trending: saved %d items for %s", len(items), today)
