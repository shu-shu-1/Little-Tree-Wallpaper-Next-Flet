"""Plugin abstractions for the Little Tree Wallpaper Next application."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Protocol, Tuple

import flet as ft
from loguru import logger as _loguru_logger

from .permissions import PermissionState
from .operations import PluginOperationResult

if TYPE_CHECKING:
    from loguru._logger import Logger
    from .runtime import PluginRuntimeInfo
    from .events import PluginEventBus, EventDefinition, EventHandler
    from .data import GlobalDataAccess
    from .manager import PluginImportResult
else:  # pragma: no cover - runtime assignment for typing compatibility
    Logger = type(_loguru_logger)
    from .events import PluginEventBus, EventDefinition, EventHandler
    from .data import GlobalDataAccess


class PluginKind(str, Enum):
    FEATURE = "feature"
    LIBRARY = "library"


def _parse_version_parts(version: str | None) -> tuple[int, ...]:
    if not version:
        return tuple()
    parts = re.split(r"[.-]", version)
    result = []
    for part in parts:
        if part.isdigit():
            result.append(int(part))
        else:
            break
    return tuple(result)


def _compare_versions(current: str | None, expected: str | None) -> int:
    current_parts = _parse_version_parts(current)
    expected_parts = _parse_version_parts(expected)
    length = max(len(current_parts), len(expected_parts))
    for idx in range(length):
        c = current_parts[idx] if idx < len(current_parts) else 0
        e = expected_parts[idx] if idx < len(expected_parts) else 0
        if c < e:
            return -1
        if c > e:
            return 1
    return 0


@dataclass(slots=True, frozen=True)
class PluginDependencySpec:
    identifier: str
    comparator: str | None = None
    version: str | None = None

    @classmethod
    def from_string(cls, declaration: str) -> "PluginDependencySpec":
        text = declaration.strip()
        if not text:
            raise ValueError("依赖声明不能为空")
        match = re.match(r"^([a-zA-Z0-9_\-]+)\s*(==|>=|<=|>|<)?\s*([\w.\-]+)?$", text)
        if not match:
            raise ValueError(f"无法解析依赖声明: {declaration}")
        identifier, comparator, version = match.groups()
        return cls(identifier=identifier, comparator=comparator, version=version)

    def describe(self) -> str:
        if not self.comparator or not self.version:
            return self.identifier
        return f"{self.identifier} {self.comparator} {self.version}"

    def is_satisfied_by(self, version: str | None) -> bool:
        if not self.comparator or not self.version:
            return version is not None
        comparison = _compare_versions(version, self.version)
        if self.comparator == "==":
            return comparison == 0
        if self.comparator == ">=":
            return comparison >= 0
        if self.comparator == "<=":
            return comparison <= 0
        if self.comparator == ">":
            return comparison > 0
        if self.comparator == "<":
            return comparison < 0
        return True


@dataclass(slots=True)
class PluginManifest:
    """Static metadata describing a plugin."""

    identifier: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    homepage: str | None = None
    dependencies: Tuple[str | PluginDependencySpec, ...] = tuple()
    permissions: Tuple[str, ...] = tuple()
    kind: PluginKind = PluginKind.FEATURE

    def short_label(self) -> str:
        return f"{self.name} v{self.version}"

    def dependency_specs(self) -> tuple[PluginDependencySpec, ...]:
        specs: list[PluginDependencySpec] = []
        for dependency in self.dependencies:
            if isinstance(dependency, PluginDependencySpec):
                specs.append(dependency)
            else:
                specs.append(PluginDependencySpec.from_string(dependency))
        return tuple(specs)


PathFactory = Callable[[str, Tuple[str, ...], bool], Path]
ActionFactory = Callable[[], ft.Control]


class PluginService(Protocol):
    """Operations exposed to privileged plugins for lifecycle management."""

    def list_plugins(self) -> list["PluginRuntimeInfo"]:
        ...

    def set_enabled(self, identifier: str, enabled: bool) -> None:
        ...

    def delete_plugin(self, identifier: str) -> None:
        ...

    def import_plugin(self, source_path: Path) -> "PluginImportResult":
        ...

    def update_permission(
        self, identifier: str, permission: str, allowed: bool | PermissionState | None
    ) -> None:
        ...

    def reload(self) -> None:
        ...


@dataclass(slots=True)
class PluginSettingsPage:
    """Definition for a plugin-specific settings page."""

    plugin_identifier: str
    title: str
    builder: Callable[[], ft.Control]
    icon: str | None = None
    button_label: str = "插件设置"
    description: str | None = None


# Backwards compatibility alias for legacy imports
PluginSettingsTab = PluginSettingsPage


@dataclass(slots=True)
class AppNavigationView:
    """Definition for a navigation destination in the sidebar."""

    id: str
    label: str
    icon: str
    selected_icon: str
    content: ft.Control


@dataclass(slots=True)
class AppRouteView:
    """Definition for a secondary route (page.views stack)."""

    route: str
    builder: Callable[[], ft.View]


StartupHook = Callable[[], None]


@dataclass(slots=True)
class PluginContext:
    """Context object exposed to plugins during activation."""

    page: ft.Page
    register_navigation: Callable[[AppNavigationView], None]
    register_route: Callable[[AppRouteView], None]
    register_startup_hook: Callable[[StartupHook], None]
    set_initial_route: Callable[[str], None]
    manifest: PluginManifest
    data_path_factory: PathFactory
    config_path_factory: PathFactory
    cache_path_factory: PathFactory
    logger: Logger
    bing_action_factories: list[ActionFactory]
    spotlight_action_factories: list[ActionFactory]
    settings_pages: list[PluginSettingsPage]
    permissions: dict[str, PermissionState] = field(default_factory=dict)
    plugin_service: PluginService | None = None
    event_bus: PluginEventBus | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    global_data: GlobalDataAccess | None = None
    _open_route_handler: Callable[[str], PluginOperationResult] | None = None
    _switch_home_handler: Callable[[str], PluginOperationResult] | None = None
    _open_settings_handler: Callable[[str], PluginOperationResult] | None = None
    _set_wallpaper_handler: Callable[[str], PluginOperationResult] | None = None
    _ipc_broadcast_handler: Callable[[str, dict], PluginOperationResult] | None = None
    _ipc_subscribe_handler: Callable[[str], PluginOperationResult] | None = None
    _ipc_unsubscribe_handler: Callable[[str], PluginOperationResult] | None = None

    def add_navigation_view(self, view: AppNavigationView) -> None:
        """Register a navigation destination for the application sidebar."""

        self.register_navigation(view)

    def add_route_view(self, view: AppRouteView) -> None:
        """Register an auxiliary route handled through ``page.views``."""

        self.register_route(view)

    # ------------------------------------------------------------------
    # privilege-requiring helpers
    # ------------------------------------------------------------------
    def open_route(self, route: str) -> PluginOperationResult:
        if not self._open_route_handler:
            return PluginOperationResult.failed("operation_unavailable", "应用未提供路由跳转接口。")
        return self._open_route_handler(route)

    def switch_home(self, navigation_id: str) -> PluginOperationResult:
        if not self._switch_home_handler:
            return PluginOperationResult.failed("operation_unavailable", "应用未开放首页导航切换。")
        return self._switch_home_handler(navigation_id)

    def open_settings_tab(self, tab_id: str) -> PluginOperationResult:
        if not self._open_settings_handler:
            return PluginOperationResult.failed("operation_unavailable", "应用未开放设置页切换。")
        return self._open_settings_handler(tab_id)

    def set_wallpaper(self, path: str) -> PluginOperationResult:
        if not self._set_wallpaper_handler:
            return PluginOperationResult.failed("operation_unavailable", "应用未提供壁纸操作接口。")
        return self._set_wallpaper_handler(path)

    def ipc_broadcast(self, channel: str, payload: dict) -> PluginOperationResult:
        if not self._ipc_broadcast_handler:
            return PluginOperationResult.failed("operation_unavailable", "应用未启用跨进程广播。")
        return self._ipc_broadcast_handler(channel, payload)

    def ipc_subscribe(self, channel: str) -> PluginOperationResult:
        if not self._ipc_subscribe_handler:
            return PluginOperationResult.failed("operation_unavailable", "应用未启用跨进程广播。")
        return self._ipc_subscribe_handler(channel)

    def ipc_unsubscribe(self, subscription: Any) -> PluginOperationResult:
        if not self._ipc_unsubscribe_handler:
            return PluginOperationResult.failed("operation_unavailable", "应用未启用跨进程广播。")
        subscription_id = getattr(subscription, "subscription_id", subscription)
        if not isinstance(subscription_id, str):
            return PluginOperationResult.failed("invalid_argument", "订阅 ID 无效。")
        return self._ipc_unsubscribe_handler(subscription_id)

    def add_startup_hook(self, hook: StartupHook) -> None:
        """Register a callable to execute once the application is ready."""

        self.register_startup_hook(hook)

    def add_bing_action(self, factory: ActionFactory) -> None:
        """Register an action control to display under the Bing wallpaper tab."""

        self.bing_action_factories.append(factory)

    def add_spotlight_action(self, factory: ActionFactory) -> None:
        """Register an action control to display under the Spotlight wallpaper tab."""

        self.spotlight_action_factories.append(factory)

    def register_settings_page(
        self,
        label: str,
        builder: Callable[[], ft.Control],
        *,
        icon: str | None = None,
        button_label: str | None = None,
        description: str | None = None,
    ) -> None:
        """Register a dedicated settings page accessible from the plugin management panel."""

        existing = [page for page in self.settings_pages if page.plugin_identifier != self.manifest.identifier]
        existing.append(
            PluginSettingsPage(
                plugin_identifier=self.manifest.identifier,
                title=label,
                builder=builder,
                icon=icon,
                button_label=button_label or "插件设置",
                description=description,
            )
        )
        self.settings_pages[:] = existing

    def add_settings_tab(
        self,
        label: str,
        builder: Callable[[], ft.Control],
        *,
        icon: str | None = None,
    ) -> None:
        """Backward-compatible alias for :meth:`register_settings_page`."""

        self.register_settings_page(label, builder, icon=icon)

    @property
    def settings_tabs(self) -> list[PluginSettingsPage]:
        """Backward-compatible accessor returning registered settings pages."""

        return self.settings_pages

    @settings_tabs.setter
    def settings_tabs(self, value: list[PluginSettingsPage]) -> None:
        self.settings_pages = value

    def has_permission(self, permission: str) -> bool:
        return self.permissions.get(permission, PermissionState.PROMPT) is PermissionState.GRANTED

    def plugin_data_path(self, *parts: str, create: bool = False) -> Path:
        path = self.data_path_factory(self.manifest.identifier, parts, create)
        return path

    def plugin_config_path(self, *parts: str, create: bool = False) -> Path:
        path = self.config_path_factory(self.manifest.identifier, parts, create)
        return path

    def plugin_cache_path(self, *parts: str, create: bool = False) -> Path:
        path = self.cache_path_factory(self.manifest.identifier, parts, create)
        return path

    def plugin_data_dir(self, create: bool = True) -> Path:
        return self.plugin_data_path(create=create)

    def plugin_config_dir(self, create: bool = True) -> Path:
        return self.plugin_config_path(create=create)

    def plugin_cache_dir(self, create: bool = True) -> Path:
        return self.plugin_cache_path(create=create)

    def add_metadata(self, key: str, value: object) -> None:
        self.metadata[key] = value

    # ------------------------------------------------------------------
    # event helpers
    # ------------------------------------------------------------------
    def register_event(
        self,
        event_type: str,
        *,
        description: str = "",
        permission: str | None = None,
    ) -> None:
        if not self.event_bus:
            raise RuntimeError("事件总线不可用")
        self.event_bus.register_event(
            owner=self.manifest.identifier,
            event_type=event_type,
            description=description,
            permission=permission,
        )

    def subscribe_event(
        self,
        event_type: str,
        handler: "EventHandler",
        *,
        replay_last: bool = True,
    ) -> Callable[[], None]:
        if not self.event_bus:
            raise RuntimeError("事件总线不可用")
        return self.event_bus.subscribe(
            plugin_id=self.manifest.identifier,
            event_type=event_type,
            handler=handler,
            replay_last=replay_last,
        )

    def emit_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        if not self.event_bus:
            raise RuntimeError("事件总线不可用")
        self.event_bus.emit(
            event_type=event_type,
            payload=payload or {},
            source=self.manifest.identifier,
        )

    def list_event_definitions(self) -> list["EventDefinition"]:
        if not self.event_bus:
            return []
        return self.event_bus.list_event_definitions()

    # ------------------------------------------------------------------
    # global data helpers
    # ------------------------------------------------------------------
    def register_data_namespace(
        self,
        identifier: str,
        *,
        description: str = "",
        permission: str | None = None,
        overwrite: bool = False,
    ) -> None:
        if not self.global_data:
            raise RuntimeError("全局数据系统不可用")
        self.global_data.register_namespace(
            identifier,
            description=description,
            permission=permission,
            overwrite=overwrite,
        )

    def publish_data(self, namespace_id: str, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.global_data:
            raise RuntimeError("全局数据系统不可用")
        return self.global_data.publish(namespace_id, entry_id, payload)

    def latest_data(self, namespace_id: str) -> dict[str, Any] | None:
        if not self.global_data:
            raise RuntimeError("全局数据系统不可用")
        return self.global_data.latest(namespace_id)

    def get_data(self, namespace_id: str, entry_id: str) -> dict[str, Any] | None:
        if not self.global_data:
            raise RuntimeError("全局数据系统不可用")
        return self.global_data.get(namespace_id, entry_id)

    def list_data(self, namespace_id: str) -> list[dict[str, Any]]:
        if not self.global_data:
            raise RuntimeError("全局数据系统不可用")
        return self.global_data.list(namespace_id)


class Plugin(Protocol):
    """Plugin interface."""

    manifest: PluginManifest

    def activate(self, context: PluginContext) -> None:
        """Register UI and behaviors with the host application."""
