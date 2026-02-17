"""Build prompt string for daily report from update list."""
from typing import Any, Sequence


def _title(u: Any) -> str:
    return getattr(u, "title", None) or (u.get("title") if isinstance(u, dict) else "") or ""


def _url(u: Any) -> str:
    return getattr(u, "url", None) or (u.get("url") if isinstance(u, dict) else "") or ""


def _source(u: Any) -> str:
    return getattr(u, "source", None) or (u.get("source") if isinstance(u, dict) else "") or ""


def _score(u: Any) -> float:
    return getattr(u, "score", None) or (u.get("score") if isinstance(u, dict) else 0) or 0


class PromptBuilder:
    """Build structured prompt for daily report LLM."""

    def build_daily(self, updates: Sequence[Any]) -> str:
        """Return a single prompt string summarizing the top updates for the model."""
        lines = [
            "请根据以下今日精选更新，生成一份简短的每日情报日报（中文）。",
            "要求：概括要点、突出技术/开源相关亮点，控制在合理篇幅。",
            "",
            "--- 更新列表 ---",
        ]
        for i, u in enumerate(updates, 1):
            title = _title(u)
            url = _url(u)
            source = _source(u)
            score = _score(u)
            lines.append(f"{i}. [{source}] {title}")
            lines.append(f"   链接: {url} (得分: {score:.1f})")
        lines.append("")
        lines.append("--- 请生成日报正文 ---")
        return "\n".join(lines)
