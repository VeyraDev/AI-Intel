"""
Trend analyzer processor.

职责：
- 从 data/trending_history.json 中读取 GitHub Trending 历史；
- 按语言（language）维度进行简单的“上升 / 下降 / 稳定”趋势分析；
- 将结果写入 context["trend_stats"]，供日报生成使用。

说明：
- 目前仅使用语言作为近似主题（topics），后续可扩展为按 Signal.topics 统计。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from processor.base import BaseProcessor
from storage.json_store import JSONStore

logger = logging.getLogger("ai_intel")


class TrendAnalyzerProcessor(BaseProcessor):
    def __init__(self, config: dict, storage: JSONStore):
        self.config = config
        self.storage = storage

    def process(self, context: dict) -> None:
        """计算简单趋势统计，写入 context['trend_stats']。"""
        history = self._load_history()
        if not history:
            context["trend_stats"] = {}
            logger.info("TrendAnalyzer: no trending history, trend_stats={}")
            return

        # 使用最近 14 天（或不足 14 天时全部），前 7 天为 prev，后 7 天为 curr
        # 若天数不足 8 天，则仅按总量排序给出 rising_topics。
        days = history[-14:]
        if len(days) < 2:
            topics = self._aggregate_by_language(days)
            rising = sorted(topics.items(), key=lambda x: x[1], reverse=True)
            context["trend_stats"] = {
                "rising_topics": [name for name, _ in rising[:5]],
                "falling_topics": [],
                "stable_topics": [],
            }
            logger.info("TrendAnalyzer: history<2 days, only rising_topics computed")
            return

        mid = len(days) // 2
        prev_days = days[:mid]
        curr_days = days[mid:]

        prev_lang = self._aggregate_by_language(prev_days)
        curr_lang = self._aggregate_by_language(curr_days)

        deltas: Dict[str, float] = {}
        for lang in set(prev_lang.keys()) | set(curr_lang.keys()):
            prev_val = prev_lang.get(lang, 0.0)
            curr_val = curr_lang.get(lang, 0.0)
            deltas[lang] = curr_val - prev_val

        rising: List[Tuple[str, float]] = []
        falling: List[Tuple[str, float]] = []
        stable: List[Tuple[str, float]] = []

        # 简单阈值：delta > 0 视为上升，<0 为下降，接近 0 列为稳定
        for lang, delta in deltas.items():
            if delta > 0:
                rising.append((lang, delta))
            elif delta < 0:
                falling.append((lang, delta))
            else:
                stable.append((lang, delta))

        rising.sort(key=lambda x: x[1], reverse=True)
        falling.sort(key=lambda x: x[1])  # delta 为负，越小越降温
        stable.sort(key=lambda x: abs(x[1]))

        trend_stats = {
            "rising_topics": [name for name, _ in rising[:5]],
            "falling_topics": [name for name, _ in falling[:5]],
            "stable_topics": [name for name, _ in stable[:5]],
        }
        context["trend_stats"] = trend_stats
        logger.info(
            "TrendAnalyzer: rising=%s, falling=%s, stable=%s",
            trend_stats["rising_topics"],
            trend_stats["falling_topics"],
            trend_stats["stable_topics"],
        )

    def _load_history(self) -> List[dict]:
        try:
            raw = self.storage.read_json("trending_history.json")
        except Exception as e:  # pragma: no cover - I/O 相关防御
            logger.debug("TrendAnalyzer: failed to read trending_history.json: %s", e)
            return []
        if not isinstance(raw, dict):
            return []
        history = raw.get("history") or []
        return [h for h in history if isinstance(h, dict)]

    def _aggregate_by_language(self, days: List[dict]) -> Dict[str, float]:
        """按 language 聚合 stars_today，总和作为热度近似指标。"""
        agg: Dict[str, float] = {}
        for day in days:
            items = day.get("items") or []
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                lang = str(it.get("language") or "").strip() or "Unknown"
                stars = it.get("stars_today")
                try:
                    val = float(stars) if stars is not None else 0.0
                except (TypeError, ValueError):
                    val = 0.0
                agg[lang] = agg.get(lang, 0.0) + val
        return agg

