"""Report model for reports.json."""
from dataclasses import dataclass
from typing import Any


@dataclass
class Report:
    id: str
    date: str
    content: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": self.date,
            "content": self.content,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Report":
        return cls(
            id=d.get("id", ""),
            date=d.get("date", ""),
            content=d.get("content", ""),
            generated_at=d.get("generated_at", ""),
        )
