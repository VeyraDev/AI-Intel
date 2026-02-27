"""Unified Signal model used as input for daily reports and higher-level analysis.

设计目标：
- 将不同来源的 Update / 视频等原始数据映射为统一的结构，便于打分、筛选、聚类和日报生成。
- 与现有 `Update` / `Video` 模型解耦：不改变 collectors 的输出，只在处理/生成阶段做统一抽象。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional

from models.update import Update
from models.video import Video


@dataclass
class Signal:
    """统一信号结构。

    - id: 稳定唯一标识（通常来自 Update.id / Video.id）
    - type: 语义类型，如 paper | code | video | blog | news | other
    - source: 技术来源平台，如 github | arxiv | rss | bilibili | other
    - title: 短标题
    - summary: 简要摘要（可选，用于帮助 LLM 理解）
    - raw_text: 更长的原始文本（如 RSS summary / 推文全文），可选
    - url: 原始链接
    - published_at: 统一字符串时间（ISO8601 或日期）
    - topics: 主题/标签列表，例如 ["agent", "evaluation"]
    - score: 综合得分（由 scoring/filtering 等 processor 负责维护）
    - metrics: 源相关数值，如 stars_today / views / retweets 等
    """

    id: str
    type: str
    source: str
    title: str
    summary: str = ""
    raw_text: str = ""
    url: str = ""
    published_at: str = ""
    topics: List[str] = field(default_factory=list)
    score: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好的 dict。"""
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "raw_text": self.raw_text,
            "url": self.url,
            "published_at": self.published_at,
            "topics": list(self.topics),
            "score": self.score,
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_update(
        cls,
        u: Update | dict[str, Any],
        *,
        type_hint: Optional[str] = None,
        source_hint: Optional[str] = None,
        topics: Optional[Iterable[str]] = None,
    ) -> "Signal":
        """从 Update / dict 构造 Signal。

        - 尽量保持无损：id/title/url/source/published_at/score/summary/stars_today -> metrics。
        - type/source 若未显式给出，基于 tags / source / url 做启发式推断。
        """
        if isinstance(u, Update):
            data = u.to_dict()
        else:
            data = dict(u)

        uid = str(data.get("id", "") or "")
        title = str(data.get("title", "") or "")
        url = str(data.get("url", "") or "")
        source_raw = str(data.get("source", "") or "")
        published_at = str(data.get("published_at", "") or "")
        score = float(data.get("score", 0) or 0)
        tags = list(data.get("tags") or [])
        summary = str(data.get("summary", "") or "")

        # 1) 推断 type
        t = type_hint or _infer_type_from_update(tags, source_raw, url)
        # 2) 推断 source 平台
        s = source_hint or _infer_source_from_update(tags, source_raw, url)

        topics_list: list[str] = list(topics or [])
        # 默认把 tags 并入 topics，后续 processor 可再细化
        for tag in tags:
            if tag and tag not in topics_list:
                topics_list.append(tag)

        metrics: dict[str, Any] = {}
        if "stars_today" in data and data["stars_today"] is not None:
            metrics["stars_today"] = data["stars_today"]

        return cls(
            id=uid,
            type=t or "other",
            source=s or "other",
            title=title or url or uid,
            summary=summary,
            raw_text="",
            url=url,
            published_at=published_at,
            topics=topics_list,
            score=score,
            metrics=metrics,
        )

    @classmethod
    def from_video(
        cls,
        v: Video | dict[str, Any],
        *,
        source_hint: Optional[str] = None,
        topics: Optional[Iterable[str]] = None,
    ) -> "Signal":
        """从 Video / dict 构造 Signal，统一为 type='video'。"""
        if isinstance(v, Video):
            data = v.to_dict()
        else:
            data = dict(v)

        vid = str(data.get("id", "") or "")
        title = str(data.get("title", "") or "")
        url = str(data.get("url", "") or "")
        author = str(data.get("source", "") or "")
        published_at = str(data.get("published_at", "") or "")
        score = float(data.get("score", 0) or 0)
        platform = str(data.get("platform", "") or "")

        s = source_hint or (platform or "bilibili")

        topics_list: list[str] = list(topics or [])
        # 简单把平台也当作一个 topic
        if platform and platform not in topics_list:
            topics_list.append(platform)

        metrics: dict[str, Any] = {}
        github_refs = data.get("github_refs") or []
        if github_refs:
            metrics["github_refs"] = list(github_refs)

        return cls(
            id=vid,
            type="video",
            source=s,
            title=title or url or vid,
            summary="",
            raw_text="",
            url=url,
            published_at=published_at,
            topics=topics_list,
            score=score,
            metrics=metrics,
        )


def _infer_type_from_update(tags: list[str], source: str, url: str) -> str:
    tags_lower = {t.lower() for t in tags}
    src_lower = source.lower()
    url_lower = url.lower()

    if "arxiv" in tags_lower or "paper" in tags_lower or "cs." in src_lower:
        return "paper"
    if "blog" in tags_lower or "research" in tags_lower:
        return "blog"
    if "trending" in tags_lower or "github" in src_lower or "github.com" in url_lower:
        return "code"
    return "other"


def _infer_source_from_update(tags: list[str], source: str, url: str) -> str:
    tags_lower = {t.lower() for t in tags}
    src_lower = source.lower()
    url_lower = url.lower()

    if "github.com" in url_lower or "github" in src_lower:
        return "github"
    if "arxiv" in tags_lower or "arxiv.org" in url_lower:
        return "arxiv"
    if "blog" in tags_lower or "research" in tags_lower:
        return "rss"
    return "other"

