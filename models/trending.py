"""Trending model for trending.json (GitHub trending list with date)."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrendingItem:
    repo: str
    url: str
    stars_today: int
    language: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "url": self.url,
            "stars_today": self.stars_today,
            "language": self.language,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrendingItem":
        return cls(
            repo=d.get("repo", ""),
            url=d.get("url", ""),
            stars_today=int(d.get("stars_today", 0)),
            language=d.get("language", ""),
        )


@dataclass
class Trending:
    date: str
    items: list[TrendingItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "items": [x.to_dict() for x in self.items],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Trending":
        items = [TrendingItem.from_dict(x) for x in (d.get("items") or [])]
        return cls(date=d.get("date", ""), items=items)
