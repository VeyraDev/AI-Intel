"""
Daily report generator: top_n updates -> prompt -> LLM -> Report -> reports.json.
LLM called only here; API key from environment.
"""
import logging
from typing import List

from generator.base import BaseGenerator
from generator.prompt_builder import PromptBuilder
from generator.llm_client import get_api_key, chat_completion
from models.report import Report
from models.signal import Signal
from storage.json_store import JSONStore
from utils.hashing import generate_id
from utils.time_utils import format_date, format_datetime, get_now, get_timezone
from processor.signal_normalizer import build_signals_from_context

logger = logging.getLogger("ai_intel")


class DailyReportGenerator(BaseGenerator):
    def __init__(self, config: dict, storage: JSONStore):
        self.config = config
        self.storage = storage
        self.prompt_builder = PromptBuilder()
        report_cfg = config.get("report") or {}
        self.provider = report_cfg.get("provider", "moonshot")
        self.model_name = report_cfg.get("model_name", "moonshot-v1-8k")
        bases = report_cfg.get("api_base") or {}
        self.api_base = bases.get(self.provider) or ""
        self.temperature = float(report_cfg.get("temperature", 0.7))
        self.max_tokens = int(report_cfg.get("max_tokens", 800))
        limits = config.get("limits") or {}
        self.top_n = int(limits.get("top_n", 5))

    def generate(self, context: dict) -> None:
        # 1) 先拿经过 processors 处理后的 updates（去重/评分/过滤后）
        updates = context.get("updates", [])
        if not updates:
            logger.warning("No updates for daily report")
            self._append_report("", "今日无更新数据。")
            return

        # 2) 基于 updates 构造统一的 Signal 列表，并按 top_n 截断（非视频部分）
        base_signals = build_signals_from_context({"updates": updates}) or []
        base_signals = list(base_signals)[: self.top_n]

        # 3) 从 videos.json 读取最近的 5 条视频，转为 Signal 并合并
        video_signals = self._load_video_signals(max_count=5)

        combined: List[Signal] = []
        seen_ids: set[str] = set()
        for sig in list(base_signals) + list(video_signals):
            sid = getattr(sig, "id", "") or ""
            if not sid or sid in seen_ids:
                continue
            seen_ids.add(sid)
            combined.append(sig)

        if not combined:
            logger.warning("No signals for daily report (after normalization)")
            self._append_report("", "今日无更新数据（无有效信号）。")
            return

        # 4) 使用新版基于 Signal 的结构化 Prompt
        prompt = self.prompt_builder.build_daily_from_signals(combined, trend_stats=None, context=None)
        api_key = get_api_key(self.provider)
        content = chat_completion(
            self.provider,
            self.model_name,
            self.api_base,
            api_key,
            prompt,
            self.temperature,
            self.max_tokens,
        )
        if not content:
            # LLM 未返回内容（如 429 限流），视为阶段失败，抛出异常以便 Scheduler 不更新 last_success
            raise RuntimeError("日报生成失败：LLM 未返回内容（可能限流或未配置 API Key）")
        self._append_report(content, "")

    def _append_report(self, content: str, fallback: str) -> None:
        tz = get_timezone(self.config)
        now = get_now(tz)
        date_str = format_date(now)
        report = Report(
            id=generate_id(date_str + content or fallback),
            date=date_str,
            content=content or fallback,
            generated_at=format_datetime(now),
        )
        existing = self.storage.read_json("reports.json")
        if existing is None:
            existing = {"reports": []}
        if not isinstance(existing, dict):
            existing = {"reports": []}
        reports_list = existing.get("reports") or []
        reports_list.append(report.to_dict())
        existing["reports"] = reports_list
        self.storage.write_json("reports.json", existing)
        logger.info("Daily report saved for %s", date_str)

    def _load_video_signals(self, max_count: int = 5) -> List[Signal]:
        """从 videos.json 读取最近的视频，并转换为 Signal 列表。

        - 不参与 processors 链路，只在日报生成阶段额外并入；
        - 目前仅按 published_at 字符串排序，取最近的 max_count 条。
        """
        try:
            data = self.storage.read_json("videos.json")
        except Exception:
            logger.debug("Failed to read videos.json for daily report video signals")
            return []

        if not isinstance(data, dict):
            return []
        videos = data.get("videos") or []
        if not isinstance(videos, list) or not videos:
            return []

        # 按 published_at 简单降序排序（无日期的排后）
        def _key(item: dict) -> tuple:
            if not isinstance(item, dict):
                return (1, "")
            published = str(item.get("published_at") or "")
            return (0, published) if published else (1, "")

        sorted_videos = sorted(videos, key=_key, reverse=True)[: max_count]

        result: List[Signal] = []
        for v in sorted_videos:
            if not isinstance(v, dict):
                continue
            try:
                sig = Signal.from_video(v)
            except Exception as e:  # pragma: no cover - 防御性兜底
                logger.debug("Failed to convert video to Signal for daily report: %s", e)
                continue
            result.append(sig)

        logger.info("Loaded %d video signals for daily report", len(result))
        return result
