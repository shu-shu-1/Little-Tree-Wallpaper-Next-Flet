"""Runtime metadata structures for plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .base import PluginDependencySpec, PluginKind, PluginManifest
from .permissions import PermissionState


class PluginStatus(str, Enum):
    """High-level runtime state of a plugin."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    FAILED = "failed"
    PERMISSION_BLOCKED = "permission_blocked"
    NOT_LOADED = "not_loaded"
    LOADED = "loaded"
    MISSING_DEPENDENCY = "missing_dependency"


@dataclass(slots=True)
class PluginRuntimeInfo:
    """Aggregated information about a plugin's runtime state."""

    identifier: str
    manifest: PluginManifest | None
    enabled: bool
    status: PluginStatus
    error: str | None = None
    source_path: Path | None = None
    builtin: bool = False
    permissions_required: tuple[str, ...] = tuple()
    permissions_granted: dict[str, bool] = field(default_factory=dict)
    permission_states: dict[str, PermissionState] = field(default_factory=dict)
    permissions_pending: tuple[str, ...] = tuple()
    module_name: str | None = None
    plugin_type: PluginKind = PluginKind.FEATURE
    dependencies: tuple[PluginDependencySpec, ...] = tuple()
    dependency_issues: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        if self.manifest:
            return self.manifest.name
        return self.identifier

    @property
    def version(self) -> str:
        if self.manifest:
            return self.manifest.version
        return "?"

    @property
    def description(self) -> str:
        if self.manifest:
            return self.manifest.description
        return ""

    @property
    def author(self) -> str:
        if self.manifest:
            return self.manifest.author
        return ""

    @property
    def homepage(self) -> str | None:
        if self.manifest:
            return self.manifest.homepage
        return None
