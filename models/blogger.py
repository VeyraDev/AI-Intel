"""Blogger model for bloggers.json."""
from dataclasses import dataclass
from typing import Any


@dataclass
class Blogger:
    id: str
    name: str
    source: str  # e.g. RSS URL or social type
    active: bool = True
    mention_count: int = 0
    last_seen: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "active": self.active,
            "mention_count": self.mention_count,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Blogger":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            source=d.get("source", ""),
            active=bool(d.get("active", True)),
            mention_count=int(d.get("mention_count", 0)),
            last_seen=d.get("last_seen", ""),
        )
