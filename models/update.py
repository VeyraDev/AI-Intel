"""Update model: id, title, url, source, published_at, score, tags."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Update:
    id: str
    title: str
    url: str
    source: str
    published_at: str = ""
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
    # Optional: content snippet (abstract / RSS summary) to help daily report analysis
    summary: str = ""
    # Optional for trending: stars_today
    stars_today: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at,
            "score": self.score,
            "tags": self.tags,
            **({"summary": self.summary} if self.summary else {}),
            **({"stars_today": self.stars_today} if self.stars_today is not None else {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Update":
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            url=d.get("url", ""),
            source=d.get("source", ""),
            published_at=d.get("published_at", ""),
            score=float(d.get("score", 0)),
            tags=list(d.get("tags") or []),
            summary=d.get("summary", "") or "",
            stars_today=d.get("stars_today"),
        )
