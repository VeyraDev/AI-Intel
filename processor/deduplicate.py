"""
Deduplicate processor: skip items already in state.processed_items_hash, then update state.
按日重置：若上次运行日期早于今天，则清空已处理集合，保证每天首次运行能产出当日更新与日报。
"""
import logging
from processor.base import BaseProcessor
from storage.state_store import StateStore
from utils.time_utils import format_date, format_datetime, get_now, get_timezone

logger = logging.getLogger("ai_intel")

# Max hashes to keep in state to avoid unbounded growth
MAX_PROCESSED_HASHES = 50000


class DeduplicateProcessor(BaseProcessor):
    def __init__(self, config: dict, state_store: StateStore):
        self.config = config
        self.state_store = state_store

    def process(self, context: dict) -> None:
        updates = context.get("updates", [])
        state = self.state_store.load_state()
        tz = get_timezone(self.config)
        today = format_date(get_now(tz))
        last_run = state.get("last_run") or ""
        last_run_date = last_run[:10] if isinstance(last_run, str) and len(last_run) >= 10 else ""
        # 若上次运行不是今天，则按日重置：本 run 不把历史 hash 当作已处理，保证每天能产出日报
        if last_run_date != today:
            state["processed_items_hash"] = []
        seen = set(state.get("processed_items_hash") or [])

        unique = []
        new_hashes = []
        for u in updates:
            uid = getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None)
            if not uid:
                continue
            if uid in seen:
                continue
            seen.add(uid)
            new_hashes.append(uid)
            unique.append(u)

        context["updates"] = unique
        if new_hashes:
            state["processed_items_hash"] = (state.get("processed_items_hash") or []) + new_hashes
            state["processed_items_hash"] = state["processed_items_hash"][-MAX_PROCESSED_HASHES:]
            tz = get_timezone(self.config)
            state["last_run"] = format_datetime(get_now(tz))
            self.state_store.save_state(state)
        logger.info("Deduplicate: %d -> %d updates", len(updates), len(unique))
