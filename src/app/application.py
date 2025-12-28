# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Little Tree Studio <studio@zsxiaoshu.cn>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                -++-                                                
                                               +%%%%#.                                              
                                              *%#%%%%#:                                             
                                             *%#%%%%%%#:                                            
                                           .*%#%%%%%%%%%:                                           
                                          .#%#%%%%%%%%%%%-                                          
                                         .#%#%%%%%%%%%%%%%-                                         
                                        :#%#%%%%%%%%%%%%%%%=                                        
                                       :#%#%%%%%%%%%%%%%%##*=                                       
                                      :##############%%%#****=                                      
                                     -##############%##*******=                                     
                                    -################**********+                                    
                                   =###############*************+                                   
                                  =##############****************+.                                 
                                 =#############*******************+.                                
                                +############*******************+===.                               
                               +###########*******************+==-===.                              
                              *##########*******************+=--===--=.                             
                            .*#########******************+==--==-------.                            
                           .*#######*******************+==-==-----------.                           
                          .*######******************+==-====-------------:                          
                         :*#*#*******************++==-===-----------------:                         
                        :**********************+=======--------------------:                        
                       :********************++========----------------------:                       
                      :*******************+===========-----------------------:                      
                     -*****************++=============------------------------:                     
                    :***************++===============---------------------------                    
                    .+***********++===================-------------------------:                    
                      .::::::::::::::::::::::.:------:........................                      
                                               ::::::.                                              
                                               ------:                                              
                                               ------.                                              
                                               ------.                                              
                                               ------:                                              
                                               ------:                                              
                                              .------:                                              
                                               :....:                                               

🌳 Little Tree Wallpaper Next Flet
Little Tree Studio
https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet

================================================================================

Module Name: [module_name]

Copyright (C) 2024 Little Tree Studio <studio@zsxiaoshu.cn>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Project Information:
    - Official Website: https://wp.zsxiaoshu.cn/
    - Repository: https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet
    - Issue Tracker: https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet/issues

Module Description:
    Flet application bootstrap code.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any

import flet as ft
from loguru import logger

import ltwapi

from .conflicts import StartupConflict, detect_conflicts
from .constants import (
    BUILD_VERSION,
    ENABLE_FIRST_RUN_GUIDE,
    FIRST_RUN_MARKER_VERSION,
    MODE,
)
from .core.pages import Pages
from .first_run import should_show_first_run
from .ipc import IPCService
from .paths import (
    CACHE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    HITO_FONT_PATH,
    ICO_PATH,
    PLUGINS_DIR,
    UI_FONT_PATH,
)
from .plugins import (
    CORE_EVENT_DEFINITIONS,
    KNOWN_PERMISSIONS,
    AppNavigationView,
    AppRouteView,
    FavoriteService,
    GlobalDataAccess,
    GlobalDataStore,
    PermissionState,
    Plugin,
    PluginContext,
    PluginEventBus,
    PluginImportResult,
    PluginManager,
    PluginManifest,
    PluginOperationResult,
    PluginSettingsPage,
    ensure_permission_states,
    normalize_permission_state,
)
from .plugins.config import PluginConfigStore
from .settings import SettingsStore
from .theme import ThemeManager
from .tray import TrayIcon
from .ui_utils import apply_hide_on_close, build_watermark

app_config = SettingsStore()

_AUTO_GRANTED_PERMISSIONS: set[str] = {
    "theme_read",
    "theme_apply",
}


class ApplicationPluginService:
    """High-level plugin lifecycle helper exposed to privileged UI."""

    def __init__(self, app: Application) -> None:
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

    def delete_plugin(self, identifier: str) -> None:
        self._app._plugin_manager.delete_plugin(identifier)
        self._app.mark_reload_required()

    def import_plugin(self, source_path: Path) -> PluginImportResult:
        return self._app._plugin_manager.import_plugin(source_path)

    def update_permission(
        self, identifier: str, permission: str, allowed: bool | PermissionState | None,
    ) -> None:
        state = normalize_permission_state(allowed)
        self._app._set_permission_state(identifier, permission, state)
        runtime = self._app._plugin_manager.get_runtime(identifier)
        if runtime is None or runtime.enabled:
            self._app.mark_reload_required()

    def reload(self) -> None:
        self._app.reload()

    def is_reload_required(self) -> bool:
        # 同时考虑插件管理器中的待处理更改以及应用级别的标志。
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
    on_denied: Callable[[], PluginOperationResult] | None = None
    result: PluginOperationResult | None = None
    completion: Event = field(default_factory=Event, repr=False)
    message: str | None = None


