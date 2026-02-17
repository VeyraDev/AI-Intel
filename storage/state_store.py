"""
State persistence (state.json in data/). 记录阶段执行状态与去重 hash。
日期格式统一 YYYY-MM-DD。更新某阶段时禁止覆盖其他阶段或 processed_items_hash。
"""
from typing import Any

from storage.json_store import JSONStore

STAGES = ("collect", "process", "generate")


class StateStore:
    STATE_FILE = "state.json"

    def __init__(self, json_store: JSONStore):
        self._store = json_store

    def load_state(self) -> dict[str, Any]:
        """加载完整 state.json，保留所有已有键（含 collect/process/generate 与 processed_items_hash）。"""
        data = self._store.read_json(self.STATE_FILE)
        if not data or not isinstance(data, dict):
            return {}
        return dict(data)

    def save_state(self, state: dict[str, Any]) -> None:
        """写入完整 state 到 state.json。"""
        self._store.write_json(self.STATE_FILE, state)

    def get_stage_last_success(self, stage: str) -> str | None:
        """返回某阶段 last_success 日期（YYYY-MM-DD），无则 None。"""
        state = self.load_state()
        stage_data = state.get(stage)
        if not isinstance(stage_data, dict):
            return None
        return stage_data.get("last_success")

    def set_stage_last_success(self, stage: str, date: str) -> None:
        """仅更新该阶段的 last_success，不覆盖其他阶段或 processed_items_hash。"""
        state = self.load_state()
        if stage not in state or not isinstance(state[stage], dict):
            state[stage] = {}
        state[stage]["last_success"] = date
        self.save_state(state)

    def get_last_run(self) -> str | None:
        """兼容旧逻辑：返回最后运行时间（若有）。"""
        return self.load_state().get("last_run")

    def update_last_run(self, timestamp: str) -> None:
        """兼容：更新 last_run 并保存。"""
        s = self.load_state()
        s["last_run"] = timestamp
        self.save_state(s)
