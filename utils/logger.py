"""
Logging configuration. Log level is read from config (system.log_level).
Supports output to file and console.
"""
import logging
import sys
from pathlib import Path


def setup_logger(
    level: str = "INFO",
    log_file: str | None = None,
    name: str = "ai_intel",
) -> logging.Logger:
    """Configure and return logger. Level from config (e.g. INFO, DEBUG)."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger
