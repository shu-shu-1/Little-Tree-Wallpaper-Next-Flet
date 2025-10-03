"""Persistent configuration store for plugin settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .permissions import PermissionState, normalize_permission_state


@dataclass(slots=True)
class PluginConfigEntry:
    identifier: str
    enabled: bool
    source: dict[str, Any]
    permissions: dict[str, PermissionState]


class PluginConfigStore:
    """Load and persist plugin enablement and permission states."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = {"plugins": {}}
        self._load()

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {"plugins": {}}
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    def _ensure_entry(
        self,
        identifier: str,
        *,
        default_enabled: bool,
        source: dict[str, Any],
        permissions: dict[str, Any] | None = None,
    ) -> PluginConfigEntry:
        plugins = self._data.setdefault("plugins", {})
        entry = plugins.get(identifier)
        serialized_permissions = self._serialize_permissions(permissions)
        if entry is None:
            entry = {
                "enabled": default_enabled,
                "source": source,
                "permissions": serialized_permissions,
            }
            plugins[identifier] = entry
            self._save()
        else:
            # Merge source updates or new permissions keys without overriding grants
            entry.setdefault("enabled", default_enabled)
            entry.setdefault("source", source)
            entry.setdefault("permissions", {})
            if serialized_permissions:
                for key, value in serialized_permissions.items():
                    entry["permissions"].setdefault(key, value)
            self._save()
        return PluginConfigEntry(
            identifier=identifier,
            enabled=bool(entry.get("enabled", True)),
            source=dict(entry.get("source", {})),
            permissions=self._normalize_permissions(entry.get("permissions", {})),
        )

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def register_plugin(
        self,
        identifier: str,
        *,
        default_enabled: bool,
        source: dict[str, Any],
        permissions: dict[str, Any] | None = None,
    ) -> PluginConfigEntry:
        return self._ensure_entry(
            identifier,
            default_enabled=default_enabled,
            source=source,
            permissions=permissions,
        )

    def remove_plugin(self, identifier: str) -> None:
        plugins = self._data.setdefault("plugins", {})
        if identifier in plugins:
            del plugins[identifier]
            self._save()

    def is_enabled(self, identifier: str) -> bool:
        plugins = self._data.setdefault("plugins", {})
        entry = plugins.get(identifier)
        if entry is None:
            return True
        return bool(entry.get("enabled", True))

    def set_enabled(self, identifier: str, enabled: bool) -> None:
        plugins = self._data.setdefault("plugins", {})
        entry = plugins.setdefault(identifier, {})
        entry["enabled"] = enabled
        self._save()

    def get_permissions(self, identifier: str) -> dict[str, PermissionState]:
        plugins = self._data.setdefault("plugins", {})
        entry = plugins.get(identifier)
        if entry is None:
            return {}
        return self._normalize_permissions(entry.get("permissions", {}))

    def set_permission(self, identifier: str, permission: str, allowed: bool) -> None:
        state = PermissionState.GRANTED if allowed else PermissionState.DENIED
        self.set_permission_state(identifier, permission, state)

    def set_permission_state(
        self, identifier: str, permission: str, state: PermissionState
    ) -> None:
        plugins = self._data.setdefault("plugins", {})
        entry = plugins.setdefault(identifier, {})
        permissions = entry.setdefault("permissions", {})
        permissions[permission] = state.value
        self._save()

    def all_plugins(self) -> dict[str, PluginConfigEntry]:
        plugins = self._data.setdefault("plugins", {})
        result: dict[str, PluginConfigEntry] = {}
        for identifier, entry in plugins.items():
            result[identifier] = PluginConfigEntry(
                identifier=identifier,
                enabled=bool(entry.get("enabled", True)),
                source=dict(entry.get("source", {})),
                permissions=self._normalize_permissions(entry.get("permissions", {})),
            )
        return result

    def get_permission_state(
        self, identifier: str, permission: str
    ) -> PermissionState:
        entry = self.get_permissions(identifier)
        return entry.get(permission, PermissionState.PROMPT)

    def _normalize_permissions(
        self, values: Dict[str, Any] | None
    ) -> dict[str, PermissionState]:
        result: dict[str, PermissionState] = {}
        if not values:
            return result
        for key, value in values.items():
            result[key] = normalize_permission_state(value)
        return result

    def _serialize_permissions(
        self, values: Dict[str, Any] | None
    ) -> dict[str, str]:
        if not values:
            return {}
        return {
            key: normalize_permission_state(value).value for key, value in values.items()
        }

    @property
    def path(self) -> Path:
        return self._path
