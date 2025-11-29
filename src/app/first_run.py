"""First-run experience state tracking utilities."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from .paths import CONFIG_DIR

_MARKER_FILENAME = "first_run_marker.txt"


def marker_path() -> Path:
    """Return the path of the first-run marker file."""
    return CONFIG_DIR / _MARKER_FILENAME


def read_marker() -> int | None:
    """Read the stored marker value from disk.

    Returns the parsed integer value if available, otherwise ``None``.
    """
    path = marker_path()
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.error("读取首次运行标记失败: {error}", error=str(exc))
        return None
    if not raw:
        return None
    try:
        return int(raw, 10)
    except ValueError:
        logger.warning("首次运行标记内容无法解析: {raw}", raw=raw)
        return None


def should_show_first_run(expected_marker: int) -> bool:
    """Determine whether the first-run view should be displayed."""
    current = read_marker()
    return current != expected_marker


def update_marker(value: int) -> None:
    """Persist the supplied marker value to disk."""
    path = marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{int(value)}\n", encoding="utf-8")
    except OSError as exc:
        logger.error("写入首次运行标记失败: {error}", error=str(exc))
        raise


def clear_marker() -> None:
    """Delete the marker file, forcing the next launch to show first-run."""
    path = marker_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.error("移除首次运行标记失败: {error}", error=str(exc))
        raise
