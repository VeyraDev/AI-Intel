"""
Signal normalizer processor.

职责：
- 从 context["updates"]（Update 或 dict 列表）构造统一的 Signal 列表；
- 不改变原有 processors 链路的行为，只是额外在 context 中填充 context["signals"]。

注意：
- 目前不直接依赖 videos.json，视频信号后续可在生成层或其他 Processor 中合并。
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, List

from models.signal import Signal
from processor.base import BaseProcessor

logger = logging.getLogger("ai_intel")


class SignalNormalizerProcessor(BaseProcessor):
    """将 updates 统一映射为 Signal 列表。

    - 输入：context["updates"]（可能是 models.Update 或 dict）
    - 输出：context["signals"] = List[Signal]
    - 不修改 context["updates"]，以保持与现有 Scoring/Filtering 兼容。
    """

    def __init__(self, config: dict):
        self.config = config

    def process(self, context: dict) -> None:
        updates = context.get("updates") or []
        if not isinstance(updates, list) or not updates:
            context["signals"] = []
            logger.info("SignalNormalizer: no updates, signals=[]")
            return

        signals: List[Signal] = []
        for u in updates:
            try:
                sig = Signal.from_update(u)
            except Exception as e:  # pragma: no cover - 防御性兜底
                logger.warning("SignalNormalizer: failed to normalize update %r: %s", u, e)
                continue
            signals.append(sig)

        context["signals"] = signals
        logger.info("SignalNormalizer: %d updates -> %d signals", len(updates), len(signals))


def build_signals_from_context(context: dict) -> list[Signal]:
    """辅助函数：从 context 中构造或复用 Signal 列表。

    用途：
    - 供 DailyReportGenerator 等直接调用，而不强依赖在 processors 链路中显式配置。
    """
    existing = context.get("signals")
    if isinstance(existing, list) and existing and isinstance(existing[0], Signal):
        return existing

    updates = context.get("updates") or []
    if not isinstance(updates, list) or not updates:
        return []

    signals: list[Signal] = []
    for u in updates:
        try:
            sig = Signal.from_update(u)
        except Exception as e:  # pragma: no cover
            logger.debug("build_signals_from_context: skip invalid update %r: %s", u, e)
            continue
        signals.append(sig)
    context["signals"] = signals
    return signals

