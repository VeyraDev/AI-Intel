"""Video model for videos.json (B站精选 / Twitter 等). 独立于 Update，不参与 updates 流程。"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Video:
    id: str
    title: str
    url: str
    source: str  # 作者或 UP 主 / 账号
    published_at: str = ""
    score: float = 0.0
    github_refs: list[str] = field(default_factory=list)  # 提取的 GitHub 链接
    platform: str = "bilibili"  # 平台标记：bilibili | twitter | ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at,
            "score": self.score,
            "github_refs": list(self.github_refs),
            "platform": self.platform,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Video":
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            url=d.get("url", ""),
            source=d.get("source", ""),
            published_at=d.get("published_at", ""),
            score=float(d.get("score", 0)),
            github_refs=list(d.get("github_refs") or []),
            platform=d.get("platform", "bilibili") or "bilibili",
        )
