"""Centralized Loguru logging configuration for the application."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .constants import MODE
from .paths import CACHE_DIR

_LOG_CONFIGURED = False
_PERSISTENT_SINKS: list = []


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

    # 移除已有的 sinks，重新配置
    logger.remove()

    is_test_mode = MODE.upper() == "TEST"
    log_level = "DEBUG" if is_test_mode else "INFO"

    # 1) 尝试添加控制台 sink（sys.stderr）。在打包为 windowed exe 时
    # sys.stderr 可能为 None，loguru.add 会抛出 TypeError -> 在此处容错并回退到文件。
    try:
        if sys.stderr is None:
            raise TypeError("sys.stderr is None")
        logger.add(
            sys.stderr,
            level=log_level,
            enqueue=True,
            backtrace=is_test_mode,
            diagnose=is_test_mode,
        )
    except Exception:
        # 控制台不可用，回退到磁盘上的 console.log（追加）
        try:
            console_fallback = log_dir / "console.log"
            f = open(console_fallback, "a", encoding="utf-8")
            # 保持对打开文件对象的引用，避免被垃圾回收导致 sink 失效
            _PERSISTENT_SINKS.append(f)
            logger.add(
                f,
                level=log_level,
                enqueue=True,
                backtrace=is_test_mode,
                diagnose=is_test_mode,
            )
        except Exception:
            # 最后手段：不添加控制台 sink（所有日志将只写文件 sink）
            pass

    # 2) 添加按日期时间滚动的应用日志文件（主文件 sink），确保使用可写路径
    log_path = log_dir / "app_{time:YYYYMMDD_HHmmss}.log"
    try:
        logger.add(
            str(log_path),
            level=log_level,
            rotation="00:00",
            retention=10,
            enqueue=True,
            encoding="utf-8",
            backtrace=is_test_mode,
            diagnose=is_test_mode,
        )
    except Exception:
        # 如果直接传 Path/str 也失败（极少见），尝试用一个已打开的文件对象
        try:
            f2 = open(log_dir / "app_fallback.log", "a", encoding="utf-8")
            _PERSISTENT_SINKS.append(f2)
            logger.add(
                f2,
                level=log_level,
                enqueue=True,
                backtrace=is_test_mode,
                diagnose=is_test_mode,
            )
        except Exception:
            # 实在无法配置文件 sink，则降级为只移除旧 sinks（不添加任何新的）
            pass

    _LOG_CONFIGURED = True
