"""
Videos collector (SignalCollector).
- 抓取各 UP 近期一批视频（非仅今日；API 返回即用），关键词+排除词过滤，提取 GitHub 链接 → 更新 bloggers.json
- 有关键词匹配则按时间排序取前 N 条；若无匹配则用「仅通过排除词」的一批作为基础数据，按时间取前 N 条
- 保存至 videos.json；展示逻辑：按时间顺序展示前 N 条（如 5 条）
- 从 GitHub 项目链接提取 owner，调用 GitHub API 获取项目信息，将 owner 加入 bloggers.json
"""
import re
import logging
import os
from typing import Any

from collectors.base import SignalCollector
from collectors import twitter_collector
from collectors import twitter_scraper
from collectors import twitter_twikit
from models.video import Video
from storage.json_store import JSONStore
from utils.hashing import generate_id
from utils.time_utils import format_date, get_now, get_timezone
from utils.bilibili_wbi import get_wbi_keys, enc_wbi

logger = logging.getLogger("ai_intel")

try:
    import requests
except ImportError:
    requests = None


class VideosCollector(SignalCollector):
    def __init__(self, config: dict, storage: JSONStore):
        self.config = config
        self.storage = storage

    def collect(self, context: dict) -> None:
        """不修改 context['updates']，仅更新 bloggers.json 并写入 videos.json。"""
        if not requests:
            logger.warning("requests not installed; skip videos collector")
            return
        videos_cfg = self.config.get("videos") or {}
        platforms = videos_cfg.get("platforms") or {}
        video_filter = self.config.get("video_filter") or {}
        keywords = [k for k in (video_filter.get("keywords") or []) if k]
        keywords_lower = set((k or "").strip().lower() for k in keywords)
        exclude = set((k or "").strip().lower() for k in video_filter.get("exclude_keywords") or [])
        fetch_limit = videos_cfg.get("fetch_limit", 20)
        display_count = int(videos_cfg.get("display_count", 5))  # 前端主展示条数（按时间前 N）
        max_history = int(videos_cfg.get("max_history", 50))     # videos.json 中最多保留多少条历史记录
        gh_extract = videos_cfg.get("github_extract") or {}
        gh_regex = gh_extract.get("regex", r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
        scoring = (videos_cfg.get("scoring") or {})
        keyword_weight = float(scoring.get("keyword_weight", 1))
        github_ref_weight = float(scoring.get("github_ref_weight", 0.5))

        mentions: dict[str, int] = {}
        all_videos: list[Video] = []   # 通过关键词过滤的（B站）
        raw_videos: list[Video] = []   # 仅通过排除词，用作基础数据（无关键词匹配时，B站）

        # 1) 采集各平台视频信号
        twitter_items: list[dict[str, Any]] = []

        for platform_name, platform_cfg in platforms.items():
            # 统一先看 enabled，具体平台再各自校验配置
            if not platform_cfg.get("enabled"):
                continue
            if platform_name == "bilibili":
                if not platform_cfg.get("api_url"):
                    logger.warning("Bilibili 平台未配置 api_url，跳过 B站视频采集")
                    continue
                self._collect_bilibili(
                    platform_cfg, keywords_lower, exclude, fetch_limit,
                    gh_regex, keyword_weight, github_ref_weight,
                    mentions, all_videos, raw_videos,
                )
            elif platform_name == "twitter":
                # Twitter 视频推文采集可选择官方 API、网页爬虫或 twikit 模式
                twitter_cfg = (self.config.get("twitter") or {})
                mode = str(twitter_cfg.get("mode") or "api").lower()
                try:
                    if mode == "scrape":
                        twitter_items = twitter_scraper.collect(self.config) or []
                    elif mode == "twikit":
                        twitter_items = twitter_twikit.collect(self.config) or []
                    else:
                        twitter_items = twitter_collector.collect(self.config) or []
                except Exception as e:
                    logger.warning("Twitter 视频采集失败（mode=%s）: %s", mode, e)
                    twitter_items = []

        # 2) 将 Twitter 中的 GitHub 引用并入 mentions，用于 bloggers.json 更新和 GitHub owner 提取
        for item in twitter_items:
            for ref in item.get("github_refs") or []:
                if not ref:
                    continue
                mentions[ref] = mentions.get(ref, 0) + 1

        if mentions:
            # 从 GitHub 项目链接提取 owner 并加入 bloggers
            github_owners = self._extract_github_owners(list(mentions.keys()))
            if github_owners:
                self._add_github_owners_to_bloggers(github_owners)
            # 更新 bloggers.json（项目提及计数）
            self._update_bloggers_json(mentions)

        # 3) 合并 B站 与 Twitter 视频，统一写入 videos.json
        # B站：按时间排序（published_at 降序，新的在前），取前 display_count 条；无日期置后
        def sort_key_video(v: Video) -> tuple:
            # (0, date) 有日期时排前面，(1, "") 无日期时排后面；reverse 后新的在前
            return (0, v.published_at) if v.published_at else (1, "")

        bili_selected: list[Video] = sorted(all_videos, key=sort_key_video, reverse=True)[:display_count]
        if not bili_selected and raw_videos:
            bili_selected = sorted(raw_videos, key=sort_key_video, reverse=True)[:display_count]
            logger.info("Videos collector: 无关键词匹配，使用 %d 条基础数据（按时间前 %d）", len(bili_selected), display_count)

        # 将 B站 Video 对象转为 dict，并标记平台为 bilibili
        bili_dicts: list[dict[str, Any]] = []
        for v in bili_selected:
            d = v.to_dict()
            d["platform"] = d.get("platform") or "bilibili"
            bili_dicts.append(d)

        # Twitter 项目已按统一 schema 返回，直接并入
        merged: list[dict[str, Any]] = bili_dicts + list(twitter_items or [])

        # 统一按 published_at 降序排序（缺失日期的排后）
        def sort_key_any(item: dict[str, Any]) -> tuple:
            published = str(item.get("published_at") or "")
            return (0, published) if published else (1, "")

        merged_sorted = sorted(merged, key=sort_key_any, reverse=True)

        # 4) 与历史数据合并，而不是完全重写
        tz = get_timezone(self.config)
        today = format_date(get_now(tz))

        existing = self.storage.read_json("videos.json")
        if not existing or not isinstance(existing, dict):
            existing = {"date": today, "videos": []}
        existing_list = existing.get("videos") or []
        if not isinstance(existing_list, list):
            existing_list = []

        # 新数据在前，历史在后，按 id 去重，限制总条数 max_history
        combined = list(merged_sorted) + list(existing_list)
        seen_ids: set[str] = set()
        history: list[dict[str, Any]] = []
        for item in combined:
            if not isinstance(item, dict):
                continue
            vid = str(item.get("id") or "")
            if not vid or vid in seen_ids:
                continue
            seen_ids.add(vid)
            history.append(item)
            if len(history) >= max_history:
                break

        self.storage.write_json("videos.json", {
            "date": today,
            "videos": history,
        })
        logger.info(
            "Videos collector: bloggers %d mentions, videos.json 本次新增 %d 条，合计保留 %d 条（历史上限 %d）%s",
            len(mentions), len(merged_sorted), len(history), max_history,
            "（基础数据，仅 B站）" if not all_videos and bili_selected else "",
        )

    def _collect_bilibili(
        self,
        platform_cfg: dict,
        keywords_lower: set[str],
        exclude: set[str],
        fetch_limit: int,
        gh_regex: str,
        keyword_weight: float,
        github_ref_weight: float,
        mentions: dict[str, int],
        all_videos: list,
        raw_videos: list,
    ) -> None:
        api_url = platform_cfg.get("api_url", "")
        uids = platform_cfg.get("uids") or []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0",
            "Referer": "https://www.bilibili.com",
        }
        # 获取 WBI 签名密钥
        wbi_keys = get_wbi_keys()
        if "/wbi/" in api_url:
            if not wbi_keys:
                logger.error("WBI API 需要签名，但无法获取 WBI keys，跳过 B站视频采集")
                return
            logger.debug("已获取 WBI keys，将使用签名调用 API")
        
        for uid in uids[:20]:
            try:
                params = {"mid": uid, "ps": min(30, fetch_limit), "pn": 1}
                # 如果使用 WBI API，添加签名
                if "/wbi/" in api_url and wbi_keys:
                    img_key, sub_key = wbi_keys
                    params = enc_wbi(params, img_key, sub_key)
                    logger.debug("Bilibili uid %s: 使用 WBI 签名调用 API", uid)
                r = requests.get(api_url, params=params, headers=headers, timeout=15)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                logger.warning("Bilibili uid %s 请求异常: %s", uid, e)
                continue
            if not isinstance(data, dict) or data.get("code") != 0:
                logger.warning("Bilibili uid %s 返回异常 code=%s", uid, data.get("code") if isinstance(data, dict) else "?")
                continue
            # API 返回 data.list.vlist（列表在 list.vlist 里）
            inner = (data.get("data") or {}).get("list")
            if isinstance(inner, list):
                raw_list = inner
            elif isinstance(inner, dict):
                raw_list = inner.get("vlist") or inner.get("archives") or []
            else:
                raw_list = []
            raw_count = len(raw_list)
            added_this_uid = 0
            for v in raw_list[:fetch_limit]:
                title = (v.get("title") or "").strip()
                desc = (v.get("description") or v.get("desc") or "").strip()
                text = (title + " " + desc).lower()
                if exclude and any(ex in text for ex in exclude):
                    continue
                # 提取 GitHub 链接
                full_text = title + " " + desc
                github_refs = list({m.group(0).strip("/") for m in re.finditer(gh_regex, full_text)})
                for ref in github_refs:
                    if ref:
                        mentions[ref] = mentions.get(ref, 0) + 1
                # 视频链接与作者
                bvid = v.get("bvid") or v.get("aid") or ""
                video_url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
                if not video_url and v.get("link"):
                    video_url = v.get("link", "")
                author = v.get("author") or v.get("owner", {}) or {}
                if isinstance(author, dict):
                    author_name = author.get("name") or str(uid)
                else:
                    author_name = str(author)
                published_at = v.get("created") or v.get("pubdate") or ""
                if published_at and isinstance(published_at, (int, float)):
                    from datetime import datetime
                    try:
                        published_at = datetime.fromtimestamp(published_at).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        published_at = str(published_at)
                published_at_str = published_at if isinstance(published_at, str) else str(published_at)
                video_id = generate_id(video_url or title)
                kw_count = sum(1 for k in keywords_lower if k in text)
                score = kw_count * keyword_weight + len(github_refs) * github_ref_weight
                video = Video(
                    id=video_id,
                    title=title,
                    url=video_url,
                    source=author_name,
                    published_at=published_at_str,
                    score=score,
                    github_refs=github_refs,
                )
                raw_videos.append(video)   # 通过排除词的都进基础数据
                if not keywords_lower or any(kw in text for kw in keywords_lower):
                    all_videos.append(video)
                    added_this_uid += 1
            if raw_count > 0 and added_this_uid == 0:
                logger.info("Bilibili uid %s: API 返回 %d 条，关键词过滤后 0 条（keywords=%s）", uid, raw_count, list(keywords_lower)[:5])
            elif raw_count > 0:
                logger.debug("Bilibili uid %s: 原始 %d 条，通过 %d 条", uid, raw_count, added_this_uid)

    def _update_bloggers_json(self, mentions: dict[str, int]) -> None:
        raw = self.storage.read_json("bloggers.json")
        if not raw or not isinstance(raw, dict):
            raw = {"bloggers": []}
        bloggers_list = raw.get("bloggers") if isinstance(raw, dict) else []
        if not isinstance(bloggers_list, list):
            bloggers_list = []
        by_id = {b.get("id"): b for b in bloggers_list if isinstance(b, dict) and b.get("id")}
        tz = get_timezone(self.config)
        today = format_date(get_now(tz))
        for entity_id, count in mentions.items():
            if entity_id in by_id:
                # 仅更新提及计数，保留原有 source/name 等（白名单不受影响）
                by_id[entity_id]["mention_count"] = by_id[entity_id].get("mention_count", 0) + count
                by_id[entity_id]["last_seen"] = today
            else:
                name = entity_id.split("/")[-1] if "/" in entity_id else entity_id
                by_id[entity_id] = {
                    "id": entity_id,
                    "name": name,
                    "source": f"https://github.com/{entity_id}" if entity_id.count("/") >= 1 else "",
                    "active": True,
                    "mention_count": count,
                    "last_seen": today,
                }
        raw["bloggers"] = list(by_id.values())
        self.storage.write_json("bloggers.json", raw)

    def _extract_github_owners(self, github_refs: list[str]) -> dict[str, str]:
        """从 GitHub 项目链接提取 owner，调用 GitHub API 获取项目信息。
        返回 {owner_username: project_full_name} 映射。
        """
        if not requests:
            return {}
        github_token = os.environ.get("GITHUB_TOKEN", "")
        headers = {}
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        headers["Accept"] = "application/vnd.github.v3+json"
        owners_map: dict[str, str] = {}
        github_cfg = self.config.get("github") or {}
        api_base = github_cfg.get("api_base", "https://api.github.com")
        for ref in github_refs:
            # ref 格式：https://github.com/owner/repo 或 owner/repo
            if not ref:
                continue
            # 清理 URL 格式
            if ref.startswith("https://github.com/"):
                ref = ref.replace("https://github.com/", "").strip("/")
            elif ref.startswith("http://github.com/"):
                ref = ref.replace("http://github.com/", "").strip("/")
            parts = ref.split("/")
            if len(parts) < 2:
                continue
            owner, repo = parts[0], parts[1]
            if not owner or not repo:
                continue
            # 调用 GitHub API 获取项目信息
            try:
                api_url = f"{api_base}/repos/{owner}/{repo}"
                resp = requests.get(api_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    repo_data = resp.json()
                    owner_login = repo_data.get("owner", {}).get("login", owner)
                    if owner_login:
                        owners_map[owner_login] = f"{owner}/{repo}"
                        logger.debug("GitHub 项目 %s/%s: owner=%s", owner, repo, owner_login)
                elif resp.status_code == 404:
                    logger.debug("GitHub 项目 %s/%s 不存在", owner, repo)
                elif resp.status_code == 403:
                    logger.warning("GitHub API 限流，跳过项目 %s/%s", owner, repo)
                else:
                    logger.debug("GitHub API 返回 %d for %s/%s", resp.status_code, owner, repo)
            except Exception as e:
                logger.debug("获取 GitHub 项目 %s/%s 信息失败: %s", owner, repo, e)
        return owners_map

    def _add_github_owners_to_bloggers(self, owners_map: dict[str, str]) -> None:
        """将 GitHub owner 加入 bloggers.json（如果不存在）。"""
        raw = self.storage.read_json("bloggers.json")
        if not raw or not isinstance(raw, dict):
            raw = {"bloggers": []}
        bloggers_list = raw.get("bloggers") if isinstance(raw, dict) else []
        if not isinstance(bloggers_list, list):
            bloggers_list = []
        by_id = {b.get("id"): b for b in bloggers_list if isinstance(b, dict) and b.get("id")}
        tz = get_timezone(self.config)
        today = format_date(get_now(tz))
        added_count = 0
        for owner_username, project_name in owners_map.items():
            # 使用 GitHub username 作为 id
            owner_id = owner_username
            if owner_id not in by_id:
                by_id[owner_id] = {
                    "id": owner_id,
                    "name": owner_username,
                    "source": f"https://github.com/{owner_username}.atom",
                    "active": True,
                    "mention_count": 0,
                    "last_seen": today,
                }
                added_count += 1
                logger.info("添加 GitHub owner 到 bloggers: %s (来自项目 %s)", owner_username, project_name)
            else:
                # 更新 last_seen
                by_id[owner_id]["last_seen"] = today
        if added_count > 0:
            raw["bloggers"] = list(by_id.values())
            self.storage.write_json("bloggers.json", raw)
            logger.info("已添加 %d 个 GitHub owner 到 bloggers.json", added_count)
