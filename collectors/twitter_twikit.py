"""
Twitter/X 视频推文采集（twikit 版，依赖网页客户端登录）。

职责：
- 从 config['twitter']['accounts'] 读取要监控的账号列表。
- 使用 twikit 客户端登录（基于环境变量提供的账号信息），抓取用户时间线推文。
- 目前简单以「时间线最近推文」作为候选，不强制区分是否一定包含视频媒体。
- 返回与 twitter_collector.collect / twitter_scraper.collect 相同的统一视频信号结构：
  id, platform, title, url, source, published_at, score, github_refs。

注意：
- 依赖非官方网页协议，Twitter/X 反爬或登录流程变化时可能失效，需要更新 twikit 或调整逻辑。
- 强烈建议使用单独的采集专用账号，并通过 .env 传入登录信息：
  TWIKIT_AUTH_INFO_1, TWIKIT_AUTH_INFO_2, TWIKIT_PASSWORD, TWIKIT_TOTP_SECRET。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - 可选依赖，缺失时跳过采集
    from twikit import Client  # type: ignore
except ImportError:  # pragma: no cover
    Client = None  # type: ignore

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
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _extract_github_refs(text: str) -> List[str]:
    """从 tweet 文本中提取 owner/repo 形式的 GitHub 链接。"""
    if not text:
        return []
    refs = {f"{m.group(1)}/{m.group(2)}" for m in GITHUB_RE.finditer(text)}
    return sorted(refs)


def _get_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _get_cookies_file() -> str:
    # 默认将 cookies 存在项目 data 目录，避免与代码混在一起
    base = os.environ.get("TWIKIT_COOKIES_FILE")
    if base:
        return base
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        # 若创建失败，退回当前工作目录
        data_dir = "."
    return os.path.join(data_dir, "twikit_cookies.json")


async def _create_client() -> Optional["Client"]:
    if Client is None:
        logger.warning("twikit 未安装，跳过 Twitter twikit 采集（pip install twikit）")
        return None

    auth_info_1 = _get_env("TWIKIT_AUTH_INFO_1")
    password = _get_env("TWIKIT_PASSWORD")
    if not auth_info_1 or not password:
        logger.warning(
            "Twikit 登录信息未配置完整（至少需要 TWIKIT_AUTH_INFO_1 与 TWIKIT_PASSWORD），"
            "跳过 Twitter twikit 采集"
        )
        return None

    auth_info_2 = _get_env("TWIKIT_AUTH_INFO_2") or None
    totp_secret = _get_env("TWIKIT_TOTP_SECRET") or None
    cookies_file = _get_cookies_file()

    client = Client(language="en-US")

    # 优先尝试使用已有 cookies，避免频繁登录触发风控
    if os.path.exists(cookies_file):
        try:
            client.load_cookies(cookies_file)
            logger.info("Twikit 已从 cookies 加载会话: %s", cookies_file)
            return client
        except Exception as e:  # pragma: no cover
            logger.warning("加载 Twikit cookies 失败，将尝试重新登录: %s", e)

    # 若 cookies 不存在或加载失败，再进行一次登录并写入 cookies
    try:
        await client.login(
            auth_info_1=auth_info_1,
            auth_info_2=auth_info_2,
            password=password,
            totp_secret=totp_secret,
            cookies_file=cookies_file,
        )
        logger.info("Twikit 登录成功，cookies 文件: %s", cookies_file)
        return client
    except Exception as e:  # pragma: no cover - 网络/登录环境相关
        logger.warning("Twikit 登录失败，跳过 Twitter twikit 采集: %s", e)
        return None


async def _collect_async(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    twitter_cfg = (config or {}).get("twitter") or {}
    accounts = twitter_cfg.get("accounts") or []
    if not accounts:
        return []

    fetch_limit = int(twitter_cfg.get("fetch_limit", 10))
    days_window = int(twitter_cfg.get("days_window", 3))

    client = await _create_client()
    if client is None:
        return []

    items: List[Dict[str, Any]] = []

    for raw_handle in accounts:
        handle = str(raw_handle or "").strip()
        if not handle:
            continue
        screen_name = handle.lstrip("@")

        try:
            user = await client.get_user_by_screen_name(screen_name)
        except Exception as e:  # pragma: no cover - 网络/账号环境相关
            logger.warning("Twikit 获取用户失败 handle=%s: %s", handle, e)
            continue

        try:
            tweets_result = await client.get_user_tweets(
                user.id,
                "Tweets",
                count=max(5, min(fetch_limit, 50)),
            )
        except Exception as e:  # pragma: no cover
            logger.warning("Twikit 获取时间线失败 handle=%s: %s", handle, e)
            continue

        # tweets_result 是 Result[Tweet]，可迭代
        count_for_handle = 0
        for tw in tweets_result:
            # 简单时间窗口过滤：如果有 created_at_datetime，则按 days_window 粗略过滤
            try:
                created_dt = getattr(tw, "created_at_datetime", None)
                if created_dt is not None:
                    from datetime import datetime, timedelta

                    if created_dt < datetime.utcnow() - timedelta(days=days_window):
                        continue
            except Exception:
                pass

            text = getattr(tw, "text", "") or ""
            title = _clean_title(text)
            tweet_id = getattr(tw, "id", "") or ""
            if not tweet_id:
                continue

            url = f"https://twitter.com/{screen_name}/status/{tweet_id}"
            vid = generate_id(url or tweet_id)
            github_refs = _extract_github_refs(text)
            published_at = getattr(tw, "created_at", "") or ""

            item: Dict[str, Any] = {
                "id": vid,
                "platform": "twitter",
                "title": title,
                "url": url,
                "source": f"@{screen_name}",
                "published_at": published_at,
                "score": 0.0,
                "github_refs": github_refs,
            }
            items.append(item)
            count_for_handle += 1
            if count_for_handle >= fetch_limit:
                break

        logger.info(
            "Twitter twikit: handle=%s, tweets_used=%d",
            handle,
            count_for_handle,
        )

    return items


def collect(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """同步入口，供 VideosCollector 调用。"""
    try:
        return asyncio.run(_collect_async(config))
    except RuntimeError:
        # 若在已有事件循环中（极少见），退回创建新循环
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_collect_async(config))
        finally:
            try:
                loop.close()
            except Exception:
                pass

