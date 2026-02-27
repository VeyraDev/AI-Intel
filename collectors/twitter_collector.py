"""
Twitter/X 视频推文采集。

职责（本模块不直接写入 videos.json，只返回统一结构的 List[Dict]）：
- 从 config['twitter']['accounts'] 读取要监控的 Twitter 用户 handle 列表。
- 使用 Twitter API v2：
  - /2/users/by/username/:username 获取 user_id
  - /2/users/:id/tweets 获取最近推文（带 media 扩展信息）
- 仅保留包含视频媒体的推文（media.type in {'video', 'animated_gif'}）。
- 映射为统一的视频信号结构（与 B 站视频共用）：
  id, platform, title, url, source, published_at, score, github_refs。
"""
from __future__ import annotations

import logging
import os
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


def _get_bearer_token() -> Optional[str]:
    token = os.environ.get("TWITTER_BEARER_TOKEN") or os.environ.get("X_BEARER_TOKEN")
    if not token:
        logger.warning("TWITTER_BEARER_TOKEN 未配置，跳过 Twitter 视频采集")
        return None
    return token


def _api_get(
    url: str,
    token: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    if not requests:
        logger.warning("requests 未安装，无法调用 Twitter API")
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "ai-intel-system-twitter-collector/1.0",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)  # type: ignore[arg-type]
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            logger.warning("Twitter API 返回非 JSON 对象: %r", type(data))
            return None
        return data
    except Exception as e:  # pragma: no cover - 网络环境相关
        logger.warning("调用 Twitter API 失败 (%s): %s", url, e)
        return None


def _get_user_id(api_base: str, handle: str, token: str) -> Optional[str]:
    """根据用户名获取 user_id。"""
    handle = handle.lstrip("@").strip()
    if not handle:
        return None
    url = f"{api_base}/2/users/by/username/{handle}"
    data = _api_get(url, token)
    if not data or "data" not in data:
        logger.warning("获取 Twitter 用户 %s 的 user_id 失败: %s", handle, data)
        return None
    user = data.get("data") or {}
    uid = user.get("id")
    if not uid:
        logger.warning("Twitter 用户 %s 响应中缺少 id 字段: %s", handle, user)
        return None
    return str(uid)


def _get_tweets_with_media(
    api_base: str,
    user_id: str,
    token: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    """获取带 media 扩展信息的最近推文。"""
    url = f"{api_base}/2/users/{user_id}/tweets"
    params = {
        "max_results": max(5, min(max_results, 100)),
        "tweet.fields": "created_at",
        "expansions": "attachments.media_keys",
        "media.fields": "type,url,preview_image_url",
    }
    data = _api_get(url, token, params=params)
    if not data:
        return []
    tweets = data.get("data") or []
    includes = data.get("includes") or {}
    media_list = includes.get("media") or []
    media_by_key = {m.get("media_key"): m for m in media_list if isinstance(m, dict)}

    results: List[Dict[str, Any]] = []
    for tw in tweets:
        if not isinstance(tw, dict):
            continue
        attachments = tw.get("attachments") or {}
        media_keys = attachments.get("media_keys") or []
        has_video = False
        for mk in media_keys:
            m = media_by_key.get(mk)
            if not m:
                continue
            m_type = (m.get("type") or "").lower()
            if m_type in {"video", "animated_gif"}:
                has_video = True
                break
        if not has_video:
            continue
        tw["__media_keys"] = media_keys
        results.append(tw)
    return results


def collect(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """采集 Twitter/X 视频推文，返回统一视频信号结构的 List[Dict].

    每个返回的 dict 包含字段且仅包含：
    - id: 基于 url 或 tweet_id 生成的稳定哈希
    - platform: 固定 "twitter"
    - title: 清洗后的 tweet 文本前 100 字
    - url: 推文链接 https://twitter.com/{handle}/status/{tweet_id}
    - source: 作者，形如 @handle
    - published_at: tweet 的 created_at（ISO8601 字符串）
    - score: 初始为 0，由后续 Processor 统一计算
    - github_refs: 从文本中提取的 owner/repo 字符串数组
    """
    twitter_cfg = (config or {}).get("twitter") or {}
    accounts = twitter_cfg.get("accounts") or []
    if not accounts:
        # 未配置账号时静默返回空列表，保持 pipeline 稳定
        return []

    token = _get_bearer_token()
    if not token:
        return []

    api_base = twitter_cfg.get("api_base", "https://api.twitter.com")
    fetch_limit = int(twitter_cfg.get("fetch_limit", 20))

    results: List[Dict[str, Any]] = []
    for raw_handle in accounts:
        handle = str(raw_handle).strip()
        if not handle:
            continue
        uid = _get_user_id(api_base, handle, token)
        if not uid:
            continue

        tweets = _get_tweets_with_media(api_base, uid, token, fetch_limit)
        if not tweets:
            continue

        for tw in tweets:
            text = tw.get("text") or ""
            title = _clean_title(text)
            tweet_id = tw.get("id")
            if not tweet_id:
                continue
            url = f"https://twitter.com/{handle.lstrip('@')}/status/{tweet_id}"
            vid = generate_id(url or str(tweet_id))
            github_refs = _extract_github_refs(text)
            published_at = tw.get("created_at") or ""

            video_item: Dict[str, Any] = {
                "id": vid,
                "platform": "twitter",
                "title": title,
                "url": url,
                "source": f"@{handle.lstrip('@')}",
                "published_at": published_at,
                "score": 0.0,
                "github_refs": github_refs,
            }
            results.append(video_item)

        logger.debug(
            "Twitter collector: handle=%s, fetched=%d, video_tweets=%d",
            handle,
            len(tweets),
            len(results),
        )

    return results

