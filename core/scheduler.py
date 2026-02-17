"""
Scheduler：控制每日执行逻辑与阶段判断。每个阶段每天最多执行一次，独立记录状态。
"""
import logging
import time
from typing import Any

from storage.state_store import StateStore
from utils.time_utils import format_date, get_now, get_timezone

logger = logging.getLogger("ai_intel")

STAGES = ("collect", "process", "generate")


class Scheduler:
    def __init__(self, config: dict, pipeline: Any, state_store: StateStore):
        self.config = config
        self.pipeline = pipeline
        self.state_store = state_store

    def run(self, stage: str | None = None, force: bool = False) -> None:
        """
        执行流程。若 force=True 且 stage 指定，则仅执行该阶段且不做日期检查。
        否则按 collect → process → generate 顺序，今日已成功则跳过；有阶段依赖。
        """
        tz = get_timezone(self.config)
        today = format_date(get_now(tz))

        if force and stage:
            if stage not in STAGES:
                logger.error("Unknown stage: %s", stage)
                return
            self._execute_stage(stage, today, skip_date_check=True)
            return

        state = self.state_store.load_state()
        for s in STAGES:
            last = self.state_store.get_stage_last_success(s)
            if last == today:
                logger.info("[%s] 已执行（last_success=%s），跳过", s, today)
                continue
            # 阶段依赖：collect 未成功今日则不执行 process；process 未成功今日则不执行 generate
            if s == "process" and self.state_store.get_stage_last_success("collect") != today:
                logger.warning("[process] 今日 collect 未成功，跳过")
                continue
            if s == "generate" and self.state_store.get_stage_last_success("process") != today:
                logger.warning("[generate] 今日 process 未成功，跳过")
                continue
            self._execute_stage(s, today, skip_date_check=False)

    def _execute_stage(self, stage_name: str, today: str, *, skip_date_check: bool = False) -> None:
        """执行单阶段：记录开始时间、捕获异常、仅成功时更新 last_success、记录耗时。"""
        started = time.perf_counter()
        logger.info("[%s] 开始执行", stage_name)
        try:
            self.pipeline.run_stage(stage_name)
        except Exception as e:
            logger.exception("[%s] 执行失败: %s", stage_name, e)
            return
        elapsed = time.perf_counter() - started
        self.state_store.set_stage_last_success(stage_name, today)
        logger.info("[%s] 执行成功，耗时 %.2fs", stage_name, elapsed)
