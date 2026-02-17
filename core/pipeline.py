"""
Pipeline：仅负责执行阶段函数，不判断日期、不写状态。
run_stage(stage_name) 支持 collect / process / generate。
"""
import logging
from typing import Any

from storage.json_store import JSONStore
from utils.time_utils import format_date, get_now, get_timezone

logger = logging.getLogger("ai_intel")

COLLECTED_UPDATES_FILE = "collected_updates.json"


class Pipeline:
    def __init__(
        self,
        config: dict,
        collectors: list,
        processors: list,
        generators: list,
        storage: JSONStore,
    ):
        self.config = config
        self.collectors = collectors
        self.processors = processors
        self.generators = generators
        self.storage = storage
        self._context: dict[str, Any] = {}

    def run_stage(self, stage_name: str) -> None:
        """执行单个阶段：collect | process | generate。不判断日期，不更新状态。"""
        if stage_name == "collect":
            self._run_collect()
        elif stage_name == "process":
            self._run_process()
        elif stage_name == "generate":
            self._run_generate()
        else:
            raise ValueError(f"Unknown stage: {stage_name}")

    def _run_collect(self) -> None:
        """执行所有 Collectors，结果写入 _context 并持久化供 process 使用。"""
        self._context = {"updates": []}
        from collectors.base import SignalCollector, ContentCollector
        for c in self.collectors:
            if isinstance(c, SignalCollector):
                c.collect(self._context)
        for c in self.collectors:
            if isinstance(c, ContentCollector):
                c.collect(self._context)
        self._save_collected_updates()

    def _save_collected_updates(self) -> None:
        """将 collect 阶段的 updates 写入 data/collected_updates.json，供 process 单阶段调试加载。"""
        updates = self._context.get("updates", [])
        data = self._to_updates_payload(updates)
        self.storage.write_json(COLLECTED_UPDATES_FILE, data)

    def _load_collected_updates(self) -> list:
        """从 data/collected_updates.json 加载 updates（单阶段调试 process 时使用）。"""
        raw = self.storage.read_json(COLLECTED_UPDATES_FILE)
        if not raw or not isinstance(raw, dict):
            return []
        return list(raw.get("updates") or [])

    def _run_process(self) -> None:
        """执行所有 Processors；若 context 无 updates 则从 collected_updates.json 加载；最后写入 updates.json。"""
        if not self._context.get("updates"):
            self._context["updates"] = self._load_collected_updates()
        for p in self.processors:
            p.process(self._context)
        tz = get_timezone(self.config)
        today = format_date(get_now(tz))
        self._save_updates(self._context.get("updates", []), today)

    def _run_generate(self) -> None:
        """执行所有 Generators；若 context 无 updates 则从 updates.json 加载。"""
        if not self._context.get("updates"):
            raw = self.storage.read_json("updates.json")
            if isinstance(raw, dict) and raw.get("updates"):
                self._context["updates"] = raw["updates"]
            else:
                self._context["updates"] = []
        for g in self.generators:
            g.generate(self._context)

    def _to_updates_payload(self, updates: list) -> dict:
        def to_dict(u: Any) -> dict:
            if hasattr(u, "to_dict"):
                return u.to_dict()
            if isinstance(u, dict):
                return u
            return {}
        return {"updates": [to_dict(u) for u in updates]}

    def _save_updates(self, updates: list, date: str) -> None:
        """写入 data/updates.json（process 阶段结束时调用）。"""
        data = {"date": date, "updates": self._to_updates_payload(updates)["updates"]}
        self.storage.write_json("updates.json", data)
        logger.info("Pipeline process: %d updates saved to updates.json", len(updates))
