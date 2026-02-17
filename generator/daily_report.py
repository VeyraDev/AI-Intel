"""
Daily report generator: top_n updates -> prompt -> LLM -> Report -> reports.json.
LLM called only here; API key from environment.
"""
import logging
from generator.base import BaseGenerator
from generator.prompt_builder import PromptBuilder
from generator.llm_client import get_api_key, chat_completion
from models.report import Report
from storage.json_store import JSONStore
from utils.hashing import generate_id
from utils.time_utils import format_date, format_datetime, get_now, get_timezone

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
        updates = context.get("updates", [])[: self.top_n]
        if not updates:
            logger.warning("No updates for daily report")
            self._append_report("", "今日无更新数据。")
            return

        prompt = self.prompt_builder.build_daily(updates)
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
