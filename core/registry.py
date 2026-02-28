"""
Plugin registry: collectors, processors, generators. Load from config and instantiate.
"""
import logging
from typing import Any, Type

from collectors.base import BaseCollector, SignalCollector, ContentCollector
from collectors.github_trending import GitHubTrendingCollector
from collectors.bloggers import BloggersCollector
from collectors.research_feeds import ResearchFeedsCollector
from collectors.videos import VideosCollector
from processor.base import BaseProcessor
from processor.deduplicate import DeduplicateProcessor
from processor.scoring import ScoringProcessor
from processor.filtering import FilteringProcessor
from processor.signal_normalizer import SignalNormalizerProcessor
from processor.trend_analyzer import TrendAnalyzerProcessor
from generator.base import BaseGenerator
from generator.daily_report import DailyReportGenerator
from storage.json_store import JSONStore
from storage.state_store import StateStore

logger = logging.getLogger("ai_intel")

COLLECTORS: dict[str, Type[BaseCollector]] = {
    "github_trending": GitHubTrendingCollector,
    "bloggers": BloggersCollector,
    "research_feeds": ResearchFeedsCollector,
    "videos": VideosCollector,
}
PROCESSORS: dict[str, Type[BaseProcessor]] = {
    "deduplicate": DeduplicateProcessor,
    "scoring": ScoringProcessor,
    "filtering": FilteringProcessor,
    # 可选：将 updates 映射为统一的 Signal 列表，写入 context["signals"]
    "signal_normalizer": SignalNormalizerProcessor,
    # 可选：基于 trending_history.json 生成简单趋势统计，写入 context["trend_stats"]
    "trend_analyzer": TrendAnalyzerProcessor,
}
GENERATORS: dict[str, Type[BaseGenerator]] = {
    "daily_report": DailyReportGenerator,
}


def register_collector(name: str, cls: Type[BaseCollector]) -> None:
    COLLECTORS[name] = cls


def get_collector(name: str) -> Type[BaseCollector] | None:
    return COLLECTORS.get(name)


def register_processor(name: str, cls: Type[BaseProcessor]) -> None:
    PROCESSORS[name] = cls


def get_processor(name: str) -> Type[BaseProcessor] | None:
    return PROCESSORS.get(name)


def register_generator(name: str, cls: Type[BaseGenerator]) -> None:
    GENERATORS[name] = cls


def get_generator(name: str) -> Type[BaseGenerator] | None:
    return GENERATORS.get(name)


def build_pipeline_from_config(config_path: str) -> "Pipeline":
    """Load config, build Pipeline with registered plugins."""
    import yaml
    from pathlib import Path
    from core.pipeline import Pipeline

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    data_dir = (config.get("storage") or {}).get("data_dir", "./data")
    store = JSONStore(data_dir)
    state_store = StateStore(store)

    # Signal collectors first, then content
    signal_names = (config.get("collectors") or {}).get("signal") or []
    content_names = (config.get("collectors") or {}).get("content") or []
    collectors: list[BaseCollector] = []
    for name in signal_names:
        cls = get_collector(name)
        if cls is None:
            logger.warning("Unknown signal collector: %s", name)
            continue
        if not issubclass(cls, SignalCollector):
            logger.warning("%s is not a SignalCollector; skip", name)
            continue
        collectors.append(cls(config, store))
    for name in content_names:
        cls = get_collector(name)
        if cls is None:
            logger.warning("Unknown content collector: %s", name)
            continue
        if not issubclass(cls, ContentCollector):
            logger.warning("%s is not a ContentCollector; skip", name)
            continue
        collectors.append(cls(config, store))

    processor_names = config.get("processors") or []
    processors: list[BaseProcessor] = []
    for name in processor_names:
        cls = get_processor(name)
        if cls is None:
            logger.warning("Unknown processor: %s", name)
            continue
        if name == "deduplicate":
            processors.append(cls(config, state_store))
        elif name == "trend_analyzer":
            processors.append(cls(config, store))
        else:
            processors.append(cls(config))

    generator_names = config.get("generators") or []
    generators: list[BaseGenerator] = []
    for name in generator_names:
        cls = get_generator(name)
        if cls is None:
            logger.warning("Unknown generator: %s", name)
            continue
        generators.append(cls(config, store))

    pipeline = Pipeline(config, collectors, processors, generators, store)
    return pipeline, state_store
