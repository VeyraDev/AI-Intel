"""
入口：仅加载配置、初始化 logger、初始化 Scheduler、调用 scheduler.run()。
不含日期判断与业务逻辑；调试模式通过命令行参数传入。
"""
import argparse
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_root))

try:
    from dotenv import load_dotenv
    load_dotenv(_root / ".env")
except ImportError:
    pass

from utils.logger import setup_logger
from core.registry import build_pipeline_from_config
from core.scheduler import Scheduler


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Intel Pipeline")
    parser.add_argument("--stage", choices=["collect", "process", "generate"], help="仅执行指定阶段（需配合 --force）")
    parser.add_argument("--force", action="store_true", help="忽略日期判断，强制执行")
    args = parser.parse_args()

    config_path = _root / "config.yaml"
    if not config_path.exists():
        print("Config not found: config.yaml", file=sys.stderr)
        sys.exit(1)

    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    log_level = (config.get("system") or {}).get("log_level", "INFO")
    setup_logger(level=log_level)

    pipeline, state_store = build_pipeline_from_config(str(config_path))
    scheduler = Scheduler(config, pipeline, state_store)

    if args.force and args.stage:
        scheduler.run(stage=args.stage, force=True)
    else:
        scheduler.run()


if __name__ == "__main__":
    main()
