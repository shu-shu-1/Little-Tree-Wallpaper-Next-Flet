"""Application-level persistent settings storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from config import DEFAULT_CONFIG, save_config_file, get_config_file

from app.paths import CONFIG_DIR


class SettingsStore:
    """Simple JSON-backed settings store for application-level settings.

    Responsibilities:
    - load settings from a well-known path
    - provide get/set/reset/save operations
    - expose the underlying dict for read-only operations
    """

    def __init__(self, path: Path = CONFIG_DIR / "config.json") -> None:
        self._path = path
        self._data: Dict[str, Any] = dict(get_config_file(path))
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        try:
            if self._path.exists():
                text = self._path.read_bytes()
                # allow JSON content written by existing save_config_file
                try:
                    self._data = json.loads(text)
                except Exception:
                    # fallback: try orjson via save_config_file output (already JSON bytes)
                    self._data = json.loads(text.decode("utf-8", errors="ignore"))
            else:
                # create parent dir
                self._path.parent.mkdir(parents=True, exist_ok=True)
                # persist defaults
                save_config_file(str(self._path), DEFAULT_CONFIG)
                self._data = dict(DEFAULT_CONFIG)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("加载应用设置失败: {error}", error=str(exc))
            self._data = dict(DEFAULT_CONFIG)

    def save(self) -> None:
        try:
            save_config_file(str(self._path), self._data)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("保存应用设置失败: {error}", error=str(exc))

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key.

        Supports dotted keys for nested dict access, e.g. 'a.b.c'. If the key
        does not exist, returns `default`.
        """
        # fast path: direct top-level key
        if key in self._data:
            return self._data.get(key, default)

        # support dotted path
        if "." not in key:
            return self._data.get(key, default)

        cur: Any = self._data
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, key: str, value: Any) -> None:
        """Set a value by key.

        Supports dotted keys for nested dict assignment, creating intermediate
        dicts as needed. Examples:
          set('a.b.c', 1) -> {'a': {'b': {'c': 1}}}
          set('top', 2) -> {'top': 2}
        """
        # simple assignment for top-level
        if "." not in key:
            self._data[key] = value
            self.save()
            return

        parts = key.split(".")
        cur: Dict[str, Any] = self._data
        for part in parts[:-1]:
            if part not in cur or not isinstance(cur[part], dict):
                cur[part] = {}
            cur = cur[part]
        cur[parts[-1]] = value
        self.save()

    def reset(self) -> None:
        self._data = dict(DEFAULT_CONFIG)
        self.save()

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)


__all__ = ["SettingsStore"]
