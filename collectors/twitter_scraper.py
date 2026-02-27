"""
Twitter/X 视频推文采集（网页爬虫版，不依赖官方 API）。

职责：
- 从 config['twitter']['accounts'] 读取要监控的账号列表。
- 通过配置的 scraper_base（默认 https://nitter.net）抓取用户时间线网页。
- 解析出包含视频媒体的推文（基于 Nitter 的 DOM 结构做 best-effort 解析）。
- 返回与 twitter_collector.collect 相同的统一视频信号结构 List[Dict]：
  id, platform, title, url, source, published_at, score, github_refs。

注意：
- 依赖第三方 Nitter 实例的可用性与 DOM 结构，可能随时间变化需要调整解析逻辑。
- 仅作低频、少量抓取使用，避免对目标站点造成压力。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover - requests 缺失时直接跳过采集
    requests = None  # type: ignore

from utils.hashing import generate_id

logger = logging.getLogger("ai_intel")


GITHUB_RE = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)


def _clean_title(text: str, limit: int = 100) -> str:
    """基础清洗 tweet 文本：去掉多余换行、URL 噪音，截断长度。"""
    if not text:
        return ""
    # 去掉 URL
    text = re.sub(r"https?://\S+", "", text)
    # 合并空白
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit].rstrip() + "…"
    return text


def _extract_github_refs(text: str) -> List[str]:
    """从 tweet 文本中提取 owner/repo 形式的 GitHub 链接。"""
    if not text:
        return []
    refs = {f"{m.group(1)}/{m.group(2)}" for m in GITHUB_RE.finditer(text)}
    return sorted(refs)


def _fetch_timeline_html(
    base_url: str,
    handle: str,
    timeout: int = 15,
    max_retries: int = 2,
) -> Optional[str]:
    if not requests:
        logger.warning("requests 未安装，无法进行 Twitter 网页爬取")
        return None
    handle = handle.lstrip("@").strip()
    if not handle:
        return None
    url = f"{base_url.rstrip('/')}/{handle}"
    # 使用更接近常见浏览器的请求头，降低被反爬/限流的概率
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": base_url.rstrip("/"),
        "Upgrade-Insecure-Requests": "1",
    }

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:  # pragma: no cover - 网络环境相关
            last_error = e
            logger.warning(
                "抓取 Twitter 时间线页面失败 (%s) [attempt=%d/%d]: %s",
                url,
                attempt,
                max_retries,
                e,
            )

    if last_error:
        logger.warning(
            "抓取 Twitter 时间线页面多次失败，放弃 (%s): %s",
            url,
            last_error,
        )
    return None


def _parse_nitter_timeline(
    html: str,
    handle: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    """基于 Nitter DOM 结构的简单解析，提取包含视频的推文。

    典型结构（不同实例可能略有差异）：
    - 每条推文在 <div class="timeline-item"> ... </div> 中
    - 内含 <a class="tweet-link" href="/{handle}/status/{tweet_id}"> ... </a>
    - 视频通常带有 <span class="icon-video"> 或 data-testid 相关标记
    """
    items: List[Dict[str, Any]] = []
    # 粗切 timeline-item 块，避免写完整 HTML 解析器依赖
    blocks = re.split(r'<div[^>]+class="timeline-item[^"]*"[^>]*>', html)[1:]
    for block in blocks:
        if len(items) >= max_results:
            break
        # 粗判是否包含视频：查找 icon-video / media-gif 等标记
        if not re.search(r"icon-video|media-gif|video-icon", block, re.IGNORECASE):
            continue
        # 提取推文链接
        m_link = re.search(
            r'<a[^>]+class="tweet-link"[^>]+href="([^"]+)"', block
        )
        if not m_link:
            continue
        href = m_link.group(1)
        # Nitter 链接形如 /username/status/123456789...
        tweet_url = href
        # 规范化成 twitter.com 链接
        if tweet_url.startswith("/"):
            tweet_url = f"https://twitter.com{tweet_url}"
        # 提取 tweet id
        m_id = re.search(r"/status/(\d+)", tweet_url)
        tweet_id = m_id.group(1) if m_id else ""
        if not tweet_id:
            continue
        # 提取文本内容（非常粗糙地移除 HTML 标签）
        # 先找到内容容器，大致为 <div class="tweet-content media-body"> ... </div>
        m_content = re.search(
            r'<div[^>]+class="tweet-content[^"]*"[^>]*>(.*?)</div>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        raw_text = m_content.group(1) if m_content else ""
        # 去掉 HTML 标签
        text = re.sub(r"<br\s*/?>", "\n", raw_text)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.strip()

        title = _clean_title(text)
        github_refs = _extract_github_refs(text)

        # 发布时间：尝试从 <time datetime="..."> 提取
        m_time = re.search(
            r'<time[^>]+datetime="([^"]+)"', block, re.IGNORECASE
        )
        published_at = m_time.group(1) if m_time else ""

        vid = generate_id(tweet_url or tweet_id)

        item: Dict[str, Any] = {
            "id": vid,
            "platform": "twitter",
            "title": title,
            "url": tweet_url,
            "source": f"@{handle.lstrip('@')}",
            "published_at": published_at,
            "score": 0.0,
            "github_refs": github_refs,
        }
        items.append(item)
    return items


def collect(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """采集 Twitter/X 视频推文（网页爬虫版），返回统一视频信号结构的 List[Dict]."""
    twitter_cfg = (config or {}).get("twitter") or {}
    accounts = twitter_cfg.get("accounts") or []
    if not accounts:
        return []

    # 支持单个 scraper_base（字符串）或多个 scraper_bases（列表）
    bases_cfg = twitter_cfg.get("scraper_bases")
    if isinstance(bases_cfg, list) and bases_cfg:
        base_urls = [str(b).strip() for b in bases_cfg if str(b).strip()]
    else:
        single_base = twitter_cfg.get("scraper_base", "https://nitter.net")
        base_urls = [str(single_base).strip()]

    if not base_urls:
        base_urls = ["https://nitter.net"]

    fetch_limit = int(twitter_cfg.get("fetch_limit", 10))
    fetch_timeout = int(twitter_cfg.get("fetch_timeout", 15))

    results: List[Dict[str, Any]] = []

    for raw_handle in accounts:
        handle = str(raw_handle).strip()
        if not handle:
            continue
        html: Optional[str] = None
        for base_url in base_urls:
            html = _fetch_timeline_html(
                base_url,
                handle,
                timeout=fetch_timeout,
            )
            if html:
                break
        if not html:
            continue
        items = _parse_nitter_timeline(html, handle, fetch_limit)
        if items:
            results.extend(items)
            logger.info(
                "Twitter scraper: handle=%s, video_tweets=%d",
                handle,
                len(items),
            )
        else:
            logger.info(
                "Twitter scraper: handle=%s, 未解析到视频推文（可能是 DOM 结构变化或近期无视频）",
                handle,
            )

    return results