class Application:
    """Main entry point used by flet.app to bootstrap the UI."""

    def __init__(self, start_hidden: bool = False) -> None:
        self._plugin_config = PluginConfigStore(CONFIG_DIR / "plugins.json")
        # application-level persistent settings
        self._settings_store = SettingsStore(CONFIG_DIR / "config.json")
        self._theme_manager = ThemeManager(self._settings_store)
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
        self._plugin_contexts: dict[str, PluginContext] = {}
        self._permission_prompt_queue: list[_PermissionPromptRequest] = []
        self._permission_prompt_active: bool = False
        self._permission_dialog: ft.AlertDialog | None = None
        self._route_registry: dict[str, AppRouteView] = {}
        self._navigation_views: list[AppNavigationView] = []
        self._navigation_index: dict[str, int] = {}
        self._navigation_container: ft.Container | None = None
        self._navigation_rail: ft.NavigationRail | None = None
        self._core_pages: Pages | None = None
        self._ipc_service = IPCService()
        self._ipc_plugin_subscriptions: dict[str, set[str]] = {}
        self._reload_required = False
        self._start_hidden = start_hidden
        self._first_run_pending = False
        self._startup_conflicts: list[StartupConflict] = []
        self._theme_lock_active: bool = False
        self._theme_lock_reason: str = ""
        self._theme_lock_profile: str | None = None

    def __call__(self, page: ft.Page) -> None:
        self._page = page
        self._build_app(page)
        self._sync_theme(page)
        if self._start_hidden:
            self._apply_startup_window_visibility(page)
        # Initialize system tray (optional)
        try:
            enable_tray = bool(app_config.get("ui.enable_tray", True))
        except Exception:
            enable_tray = True
        if enable_tray:
            try:
                self._tray = TrayIcon(self, icon_path=str(ICO_PATH) if ICO_PATH else None)
                self._tray.start()
            except Exception:
                logger.debug("系统托盘初始化失败或被禁用")

    def _apply_startup_window_visibility(self, page: ft.Page) -> None:
        window = getattr(page, "window", None)
        if window is None:
            return
        try:
            window.visible = False
        except Exception as err:
            logger.error(f"初始隐藏窗口遇到错误: {err}")
            self._start_hidden = False
            return
        try:
            page.update()
            logger.info("应用启动时已隐藏窗口")
        except Exception as err:
            logger.error(f"刷新页面遇到错误: {err}")
        finally:
            self._start_hidden = False

    @staticmethod
    def _is_memorial_day() -> bool:
        today = datetime.date.today()
        return today.month == 12 and today.day == 13

    @staticmethod
    def _normalize_theme_profile(value: Any) -> str:
        if isinstance(value, str):
            token = value.strip()
            if token:
                return token
        return "default"

    # ------------------------------------------------------------------
    # lifecycle helpers
    # ------------------------------------------------------------------
    def _build_app(self, page: ft.Page) -> None:
        logger.info(f"Little Tree Wallpaper Next {BUILD_VERSION} 初始化")

        self._reload_required = False

        self._theme_lock_profile = self._normalize_theme_profile(
            app_config.get("ui.theme_profile", "default"),
        )
        self._theme_lock_active = self._is_memorial_day()
        self._theme_lock_reason = (
            "12月13日为南京大屠杀死难者国家公祭日，已启用黑白主题并暂停主题自定义，以示哀悼。"
            if self._theme_lock_active
            else ""
        )

        if self._theme_lock_active:
            logger.info("国家公祭日主题锁定已开启，将强制使用黑白主题。")
            try:
                app_config.set("ui.theme_profile", "bw")
            except Exception:
                logger.debug("在锁定期间写入黑白主题配置失败，继续使用覆盖模式。")

        if self._theme_lock_active:
            self._theme_manager.apply_profile_override(
                "bw",
                reason=self._theme_lock_reason,
                lock_changes=True,
                reload=False,
            )
        else:
            self._theme_manager.apply_profile_override(None, reload=False)

        self._theme_manager.reload()

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

        route_views: dict[str, AppRouteView] = {}
        startup_hooks: list[Callable[[], None]] = []
        initial_route: str = "/"
        self._plugin_contexts = {}

        bing_action_factories: list[Callable[[], ft.Control]] = []
        spotlight_action_factories: list[Callable[[], ft.Control]] = []
        settings_pages: list[PluginSettingsPage] = []

        self._event_bus.clear_all()
        self._register_core_events()

        navigation_registry: dict[str, list[AppNavigationView]] = {}
        navigation_plugin_order: list[str] = []

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

        def make_path_factory(
            root: Path,
        ) -> Callable[[str, tuple[str, ...], bool], Path]:
            def factory(
                plugin_id: str, segments: tuple[str, ...], create: bool = False,
            ) -> Path:
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

        # 如果该向导被禁用，跳过首次运行的检查。
        self._first_run_pending = (
            ENABLE_FIRST_RUN_GUIDE and should_show_first_run(FIRST_RUN_MARKER_VERSION)
        )
        self._startup_conflicts = detect_conflicts()
        base_metadata = {
            "app_version": BUILD_VERSION,
            "first_run_pending": self._first_run_pending,
            "first_run_required_version": FIRST_RUN_MARKER_VERSION,
        }
        base_metadata["startup_conflicts"] = tuple(self._startup_conflicts)
        base_metadata["theme_lock"] = {
            "active": self._theme_lock_active,
            "reason": self._theme_lock_reason,
            "stored_profile": self._theme_lock_profile or "default",
        }

        def build_context(plugin: Plugin, manifest: PluginManifest) -> PluginContext:
            if manifest is None:
                # Defensive: manifest should never be None for loaded plugins; raise to make the cause explicit
                raise ValueError("构建插件上下文时，清单为None")
            plugin_logger = logger.bind(plugin=manifest.identifier)
            metadata = base_metadata.copy()
            metadata["plugin_service"] = self._plugin_service
            metadata["plugin_permissions"] = KNOWN_PERMISSIONS
            metadata["plugin_runtime"] = self._plugin_manager.runtime_info
            metadata["plugin_events"] = self._event_bus.list_event_definitions()
            metadata["global_data"] = self._data_store.describe_namespaces()
            # surface application settings path and a read-only snapshot to plugins
            try:
                metadata["app_settings"] = self._settings_store.as_dict()
                metadata["app_settings_path"] = str(self._settings_store.path)
                metadata["theme_profiles"] = self._theme_manager.list_profiles()
            except Exception:
                metadata["app_settings"] = {}
                metadata["app_settings_path"] = ""
                metadata["theme_profiles"] = []
            metadata["theme_manager"] = self._theme_manager
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
                    _permission_request_handler=(
                        lambda permission_name,
                        note=None,
                        pid=manifest.identifier: self._prompt_permission_state(
                            pid,
                            permission_name,
                            note,
                        )
                    ),
            )
            context._open_route_handler = (
                lambda route, pid=manifest.identifier: self._open_route(pid, route)
            )
            context._switch_home_handler = (
                lambda navigation_id, pid=manifest.identifier: self._switch_home(
                    pid, navigation_id,
                )
            )
            context._open_settings_handler = (
                lambda tab_id, pid=manifest.identifier: self._open_settings_tab(
                    pid, tab_id,
                )
            )
            context._set_wallpaper_handler = (
                lambda path, pid=manifest.identifier: self._set_wallpaper(pid, path)
            )
            context._ipc_broadcast_handler = (
                lambda channel, payload, pid=manifest.identifier: self._ipc_broadcast(
                    pid, channel, payload,
                )
            )
            context._ipc_subscribe_handler = (
                lambda channel, pid=manifest.identifier: self._ipc_subscribe(
                    pid, channel,
                )
            )
            context._ipc_unsubscribe_handler = (
                lambda subscription_id, pid=manifest.identifier: self._ipc_unsubscribe(
                    pid, subscription_id,
                )
            )
            context._theme_list_handler = (
                lambda pid=manifest.identifier: self._list_themes(pid)
            )
            context._theme_apply_handler = (
                lambda profile, pid=manifest.identifier: self._set_theme_profile(
                    pid, profile,
                )
            )
            if self._plugin_manager.is_builtin(manifest.identifier):
                for perm in _AUTO_GRANTED_PERMISSIONS:
                    context.permissions.setdefault(perm, PermissionState.GRANTED)
            self._plugin_contexts[manifest.identifier] = context
            return context

        self._plugin_manager.activate_all(build_context)
        self._extract_core_pages()

        navigation_views: list[AppNavigationView] = []
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
        self._navigation_index = {
            view.id: index for index, view in enumerate(navigation_views)
        }

        nav_destinations = [
            ft.NavigationRailDestination(
                icon=view.icon,
                selected_icon=view.selected_icon,
                label=view.label,
            )
            for view in navigation_views
        ]

        content_container = ft.Container(
            expand=True, content=navigation_views[0].content,
        )
        self._theme_manager.apply_component_style(
            "navigation_container", content_container,
        )
        self._navigation_container = content_container

        def on_nav_change(e: ft.ControlEvent) -> None:
            selected_index = e.control.selected_index
            selected_view = navigation_views[selected_index]
            if (
                selected_view.id == "favorite"
                and getattr(self, "_core_pages", None) is not None
            ):
                try:
                    self._core_pages.show_favorite_loading()
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("刷新收藏页占位符失败: {error}", error=str(exc))
            content_container.content = selected_view.content
            page.update()

        navigation_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=80,
            destinations=nav_destinations,
            on_change=on_nav_change,
        )
        self._theme_manager.apply_component_style("navigation_rail", navigation_rail)
        self._navigation_rail = navigation_rail

        nav_divider = ft.VerticalDivider(width=1)
        self._theme_manager.apply_component_style("navigation_divider", nav_divider)

        nav_divider_container = ft.Container(
            content=nav_divider,
            width=1,
            expand=True,
            margin=0,
            padding=0,
        )

        nav_panel = ft.Container(
            content=ft.Row(
                [navigation_rail, nav_divider_container],
                spacing=0,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=0,
            margin=0,
        )
        self._theme_manager.apply_component_style("navigation_panel", nav_panel)

        main_row = ft.Row(
            [nav_panel, content_container],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        stack_controls: list[ft.Control] = []
        background_layer = self._theme_manager.build_background_layer()
        overlay_layer = self._theme_manager.build_overlay_layer()
        if background_layer is not None:
            stack_controls.append(background_layer)
        if overlay_layer is not None:
            stack_controls.append(overlay_layer)
        stack_controls.append(main_row)
        watermark = build_watermark()
        if isinstance(watermark, ft.Container) and watermark.content is not None:
            stack_controls.append(watermark)

        def open_help(_: ft.ControlEvent) -> None:
            page.launch_url("https://docs.zsxiaoshu.cn/docs/wallpaper/user/")

        appbar_actions: list[ft.Control] = [
            ft.TextButton(
                "帮助",
                icon=ft.Icons.HELP,
                on_click=open_help,
            )
        ]

        def open_settings(_: ft.ControlEvent) -> None:
            page.go("/settings")

        appbar_actions.append(
            ft.TextButton(
                "设置",
                icon=ft.Icons.SETTINGS,
                on_click=open_settings,
            ),
        )

        appbar = ft.AppBar(
            leading=ft.Image(
                str(ICO_PATH), width=24, height=24, fit=ft.BoxFit.CONTAIN,
            ),
            title=ft.Text("小树壁纸 Next - Flet"),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            actions=appbar_actions,
        )
        self._theme_manager.apply_component_style("app_bar", appbar)

        home_view = ft.View(
            "/",
            [ft.Stack(controls=stack_controls, expand=True)],
            appbar=appbar,
        )
        self._theme_manager.apply_component_style("home_view", home_view)

        self._route_registry = dict(route_views)

        def route_change(_: ft.RouteChangeEvent) -> None:
            page.views.clear()
            if page.route in route_views:
                page.views.append(route_views[page.route].builder())
            else:
                page.views.append(home_view)
            page.update()

        page.on_route_change = route_change
        page.go(
            initial_route if MODE == "TEST" and initial_route == "/" else initial_route,
        )

        for hook in startup_hooks:
            try:
                hook()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"插件启动钩子执行失败: {exc}")

    def _sync_theme(self, page: ft.Page) -> None:
        # 同步深/浅
        ui_theme = str(app_config.get("ui.theme", "system")).lower()
        if ui_theme == "light":
            page.theme_mode = ft.ThemeMode.LIGHT
        elif ui_theme == "dark":
            page.theme_mode = ft.ThemeMode.DARK
        else:
            preferred = self._theme_manager.preferred_theme_mode
            page.theme_mode = preferred or ft.ThemeMode.SYSTEM
        logger.info(f"应用主题已设置为 {page.theme_mode.name}")

    def reload(self) -> None:
        # Proactively hide any open reload banners before rebuilding,
        # in case reload is triggered outside of Pages' handlers.
        # Banner was removed from Pages; nothing to hide here.
        if self._page is None:
            return
        # Clear the flag BEFORE rebuilding so new UI doesn’t re-open the banner
        # when it checks is_reload_required during construction.
        self.clear_reload_required()
        self._build_app(self._page)

    def mark_reload_required(self) -> None:
        self._reload_required = True
        logger.debug("应用程序标记为需要重新加载")

    def clear_reload_required(self) -> None:
        self._reload_required = False
        logger.debug("应用程序标记为不需要重新加载")

    def is_reload_required(self) -> bool:
        logger.debug(
            "应用程序检查是否需要重新加载: {state}", state=self._reload_required,
        )
        return self._reload_required

    def _configure_page(self, page: ft.Page) -> None:
        page.title = f"小树壁纸 Next (Flet) | {BUILD_VERSION}"
        font_family: str | None = None
        if UI_FONT_PATH.exists() and HITO_FONT_PATH.exists():
            page.fonts = {
                "UIFont": str(UI_FONT_PATH),
                "HITOKOTOFont": str(HITO_FONT_PATH),
            }
            font_family = "UIFont"
        self._theme_manager.apply_page_theme(page)
        if font_family:
            page.theme.font_family = font_family
        apply_hide_on_close(page, bool(app_config.get("ui.hide_on_close", False)))

    def _set_permission_state(
        self, plugin_id: str, permission: str, state: PermissionState,
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
        on_denied: Callable[[], PluginOperationResult] | None = None,
        *,
        message: str | None = None,
    ) -> PluginOperationResult:
        if self._plugin_manager.is_builtin(plugin_id) and permission in _AUTO_GRANTED_PERMISSIONS:
            return on_granted()
        state = self._plugin_config.get_permission_state(plugin_id, permission)
        if state is PermissionState.GRANTED:
            return on_granted()
        if state is PermissionState.DENIED:
            result = (
                on_denied() if on_denied else PluginOperationResult.denied(permission)
            )
            if result.error == "permission_denied":
                self._notify_permission_denied(plugin_id, permission)
            return result

        request = _PermissionPromptRequest(
            plugin_id=plugin_id,
            permission=permission,
            on_granted=on_granted,
            on_denied=on_denied,
            message=message,
        )
        self._permission_prompt_queue.append(request)
        if not self._permission_prompt_active:
            self._dequeue_permission_prompt()
        request.completion.wait()
        return request.result or PluginOperationResult.failed(
            "permission_prompt_cancelled", "权限请求已取消。",
        )

    def _prompt_permission_state(
        self,
        plugin_id: str,
        permission: str,
        message: str | None = None,
    ) -> PermissionState:
        state = self._plugin_config.get_permission_state(plugin_id, permission)
        if state in (PermissionState.GRANTED, PermissionState.DENIED):
            return state

        def _noop_granted() -> PluginOperationResult:
            return PluginOperationResult.ok()

        def _noop_denied() -> PluginOperationResult:
            return PluginOperationResult.failed("permission_not_granted")

        result = self._ensure_permission(
            plugin_id,
            permission,
            _noop_granted,
            _noop_denied,
            message=message,
        )
        if result.success:
            return PermissionState.GRANTED
        return self._plugin_config.get_permission_state(plugin_id, permission)

    def _open_route(self, plugin_id: str, route: str) -> PluginOperationResult:
        target_route = route or "/"

        def _granted() -> PluginOperationResult:
            if self._page is None:
                return PluginOperationResult.failed(
                    "page_unavailable", "页面尚未初始化。",
                )
            if target_route != "/" and target_route not in self._route_registry:
                return PluginOperationResult.failed(
                    "route_not_found", f"未注册路由 {target_route}。",
                )
            self._page.go(target_route)
            return PluginOperationResult.ok(message=f"已跳转到 {target_route}")

        return self._ensure_permission(plugin_id, "app_route", _granted)

    def _switch_home(self, plugin_id: str, navigation_id: str) -> PluginOperationResult:
        nav_id = navigation_id.strip()

        def _granted() -> PluginOperationResult:
            if not nav_id:
                return PluginOperationResult.failed(
                    "invalid_argument", "导航标识不能为空。",
                )
            if self._navigation_rail is None or self._navigation_container is None:
                return PluginOperationResult.failed(
                    "navigation_unavailable", "导航尚未初始化。",
                )
            index = self._navigation_index.get(nav_id)
            if index is None:
                return PluginOperationResult.failed(
                    "navigation_not_found", f"未找到导航 {nav_id}。",
                )
            self._navigation_rail.selected_index = index
            self._navigation_container.content = self._navigation_views[index].content
            if self._page:
                self._page.update()
            return PluginOperationResult.ok(
                message=f"已切换到导航 {self._navigation_views[index].label}",
            )

        return self._ensure_permission(plugin_id, "app_home", _granted)

    def _open_settings_tab(
        self, plugin_id: str, tab_id: str | int,
    ) -> PluginOperationResult:
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
                return PluginOperationResult.failed(
                    "settings_unavailable", "设置页面尚未加载。",
                )
            if desired_index is not None:
                # If tabs are not initialized yet, Pages.select_settings_tab handles pending state
                try:
                    pages.select_settings_tab_index(desired_index)
                except Exception:
                    return PluginOperationResult.failed(
                        "invalid_argument", f"未知的设置索引 {tab_id}。",
                    )
            elif not desired_tab or not pages.select_settings_tab(desired_tab):
                return PluginOperationResult.failed(
                    "invalid_argument", f"未知的设置标签 {tab_id}。",
                )
            if self._page:
                self._page.go("/settings")
            return PluginOperationResult.ok(message=f"已切换到设置标签 {tab_id}")

        return self._ensure_permission(plugin_id, "app_settings", _granted)

    def _set_wallpaper(self, plugin_id: str, path: str) -> PluginOperationResult:
        target_path = path.strip()

        def _granted() -> PluginOperationResult:
            if not target_path:
                return PluginOperationResult.failed(
                    "invalid_argument", "壁纸路径不能为空。",
                )
            try:
                ltwapi.set_wallpaper(target_path)
            except FileNotFoundError:
                return PluginOperationResult.failed(
                    "file_not_found", f"找不到壁纸文件 {target_path}。",
                )
            except Exception as exc:  # pragma: no cover - external API safety
                logger.error("设置壁纸失败: {error}", error=str(exc))
                return PluginOperationResult.failed("operation_failed", str(exc))
            return PluginOperationResult.ok(message="壁纸已更新。")

        return self._ensure_permission(plugin_id, "wallpaper_control", _granted)

    def _ipc_broadcast(
        self, plugin_id: str, channel: str, payload: dict[str, Any],
    ) -> PluginOperationResult:
        channel_name = channel.strip()

        def _granted() -> PluginOperationResult:
            if not channel_name:
                return PluginOperationResult.failed(
                    "invalid_argument", "频道标识不能为空。",
                )
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
                return PluginOperationResult.failed(
                    "invalid_argument", "频道标识不能为空。",
                )
            subscription = self._ipc_service.subscribe(channel_name)
            self._ipc_plugin_subscriptions.setdefault(plugin_id, set()).add(
                subscription.subscription_id,
            )
            return PluginOperationResult.ok(
                data=subscription,
                message="订阅成功。",
            )

        return self._ensure_permission(plugin_id, "ipc_broadcast", _granted)

    def _ipc_unsubscribe(
        self, plugin_id: str, subscription_id: str,
    ) -> PluginOperationResult:
        subscription_key = subscription_id.strip()

        def _granted() -> PluginOperationResult:
            records = self._ipc_plugin_subscriptions.get(plugin_id)
            if not records or subscription_key not in records:
                return PluginOperationResult.failed(
                    "subscription_not_found", "未找到对应的订阅。",
                )
            self._ipc_service.unsubscribe(subscription_key)
            records.discard(subscription_key)
            if not records:
                self._ipc_plugin_subscriptions.pop(plugin_id, None)
            return PluginOperationResult.ok(message="已取消订阅。")

        return self._ensure_permission(plugin_id, "ipc_broadcast", _granted)

    def _list_themes(self, plugin_id: str) -> PluginOperationResult:
        def _granted() -> PluginOperationResult:
            try:
                profiles = self._theme_manager.list_profiles()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("获取主题列表失败: {error}", error=str(exc))
                return PluginOperationResult.failed(
                    "theme_list_failed", "无法读取主题列表。",
                )
            return PluginOperationResult.ok(data=profiles, message="主题列表已获取。")

        return self._ensure_permission(plugin_id, "theme_read", _granted)

    def _set_theme_profile(
        self, plugin_id: str, profile: str,
    ) -> PluginOperationResult:
        selection = (profile or "").strip()

        if self._theme_manager.override_locked:
            reason = self._theme_manager.override_reason or "当前已锁定主题切换。"
            return PluginOperationResult.failed("theme_locked", reason)

        def _granted() -> PluginOperationResult:
            if not selection:
                return PluginOperationResult.failed(
                    "invalid_argument", "主题标识不能为空。",
                )
            try:
                result = self._theme_manager.set_profile(selection)
            except FileNotFoundError:
                return PluginOperationResult.failed(
                    "theme_not_found", f"未找到主题 {selection}。",
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("应用主题失败: {error}", error=str(exc))
                return PluginOperationResult.failed(
                    "theme_apply_failed", "无法应用所选主题。",
                )

            message = "主题已应用。"
            if self._page is not None:
                # 重新构建界面以应用新的背景与样式。
                self.reload()
                message = "主题已应用，界面正在重新加载。"
            return PluginOperationResult.ok(data=result, message=message)

        return self._ensure_permission(plugin_id, "theme_apply", _granted)

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
                try:
                    if context.manifest.identifier == "core":
                        for perm in (
                            "favorites_read",
                            "favorites_write",
                            "favorites_export",
                            "theme_read",
                            "theme_apply",
                        ):
                            context.permissions.setdefault(
                                perm, PermissionState.GRANTED,
                            )

                        def ensure(_perm: str, ctx=context) -> None:
                            return None
                    else:

                        def ensure(permission: str, ctx=context) -> None:
                            ctx.ensure_permission(permission)

                    context.favorite_service = FavoriteService(
                        pages.favorite_manager,
                        ensure,
                    )
                except Exception:  # pragma: no cover - defensive guard
                    context.favorite_service = None
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
        if request.message:
            content_controls.append(ft.Text(request.message, size=12))

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
            title=ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE), ft.Text("权限请求")]),
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
        self._page.show_dialog(self._permission_dialog)

    def _close_permission_dialog(self) -> None:
        if self._permission_dialog and self._page is not None:
            try:
                self._page.pop_dialog()
            except Exception:
                self._permission_dialog.open = False
                self._page.update()
        self._permission_dialog = None

    def _reset_permission_prompts(self, reason: str) -> None:
        self._close_permission_dialog()
        for request in self._permission_prompt_queue:
            if request.result is None:
                request.result = PluginOperationResult.failed(
                    "permission_prompt_cancelled", reason,
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
