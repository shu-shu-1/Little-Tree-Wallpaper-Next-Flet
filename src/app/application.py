"""Flet application bootstrap code."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import flet as ft
from loguru import logger

import ltwapi

from .constants import BUILD_VERSION, MODE
from .paths import (
    CACHE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    ICO_PATH,
    HITO_FONT_PATH,
    PLUGINS_DIR,
    UI_FONT_PATH,
)
from .plugins import (
    AppNavigationView,
    AppRouteView,
    Plugin,
    PluginContext,
    PluginManifest,
    PluginManager,
    PluginSettingsPage,
    KNOWN_PERMISSIONS,
    PluginEventBus,
    CORE_EVENT_DEFINITIONS,
    GlobalDataStore,
    GlobalDataAccess,
    PluginImportResult,
    PermissionState,
    ensure_permission_states,
    normalize_permission_state,
    PluginOperationResult,
)
from .plugins.config import PluginConfigStore
from .core.pages import Pages
from .ipc import IPCService
from .ui_utils import build_watermark


class ApplicationPluginService:
    """High-level plugin lifecycle helper exposed to privileged UI."""

    def __init__(self, app: "Application") -> None:
        self._app = app

    def list_plugins(self):
        return self._app._plugin_manager.runtime_info

    def list_events(self):
        return self._app._event_bus.list_event_definitions()

    def set_enabled(self, identifier: str, enabled: bool) -> None:
        self._app._plugin_manager.set_enabled(identifier, enabled)
        runtime = self._app._plugin_manager.get_runtime(identifier)
        if runtime is not None:
            runtime.enabled = enabled
        self._app.mark_reload_required()

    def delete_plugin(self, identifier: str) -> None:
        self._app._plugin_manager.delete_plugin(identifier)
        self._app.mark_reload_required()

    def import_plugin(self, source_path: Path) -> PluginImportResult:
        return self._app._plugin_manager.import_plugin(source_path)

    def update_permission(
        self, identifier: str, permission: str, allowed: bool | PermissionState | None
    ) -> None:
        state = normalize_permission_state(allowed)
        self._app._set_permission_state(identifier, permission, state)
        runtime = self._app._plugin_manager.get_runtime(identifier)
        if runtime is None or runtime.enabled:
            self._app.mark_reload_required()

    def reload(self) -> None:
        self._app.reload()

    def is_reload_required(self) -> bool:
        # Consider pending changes in the plugin manager as well as the app-level flag.
        try:
            manager_pending = bool(self._app._plugin_manager.has_pending_changes())
        except Exception:
            manager_pending = False
        return self._app.is_reload_required() or manager_pending


@dataclass(slots=True)
class _PermissionPromptRequest:
    plugin_id: str
    permission: str
    on_granted: Callable[[], PluginOperationResult]
    on_denied: Optional[Callable[[], PluginOperationResult]] = None
    result: PluginOperationResult | None = None
    completion: Event = field(default_factory=Event, repr=False)


class Application:
    """Main entry point used by flet.app to bootstrap the UI."""

    def __init__(self) -> None:
        self._plugin_config = PluginConfigStore(CONFIG_DIR / "plugins.json")
        self._plugin_manager = PluginManager(
            search_paths=[PLUGINS_DIR],
            config_store=self._plugin_config,
            builtin_identifiers={"core"},
        )
        self._plugin_service = ApplicationPluginService(self)
        self._event_bus = PluginEventBus(self._resolve_permission)
        self._data_store = GlobalDataStore(self._resolve_permission)
        self._register_core_events()
        self._page: ft.Page | None = None
        self._plugin_contexts: Dict[str, PluginContext] = {}
        self._permission_prompt_queue: List[_PermissionPromptRequest] = []
        self._permission_prompt_active: bool = False
        self._permission_dialog: ft.AlertDialog | None = None
        self._route_registry: Dict[str, AppRouteView] = {}
        self._navigation_views: List[AppNavigationView] = []
        self._navigation_index: Dict[str, int] = {}
        self._navigation_container: ft.Container | None = None
        self._navigation_rail: ft.NavigationRail | None = None
        self._core_pages: Pages | None = None
        self._ipc_service = IPCService()
        self._ipc_plugin_subscriptions: Dict[str, Set[str]] = {}
        self._reload_required = False

    def __call__(self, page: ft.Page) -> None:
        self._page = page
        self._build_app(page)

    # ------------------------------------------------------------------
    # lifecycle helpers
    # ------------------------------------------------------------------
    def _build_app(self, page: ft.Page) -> None:
        logger.info(f"Little Tree Wallpaper Next {BUILD_VERSION} 初始化")

        self._reload_required = False

        page.clean()
        self._close_permission_dialog()
        self._reset_permission_prompts("应用重新加载，操作已取消。")
        self._cleanup_ipc_subscriptions()
        self._route_registry = {}
        self._navigation_views = []
        self._navigation_index = {}
        self._navigation_container = None
        self._navigation_rail = None
        self._core_pages = None

        route_views: Dict[str, AppRouteView] = {}
        startup_hooks: List[Callable[[], None]] = []
        initial_route: str = "/"
        self._plugin_contexts = {}

        bing_action_factories: List[Callable[[], ft.Control]] = []
        spotlight_action_factories: List[Callable[[], ft.Control]] = []
        settings_pages: List[PluginSettingsPage] = []

        self._event_bus.clear_all()
        self._register_core_events()

        navigation_registry: Dict[str, List[AppNavigationView]] = {}
        navigation_plugin_order: List[str] = []

        def _register_navigation(plugin_id: str, view: AppNavigationView) -> None:
            if plugin_id not in navigation_registry:
                navigation_registry[plugin_id] = []
                navigation_plugin_order.append(plugin_id)
            navigation_registry[plugin_id].append(view)

        def register_route(view: AppRouteView) -> None:
            route_views[view.route] = view

        def register_startup_hook(hook: Callable[[], None]) -> None:
            startup_hooks.append(hook)

        def make_set_initial_route(plugin_id: str) -> Callable[[str], None]:
            def setter(route: str) -> None:
                nonlocal initial_route
                if self._plugin_manager.is_builtin(plugin_id):
                    initial_route = route
                else:
                    logger.warning(
                        "插件 {plugin_id} 尝试设置初始路由 {route} 已被忽略",
                        plugin_id=plugin_id,
                        route=route,
                    )

            return setter

        self._configure_page(page)

        for root in (DATA_DIR, CONFIG_DIR, CACHE_DIR):
            (root / "plugins").mkdir(parents=True, exist_ok=True)

        def make_path_factory(root: Path) -> Callable[[str, Tuple[str, ...], bool], Path]:
            def factory(plugin_id: str, segments: Tuple[str, ...], create: bool = False) -> Path:
                base = root / "plugins" / plugin_id
                target = base if not segments else base.joinpath(*segments)
                if create:
                    if segments:
                        target.parent.mkdir(parents=True, exist_ok=True)
                    else:
                        target.mkdir(parents=True, exist_ok=True)
                return target

            return factory

        data_path_factory = make_path_factory(DATA_DIR)
        config_path_factory = make_path_factory(CONFIG_DIR)
        cache_path_factory = make_path_factory(CACHE_DIR)

        self._plugin_manager.reset()
        self._plugin_manager.discover()
        if not self._plugin_manager.loaded_plugins:
            logger.error("未发现任何插件，应用程序无法启动")
            page.add(ft.Text("未发现可用插件"))
            return

        base_metadata = {"app_version": BUILD_VERSION}

        def build_context(plugin: Plugin, manifest: PluginManifest) -> PluginContext:
            plugin_logger = logger.bind(plugin=manifest.identifier)
            metadata = base_metadata.copy()
            metadata["plugin_service"] = self._plugin_service
            metadata["plugin_permissions"] = KNOWN_PERMISSIONS
            metadata["plugin_runtime"] = self._plugin_manager.runtime_info
            metadata["plugin_events"] = self._event_bus.list_event_definitions()
            metadata["global_data"] = self._data_store.describe_namespaces()
            permissions_map = ensure_permission_states(
                manifest.permissions,
                self._plugin_config.get_permissions(manifest.identifier),
            )
            def register_navigation(view: AppNavigationView) -> None:
                _register_navigation(manifest.identifier, view)
            global_data_access = GlobalDataAccess(manifest.identifier, self._data_store)
            context = PluginContext(
                page=page,
                register_navigation=register_navigation,
                register_route=register_route,
                register_startup_hook=register_startup_hook,
                set_initial_route=make_set_initial_route(manifest.identifier),
                manifest=manifest,
                data_path_factory=data_path_factory,
                config_path_factory=config_path_factory,
                cache_path_factory=cache_path_factory,
                logger=plugin_logger,
                bing_action_factories=bing_action_factories,
                spotlight_action_factories=spotlight_action_factories,
                settings_pages=settings_pages,
                permissions=permissions_map,
                plugin_service=self._plugin_service,
                event_bus=self._event_bus,
                metadata=metadata,
                global_data=global_data_access,
            )
            context._open_route_handler = (
                lambda route, pid=manifest.identifier: self._open_route(pid, route)
            )
            context._switch_home_handler = (
                lambda navigation_id, pid=manifest.identifier: self._switch_home(pid, navigation_id)
            )
            context._open_settings_handler = (
                lambda tab_id, pid=manifest.identifier: self._open_settings_tab(pid, tab_id)
            )
            context._set_wallpaper_handler = (
                lambda path, pid=manifest.identifier: self._set_wallpaper(pid, path)
            )
            context._ipc_broadcast_handler = (
                lambda channel, payload, pid=manifest.identifier: self._ipc_broadcast(pid, channel, payload)
            )
            context._ipc_subscribe_handler = (
                lambda channel, pid=manifest.identifier: self._ipc_subscribe(pid, channel)
            )
            context._ipc_unsubscribe_handler = (
                lambda subscription_id, pid=manifest.identifier: self._ipc_unsubscribe(pid, subscription_id)
            )
            self._plugin_contexts[manifest.identifier] = context
            return context

        self._plugin_manager.activate_all(build_context)
        self._extract_core_pages()

        navigation_views: List[AppNavigationView] = []
        for plugin_id in navigation_plugin_order:
            if self._plugin_manager.is_builtin(plugin_id):
                navigation_views.extend(navigation_registry.get(plugin_id, []))
        for plugin_id in navigation_plugin_order:
            if not self._plugin_manager.is_builtin(plugin_id):
                navigation_views.extend(navigation_registry.get(plugin_id, []))

        if not navigation_views:
            logger.error("没有插件注册导航视图，应用程序无法启动")
            page.add(ft.Text("没有可用的视图"))
            return

        self._navigation_views = navigation_views
        self._navigation_index = {view.id: index for index, view in enumerate(navigation_views)}

        nav_destinations = [
            ft.NavigationRailDestination(
                icon=view.icon,
                selected_icon=view.selected_icon,
                label=view.label,
            )
            for view in navigation_views
        ]

        content_container = ft.Container(expand=True, content=navigation_views[0].content)
        self._navigation_container = content_container

        def on_nav_change(e: ft.ControlEvent) -> None:
            selected_index = e.control.selected_index
            content_container.content = navigation_views[selected_index].content
            page.update()

        navigation_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=80,
            destinations=nav_destinations,
            on_change=on_nav_change,
        )
        self._navigation_rail = navigation_rail

        main_row = ft.Row(
            [
                navigation_rail,
                ft.VerticalDivider(width=1),
                content_container,
            ],
            expand=True,
        )

        stack_controls = [main_row]
        watermark = build_watermark()
        if isinstance(watermark, ft.Container) and watermark.content is not None:
            stack_controls.append(watermark)

        appbar_actions: list[ft.Control] = [ft.TextButton("帮助", icon=ft.Icons.HELP)]

        def open_settings(_: ft.ControlEvent) -> None:
            page.go("/settings")

        appbar_actions.append(
            ft.TextButton(
                "设置",
                icon=ft.Icons.SETTINGS,
                on_click=open_settings,
            )
        )

        home_view = ft.View(
            "/",
            [ft.Stack(controls=stack_controls, expand=True)],
            appbar=ft.AppBar(
                leading=ft.Image(str(ICO_PATH), width=24, height=24, fit=ft.ImageFit.CONTAIN),
                title=ft.Text("小树壁纸 Next - Flet"),
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                actions=appbar_actions,
            ),
        )

        self._route_registry = dict(route_views)

        def route_change(_: ft.RouteChangeEvent) -> None:
            page.views.clear()
            if page.route in route_views:
                page.views.append(route_views[page.route].builder())
            else:
                page.views.append(home_view)
            page.update()

        page.on_route_change = route_change
        page.go(initial_route if MODE == "TEST" and initial_route == "/" else initial_route)

        for hook in startup_hooks:
            try:
                hook()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"插件启动钩子执行失败: {exc}")

    def reload(self) -> None:
        # Proactively hide any open reload banners before rebuilding,
        # in case reload is triggered outside of Pages' handlers.
        try:
            if self._core_pages is not None:
                # _hide_reload_banner is defensive and no-op if nothing is open
                self._core_pages._hide_reload_banner()  # type: ignore[attr-defined]
        except Exception:
            pass
        if self._page is None:
            return
        # Clear the flag BEFORE rebuilding so new UI doesn’t re-open the banner
        # when it checks is_reload_required during construction.
        self.clear_reload_required()
        self._build_app(self._page)

    def mark_reload_required(self) -> None:
        self._reload_required = True

    def clear_reload_required(self) -> None:
        self._reload_required = False

    def is_reload_required(self) -> bool:
        return self._reload_required

    def _configure_page(self, page: ft.Page) -> None:
        page.title = f"小树壁纸 Next (Flet) | {BUILD_VERSION}"
        if UI_FONT_PATH.exists() and HITO_FONT_PATH.exists():
            page.fonts = {"UIFont": str(UI_FONT_PATH), "HITOKOTOFont": str(HITO_FONT_PATH)}
            page.theme = ft.Theme(font_family="UIFont")

    def _set_permission_state(
        self, plugin_id: str, permission: str, state: PermissionState
    ) -> None:
        self._plugin_manager.update_permission(plugin_id, permission, state)
        runtime = self._plugin_manager.get_runtime(plugin_id)
        if runtime:
            runtime.permission_states[permission] = state
            runtime.permissions_granted[permission] = state is PermissionState.GRANTED
        context = self._plugin_contexts.get(plugin_id)
        if context:
            context.permissions[permission] = state

    def _notify_permission_denied(self, plugin_id: str, permission: str) -> None:
        if self._page is None:
            return
        permission_info = KNOWN_PERMISSIONS.get(permission)
        label = permission_info.name if permission_info else permission
        runtime = self._plugin_manager.get_runtime(plugin_id)
        plugin_label = runtime.name if runtime else plugin_id
        snackbar = ft.SnackBar(
            content=ft.Text(f"插件 {plugin_label} 缺少 {label} 权限，操作已阻止。"),
            bgcolor=ft.Colors.ERROR,
        )
        self._page.open(snackbar)

    def _ensure_permission(
        self,
        plugin_id: str,
        permission: str,
        on_granted: Callable[[], PluginOperationResult],
        on_denied: Optional[Callable[[], PluginOperationResult]] = None,
    ) -> PluginOperationResult:
        state = self._plugin_config.get_permission_state(plugin_id, permission)
        if state is PermissionState.GRANTED:
            return on_granted()
        if state is PermissionState.DENIED:
            result = on_denied() if on_denied else PluginOperationResult.denied(permission)
            if result.error == "permission_denied":
                self._notify_permission_denied(plugin_id, permission)
            return result

        request = _PermissionPromptRequest(
            plugin_id=plugin_id,
            permission=permission,
            on_granted=on_granted,
            on_denied=on_denied,
        )
        self._permission_prompt_queue.append(request)
        if not self._permission_prompt_active:
            self._dequeue_permission_prompt()
        request.completion.wait()
        return request.result or PluginOperationResult.failed(
            "permission_prompt_cancelled", "权限请求已取消。"
        )

    def _open_route(self, plugin_id: str, route: str) -> PluginOperationResult:
        target_route = route or "/"

        def _granted() -> PluginOperationResult:
            if self._page is None:
                return PluginOperationResult.failed("page_unavailable", "页面尚未初始化。")
            if target_route != "/" and target_route not in self._route_registry:
                return PluginOperationResult.failed("route_not_found", f"未注册路由 {target_route}。")
            self._page.go(target_route)
            return PluginOperationResult.ok(message=f"已跳转到 {target_route}")

        return self._ensure_permission(plugin_id, "app_route", _granted)

    def _switch_home(self, plugin_id: str, navigation_id: str) -> PluginOperationResult:
        nav_id = navigation_id.strip()

        def _granted() -> PluginOperationResult:
            if not nav_id:
                return PluginOperationResult.failed("invalid_argument", "导航标识不能为空。")
            if self._navigation_rail is None or self._navigation_container is None:
                return PluginOperationResult.failed("navigation_unavailable", "导航尚未初始化。")
            index = self._navigation_index.get(nav_id)
            if index is None:
                return PluginOperationResult.failed("navigation_not_found", f"未找到导航 {nav_id}。")
            self._navigation_rail.selected_index = index
            self._navigation_container.content = self._navigation_views[index].content
            if self._page:
                self._page.update()
            return PluginOperationResult.ok(message=f"已切换到导航 {self._navigation_views[index].label}")

        return self._ensure_permission(plugin_id, "app_home", _granted)

    def _open_settings_tab(self, plugin_id: str, tab_id: str | int) -> PluginOperationResult:
        # Accept numeric index or string identifier
        desired_index: int | None = None
        desired_tab: str | None = None
        if isinstance(tab_id, int):
            desired_index = tab_id
        elif isinstance(tab_id, str):
            s = tab_id.strip()
            if s.isdigit():
                desired_index = int(s)
            else:
                desired_tab = s.lower()

        def _granted() -> PluginOperationResult:
            pages = self._core_pages or self._extract_core_pages()
            if pages is None:
                return PluginOperationResult.failed("settings_unavailable", "设置页面尚未加载。")
            if desired_index is not None:
                # If tabs are not initialized yet, Pages.select_settings_tab handles pending state
                try:
                    pages.select_settings_tab_index(desired_index)
                except Exception:
                    return PluginOperationResult.failed("invalid_argument", f"未知的设置索引 {tab_id}。")
            else:
                if not desired_tab or not pages.select_settings_tab(desired_tab):
                    return PluginOperationResult.failed("invalid_argument", f"未知的设置标签 {tab_id}。")
            if self._page:
                self._page.go("/settings")
            return PluginOperationResult.ok(message=f"已切换到设置标签 {tab_id}")

        return self._ensure_permission(plugin_id, "app_settings", _granted)

    def _set_wallpaper(self, plugin_id: str, path: str) -> PluginOperationResult:
        target_path = path.strip()

        def _granted() -> PluginOperationResult:
            if not target_path:
                return PluginOperationResult.failed("invalid_argument", "壁纸路径不能为空。")
            try:
                ltwapi.set_wallpaper(target_path)
            except FileNotFoundError:
                return PluginOperationResult.failed("file_not_found", f"找不到壁纸文件 {target_path}。")
            except Exception as exc:  # pragma: no cover - external API safety
                logger.error("设置壁纸失败: {error}", error=str(exc))
                return PluginOperationResult.failed("operation_failed", str(exc))
            return PluginOperationResult.ok(message="壁纸已更新。")

        return self._ensure_permission(plugin_id, "wallpaper_control", _granted)

    def _ipc_broadcast(
        self, plugin_id: str, channel: str, payload: Dict[str, Any]
    ) -> PluginOperationResult:
        channel_name = channel.strip()

        def _granted() -> PluginOperationResult:
            if not channel_name:
                return PluginOperationResult.failed("invalid_argument", "频道标识不能为空。")
            if payload is None:
                coerced = {}
            elif not isinstance(payload, dict):
                try:
                    coerced = dict(payload)
                except Exception:
                    coerced = {"value": payload}
            else:
                coerced = payload
            self._ipc_service.broadcast(channel_name, coerced, origin=plugin_id)
            return PluginOperationResult.ok(message="广播已发送。")

        return self._ensure_permission(plugin_id, "ipc_broadcast", _granted)

    def _ipc_subscribe(self, plugin_id: str, channel: str) -> PluginOperationResult:
        channel_name = channel.strip()

        def _granted() -> PluginOperationResult:
            if not channel_name:
                return PluginOperationResult.failed("invalid_argument", "频道标识不能为空。")
            subscription = self._ipc_service.subscribe(channel_name)
            self._ipc_plugin_subscriptions.setdefault(plugin_id, set()).add(
                subscription.subscription_id
            )
            return PluginOperationResult.ok(
                data=subscription,
                message="订阅成功。",
            )

        return self._ensure_permission(plugin_id, "ipc_broadcast", _granted)

    def _ipc_unsubscribe(self, plugin_id: str, subscription_id: str) -> PluginOperationResult:
        subscription_key = subscription_id.strip()

        def _granted() -> PluginOperationResult:
            records = self._ipc_plugin_subscriptions.get(plugin_id)
            if not records or subscription_key not in records:
                return PluginOperationResult.failed("subscription_not_found", "未找到对应的订阅。")
            self._ipc_service.unsubscribe(subscription_key)
            records.discard(subscription_key)
            if not records:
                self._ipc_plugin_subscriptions.pop(plugin_id, None)
            return PluginOperationResult.ok(message="已取消订阅。")

        return self._ensure_permission(plugin_id, "ipc_broadcast", _granted)

    def _extract_core_pages(self) -> Pages | None:
        core_context = self._plugin_contexts.get("core")
        if not core_context:
            return None
        pages = core_context.metadata.get("core_pages")
        if isinstance(pages, Pages):
            self._core_pages = pages
            try:
                pages.set_route_registrar(core_context.register_route)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "注册核心设置路由回调失败: {error}",
                    error=str(exc),
                )
            for context in self._plugin_contexts.values():
                context.metadata["core_pages"] = pages
            return pages
        return None

    def _dequeue_permission_prompt(self) -> None:
        if not self._permission_prompt_queue:
            self._permission_prompt_active = False
            return

        if self._page is None:
            self._reset_permission_prompts("页面尚未初始化，权限请求已取消。")
            return

        request = self._permission_prompt_queue.pop(0)
        plugin_id = request.plugin_id
        permission = request.permission
        runtime = self._plugin_manager.get_runtime(plugin_id)
        permission_info = KNOWN_PERMISSIONS.get(permission)
        plugin_name = runtime.name if runtime else plugin_id
        permission_name = permission_info.name if permission_info else permission
        permission_desc = permission_info.description if permission_info else ""

        content_controls: list[ft.Control] = [
            ft.Text(
                f"插件 {plugin_name} 请求 {permission_name} 权限",
                size=16,
                weight=ft.FontWeight.BOLD,
            ),
        ]
        if permission_desc:
            content_controls.append(ft.Text(permission_desc, size=13))

        def _finish(decision: PermissionState) -> None:
            self._close_permission_dialog()
            if decision is not PermissionState.PROMPT:
                self._set_permission_state(plugin_id, permission, decision)
            if decision is PermissionState.GRANTED:
                result = request.on_granted()
            else:
                if request.on_denied:
                    result = request.on_denied()
                else:
                    result = PluginOperationResult.denied(permission)
                if result.error == "permission_denied":
                    self._notify_permission_denied(plugin_id, permission)
            request.result = result
            request.completion.set()
            self._permission_prompt_active = False
            self._dequeue_permission_prompt()

        def _allow(_: ft.ControlEvent) -> None:
            _finish(PermissionState.GRANTED)

        def _deny(_: ft.ControlEvent) -> None:
            _finish(PermissionState.DENIED)

        def _later(_: ft.ControlEvent) -> None:
            _finish(PermissionState.PROMPT)

        self._permission_prompt_active = True
        self._permission_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE),ft.Text("权限请求")]),
            content=ft.Container(
                width=420,
                height=200,
                content=ft.Column(
                    content_controls,
                    spacing=12,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
            actions=[
                ft.TextButton("稍后决定", on_click=_later),
                ft.TextButton("拒绝", on_click=_deny),
                ft.FilledButton("允许", on_click=_allow),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.dialog = self._permission_dialog
        self._page.open(self._permission_dialog)

    def _close_permission_dialog(self) -> None:
        if self._permission_dialog and self._page is not None:
            self._page.close(self._permission_dialog)
        self._permission_dialog = None

    def _reset_permission_prompts(self, reason: str) -> None:
        self._close_permission_dialog()
        for request in self._permission_prompt_queue:
            if request.result is None:
                request.result = PluginOperationResult.failed(
                    "permission_prompt_cancelled", reason
                )
                request.completion.set()
        self._permission_prompt_queue.clear()
        self._permission_prompt_active = False

    def _cleanup_ipc_subscriptions(self) -> None:
        for subscription_ids in list(self._ipc_plugin_subscriptions.values()):
            for subscription_id in list(subscription_ids):
                try:
                    self._ipc_service.unsubscribe(subscription_id)
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("取消 IPC 订阅失败: {error}", error=str(exc))
        self._ipc_plugin_subscriptions.clear()

    def _resolve_permission(self, plugin_id: str, permission: str) -> bool:
        state = self._plugin_config.get_permission_state(plugin_id, permission)
        return state is PermissionState.GRANTED

    def _register_core_events(self) -> None:
        for definition in CORE_EVENT_DEFINITIONS:
            self._event_bus.register_event(
                owner="core",
                event_type=definition.event_type,
                description=definition.description,
                permission=definition.permission,
                overwrite=True,
            )
