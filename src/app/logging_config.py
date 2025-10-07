"""Centralized Loguru logging configuration for the application."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .constants import MODE
from .paths import CACHE_DIR

_LOG_CONFIGURED = False


def _resolve_log_directory() -> Path:
    log_dir = CACHE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging() -> None:
    """Configure Loguru sinks for console and rotating file outputs."""
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return

    log_dir = _resolve_log_directory()

    logger.remove()

    is_test_mode = MODE.upper() == "TEST"
    log_level = "DEBUG" if is_test_mode else "INFO"

    logger.add(
        sys.stderr,
        level=log_level,
        enqueue=True,
        backtrace=is_test_mode,
        diagnose=is_test_mode,
    )

    log_path = log_dir / "app_{time:YYYYMMDD_HHmmss}.log"
    logger.add(
        log_path,
        level=log_level,
        rotation="00:00",
        retention=10,
        enqueue=True,
        encoding="utf-8",
        backtrace=is_test_mode,
        diagnose=is_test_mode,
    )

    _LOG_CONFIGURED = True
