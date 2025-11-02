"""Core page implementations for Little Tree Wallpaper Next."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import tarfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, TYPE_CHECKING

from urllib.parse import parse_qsl, quote, quote_plus, urlencode

import aiohttp
import flet as ft
import pyperclip
from loguru import logger

import ltwapi

from app.constants import BUILD_VERSION, HITOKOTO_API, SHOW_WATERMARK, VER
from app.paths import LICENSE_PATH, CACHE_DIR
from app.favorites import (
    FavoriteFolder,
    FavoriteItem,
    FavoriteManager,
    FavoriteSource,
)
from app.ui_utils import (
    build_watermark,
    copy_files_to_clipboard,
    copy_image_to_clipboard,
)
from app.wallpaper_sources import (
    WallpaperCategoryRef,
    WallpaperItem,
    WallpaperSourceError,
    WallpaperSourceFetchError,
    WallpaperSourceImportError,
    WallpaperSourceManager,
    WallpaperSourceRecord,
)
from app.plugins import (
    AppRouteView,
    PluginPermission,
    PluginRuntimeInfo,
    PluginService,
    PluginStatus,
    GlobalDataAccess,
    GlobalDataError,
    PluginImportResult,
    PluginKind,
    PluginOperationResult,
    PermissionState,
    KNOWN_PERMISSIONS,
)
from app.plugins.events import EventDefinition, PluginEventBus

from app.settings import SettingsStore

app_config = SettingsStore()

_WS_DEFAULT_KEY = "__default__"


@dataclass(slots=True)
class _IMParameterControl:
    config: Dict[str, Any]
    control: ft.Control
    display: ft.Control
    getter: Callable[[], Any]
    setter: Callable[[Any], None]
    key: str


@dataclass(slots=True)
class _WSParameterControl:
    option: Any
    control: ft.Control
    display: ft.Control
    getter: Callable[[], Any]
    setter: Callable[[Any], None]


if TYPE_CHECKING:
    from app.plugins.base import PluginSettingsPage
    from app.theme import ThemeManager
    from app.plugins import PluginOperationResult


class Pages:
    def __init__(
        self,
        page: ft.Page,
        bing_action_factories: list[Callable[[], ft.Control]] | None = None,
        spotlight_action_factories: list[Callable[[], ft.Control]] | None = None,
        settings_pages: list["PluginSettingsPage"] | None = None,
        event_bus: PluginEventBus | None = None,
        plugin_service: Optional[PluginService] = None,
        plugin_runtime: Optional[List[PluginRuntimeInfo]] = None,
        known_permissions: Optional[Dict[str, PluginPermission]] = None,
        event_definitions: Optional[List[EventDefinition]] = None,
        global_data: GlobalDataAccess | None = None,
        theme_manager: "ThemeManager" | None = None,
        theme_list_handler: Callable[[], "PluginOperationResult"] | None = None,
        theme_apply_handler: Callable[[str], "PluginOperationResult"] | None = None,
        theme_profiles: Optional[List[Dict[str, Any]]] = None,
    ):
        self.page = page
        self.event_bus = event_bus
        self.plugin_service = plugin_service
        self._plugin_runtime_cache: List[PluginRuntimeInfo] = list(plugin_runtime or [])
        self._known_permissions: Dict[str, PluginPermission] = dict(
            known_permissions or {}
        )
        self._sync_known_permissions()
        # Flet Colors compatibility: some versions may not expose SURFACE_CONTAINER_LOW
        self._bgcolor_surface_low = getattr(
            ft.Colors, "SURFACE_CONTAINER_LOW", ft.Colors.SURFACE_CONTAINER_HIGHEST
        )
        self._event_definitions: List[EventDefinition] = list(event_definitions or [])
        self._plugin_list_column: Optional[ft.Column] = None
        self._plugin_file_picker: Optional[ft.FilePicker] = None
        self._favorite_file_picker: Optional[ft.FilePicker] = None
        self._theme_file_picker: Optional[ft.FilePicker] = None
        self.wallpaper_path = ltwapi.get_sys_wallpaper()
        self.bing_wallpaper = None
        self.bing_wallpaper_url = None
        self.bing_loading = True
        self.spotlight_loading = True
        self.spotlight_wallpaper_url = None
        self.spotlight_wallpaper = list()
        self.spotlight_current_index = 0

        self.bing_action_factories = (
            bing_action_factories if bing_action_factories is not None else []
        )
        self.spotlight_action_factories = (
            spotlight_action_factories if spotlight_action_factories is not None else []
        )
        self._settings_pages = settings_pages if settings_pages is not None else []
        self._settings_page_map: dict[str, "PluginSettingsPage"] = {}
        self._refresh_settings_registry()
        self._global_data = global_data
        self._bing_data_id: str | None = None
        self._spotlight_data_id: str | None = None
        self._settings_tabs = None
        self._settings_tab_indices: dict[str, int] = {}
        self._pending_settings_tab: str | None = None
        # reload banner removed: use no-op methods instead
        self._route_register: Callable[[AppRouteView], None] | None = None

        self._ensure_global_namespaces()

        self._favorite_manager = FavoriteManager()
        self._favorite_tabs: ft.Tabs | None = None
        self._favorite_selected_folder: str = "__all__"
        self._favorite_folder_dropdown: ft.Dropdown | None = None
        self._favorite_form_fields: dict[str, ft.Control] = {}
        self._favorite_edit_folder_button: ft.IconButton | None = None
        self._favorite_delete_folder_button: ft.IconButton | None = None
        self._favorite_localize_button: ft.IconButton | None = None
        self._favorite_export_button: ft.IconButton | None = None
        self._favorite_import_button: ft.IconButton | None = None
        self._favorite_localization_status_text: ft.Text | None = None
        self._favorite_localization_progress_bar: ft.ProgressBar | None = None
        self._favorite_localization_status_row: ft.Row | None = None
        self._favorite_localization_spinner: ft.ProgressRing | None = None
        self._favorite_localizing_items: set[str] = set()
        self._favorite_item_localize_controls: dict[
            str, tuple[ft.IconButton, ft.Control]
        ] = {}
        self._favorite_item_wallpaper_buttons: dict[str, ft.IconButton] = {}
        self._favorite_item_export_buttons: dict[str, ft.IconButton] = {}
        self._favorite_batch_total: int = 0
        self._favorite_batch_done: int = 0
        self._favorite_preview_cache: dict[str, tuple[float, str]] = {}
        self._favorite_add_local_button: ft.IconButton | None = None

        self._theme_manager = theme_manager
        self._theme_list_handler = theme_list_handler
        self._theme_apply_handler = theme_apply_handler
        self._theme_profiles: list[Dict[str, Any]] = list(theme_profiles or [])
        self._theme_cards_wrap: ft.Wrap | None = None
        self._theme_detail_dialog: ft.AlertDialog | None = None

        self._generate_provider_dropdown: ft.Dropdown | None = None
        self._generate_seed_field: ft.TextField | None = None
        self._generate_width_field: ft.TextField | None = None
        self._generate_height_field: ft.TextField | None = None
        self._generate_enhance_switch: ft.Switch | None = None
        self._generate_prompt_field: ft.TextField | None = None
        self._generate_output_container: ft.Container | None = None
        self._generate_status_text: ft.Text | None = None
        self._generate_loading_indicator: ft.ProgressRing | None = None
        self._generate_last_file: Path | None = None

        # IntelliMarkets source marketplace state
        self._im_sources_by_category: dict[str, list[dict[str, Any]]] = {}
        self._im_all_category_key: str = "__all__"
        self._im_all_category_label: str = "全部"
        self._im_total_sources: int = 0
        self._im_loading: bool = False
        self._im_error: str | None = None
        self._im_selected_category: str | None = None
        self._im_last_updated: float | None = None
        self._im_status_text: ft.Text | None = None
        self._im_loading_indicator: ft.ProgressRing | None = None
        self._im_category_dropdown: ft.Dropdown | None = None
        self._im_sources_list: ft.ListView | None = None
        self._im_search_field: ft.TextField | None = None
        self._im_search_text: str = ""
        self._im_refresh_button: ft.TextButton | None = None
        self._im_repo_owner = "IntelliMarkets"
        self._im_repo_name = "Wallpaper_API_Index"
        self._im_repo_branch = "main"
        self._im_mirror_pref_dropdown: ft.Dropdown | None = None
        self._im_source_dialog: ft.AlertDialog | None = None
        self._im_active_source: dict[str, Any] | None = None
        self._im_param_controls: list[_IMParameterControl] = []
        self._im_cached_inputs: dict[str, dict[str, Any]] = {}
        self._im_run_button: ft.Control | None = None
        self._im_result_container: ft.Column | None = None
        self._im_result_status_text: ft.Text | None = None
        self._im_result_spinner: ft.ProgressRing | None = None
        self._im_running: bool = False
        self._im_last_results: list[dict[str, Any]] = []

        self._wallpaper_source_manager = WallpaperSourceManager()
        self._ws_fetch_button: ft.FilledButton | None = None
        self._ws_reload_button: ft.OutlinedButton | None = None
        self._ws_search_field: ft.TextField | None = None
        self._ws_source_tabs: ft.Tabs | None = None
        self._ws_primary_tabs: ft.Tabs | None = None
        self._ws_secondary_tabs: ft.Tabs | None = None
        self._ws_tertiary_tabs: ft.Tabs | None = None
        self._ws_leaf_tabs: ft.Tabs | None = None
        self._ws_source_tabs_container: ft.Container | None = None
        self._ws_primary_container: ft.Container | None = None
        self._ws_secondary_container: ft.Container | None = None
        self._ws_tertiary_container: ft.Container | None = None
        self._ws_leaf_container: ft.Container | None = None
        self._ws_source_info_container: ft.Container | None = None
        self._ws_param_container: ft.Container | None = None
        self._ws_status_text: ft.Text | None = None
        self._ws_loading_indicator: ft.ProgressRing | None = None
        self._ws_result_list: ft.ListView | None = None
        self._ws_file_picker: ft.FilePicker | None = None
        self._ws_settings_list: ft.Column | None = None
        self._ws_settings_summary_text: ft.Text | None = None
        self._ws_active_source_id: str | None = (
            self._wallpaper_source_manager.active_source_identifier()
        )
        self._ws_active_primary_key: str | None = None
        self._ws_active_secondary_key: str | None = None
        self._ws_active_tertiary_key: str | None = None
        self._ws_active_leaf_index: int = 0
        self._ws_active_category_id: str | None = None
        self._ws_cached_results: dict[str, list[WallpaperItem]] = {}
        self._ws_item_index: dict[str, WallpaperItem] = {}
        self._ws_search_text: str = ""
        self._ws_hierarchy: dict[str, Any] = {}
        self._ws_logo_cache: dict[str, tuple[str, bool]] = {}
        self._ws_updating_ui: bool = False
        self._ws_param_controls: list[_WSParameterControl] = []
        self._ws_param_cache: dict[str, dict[str, Any]] = {}
        self._ws_fetch_in_progress: bool = False
        self._ws_preview_item: WallpaperItem | None = None
        self._ws_preview_item_id: str | None = None

        self.home = self._build_home()
        self.resource = self._build_resource()
        self.generate = self._build_generate()
        self.sniff = self._build_sniff()
        self.favorite = self._build_favorite()
        self.test = self._build_test()

        self._refresh_theme_profiles(initial=True)

        self.page.run_task(self._load_bing_wallpaper)
        self.page.run_task(self._load_spotlight_wallpaper)
        self.page.run_task(self._load_im_sources)

    # 模型列表加载已移除

    def _sync_known_permissions(self) -> None:
        self._known_permissions.update(KNOWN_PERMISSIONS)

    @property
    def favorite_manager(self) -> FavoriteManager:
        return self._favorite_manager

    def _ensure_global_namespaces(self) -> None:
        if not self._global_data:
            return
        try:
            self._global_data.register_namespace(
                "resource.bing",
                description="Bing 每日壁纸元数据",
                permission="resource_data",
            )
            self._global_data.register_namespace(
                "resource.spotlight",
                description="Windows 聚焦壁纸列表",
                permission="resource_data",
            )
        except GlobalDataError as exc:
            logger.error(f"初始化全局数据命名空间失败: {exc}")

    def _build_plugin_actions(
        self, factories: list[Callable[[], ft.Control]]
    ) -> list[ft.Control]:
        controls: list[ft.Control] = []
        for factory in factories:
            try:
                control = factory()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"插件动作生成失败: {exc}")
                continue
            if control is not None:
                controls.append(control)
        return controls

    def _build_plugin_settings_content(self) -> ft.Control:
        management_section = self._build_plugin_management_panel()
        # 插件特定的设置页面可从插件卡片按钮获取
        # 此处仅显示管理面板；插件特定页面可通过每个插件的“插件设置”按钮获取，该按钮会导航至专用视图。
        return ft.Container(
            content=ft.Column(
                [
                    management_section,
                ],
                spacing=24,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=20,
            expand=True,
        )

    def _refresh_settings_registry(self) -> None:
        if not self._settings_pages:
            self._settings_page_map = {}
            return
        self._settings_page_map = {
            entry.plugin_identifier: entry
            for entry in self._settings_pages
            if getattr(entry, "plugin_identifier", None)
        }

    def set_route_registrar(self, registrar: Callable[[AppRouteView], None]) -> None:
        """Provide a callback used to register plugin settings routes."""

        self._route_register = registrar
        self._register_all_plugin_settings_routes()

    def _make_plugin_settings_route(self, entry: "PluginSettingsPage") -> AppRouteView:
        route_path = self._settings_route(entry.plugin_identifier)

        def _builder(pid: str = entry.plugin_identifier) -> ft.View:
            return self.build_plugin_settings_view(pid)

        return AppRouteView(route=route_path, builder=_builder)

    def _register_settings_page_route(self, entry: "PluginSettingsPage") -> None:
        if not self._route_register:
            return
        try:
            view = self._make_plugin_settings_route(entry)
            self._route_register(view)
        except Exception as exc:
            logger.warning(
                "注册插件设置路由失败: {error}",
                error=str(exc),
            )

    def _register_all_plugin_settings_routes(self) -> None:
        if not self._route_register:
            return
        for entry in self.iter_plugin_settings_pages():
            self._register_settings_page_route(entry)

    def notify_settings_page_registered(self, entry: "PluginSettingsPage") -> None:
        self._refresh_settings_registry()
        self._register_settings_page_route(entry)

    def iter_plugin_settings_pages(self) -> list["PluginSettingsPage"]:
        self._refresh_settings_registry()
        return list(self._settings_pages)

    def select_settings_tab(self, tab_id: str) -> bool:
        normalized = tab_id.strip().lower()
        if not normalized:
            return False
        if normalized not in self._settings_tab_indices:
            return False
        if self._settings_tabs is None:
            logger.info(f"延迟切换设置页面标签到 {normalized}")
            self._pending_settings_tab = normalized
            return True
        
        self._settings_tabs.selected_index = self._settings_tab_indices[normalized]
        logger.info(f"切换设置页面标签到 {normalized}({self._settings_tabs.selected_index})")
        self.page.update()
        return True

    def select_settings_tab_index(self, index: int) -> bool:
        # 允许按数字索引进行选择。如果标签尚未创建，则保存待处理索引。
        try:
            if index < 0:
                return False
        except Exception:
            return False
        if self._settings_tabs is None:
            logger.info(f"延迟切换设置页面索引到 {index}")
            # 存储为标准化字符串，以便现有的待处理逻辑能够处理它
            self._pending_settings_tab = str(index)
            return True
        # 防止超出范围
        if not getattr(self._settings_tabs, "tabs", None):
            return False
        if index >= len(self._settings_tabs.tabs):
            return False
        logger.info(f"切换设置页面索引到 {index}")
        self._settings_tabs.selected_index = index
        self.page.update()
        return True

    def _resolve_plugin_runtime(self, plugin_id: str) -> Optional[PluginRuntimeInfo]:
        for runtime in self._plugin_runtime_cache:
            if runtime.identifier == plugin_id:
                return runtime
        return None

    def _open_plugin_settings_page(self, runtime: PluginRuntimeInfo) -> None:
        self._refresh_settings_registry()
        registration = self._settings_page_map.get(runtime.identifier)
        if not registration:
            self._show_snackbar("该插件未提供设置页面。", error=True)
            return
        self.page.go(self._settings_route(runtime.identifier))

    def _settings_route(self, plugin_id: str) -> str:
        return f"/settings/plugin/{plugin_id}"

    def _handle_reload_request(self, _: ft.ControlEvent | None = None) -> None:
        logger.debug("已点击重载按钮")
        self._reload_plugins()

    # Banner-related functionality removed. Methods and UI have been deleted.

    def build_plugin_settings_view(self, plugin_id: str) -> ft.View:
        self._refresh_settings_registry()
        registration = self._settings_page_map.get(plugin_id)
        runtime = self._resolve_plugin_runtime(plugin_id)

        display_name = runtime.name if runtime else plugin_id
        description_text = (runtime.description if runtime else "") or ""
        if registration:
            try:
                plugin_control = registration.builder()
            except Exception as exc:
                message = f"插件设置内容构建失败：{exc}"
                logger.error(message)
                plugin_control = ft.Text(message, color=ft.Colors.ERROR)
        else:
            plugin_control = ft.Text("该插件未注册专属设置页面。", color=ft.Colors.GREY)

        content_controls: list[ft.Control] = []

        if registration:
            content_controls.append(
                ft.Text(registration.title, size=20, weight=ft.FontWeight.BOLD)
            )

        if description_text:
            content_controls.append(
                ft.Text(description_text, size=12, color=ft.Colors.GREY)
            )

        if registration and registration.description:
            content_controls.append(
                ft.Text(
                    registration.description,
                    size=12,
                    color=ft.Colors.GREY,
                )
            )

        content_controls.append(plugin_control)

        body = ft.Container(
            content=ft.Column(
                controls=content_controls,
                spacing=16,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=20,
            expand=True,
        )

        return ft.View(
            self._settings_route(plugin_id),
            [
                ft.AppBar(
                    title=ft.Text(f"{display_name} 设置"),
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        tooltip="返回",
                        on_click=lambda _: self.page.go("/settings"),
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                body,
            ],
        )

    # ------------------------------------------------------------------
    # plugin management helpers
    # ------------------------------------------------------------------
    def _build_plugin_management_panel(self) -> ft.Control:
        if not self.plugin_service:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text("插件管理", size=24),
                        ft.Text("插件管理服务暂不可用。"),
                    ],
                    spacing=12,
                ),
                padding=20,
                bgcolor=self._bgcolor_surface_low,
                border_radius=12,
            )

        self._ensure_plugin_file_picker()
        if self._plugin_list_column is None:
            self._plugin_list_column = ft.Column(spacing=12, expand=True)

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("插件管理", size=24),
                        ft.Text(
                            "在此启用/禁用、导入、删除插件，并管理权限。",
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                ft.Row(
                    [
                        ft.TextButton(
                            text="刷新列表",
                            icon=ft.Icons.REFRESH,
                            tooltip="刷新插件状态",
                            on_click=lambda _: self._refresh_plugin_list(),
                        ),
                        ft.FilledTonalButton(
                            text="重载插件",
                            icon=ft.Icons.RESTART_ALT,
                            tooltip="重新加载所有插件",
                            on_click=lambda _: self._reload_plugins(),
                        ),
                        ft.FilledButton(
                            "导入插件 (.py)",
                            icon=ft.Icons.UPLOAD_FILE,
                            on_click=lambda _: self._open_import_picker(),
                        ),
                    ],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._refresh_plugin_list()

        body_controls: list[ft.Control] = [header, self._plugin_list_column]

        permission_catalog = self._build_permission_catalog_section()
        if permission_catalog:
            body_controls.extend([ft.Divider(), permission_catalog])

        event_section = self._build_event_definitions_section()
        if event_section:
            body_controls.extend([ft.Divider(), event_section])

        return ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(body_controls, spacing=16, expand=True),
            ),
        )

    def _refresh_plugin_list(self) -> None:
        if not self.plugin_service or not self._plugin_list_column:
            return

        self._plugin_list_column.controls = [
            ft.Row(
                [ft.ProgressRing(), ft.Text("正在加载插件信息…")],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        ]
        self.page.update()

        try:
            runtimes = self.plugin_service.list_plugins()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"获取插件状态失败: {exc}")
            self._plugin_list_column.controls = [
                ft.Text(f"加载插件状态失败：{exc}", color=ft.Colors.ERROR),
            ]
            self.page.update()
            return

        self._plugin_runtime_cache = list(runtimes)

        if not runtimes:
            self._plugin_list_column.controls = [ft.Text("当前没有检测到插件。")]
        else:
            sorted_runtime = sorted(
                runtimes,
                key=lambda info: (not getattr(info, "builtin", False), info.identifier),
            )
            self._plugin_list_column.controls = [
                self._build_plugin_card(info) for info in sorted_runtime
            ]

        self.page.update()

    def _build_plugin_card(self, runtime: PluginRuntimeInfo) -> ft.Control:
        self._sync_known_permissions()
        status_label, status_color = self._status_display(runtime.status)
        permissions_summary = self._format_permissions(runtime)

        switch_disabled = runtime.builtin

        def _on_toggle(
            e: ft.ControlEvent,
            *,
            plugin_id: str = runtime.identifier,
            runtime_info: PluginRuntimeInfo = runtime,
        ) -> None:
            new_value = bool(e.control.value)
            if runtime_info.enabled == new_value:
                return
            if not self._toggle_plugin_enabled(plugin_id, new_value):
                e.control.value = runtime_info.enabled
                self.page.update()
                return
            runtime_info.enabled = new_value

        toggle = ft.Switch(
            label="启用",
            value=runtime.enabled,
            disabled=switch_disabled,
            on_change=_on_toggle,
        )

        action_buttons: list[ft.Control] = [
            ft.TextButton(
                "查看详情",
                icon=ft.Icons.INFO,
                on_click=lambda _: self._show_plugin_details(runtime),
            )
        ]

        self._refresh_settings_registry()
        settings_page = self._settings_page_map.get(runtime.identifier)
        if settings_page:
            action_buttons.append(
                ft.TextButton(
                    settings_page.button_label,
                    icon=settings_page.icon or ft.Icons.TUNE,
                    on_click=lambda _: self._open_plugin_settings_page(runtime),
                )
            )

        all_permissions = set(runtime.permissions_required) | set(
            runtime.permissions_granted.keys()
        )
        if all_permissions:
            action_buttons.append(
                ft.TextButton(
                    "管理权限",
                    icon=ft.Icons.ADMIN_PANEL_SETTINGS,
                    on_click=lambda _: self._show_permission_dialog(runtime),
                )
            )

        if not runtime.builtin:
            action_buttons.append(
                ft.TextButton(
                    "删除插件",
                    icon=ft.Icons.DELETE,
                    on_click=lambda _: self._confirm_delete_plugin(runtime),
                )
            )

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            f"{runtime.name} v{runtime.version}",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            runtime.description or "暂无描述",
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                toggle,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        status_row = ft.Row(
            [
                ft.Text(f"状态：{status_label}", color=status_color),
                ft.Text(
                    f"标识符：{runtime.identifier}",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Text(
                    f"来源：{runtime.source_path if runtime.source_path else runtime.module_name or '未知'}",
                    size=12,
                    color=ft.Colors.GREY,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        controls: list[ft.Control] = [header, status_row]

        denied_permissions = [
            self._format_permission_label(perm)
            for perm, state in runtime.permission_states.items()
            if state is PermissionState.DENIED
        ]
        prompt_permissions = [
            self._format_permission_label(perm)
            for perm, state in runtime.permission_states.items()
            if state is PermissionState.PROMPT
        ]

        badges: list[ft.Control] = []
        if denied_permissions:
            badges.append(
                ft.Container(
                    padding=ft.Padding(8, 4, 8, 4),
                    bgcolor=ft.Colors.RED_50,
                    border_radius=6,
                    content=ft.Text(
                        f"已拒绝：{', '.join(denied_permissions)}",
                        size=11,
                        color=ft.Colors.RED_700,
                    ),
                )
            )
        if prompt_permissions:
            badges.append(
                ft.Container(
                    padding=ft.Padding(8, 4, 8, 4),
                    bgcolor=ft.Colors.AMBER_50,
                    border_radius=6,
                    content=ft.Text(
                        f"下次询问：{', '.join(prompt_permissions)}",
                        size=11,
                        color=ft.Colors.AMBER_800,
                    ),
                )
            )

        if badges:
            controls.append(
                ft.Row(
                    controls=badges,
                    spacing=6,
                    run_spacing=6,
                    wrap=True,
                )
            )

        controls.append(
            ft.Text(
                f"类型：{self._format_plugin_kind(runtime.plugin_type)}",
                size=12,
                color=ft.Colors.GREY,
            )
        )

        dependency_summary = self._dependency_summary(runtime)
        controls.append(
            ft.Text(
                f"依赖：{dependency_summary}",
                size=12,
                color=ft.Colors.ERROR if runtime.dependency_issues else ft.Colors.GREY,
            )
        )

        if runtime.error:
            controls.append(ft.Text(f"错误：{runtime.error}", color=ft.Colors.ERROR))

        controls.append(
            ft.Text(f"权限：{permissions_summary}", size=12, color=ft.Colors.GREY)
        )
        controls.append(
            ft.Row(
                controls=action_buttons,
                spacing=10,
                run_spacing=6,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )

        return ft.Card(
            content=ft.Container(
                padding=16,
                content=ft.Column(controls, spacing=10),
            ),
        )

    def _status_display(self, status: PluginStatus | str) -> tuple[str, str]:
        try:
            key = status if isinstance(status, PluginStatus) else PluginStatus(status)
        except ValueError:  # pragma: no cover - defensive
            key = PluginStatus.ERROR

        mapping: dict[PluginStatus, tuple[str, str]] = {
            PluginStatus.ACTIVE: ("运行中", ft.Colors.GREEN),
            PluginStatus.LOADED: ("已加载", ft.Colors.BLUE),
            PluginStatus.DISABLED: ("已禁用", ft.Colors.GREY),
            PluginStatus.PERMISSION_BLOCKED: ("权限待授权", ft.Colors.AMBER),
            PluginStatus.ERROR: ("激活失败", ft.Colors.RED),
            PluginStatus.FAILED: ("加载失败", ft.Colors.RED),
            PluginStatus.NOT_LOADED: ("未加载", ft.Colors.GREY),
            PluginStatus.MISSING_DEPENDENCY: ("依赖缺失", ft.Colors.RED),
        }

        return mapping.get(key, ("未知", ft.Colors.GREY))

    def _format_plugin_kind(self, kind: PluginKind) -> str:
        mapping = {
            PluginKind.FEATURE: "功能插件",
            PluginKind.LIBRARY: "依赖插件",
        }
        return mapping.get(kind, str(kind))

    def _dependency_summary(self, runtime: PluginRuntimeInfo) -> str:
        if not runtime.dependencies:
            return "无"
        parts: list[str] = []
        for spec in runtime.dependencies:
            issue = runtime.dependency_issues.get(spec.identifier)
            if issue:
                parts.append(f"{spec.describe()}（未满足）")
            else:
                parts.append(f"{spec.describe()}（已满足）")
        return "、".join(parts)

    def _dependency_detail_controls(
        self, runtime: PluginRuntimeInfo
    ) -> list[ft.Control]:
        if not runtime.dependencies:
            return [ft.Text("无依赖", size=12, color=ft.Colors.GREY)]
        controls: list[ft.Control] = []
        for spec in runtime.dependencies:
            issue = runtime.dependency_issues.get(spec.identifier)
            if issue:
                controls.append(
                    ft.Text(
                        f"{spec.describe()} - {issue}",
                        size=12,
                        color=ft.Colors.ERROR,
                    )
                )
            else:
                controls.append(
                    ft.Text(
                        f"{spec.describe()} - 已满足",
                        size=12,
                        color=ft.Colors.GREY,
                    )
                )
        return controls

    def _format_permissions(self, runtime: PluginRuntimeInfo) -> str:
        keys = sorted(
            set(runtime.permission_states.keys()) | set(runtime.permissions_required)
        )
        if not keys:
            return "无需权限"

        parts: list[str] = []
        for key in keys:
            permission = self._known_permissions.get(key)
            name = permission.name if permission else key
            state = runtime.permission_states.get(key)
            if state is None:
                state = (
                    PermissionState.GRANTED
                    if runtime.permissions_granted.get(key, False)
                    else PermissionState.PROMPT
                )
            if state is PermissionState.GRANTED:
                suffix = "已授权"
            elif state is PermissionState.DENIED:
                suffix = "已拒绝"
            else:
                suffix = "待确认"
            parts.append(f"{name}（{suffix}）")
        return "、".join(parts)

    def _show_plugin_details(self, runtime: PluginRuntimeInfo) -> None:
        manifest = runtime.manifest
        info_rows = [
            ft.ListTile(title=ft.Text("标识符"), subtitle=ft.Text(runtime.identifier)),
            ft.ListTile(title=ft.Text("版本"), subtitle=ft.Text(runtime.version)),
            ft.ListTile(
                title=ft.Text("描述"),
                subtitle=ft.Text(
                    manifest.description if manifest else runtime.description or "无"
                ),
            ),
            ft.ListTile(
                title=ft.Text("作者"),
                subtitle=ft.Text(manifest.author if manifest else "未知"),
            ),
            ft.ListTile(
                title=ft.Text("类型"),
                subtitle=ft.Text(self._format_plugin_kind(runtime.plugin_type)),
            ),
        ]

        if manifest and manifest.homepage:
            info_rows.append(
                ft.ListTile(
                    title=ft.Text("主页"),
                    subtitle=ft.Text(manifest.homepage, selectable=True),
                    on_click=lambda _: self.page.launch_url(manifest.homepage),
                )
            )

        info_rows.extend(
            [
                ft.ListTile(
                    title=ft.Text("来源"),
                    subtitle=ft.Text(
                        str(runtime.source_path)
                        if runtime.source_path
                        else runtime.module_name or "未知"
                    ),
                ),
                ft.ListTile(
                    title=ft.Text("状态"),
                    subtitle=ft.Text(self._status_display(runtime.status)[0]),
                ),
            ]
        )

        if runtime.error:
            info_rows.append(
                ft.ListTile(
                    title=ft.Text("错误"),
                    subtitle=ft.Text(runtime.error, color=ft.Colors.ERROR),
                )
            )

        permissions_text = self._format_permissions(runtime)
        info_rows.append(
            ft.ListTile(title=ft.Text("权限"), subtitle=ft.Text(permissions_text))
        )

        info_rows.append(
            ft.ListTile(
                title=ft.Text("依赖"),
                subtitle=ft.Column(
                    self._dependency_detail_controls(runtime), spacing=4
                ),
            )
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"插件详情 - {runtime.name}"),
            content=ft.Container(
                width=400,
                content=ft.Column(
                    info_rows, tight=True, spacing=4, scroll=ft.ScrollMode.AUTO
                ),
            ),
            actions=[
                ft.TextButton("关闭", on_click=lambda _: self._close_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _show_permission_dialog(self, runtime: PluginRuntimeInfo) -> None:
        self._sync_known_permissions()
        requested = sorted(
            set(runtime.permission_states.keys()) | set(runtime.permissions_required)
        )

        if not requested:
            self._show_snackbar("该插件未请求任何权限。")
            return

        pending_choices: dict[str, str] = {}
        initial_choices: dict[str, str] = {}
        action_holder: dict[str, ft.FilledButton | None] = {"button": None}

        def _update_apply_state() -> None:
            button = action_holder["button"]
            if not button:
                return
            button.disabled = not pending_choices
            button.update()

        def _submit(_: ft.ControlEvent | None = None) -> None:
            if not pending_choices:
                self._close_dialog()
                return
            for permission_id, choice in list(pending_choices.items()):
                new_state = self._state_from_choice(choice)
                if not self._update_permission_state(
                    runtime.identifier, permission_id, new_state
                ):
                    _update_apply_state()
                    return
            pending_choices.clear()
            _update_apply_state()
            self._close_dialog()

        rows: list[ft.Control] = []

        for permission_id in requested:
            permission = self._known_permissions.get(permission_id)
            title = permission.name if permission else permission_id
            description = permission.description if permission else ""
            current_state = runtime.permission_states.get(permission_id)
            if current_state is None:
                current_state = (
                    PermissionState.GRANTED
                    if runtime.permissions_granted.get(permission_id, False)
                    else PermissionState.PROMPT
                )

            initial_choice = self._choice_from_state(current_state)
            initial_choices[permission_id] = initial_choice

            def _on_choice(
                e: ft.ControlEvent,
                *,
                perm: str = permission_id,
            ) -> None:
                choice = e.control.value
                if choice == initial_choices.get(perm):
                    pending_choices.pop(perm, None)
                else:
                    pending_choices[perm] = choice
                _update_apply_state()

            rows.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.SECURITY),
                    title=ft.Text(title),
                    subtitle=ft.Text(description or f"权限标识：{permission_id}"),
                    trailing=ft.Dropdown(
                        width=180,
                        value=initial_choice,
                        options=[
                            ft.DropdownOption(key="deny", text="禁用"),
                            ft.DropdownOption(key="prompt", text="下次询问"),
                            ft.DropdownOption(key="allow", text="允许"),
                        ],
                        on_change=_on_choice,
                    ),
                )
            )

        apply_button = ft.FilledButton(
            "确定", icon=ft.Icons.CHECK, disabled=True, on_click=_submit
        )
        action_holder["button"] = apply_button

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"权限管理 - {runtime.name}"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    rows, tight=True, spacing=4, scroll=ft.ScrollMode.AUTO
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                apply_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _toggle_plugin_enabled(self, identifier: str, enabled: bool) -> bool:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            return False
        try:
            self.plugin_service.set_enabled(identifier, enabled)
            self._show_snackbar("插件状态已更新，将在重新加载后生效。")

            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"更新插件启用状态失败: {exc}")
            self._show_snackbar(f"更新失败：{exc}", error=True)
            return False

    def _update_permission_state(
        self, identifier: str, permission: str, state: PermissionState
    ) -> bool:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            return False
        try:
            self.plugin_service.update_permission(identifier, permission, state)
            pending_reload = False
            try:
                pending_reload = bool(self.plugin_service.is_reload_required())
            except Exception:
                pending_reload = False
            if pending_reload:
                self._show_snackbar("权限已更新，将在重新加载后生效。")
            else:
                self._show_snackbar("权限已更新，启用插件后生效。")

            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"更新插件权限失败: {exc}")
            self._show_snackbar(f"权限更新失败：{exc}", error=True)
            return False

    def _confirm_delete_plugin(self, runtime: PluginRuntimeInfo) -> None:
        if runtime.builtin:
            self._show_snackbar("内置插件无法删除。", error=True)
            return

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("删除插件"),
            content=ft.Text(f"确定要删除插件 {runtime.name} 吗？此操作不可撤销。"),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledTonalButton(
                    "删除",
                    icon=ft.Icons.DELETE_FOREVER,
                    on_click=lambda _: self._execute_delete_plugin(runtime.identifier),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _execute_delete_plugin(self, identifier: str) -> None:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            self._close_dialog()
            return
        try:
            self.plugin_service.delete_plugin(identifier)
            # 更新列表，提示用户稍后手动重新加载
            self._refresh_plugin_list()
            self._show_snackbar("插件已删除，需要重新加载后生效。")

        except Exception as exc:
            logger.error(f"删除插件失败: {exc}")
            self._show_snackbar(f"删除失败：{exc}", error=True)
        finally:
            self._close_dialog()

    def _reload_plugins(self) -> None:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            logger.warning("尝试重新加载插件，但插件服务不可用。")
            return
        try:
            logger.info("重新加载插件…")
            self.plugin_service.reload()

            self._show_snackbar("插件正在重新加载…")
            logger.info("重载插件命令已发送。")

        except Exception as exc:
            logger.error(f"重新加载插件失败: {exc}")
            self._show_snackbar(f"重新加载失败：{exc}", error=True)

    def _open_dialog(self, dialog: ft.AlertDialog) -> None:
        self.page.dialog = dialog
        self.page.open(self.page.dialog)

    def _close_dialog(self) -> None:
        if self.page.dialog is not None:
            self.page.close(self.page.dialog)

    # -----------------------------
    # 收藏：添加本地图片入口
    # -----------------------------
    def _ensure_favorite_file_picker(self) -> None:
        if self._favorite_file_picker is None:
            self._favorite_file_picker = ft.FilePicker(
                on_result=self._handle_add_local_favorite_result
            )
        if self._favorite_file_picker not in self.page.overlay:
            self.page.overlay.append(self._favorite_file_picker)
            self.page.update()

    def _open_add_local_favorite_picker(self) -> None:
        self._ensure_favorite_file_picker()
        if self._favorite_file_picker:
            self._favorite_file_picker.pick_files(
                allow_multiple=True,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[
                    "jpg",
                    "jpeg",
                    "png",
                    "webp",
                    "bmp",
                    "gif",
                    "avif",
                ],
            )

    def _handle_add_local_favorite_result(
        self, event: ft.FilePickerResultEvent
    ) -> None:
        if not event.files:
            return
        count = 0
        errors = 0
        folder_id = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else None
        )
        for f in event.files:
            try:
                if not f.path:
                    continue
                item, created = self._favorite_manager.add_local_item(
                    path=f.path,
                    folder_id=folder_id,
                )
                if created:
                    count += 1
            except Exception as exc:
                logger.error(f"添加本地收藏失败: {exc}")
                errors += 1
        # 刷新列表
        self._refresh_favorite_tabs()
        if count and not errors:
            self._show_snackbar(f"已添加 {count} 项本地收藏。")
        elif count and errors:
            self._show_snackbar(
                f"已添加 {count} 项本地收藏，{errors} 项失败。", error=True
            )
        elif errors:
            self._show_snackbar("添加本地收藏失败。", error=True)

    def _ensure_plugin_file_picker(self) -> None:
        if self._plugin_file_picker is None:
            self._plugin_file_picker = ft.FilePicker(
                on_result=self._handle_import_result
            )
        if self._plugin_file_picker not in self.page.overlay:
            self.page.overlay.append(self._plugin_file_picker)
            self.page.update()

    def _open_import_picker(self) -> None:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            return
        self._ensure_plugin_file_picker()
        if self._plugin_file_picker:
            self._plugin_file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.ANY,
                allowed_extensions=["py"],
            )

    def _handle_import_result(self, event: ft.FilePickerResultEvent) -> None:
        if not self.plugin_service or not event.files:
            return
        file = event.files[0]
        if not file.path:
            self._show_snackbar("未选择有效的文件。", error=True)
            return
        try:
            result = self.plugin_service.import_plugin(Path(file.path))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"导入插件失败: {exc}")
            self._show_snackbar(f"导入失败：{exc}", error=True)
            return

        if result.error:
            logger.warning(f"导入插件时解析 manifest 失败: {result.error}")

        if not result.identifier:
            self._show_snackbar(
                "插件已导入，但无法识别 manifest，将使用默认设置重新加载。"
            )
            try:
                self.plugin_service.reload()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"重新加载插件失败: {exc}")
                self._show_snackbar(f"重新加载失败：{exc}", error=True)
            return

        self._show_import_permission_dialog(result)

    def _show_import_permission_dialog(self, result: PluginImportResult) -> None:
        if not self.plugin_service:
            return

        self._sync_known_permissions()

        identifier = result.identifier or result.module_name or result.destination.stem
        manifest = result.manifest
        permission_controls: list[ft.Control] = []
        toggles: dict[str, ft.Dropdown] = {}

        description = manifest.description if manifest else ""
        plugin_title = manifest.name if manifest else identifier

        if result.requested_permissions:
            for perm in result.requested_permissions:
                info = self._known_permissions.get(perm)
                label = info.name if info else perm
                detail = info.description if info else "未在权限目录中登记。"
                selector = ft.Dropdown(
                    width=220,
                    label=f"授予 {label}",
                    value="prompt",
                    options=[
                        ft.DropdownOption(key="deny", text="禁用"),
                        ft.DropdownOption(key="prompt", text="下次询问"),
                        ft.DropdownOption(key="allow", text="允许"),
                    ],
                )
                toggles[perm] = selector
                permission_controls.append(
                    ft.Column(
                        [
                            selector,
                            ft.Text(
                                f"权限 ID：{perm}\n{detail}",
                                size=12,
                                color=ft.Colors.GREY,
                            ),
                        ],
                        spacing=4,
                    )
                )
        else:
            permission_controls.append(
                ft.Text(
                    "该插件未请求额外权限，可直接加载。", size=12, color=ft.Colors.GREY
                )
            )

        warning_text: list[ft.Control] = []
        if result.error:
            warning_text.append(
                ft.Text(
                    f"警告：解析 manifest 时出现问题（{result.error}）。将尝试继续加载。",
                    color=ft.Colors.ERROR,
                    size=12,
                )
            )

        def _on_accept(_: ft.ControlEvent) -> None:
            self._close_dialog()
            self._apply_import_permissions(identifier, toggles)

        def _on_skip(_: ft.ControlEvent) -> None:
            self._close_dialog()
            self._show_snackbar("插件已导入并保持禁用，可稍后在列表中启用。")
            self._refresh_plugin_list()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"新插件：{plugin_title}"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    [
                        ft.Text(
                            identifier,
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                        *(warning_text or []),
                        ft.Text(description, size=12)
                        if description
                        else ft.Container(),
                        ft.Divider(),
                        ft.Column(permission_controls, spacing=8),
                    ],
                    spacing=12,
                ),
            ),
            actions=[
                ft.TextButton("稍后再说", on_click=_on_skip),
                ft.FilledButton("保存设置", on_click=_on_accept),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _apply_import_permissions(
        self, identifier: str, toggles: dict[str, ft.Dropdown]
    ) -> None:
        if not self.plugin_service:
            return

        try:
            for perm, control in toggles.items():
                state = self._state_from_choice(control.value)
                self.plugin_service.update_permission(identifier, perm, state)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"设置导入权限失败: {exc}")
            self._show_snackbar(f"保存权限失败：{exc}", error=True)
            return

        self._show_snackbar("权限已保存，将在启用插件时生效。")
        self._refresh_plugin_list()

    def _build_permission_catalog_section(self) -> ft.Control | None:
        self._sync_known_permissions()
        if not self._known_permissions:
            return None

        items = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.VERIFIED_USER),
                title=ft.Text(f"{permission.name} ({permission.identifier})"),
                subtitle=ft.Text(permission.description),
            )
            for permission in sorted(
                self._known_permissions.values(), key=lambda p: p.identifier
            )
        ]

        return ft.Column(
            [
                ft.Text("权限说明", size=16, weight=ft.FontWeight.BOLD),
                ft.Column(items, spacing=4),
            ],
            spacing=8,
        )

    def _build_event_definitions_section(self) -> ft.Control | None:
        definitions = self._event_definitions or []
        if not definitions:
            return None

        items: list[ft.Control] = []
        for definition in sorted(definitions, key=lambda d: d.event_type):
            permission_text = (
                "无需权限"
                if not definition.permission
                else f"需要权限：{self._format_permission_label(definition.permission)}"
            )
            items.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.EVENT),
                    title=ft.Text(definition.event_type, selectable=True),
                    subtitle=ft.Text(f"{definition.description}\n{permission_text}"),
                )
            )

        return ft.Column(
            [
                ft.Text("可用事件", size=16, weight=ft.FontWeight.BOLD),
                ft.Column(items, spacing=4),
            ],
            spacing=8,
        )

    def _format_permission_label(self, permission_id: str) -> str:
        permission = self._known_permissions.get(permission_id)
        if permission:
            return f"{permission.name} ({permission.identifier})"
        return permission_id

    @staticmethod
    def _choice_from_state(state: PermissionState | None) -> str:
        if state is PermissionState.GRANTED:
            return "allow"
        if state is PermissionState.DENIED:
            return "deny"
        return "prompt"

    @staticmethod
    def _state_from_choice(value: str | None) -> PermissionState:
        if value == "allow":
            return PermissionState.GRANTED
        if value == "deny":
            return PermissionState.DENIED
        return PermissionState.PROMPT

    def _show_snackbar(self, message: str, *, error: bool = False) -> None:
        snackbar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.Colors.ERROR if error else None,
        )
        self.page.open(snackbar)

    @staticmethod
    def _abbreviate_text(text: str, max_len: int = 80) -> str:
        if len(text) <= max_len:
            return text
        if max_len <= 3:
            return text[:max_len]
        return text[: max_len - 3] + "..."

    # ------------------------------------------------------------------
    # plugin event helpers
    # ------------------------------------------------------------------
    def _bing_payload_data(self) -> Dict[str, Any]:
        data = self.bing_wallpaper or {}
        payload: Dict[str, Any] = {
            "available": bool(self.bing_wallpaper_url),
            "title": data.get("title"),
            "description": data.get("copyright") or data.get("desc"),
            "image_url": self.bing_wallpaper_url,
            "download_url": self.bing_wallpaper_url,
            "raw": dict(data) if isinstance(data, dict) else data,
        }
        return payload

    def _spotlight_payload_data(self) -> Dict[str, Any]:
        items = self.spotlight_wallpaper or []
        idx = self.spotlight_current_index if items else None
        current = items[idx] if idx is not None and idx < len(items) else None
        if isinstance(current, dict):
            current = dict(current)
        return {
            "available": bool(items),
            "current_index": idx,
            "current": current,
            "items": items,
        }

    def _resolve_bing_entry_id(self, payload: Dict[str, Any]) -> str:
        raw = payload.get("raw") or {}
        if isinstance(raw, dict):
            for key in ("startdate", "enddate", "date"):
                value = raw.get(key)
                if value:
                    return str(value)
            if raw.get("url"):
                return str(raw.get("url"))
        if payload.get("image_url"):
            return str(payload["image_url"])
        return f"bing-{int(time.time())}"

    def _resolve_spotlight_entry_id(self, payload: Dict[str, Any]) -> str:
        current = payload.get("current")
        if isinstance(current, dict):
            for key in ("id", "identifier", "sha256", "url"):
                value = current.get(key)
                if value:
                    return str(value)
        return f"spotlight-{int(time.time())}"

    def _publish_bing_data(self) -> None:
        if not self._global_data:
            return
        payload = self._bing_payload_data()
        entry_id = (
            self._resolve_bing_entry_id(payload)
            if payload.get("available")
            else (self._bing_data_id or "bing-latest")
        )
        payload_with_meta = dict(payload)
        payload_with_meta["namespace"] = "resource.bing"
        try:
            snapshot = self._global_data.publish(
                "resource.bing", entry_id, payload_with_meta
            )
            self._bing_data_id = snapshot.get("identifier")
        except GlobalDataError as exc:
            logger.error(f"写入 Bing 全局数据失败: {exc}")

    def _publish_spotlight_data(self) -> None:
        if not self._global_data:
            return
        payload = self._spotlight_payload_data()
        entry_id = (
            self._resolve_spotlight_entry_id(payload)
            if payload.get("available")
            else (self._spotlight_data_id or "spotlight-latest")
        )
        payload_with_meta = dict(payload)
        payload_with_meta["namespace"] = "resource.spotlight"
        try:
            snapshot = self._global_data.publish(
                "resource.spotlight",
                entry_id,
                payload_with_meta,
            )
            self._spotlight_data_id = snapshot.get("identifier")
        except GlobalDataError as exc:
            logger.error(f"写入 Spotlight 全局数据失败: {exc}")

    def _emit_resource_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        try:
            self.event_bus.emit(event_type, payload, source="core")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"派发插件事件失败 {event_type}: {exc}")

    def _emit_download_completed(
        self,
        source: str,
        action: str,
        file_path: str,
        extra: Dict[str, Any] | None = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "source": source,
            "action": action,
            "file_path": str(file_path),
        }
        if source == "bing":
            payload.update(self._bing_event_payload())
        elif source == "spotlight":
            payload.update(self._spotlight_event_payload())
        if extra:
            payload.update(extra)
        self._emit_resource_event("resource.download.completed", payload)

    def _bing_event_payload(self) -> Dict[str, Any]:
        payload = self._bing_payload_data()
        payload["data_id"] = self._bing_data_id
        payload["namespace"] = "resource.bing"
        return payload

    def _spotlight_event_payload(self) -> Dict[str, Any]:
        payload = self._spotlight_payload_data()
        payload["data_id"] = self._spotlight_data_id
        payload["namespace"] = "resource.spotlight"
        return payload

    def _emit_bing_action(
        self, action: str, success: bool, extra: Dict[str, Any] | None = None
    ) -> None:
        payload = {
            "action": action,
            "success": success,
        }
        payload.update(self._bing_event_payload())
        if extra:
            payload.update(extra)
        self._emit_resource_event("resource.bing.action", payload)

    def _emit_spotlight_action(
        self,
        action: str,
        success: bool,
        extra: Dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "action": action,
            "success": success,
        }
        payload.update(self._spotlight_event_payload())
        if extra:
            payload.update(extra)
        self._emit_resource_event("resource.spotlight.action", payload)

    def _get_license_text(self):
        parts: list[str] = []
        try:
            files = sorted(
                [p for p in LICENSE_PATH.iterdir() if p.is_file()],
                key=lambda p: p.name.lower(),
            )
        except Exception as exc:
            logger.error(f"读取许可证目录失败: {exc}")
            return "暂无许可证信息"

        for fp in files:
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                logger.error(f"读取许可证文件失败: {fp}: {exc}")
                continue
            title = fp.stem
            parts.append(f"# {title}\n\n{content}\n\n---")

        return "\n\n".join(parts) if parts else "暂无许可证信息"

    async def _load_hitokoto(self):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(HITOKOTO_API[1]) as r:
                    return (await r.json())["hitokoto"]
        except Exception:
            return "一言获取失败"

    async def _show_hitokoto(self):
        self.hitokoto_text.value = ""
        self.hitokoto_loading.visible = True
        self.page.update()
        self.hitokoto_text.value = f"「{await self._load_hitokoto()}」"
        self.hitokoto_loading.visible = False
        self.page.update()

    def refresh_hitokoto(self, _=None):
        self.page.run_task(self._show_hitokoto)

    def _update_wallpaper(self):
        self.wallpaper_path = ltwapi.get_sys_wallpaper()

    def _copy_sys_wallpaper_path(self):
        pyperclip.copy(self.wallpaper_path)
        self.page.open(
            ft.SnackBar(
                ft.Row(
                    controls=[
                        ft.Icon(name=ft.Icons.DONE, color=ft.Colors.ON_SECONDARY),
                        ft.Text("壁纸路径已复制~ (。・∀・)"),
                    ]
                )
            )
        )

    def _refresh_home(self, _):
        self._update_wallpaper()
        self.img.src = self.wallpaper_path
        self.file_name.spans = [
            ft.TextSpan(
                f"当前壁纸：{Path(self.wallpaper_path).name}",
                ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE),
                on_click=lambda _: self._copy_sys_wallpaper_path(),
            )
        ]

        self.page.update()

    async def _load_bing_wallpaper(self):
        try:
            self.bing_wallpaper = await ltwapi.get_bing_wallpaper_async()
            base = self.bing_wallpaper.get("url")
            if base:
                self.bing_wallpaper_url = f"https://www.bing.com{base}".replace(
                    "1920x1080", "UHD"
                )
        except Exception:
            self.bing_wallpaper_url = None
        finally:
            self.bing_loading = False
            self._publish_bing_data()
            self._emit_resource_event(
                "resource.bing.updated", self._bing_event_payload()
            )
            self._refresh_bing_tab()

    async def _load_spotlight_wallpaper(self):
        try:
            self.spotlight_wallpaper = await ltwapi.get_spotlight_wallpaper_async()
            if self.spotlight_wallpaper and len(self.spotlight_wallpaper) > 0:
                self.spotlight_loading = self.spotlight_wallpaper
                self.spotlight_current_index = 0
            if self.spotlight_loading:
                self.spotlight_wallpaper_url = [
                    item["url"] for item in self.spotlight_wallpaper
                ]

        except Exception as e:
            self.spotlight_wallpaper_url = None
            logger.error(f"加载 Windows 聚焦壁纸失败: {e}")
        finally:
            self.spotlight_loading = False
            self._publish_spotlight_data()
            self._emit_resource_event(
                "resource.spotlight.updated", self._spotlight_event_payload()
            )
            self._refresh_spotlight_tab()

    def _refresh_bing_tab(self):
        for tab in self.resource_tabs.tabs:
            if tab.text == "Bing 每日":
                tab.content = self._build_bing_daily_content()
                break
        self.page.update()

    def _refresh_spotlight_tab(self):
        for tab in self.resource_tabs.tabs:
            if tab.text == "Windows 聚焦":
                tab.content = self._build_spotlight_daily_content()
                break
        self.page.update()

    def _build_home(self):
        from app.paths import ASSET_DIR  # local import to avoid circular dependencies

        self.file_name = ft.Text(
            spans=[
                ft.TextSpan(
                    f"当前壁纸：{Path(self.wallpaper_path).name}",
                    ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE),
                    on_click=lambda _: self._copy_sys_wallpaper_path(),
                )
            ]
        )

        self.img = ft.Image(
            src=self.wallpaper_path,
            height=200,
            border_radius=10,
            fit=ft.ImageFit.COVER,
            tooltip="当前计算机的壁纸",
            error_content=ft.Container(ft.Text("图片已失效，请刷新数据~"), padding=20),
        )
        self.hitokoto_loading = ft.ProgressRing(visible=False, width=24, height=24)
        self.hitokoto_text = ft.Text("", size=16, font_family="HITOKOTOFont")
        refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH, tooltip="刷新一言", on_click=self.refresh_hitokoto
        )
        return ft.Container(
            ft.Column(
                [
                    ft.Text("当前壁纸", size=30),
                    ft.Row(
                        [
                            self.img,
                            ft.Column(
                                [
                                    ft.TextButton("导出", icon=ft.Icons.SAVE_ALT),
                                    ft.TextButton("更换", icon=ft.Icons.PHOTO_LIBRARY),
                                    ft.TextButton(
                                        "收藏",
                                        icon=ft.Icons.STAR,
                                        on_click=lambda _: self._open_favorite_editor(
                                            self._make_current_wallpaper_payload()
                                        ),
                                    ),
                                    ft.TextButton(
                                        "刷新",
                                        tooltip="刷新当前壁纸信息",
                                        icon=ft.Icons.REFRESH,
                                        on_click=self._refresh_home,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.END,
                            ),
                        ]
                    ),
                    self.file_name,
                    ft.Container(
                        content=ft.Divider(height=1, thickness=1),
                        margin=ft.margin.only(top=30),
                    ),
                    ft.Row(
                        [self.hitokoto_loading, self.hitokoto_text, refresh_btn],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Image(src=ASSET_DIR / "images" / "1.gif"),
                ],
            ),
            expand=True,
            padding=16,
        )

    def _build_resource(self):
        self.resource_tabs = ft.Tabs(
            tabs=[
                ft.Tab(
                    text="Bing 每日",
                    icon=ft.Icons.TODAY,
                    content=self._build_bing_loading_indicator(),
                ),
                ft.Tab(
                    text="Windows 聚焦",
                    icon=ft.Icons.WINDOW,
                    content=self._build_spotlight_loading_indicator(),
                ),
                ft.Tab(text="搜索", icon=ft.Icons.SEARCH),
                ft.Tab(
                    text="IntelliMarkets 图片源",
                    icon=ft.Icons.SUBJECT,
                    content=self._build_im_page(),
                ),
                ft.Tab(
                    text="其他",
                    icon=ft.Icons.SUBJECT,
                    content=self._build_wallpaper_source_tab(),
                ),
            ],
            animation_duration=300,
        )
        return ft.Container(
            ft.Column(
                [
                    ft.Text("资源", size=30),
                    ft.Container(
                        content=self.resource_tabs,
                        expand=True,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    ),
                ],
            ),
            expand=True,
            padding=16,
        )

    def _build_generate(self):
        self._generate_provider_dropdown = ft.Dropdown(
            label="服务提供商",
            value="pollinations",
            options=[
                ft.DropdownOption(key="pollinations", text="Pollinations.ai"),
            ],
        )
        self._generate_seed_field = ft.TextField(
            label="种子（相同种子将生成相同图片）",
            value="42",
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self._generate_width_field = ft.TextField(
            label="图片宽度",
            value="1920",
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self._generate_height_field = ft.TextField(
            label="图片高度",
            value="1080",
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self._generate_enhance_switch = ft.Switch(
            label="使用大模型优化提示词",
            value=False,
        )
        self._generate_prompt_field = ft.TextField(
            label="提示词",
            min_lines=3,
            max_lines=5,
            multiline=True,
        )

        self._generate_loading_indicator = ft.ProgressRing(
            width=20,
            height=20,
            stroke_width=2,
            visible=False,
        )
        self._generate_status_text = ft.Text(
            "填写提示词后点击生成，即可在右侧查看图片",
            size=12,
            color=ft.Colors.OUTLINE,
        )

        placeholder = ft.Column(
            [
                ft.Icon(ft.Icons.IMAGE, size=72, color=ft.Colors.OUTLINE),
                ft.Text("生成的图片会展示在这里", color=ft.Colors.OUTLINE),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        )

        self._generate_output_container = ft.Container(
            expand=True,
            border_radius=12,
            bgcolor=self._bgcolor_surface_low,
            alignment=ft.alignment.center,
            padding=16,
            content=placeholder,
        )

        left_panel = ft.Container(
            width=360,
            padding=16,
            bgcolor=self._bgcolor_surface_low,
            border_radius=12,
            content=ft.Column(
                [
                    self._generate_provider_dropdown,
                    self._generate_seed_field,
                    self._generate_width_field,
                    self._generate_height_field,
                    self._generate_enhance_switch,
                    self._generate_prompt_field,
                    ft.FilledButton("生成", on_click=self._handle_generate_clicked),
                ],
                spacing=12,
                tight=True,
            ),
        )

        right_panel = ft.Container(
            expand=True,
            padding=16,
            bgcolor=ft.Colors.SURFACE,
            border_radius=12,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self._generate_loading_indicator,
                            self._generate_status_text,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._generate_output_container,
                ],
                spacing=16,
                expand=True,
            ),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("生成", size=30),
                    ft.Row(
                        [
                            left_panel,
                            right_panel,
                        ],
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=24,
                expand=True,
            ),
            expand=True,
            padding=16,
        )

    def _handle_generate_error(self, message: str) -> None:
        logger.error("Image generation failed: {message}", message=message)
        self._set_generate_loading(False)
        self._update_generate_status(message, error=True)
        self._show_snackbar(message, error=True)

    def _set_generate_loading(self, active: bool) -> None:
        if self._generate_loading_indicator is None:
            return
        self._generate_loading_indicator.visible = active
        if self._generate_loading_indicator.page is not None:
            self._generate_loading_indicator.update()

    def _update_generate_status(self, message: str, *, error: bool = False) -> None:
        if self._generate_status_text is None:
            return
        self._generate_status_text.value = message
        self._generate_status_text.color = (
            ft.Colors.ERROR if error else ft.Colors.OUTLINE
        )
        if self._generate_status_text.page is not None:
            self._generate_status_text.update()

    def _set_generate_output_image(
        self,
        source: str,
        *,
        is_local_file: bool = False,
    ) -> None:
        if self._generate_output_container is None:
            return
        logger.debug(
            "Updating preview image",
            source=source,
            local=is_local_file,
        )
        image_kwargs = dict(
            fit=ft.ImageFit.CONTAIN,
            expand=True,
            border_radius=12,
        )
        if is_local_file:
            try:
                data = Path(source).read_bytes()
            except Exception as exc:
                logger.error(
                    "Failed to read generated image file: {error}",
                    error=str(exc),
                )
                raise
            encoded = base64.b64encode(data).decode("ascii")
            image_control = ft.Image(src_base64=encoded, **image_kwargs)
        else:
            image_control = ft.Image(src=source, **image_kwargs)

        self._generate_output_container.content = image_control
        if self._generate_output_container.page is not None:
            self._generate_output_container.update()

    def _handle_generate_clicked(self, _: ft.ControlEvent) -> None:
        prompt = (
            (self._generate_prompt_field.value or "").strip()
            if self._generate_prompt_field
            else ""
        )
        if not prompt:
            self._handle_generate_error("请输入提示词。")
            return

        logger.info(
            "Generate button clicked with prompt: {prompt}",
            prompt=self._abbreviate_text(prompt, 120),
        )

        provider = (
            (self._generate_provider_dropdown.value or "").strip().lower()
            if self._generate_provider_dropdown
            else "pollinations"
        )
        if provider not in ("pollinations", ""):
            logger.error("Unsupported provider selected: {provider}", provider=provider)
            self._handle_generate_error("当前仅支持 Pollinations.ai。")
            return

        width: int | None = None
        if self._generate_width_field:
            raw_width = (self._generate_width_field.value or "").strip()
            if raw_width:
                try:
                    width = int(raw_width)
                    if width <= 0:
                        raise ValueError
                except ValueError:
                    logger.warning("Invalid width value: {value}", value=raw_width)
                    self._handle_generate_error("图片宽度必须是正整数。")
                    return

        height: int | None = None
        if self._generate_height_field:
            raw_height = (self._generate_height_field.value or "").strip()
            if raw_height:
                try:
                    height = int(raw_height)
                    if height <= 0:
                        raise ValueError
                except ValueError:
                    logger.warning("Invalid height value: {value}", value=raw_height)
                    self._handle_generate_error("图片高度必须是正整数。")
                    return

        params: dict[str, str] = {}
        seed = (
            (self._generate_seed_field.value or "").strip()
            if self._generate_seed_field
            else ""
        )
        enhance = (
            self._generate_enhance_switch.value
            if self._generate_enhance_switch is not None
            else False
        )
        allow_nsfw = bool(app_config.get("wallpaper.allow_nsfw", False))

        if seed:
            params["seed"] = seed
        if width is not None:
            params["width"] = str(width)
        if height is not None:
            params["height"] = str(height)
        if enhance:
            params["enhance"] = "true"
        params["safe"] = "false" if allow_nsfw else "true"

        base_url = "https://image.pollinations.ai/prompt/"
        encoded_prompt = quote_plus(prompt)
        request_url = f"{base_url}{encoded_prompt}"
        if params:
            request_url = f"{request_url}?{urlencode(params)}"
        cache_token = str(int(time.time() * 1000))
        cache_suffix = f"cb={cache_token}"
        request_url = (
            f"{request_url}&{cache_suffix}"
            if params
            else f"{request_url}?{cache_suffix}"
        )

        logger.info(
            "Dispatching Pollinations request",
            prompt=self._abbreviate_text(prompt, 120),
            url=request_url,
            width=width,
            height=height,
            seed=seed,
            model="<default>",
            enhance=enhance,
            safe=params.get("safe"),
        )

        self._set_generate_loading(True)
        self._update_generate_status("已发送生成请求，正在等待图像生成…")
        self.page.run_task(
            self._process_generate_request,
            request_url,
            prompt,
            width,
            height,
            seed,
            "",
            enhance,
            allow_nsfw,
        )

    async def _process_generate_request(
        self,
        request_url: str,
        prompt: str,
        width: int | None,
        height: int | None,
        seed: str,
        model: str,
        enhance: bool,
        allow_nsfw: bool,
    ) -> None:
        cache_dir = CACHE_DIR / "generations"
        cache_dir.mkdir(parents=True, exist_ok=True)

        slug = self._favorite_filename_slug(prompt, "generation")
        timestamp = int(time.time())
        custom_name = f"{slug}-{timestamp}"

        async def _download() -> str | None:
            return await asyncio.to_thread(
                ltwapi.download_file,
                request_url,
                cache_dir,
                custom_name,
                120,
                3,
                {"Accept": "image/*"},
                None,
                False,
            )

        try:
            path_str = await _download()
        except Exception as exc:  # pragma: no cover - network
            logger.error(
                "Error downloading generated image: {error}",
                error=str(exc),
            )
            self._handle_generate_error("生成图片下载失败，请稍后重试。")
            return

        if not path_str:
            self._handle_generate_error("生成图片失败，请稍后重试。")
            return

        path = Path(path_str)
        self._generate_last_file = path
        try:
            self._set_generate_output_image(str(path), is_local_file=True)
        except Exception:
            self._handle_generate_error("加载生成的图片失败。")
            return

        self._update_generate_status(f"生成完成，已保存到 {path.name}")
        logger.info(
            "Generated image cached locally",
            path=str(path),
            prompt=self._abbreviate_text(prompt, 120),
            width=width,
            height=height,
            seed=seed,
            model="<default>",
            enhance=enhance,
            safe="false" if allow_nsfw else "true",
        )
        self._set_generate_loading(False)
        self.page.update()

    def _build_bing_loading_indicator(self):
        return ft.Container(
            ft.Column(
                [
                    ft.ProgressRing(width=32, height=32),
                    ft.Text("正在加载 Bing 每日壁纸…"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=32,
        )

    def _build_spotlight_loading_indicator(self):
        return ft.Container(
            ft.Column(
                [
                    ft.ProgressRing(width=32, height=32),
                    ft.Text("正在加载 Windows 聚焦壁纸…"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=32,
        )

    def _build_wallpaper_source_tab(self):
        self._ws_fetch_button = ft.FilledButton(
            "获取壁纸",
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda _: self._ws_fetch_active_category(force=True),
        )
        self._ws_reload_button = ft.OutlinedButton(
            "刷新源列表",
            icon=ft.Icons.SYNC,
            on_click=lambda _: self._ws_reload_sources(),
        )
        manage_button = ft.TextButton(
            "在设置中管理",
            icon=ft.Icons.SETTINGS,
            on_click=lambda _: self._ws_open_wallpaper_source_settings(),
        )

        header_actions = ft.Row(
            controls=[
                self._ws_fetch_button,
                self._ws_reload_button,
                manage_button,
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._ws_source_info_container = ft.Container(visible=False)
        self._ws_source_tabs = ft.Tabs(
            tabs=[],
            scrollable=True,
            animation_duration=150,
            on_change=self._ws_on_source_tab_change,
        )
        self._ws_source_tabs_container = ft.Container(content=self._ws_source_tabs)

        self._ws_primary_container = ft.Container(visible=False)
        self._ws_secondary_container = ft.Container(visible=False)
        self._ws_tertiary_container = ft.Container(visible=False)
        self._ws_leaf_container = ft.Container(visible=False)
        self._ws_param_container = ft.Container(visible=False)

        self._ws_search_field = ft.TextField(
            label="搜索分类或壁纸",
            hint_text="输入关键字以筛选分类或壁纸",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            expand=True,
            on_change=self._ws_on_search_change,
        )

        self._ws_loading_indicator = ft.ProgressRing(
            width=18,
            height=18,
            stroke_width=2,
            visible=False,
        )
        self._ws_status_text = ft.Text("请选择分类", size=12, color=ft.Colors.GREY)

        status_row = ft.Row(
            [
                ft.Row(
                    [self._ws_loading_indicator, self._ws_status_text],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self._ws_result_list = ft.ListView(
            expand=True,
            spacing=12,
            auto_scroll=False,
        )

        content_column = ft.Column(
            controls=[
                header_actions,
                self._ws_search_field,
                self._ws_source_tabs_container,
                self._ws_primary_container,
                self._ws_secondary_container,
                self._ws_tertiary_container,
                self._ws_leaf_container,
                self._ws_param_container,
                status_row,
                ft.Container(content=self._ws_result_list, expand=True),
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO
        )

        container = ft.Container(
            content=content_column,
            padding=12,
            expand=True,
        )

        self._ws_recompute_ui(preserve_selection=True)
        self._ws_update_fetch_button_state()
        return container

    def _ws_reload_sources(self) -> None:
        self._wallpaper_source_manager.reload()
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        self._ws_recompute_ui(preserve_selection=False)

    def _ws_recompute_ui(self, preserve_selection: bool = True) -> None:
        if self._ws_source_tabs is None or self._ws_source_tabs_container is None:
            return

        records = self._wallpaper_source_manager.enabled_records()

        if self._ws_search_field is not None:
            self._ws_search_field.disabled = not bool(records)
            if self._ws_search_field.page is not None:
                self._ws_search_field.update()

        self._ws_hierarchy = self._ws_build_hierarchy(records)
        available_ids = [
            record.identifier for record in records if record.identifier in self._ws_hierarchy
        ]

        has_records = bool(records)
        if not available_ids:
            self._ws_active_source_id = None
            self._ws_active_primary_key = None
            self._ws_active_secondary_key = None
            self._ws_active_tertiary_key = None
            self._ws_active_leaf_index = 0
            self._ws_active_category_id = None
            if self._ws_source_info_container is not None:
                self._ws_source_info_container.content = ft.Container()
                self._ws_source_info_container.visible = False
                if self._ws_source_info_container.page is not None:
                    self._ws_source_info_container.update()
            self._ws_param_controls = []
            if self._ws_param_container is not None:
                self._ws_param_container.content = ft.Container()
                if self._ws_param_container.page is not None:
                    self._ws_param_container.update()
            empty_title = (
                "未找到匹配的壁纸源或分类"
                if has_records
                else "尚未启用壁纸源"
            )
            empty_hint = (
                "请尝试调整搜索条件或启用更多分类。"
                if has_records
                else "请刷新或前往设置 → 内容 导入/启用壁纸源。"
            )
            actions = [
                ft.TextButton(
                    "在设置中管理" if has_records else "前往设置管理壁纸源",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _: self._ws_open_wallpaper_source_settings(),
                )
            ]
            placeholder = ft.Column(
                [
                    ft.Icon(
                        ft.Icons.FILTER_ALT_OFF if has_records else ft.Icons.LIBRARY_ADD,
                        size=48,
                        color=ft.Colors.OUTLINE,
                    ),
                    ft.Text(empty_title, size=15, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        empty_hint,
                        size=12,
                        color=ft.Colors.GREY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    *actions,
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            )
            self._ws_source_tabs.tabs = []
            self._ws_source_tabs.selected_index = 0
            self._ws_source_tabs_container.content = ft.Container(
                content=placeholder,
                alignment=ft.alignment.center,
                padding=16,
                bgcolor=self._bgcolor_surface_low,
                border_radius=8,
            )
            self._ws_source_tabs_container.visible = True
            if self._ws_source_tabs.page is not None:
                self._ws_source_tabs.update()
            if self._ws_source_tabs_container.page is not None:
                self._ws_source_tabs_container.update()
            for container in (
                self._ws_primary_container,
                self._ws_secondary_container,
                self._ws_tertiary_container,
                self._ws_leaf_container,
            ):
                container.content = None
                container.visible = False
                if container.page is not None:
                    container.update()
            status_message = (
                "未找到匹配的分类，请调整筛选条件。"
                if has_records
                else "尚未启用壁纸源，请先导入。"
            )
            self._ws_clear_results(status_message)
            self._ws_param_container.content = None
            self._ws_param_container.visible = False
            if self._ws_param_container.page is not None:
                self._ws_param_container.update()
            self._ws_update_fetch_button_state()
            return

        if not preserve_selection or self._ws_active_source_id not in available_ids:
            self._ws_active_source_id = available_ids[0]

        self._ws_update_source_tabs(records, preserve_selection=preserve_selection)
        active_record = self._ws_hierarchy.get(self._ws_active_source_id, {}).get("record")
        self._ws_update_source_info(active_record)
        self._ws_update_primary_tabs(
            self._ws_active_source_id,
            preserve_selection=preserve_selection,
        )
        self._ws_update_fetch_button_state()

    def _ws_build_hierarchy(
        self, records: list[WallpaperSourceRecord]
    ) -> dict[str, Any]:
        hierarchy: dict[str, Any] = {}
        term = (self._ws_search_text or "").strip().lower()
        for record in records:
            refs = self._wallpaper_source_manager.category_refs(record.identifier)
            primary_map: dict[str, dict[str, Any]] = {}
            primary_list: list[dict[str, Any]] = []
            for ref in refs:
                if term and not any(term in token for token in ref.search_tokens):
                    continue
                category = ref.category
                primary_label = category.category or ref.source_name or ref.label
                if not primary_label:
                    primary_label = record.spec.name
                primary_key = f"{record.identifier}:{primary_label}"
                primary_entry = primary_map.get(primary_key)
                if primary_entry is None:
                    primary_entry = {
                        "key": primary_key,
                        "label": primary_label,
                        "secondary_list": [],
                        "secondary_map": {},
                    }
                    primary_map[primary_key] = primary_entry
                    primary_list.append(primary_entry)

                secondary_key = category.subcategory or _WS_DEFAULT_KEY
                secondary_label = category.subcategory or "全部"
                secondary_map = primary_entry["secondary_map"]
                secondary_entry = secondary_map.get(secondary_key)
                if secondary_entry is None:
                    secondary_entry = {
                        "key": secondary_key,
                        "label": secondary_label if secondary_key != _WS_DEFAULT_KEY else "全部",
                        "tertiary_list": [],
                        "tertiary_map": {},
                    }
                    secondary_map[secondary_key] = secondary_entry
                    primary_entry["secondary_list"].append(secondary_entry)

                tertiary_key = category.subsubcategory or _WS_DEFAULT_KEY
                tertiary_label = category.subsubcategory or (
                    category.subcategory or ref.label
                )
                tertiary_map = secondary_entry["tertiary_map"]
                tertiary_entry = tertiary_map.get(tertiary_key)
                if tertiary_entry is None:
                    label = tertiary_label if tertiary_key != _WS_DEFAULT_KEY else (
                        category.subcategory or ref.label
                    )
                    tertiary_entry = {
                        "key": tertiary_key,
                        "label": label,
                        "refs": [],
                    }
                    tertiary_map[tertiary_key] = tertiary_entry
                    secondary_entry["tertiary_list"].append(tertiary_entry)
                tertiary_entry["refs"].append(ref)

            if primary_list:
                for entry in primary_list:
                    entry.pop("secondary_map", None)
                    for secondary_entry in entry["secondary_list"]:
                        secondary_entry.pop("tertiary_map", None)
                hierarchy[record.identifier] = {
                    "record": record,
                    "primary_list": primary_list,
                }
        return hierarchy

    def _ws_update_source_tabs(
        self,
        records: list[WallpaperSourceRecord],
        *,
        preserve_selection: bool,
    ) -> None:
        if self._ws_source_tabs is None or self._ws_source_tabs_container is None:
            return
        available_records = [
            record for record in records if record.identifier in self._ws_hierarchy
        ]
        keys = [record.identifier for record in available_records]
        if not available_records:
            return
        self._ws_updating_ui = True
        self._ws_source_tabs.tabs = [
            ft.Tab(
                text=f"{record.spec.name} ({len(record.spec.categories)})"
            )
            for record in available_records
        ]
        if not preserve_selection or self._ws_active_source_id not in keys:
            self._ws_active_source_id = keys[0]
        selected_index = keys.index(self._ws_active_source_id)
        self._ws_source_tabs.selected_index = selected_index
        self._ws_source_tabs.data = {"keys": keys}
        self._ws_source_tabs_container.content = self._ws_source_tabs
        self._ws_source_tabs_container.visible = True
        self._ws_updating_ui = False
        if self._ws_source_tabs.page is not None:
            self._ws_source_tabs.update()
        if self._ws_source_tabs_container.page is not None:
            self._ws_source_tabs_container.update()

    def _ws_update_source_info(self, record: WallpaperSourceRecord | None) -> None:
        if self._ws_source_info_container is None:
            return
        if record is None:
            self._ws_source_info_container.content = ft.Container()
            self._ws_source_info_container.visible = False
            if self._ws_source_info_container.page is not None:
                self._ws_source_info_container.update()
            return
        spec = record.spec
        origin_label = "内置" if record.origin == "builtin" else "用户导入"
        detail_preview = spec.details or spec.description or spec.name
        summary = ft.Text(
            f"{origin_label} · 版本 {spec.version} · {len(spec.apis)} 个接口 · {len(spec.categories)} 个分类",
            size=12,
            color=ft.Colors.GREY,
        )
        info_column = ft.Column(
            [
                ft.Text(spec.name, size=18, weight=ft.FontWeight.BOLD),
                summary,
                ft.Text(
                    detail_preview,
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    selectable=True,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.TextButton(
                    "显示详情",
                    icon=ft.Icons.INFO,
                    on_click=lambda _: self._ws_open_source_details(record),
                ),
            ],
            spacing=4,
        )
        self._ws_source_info_container.content = ft.Row(
            [
                ft.Container(
                    content=self._ws_build_logo_control(record, size=56),
                    width=64,
                    height=64,
                    alignment=ft.alignment.center,
                ),
                info_column,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._ws_source_info_container.visible = True
        if self._ws_source_info_container.page is not None:
            self._ws_source_info_container.update()

    def _ws_update_primary_tabs(self, source_id: str | None, *, preserve_selection: bool) -> None:
        if not source_id or source_id not in self._ws_hierarchy:
            for container in (
                self._ws_primary_container,
                self._ws_secondary_container,
                self._ws_tertiary_container,
                self._ws_leaf_container,
            ):
                container.content = None
                container.visible = False
                if container.page is not None:
                    container.update()
            self._ws_active_primary_key = None
            self._ws_active_secondary_key = None
            self._ws_active_tertiary_key = None
            self._ws_active_leaf_index = 0
            self._ws_active_category_id = None
            self._ws_clear_results("该壁纸源没有可用的分类。")
            return
        primary_list = self._ws_hierarchy[source_id].get("primary_list", [])
        if not primary_list:
            for container in (
                self._ws_primary_container,
                self._ws_secondary_container,
                self._ws_tertiary_container,
                self._ws_leaf_container,
            ):
                container.content = None
                container.visible = False
                if container.page is not None:
                    container.update()
            self._ws_active_primary_key = None
            self._ws_active_secondary_key = None
            self._ws_active_tertiary_key = None
            self._ws_active_leaf_index = 0
            self._ws_active_category_id = None
            self._ws_clear_results("该壁纸源没有可用的分类。")
            return
        show_tabs = len(primary_list) > 1
        if show_tabs:
            if self._ws_primary_tabs is None:
                self._ws_primary_tabs = ft.Tabs(
                    tabs=[],
                    scrollable=True,
                    animation_duration=150,
                    on_change=self._ws_on_primary_tab_change,
                )
            keys = [entry["key"] for entry in primary_list]
            self._ws_updating_ui = True
            self._ws_primary_tabs.tabs = [
                ft.Tab(text=entry["label"]) for entry in primary_list
            ]
            if not preserve_selection or self._ws_active_primary_key not in keys:
                self._ws_active_primary_key = keys[0]
            self._ws_primary_tabs.selected_index = keys.index(self._ws_active_primary_key)
            self._ws_primary_tabs.data = {
                "source_id": source_id,
                "keys": keys,
            }
            self._ws_primary_container.content = self._ws_primary_tabs
            self._ws_primary_container.visible = True
            self._ws_updating_ui = False
            if self._ws_primary_tabs.page is not None:
                self._ws_primary_tabs.update()
            if self._ws_primary_container.page is not None:
                self._ws_primary_container.update()
        else:
            self._ws_primary_container.content = None
            self._ws_primary_container.visible = False
            if self._ws_primary_container.page is not None:
                self._ws_primary_container.update()
            self._ws_active_primary_key = primary_list[0]["key"]

        current_primary = next(
            (entry for entry in primary_list if entry["key"] == self._ws_active_primary_key),
            primary_list[0],
        )
        self._ws_update_secondary_tabs(
            source_id,
            current_primary,
            preserve_selection=preserve_selection,
        )

    def _ws_update_secondary_tabs(
        self,
        source_id: str | None,
        primary_entry: dict[str, Any] | None,
        *,
        preserve_selection: bool,
    ) -> None:
        if primary_entry is None:
            self._ws_secondary_container.content = None
            self._ws_secondary_container.visible = False
            if self._ws_secondary_container.page is not None:
                self._ws_secondary_container.update()
            self._ws_active_secondary_key = None
            self._ws_update_tertiary_tabs(None, preserve_selection=preserve_selection)
            return
        secondary_list = [
            entry
            for entry in primary_entry.get("secondary_list", [])
            if any(t["refs"] for t in entry.get("tertiary_list", []))
        ]
        if not secondary_list:
            self._ws_secondary_container.content = None
            self._ws_secondary_container.visible = False
            if self._ws_secondary_container.page is not None:
                self._ws_secondary_container.update()
            self._ws_active_secondary_key = None
            self._ws_update_tertiary_tabs(None, preserve_selection=preserve_selection)
            return
        show_tabs = len(secondary_list) > 1 or secondary_list[0]["key"] != _WS_DEFAULT_KEY
        if show_tabs:
            if self._ws_secondary_tabs is None:
                self._ws_secondary_tabs = ft.Tabs(
                    tabs=[],
                    scrollable=True,
                    animation_duration=150,
                    on_change=self._ws_on_secondary_tab_change,
                )
            keys = [entry["key"] for entry in secondary_list]
            self._ws_updating_ui = True
            self._ws_secondary_tabs.tabs = [
                ft.Tab(text=entry["label"]) for entry in secondary_list
            ]
            if not preserve_selection or self._ws_active_secondary_key not in keys:
                self._ws_active_secondary_key = keys[0]
            self._ws_secondary_tabs.selected_index = keys.index(self._ws_active_secondary_key)
            self._ws_secondary_tabs.data = {
                "source_id": source_id,
                "primary_key": primary_entry["key"],
                "keys": keys,
            }
            self._ws_secondary_container.content = self._ws_secondary_tabs
            self._ws_secondary_container.visible = True
            self._ws_updating_ui = False
            if self._ws_secondary_tabs.page is not None:
                self._ws_secondary_tabs.update()
            if self._ws_secondary_container.page is not None:
                self._ws_secondary_container.update()
        else:
            self._ws_secondary_container.content = None
            self._ws_secondary_container.visible = False
            if self._ws_secondary_container.page is not None:
                self._ws_secondary_container.update()
            self._ws_active_secondary_key = secondary_list[0]["key"]

        current_secondary = next(
            (entry for entry in secondary_list if entry["key"] == self._ws_active_secondary_key),
            secondary_list[0],
        )
        self._ws_update_tertiary_tabs(
            current_secondary,
            preserve_selection=preserve_selection,
        )

    def _ws_update_tertiary_tabs(
        self,
        secondary_entry: dict[str, Any] | None,
        *,
        preserve_selection: bool,
    ) -> None:
        if secondary_entry is None:
            self._ws_tertiary_container.content = None
            self._ws_tertiary_container.visible = False
            if self._ws_tertiary_container.page is not None:
                self._ws_tertiary_container.update()
            self._ws_active_tertiary_key = None
            self._ws_update_leaf_tabs([], preserve_selection=preserve_selection)
            return
        tertiary_list = [
            entry for entry in secondary_entry.get("tertiary_list", []) if entry.get("refs")
        ]
        if not tertiary_list:
            self._ws_tertiary_container.content = None
            self._ws_tertiary_container.visible = False
            if self._ws_tertiary_container.page is not None:
                self._ws_tertiary_container.update()
            self._ws_active_tertiary_key = None
            self._ws_update_leaf_tabs([], preserve_selection=preserve_selection)
            return
        show_tabs = len(tertiary_list) > 1 or tertiary_list[0]["key"] != _WS_DEFAULT_KEY
        if show_tabs:
            if self._ws_tertiary_tabs is None:
                self._ws_tertiary_tabs = ft.Tabs(
                    tabs=[],
                    scrollable=True,
                    animation_duration=150,
                    on_change=self._ws_on_tertiary_tab_change,
                )
            keys = [entry["key"] for entry in tertiary_list]
            self._ws_updating_ui = True
            self._ws_tertiary_tabs.tabs = [
                ft.Tab(text=entry["label"]) for entry in tertiary_list
            ]
            if not preserve_selection or self._ws_active_tertiary_key not in keys:
                self._ws_active_tertiary_key = keys[0]
            self._ws_tertiary_tabs.selected_index = keys.index(self._ws_active_tertiary_key)
            self._ws_tertiary_tabs.data = {
                "source_id": self._ws_active_source_id,
                "primary_key": self._ws_active_primary_key,
                "secondary_key": secondary_entry["key"],
                "keys": keys,
            }
            self._ws_tertiary_container.content = self._ws_tertiary_tabs
            self._ws_tertiary_container.visible = True
            self._ws_updating_ui = False
            if self._ws_tertiary_tabs.page is not None:
                self._ws_tertiary_tabs.update()
            if self._ws_tertiary_container.page is not None:
                self._ws_tertiary_container.update()
        else:
            self._ws_tertiary_container.content = None
            self._ws_tertiary_container.visible = False
            if self._ws_tertiary_container.page is not None:
                self._ws_tertiary_container.update()
            self._ws_active_tertiary_key = tertiary_list[0]["key"]

        current_tertiary = next(
            (entry for entry in tertiary_list if entry["key"] == self._ws_active_tertiary_key),
            tertiary_list[0],
        )
        self._ws_update_leaf_tabs(
            current_tertiary["refs"],
            preserve_selection=preserve_selection,
        )

    def _ws_update_leaf_tabs(
        self,
        refs: list[WallpaperCategoryRef],
        *,
        preserve_selection: bool,
    ) -> None:
        if not refs:
            self._ws_leaf_container.content = None
            self._ws_leaf_container.visible = False
            if self._ws_leaf_container.page is not None:
                self._ws_leaf_container.update()
            self._ws_active_leaf_index = 0
            self._ws_active_category_id = None
            self._ws_clear_results("该分类暂无可用壁纸。")
            self._ws_update_param_controls(None)
            self._ws_update_fetch_button_state()
            return
        if self._ws_leaf_tabs is None:
            self._ws_leaf_tabs = ft.Tabs(
                tabs=[],
                scrollable=True,
                animation_duration=150,
                on_change=self._ws_on_leaf_tab_change,
            )
        self._ws_updating_ui = True
        self._ws_leaf_tabs.tabs = [ft.Tab(text=ref.label) for ref in refs]
        max_index = len(refs) - 1
        if not preserve_selection or self._ws_active_leaf_index > max_index:
            self._ws_active_leaf_index = 0
        self._ws_leaf_tabs.selected_index = self._ws_active_leaf_index
        self._ws_leaf_tabs.data = {"refs": refs}
        self._ws_leaf_container.content = self._ws_leaf_tabs
        self._ws_leaf_container.visible = True
        self._ws_updating_ui = False
        if self._ws_leaf_tabs.page is not None:
            self._ws_leaf_tabs.update()
        if self._ws_leaf_container.page is not None:
            self._ws_leaf_container.update()
        self._ws_select_leaf(refs[self._ws_active_leaf_index], force_refresh=False)
        self._ws_update_fetch_button_state()

    def _ws_update_fetch_button_state(self) -> None:
        has_category = bool(self._ws_active_category_id)
        disabled = not has_category or self._ws_fetch_in_progress
        if self._ws_fetch_button is not None:
            self._ws_fetch_button.disabled = disabled
            if self._ws_fetch_button.page is not None:
                self._ws_fetch_button.update()
        if self._ws_reload_button is not None:
            self._ws_reload_button.disabled = self._ws_fetch_in_progress
            if self._ws_reload_button.page is not None:
                self._ws_reload_button.update()

    def _ws_clear_results(self, message: str, *, error: bool = False) -> None:
        self._ws_item_index.clear()
        if self._ws_result_list is not None:
            self._ws_result_list.controls.clear()
            if self._ws_result_list.page is not None:
                self._ws_result_list.update()
        self._ws_set_status(message, error=error)

    def _ws_select_leaf(self, ref: WallpaperCategoryRef, *, force_refresh: bool) -> None:
        self._ws_active_category_id = ref.category_id
        self._ws_active_source_id = ref.source_id
        self._ws_active_leaf_index = (
            getattr(self._ws_leaf_tabs, "selected_index", 0)
            if self._ws_leaf_tabs is not None
            else 0
        )
        try:
            self._wallpaper_source_manager.set_active_source(ref.source_id)
        except WallpaperSourceError:
            pass
        if force_refresh:
            self._ws_cached_results.pop(ref.category_id, None)

        self._ws_update_param_controls(ref)

        cached = None if force_refresh else self._ws_cached_results.get(ref.category_id)
        if cached:
            self._ws_display_results(
                ref.category_id,
                cached,
                status_override=f"共 {len(cached)} 项（来自上次获取）。",
            )
        else:
            self._ws_item_index.clear()
            self._ws_set_status("参数已就绪，点击“获取壁纸”开始下载。", error=False)
            if self._ws_result_list is not None:
                self._ws_result_list.controls.clear()
                if self._ws_result_list.page is not None:
                    self._ws_result_list.update()

        self._ws_update_fetch_button_state()

    def _ws_get_active_category_ref(self) -> WallpaperCategoryRef | None:
        category_id = self._ws_active_category_id
        if not category_id:
            return None
        return self._wallpaper_source_manager.find_category(category_id)

    def _ws_update_param_controls(self, ref: WallpaperCategoryRef | None) -> None:
        self._ws_param_controls = []
        if self._ws_param_container is None:
            return
        if ref is None:
            self._ws_param_container.content = None
            self._ws_param_container.visible = False
            if self._ws_param_container.page is not None:
                self._ws_param_container.update()
            return

        record = self._wallpaper_source_manager.get_record(ref.source_id)
        if record is None:
            self._ws_param_container.content = None
            self._ws_param_container.visible = False
            if self._ws_param_container.page is not None:
                self._ws_param_container.update()
            return

        preset_id = ref.category.param_preset_id
        preset = record.spec.parameters.get(preset_id) if preset_id else None
        cached_values = self._ws_param_cache.get(ref.category_id, {})
        controls: list[_WSParameterControl] = []
        if preset is not None:
            for option in preset.options:
                if getattr(option, "hidden", False):
                    continue
                try:
                    control = self._ws_make_parameter_control(
                        option,
                        cached_values.get(option.key),
                    )
                except Exception as exc:
                    logger.error("构建参数控件失败: {error}", error=str(exc))
                    continue
                controls.append(control)

        self._ws_param_controls = controls

        message = (
            "根据需要调整参数，然后点击“获取壁纸”。"
            if controls
            else "此分类无需额外参数，可直接点击“获取壁纸”。"
        )

        body_controls: list[ft.Control] = [
            ft.Text(message, size=12, color=ft.Colors.GREY),
        ]
        if controls:
            body_controls.append(
                ft.Column(
                    [control.display for control in controls],
                    spacing=12,
                    tight=True,
                )
            )

        self._ws_param_container.content = ft.Container(
            content=ft.Column(body_controls, spacing=12, tight=True),
            bgcolor=self._bgcolor_surface_low,
            padding=12,
            border_radius=8,
        )
        self._ws_param_container.visible = True
        if self._ws_param_container.page is not None:
            self._ws_param_container.update()

    def _ws_make_parameter_control(
        self,
        option: Any,
        cached_value: Any,
    ) -> _WSParameterControl:
        label = getattr(option, "label", None) or getattr(option, "key", "参数")
        description = getattr(option, "description", None) or ""
        param_type = str(getattr(option, "type", "text") or "text").lower()
        default_value = cached_value
        if default_value is None:
            default_value = getattr(option, "default", None)

        def _wrap_display(control: ft.Control) -> ft.Control:
            if description:
                return ft.Column(
                    [control, ft.Text(description, size=11, color=ft.Colors.GREY)],
                    spacing=4,
                    tight=True,
                )
            return control

        if param_type == "choice":
            choices = list(getattr(option, "choices", []) or [])
            dropdown_options = [
                ft.DropdownOption(key=str(choice), text=str(choice)) for choice in choices
            ]
            dropdown = ft.Dropdown(
                label=label,
                options=dropdown_options,
                value=None,
                dense=True,
            )

            def setter(value: Any) -> None:
                if value is None and choices:
                    dropdown.value = str(choices[0])
                elif value is None:
                    dropdown.value = None
                else:
                    dropdown.value = str(value)
                if dropdown.page is not None:
                    dropdown.update()

            def getter() -> Any:
                raw = dropdown.value
                return None if raw in (None, "") else raw

            setter(default_value)
            display = _wrap_display(dropdown)
            return _WSParameterControl(option, dropdown, display, getter, setter)

        if param_type == "boolean":
            switch = ft.Switch(label=label, value=bool(default_value))

            def setter(value: Any) -> None:
                switch.value = bool(value)
                if switch.page is not None:
                    switch.update()

            def getter() -> bool:
                return bool(switch.value)

            setter(default_value)
            display = _wrap_display(switch)
            return _WSParameterControl(option, switch, display, getter, setter)

        text_field = ft.TextField(
            label=label,
            value="",
            dense=True,
            hint_text=getattr(option, "placeholder", None) or None,
        )

        def setter(value: Any) -> None:
            if value in (None, ""):
                text_field.value = ""
            else:
                text_field.value = str(value)
            if text_field.page is not None:
                text_field.update()

        def getter() -> Any:
            raw = text_field.value or ""
            return raw.strip()

        setter(default_value)
        display = _wrap_display(text_field)
        return _WSParameterControl(option, text_field, display, getter, setter)

    def _ws_normalize_param_value(self, option: Any, value: Any) -> Any:
        param_type = str(getattr(option, "type", "text") or "text").lower()
        if param_type == "boolean":
            return bool(value)
        if param_type == "choice":
            if value in (None, ""):
                return None
            return str(value)
        text = "" if value is None else str(value)
        text = text.strip()
        return text or None

    def _ws_collect_parameters(self, ref: WallpaperCategoryRef) -> dict[str, Any]:
        record = self._wallpaper_source_manager.get_record(ref.source_id)
        if record is None:
            self._ws_param_cache.pop(ref.category_id, None)
            return {}
        preset_id = ref.category.param_preset_id
        preset = record.spec.parameters.get(preset_id) if preset_id else None
        if preset is None:
            self._ws_param_cache.pop(ref.category_id, None)
            return {}

        option_map = {control.option.key: control for control in self._ws_param_controls}
        values: dict[str, Any] = {}
        cache_entry: dict[str, Any] = {}

        for option in preset.options:
            key = option.key
            if getattr(option, "hidden", False):
                normalized = self._ws_normalize_param_value(option, getattr(option, "default", None))
                cache_entry[key] = normalized
                if normalized is not None:
                    values[key] = normalized
                continue

            control = option_map.get(key)
            if control is not None:
                raw_value = control.getter()
            else:
                raw_value = getattr(option, "default", None)

            normalized = self._ws_normalize_param_value(option, raw_value)
            cache_entry[key] = normalized
            if normalized is not None:
                values[key] = normalized
            elif str(getattr(option, "type", "")).lower() == "boolean":
                values[key] = False

        self._ws_param_cache[ref.category_id] = cache_entry
        return values

    def _ws_on_source_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        keys: list[str] = data.get("keys", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(keys):
            return
        identifier = keys[index]
        if identifier == self._ws_active_source_id:
            return
        self._ws_active_source_id = identifier
        self._ws_active_primary_key = None
        self._ws_active_secondary_key = None
        self._ws_active_tertiary_key = None
        self._ws_active_leaf_index = 0
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        record = self._ws_hierarchy.get(identifier, {}).get("record")
        self._ws_update_source_info(record)
        self._ws_update_primary_tabs(identifier, preserve_selection=False)
        self._ws_update_fetch_button_state()

    def _ws_on_primary_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        keys: list[str] = data.get("keys", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(keys):
            return
        key = keys[index]
        if key == self._ws_active_primary_key:
            return
        self._ws_active_primary_key = key
        self._ws_active_secondary_key = None
        self._ws_active_tertiary_key = None
        self._ws_active_leaf_index = 0
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        hierarchy_entry = self._ws_hierarchy.get(self._ws_active_source_id, {})
        primary_entry = next(
            (entry for entry in hierarchy_entry.get("primary_list", []) if entry["key"] == key),
            None,
        )
        self._ws_update_secondary_tabs(
            self._ws_active_source_id,
            primary_entry,
            preserve_selection=False,
        )
        self._ws_update_fetch_button_state()

    def _ws_on_secondary_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        keys: list[str] = data.get("keys", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(keys):
            return
        key = keys[index]
        if key == self._ws_active_secondary_key:
            return
        self._ws_active_secondary_key = key
        self._ws_active_tertiary_key = None
        self._ws_active_leaf_index = 0
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        source_id = data.get("source_id")
        primary_key = data.get("primary_key")
        primary_entry = None
        if source_id and primary_key:
            primary_entry = next(
                (
                    entry
                    for entry in self._ws_hierarchy.get(source_id, {}).get("primary_list", [])
                    if entry["key"] == primary_key
                ),
                None,
            )
        secondary_entry = None
        if primary_entry is not None:
            secondary_entry = next(
                (entry for entry in primary_entry.get("secondary_list", []) if entry["key"] == key),
                None,
            )
        self._ws_update_tertiary_tabs(secondary_entry, preserve_selection=False)
        self._ws_update_fetch_button_state()

    def _ws_on_tertiary_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        keys: list[str] = data.get("keys", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(keys):
            return
        key = keys[index]
        if key == self._ws_active_tertiary_key:
            return
        self._ws_active_tertiary_key = key
        self._ws_active_leaf_index = 0
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        source_id = data.get("source_id")
        primary_key = data.get("primary_key")
        secondary_key = data.get("secondary_key")
        tertiary_entry = None
        if source_id and primary_key and secondary_key:
            primary_entry = next(
                (
                    entry
                    for entry in self._ws_hierarchy.get(source_id, {}).get("primary_list", [])
                    if entry["key"] == primary_key
                ),
                None,
            )
            if primary_entry is not None:
                secondary_entry = next(
                    (
                        entry
                        for entry in primary_entry.get("secondary_list", [])
                        if entry["key"] == secondary_key
                    ),
                    None,
                )
                if secondary_entry is not None:
                    tertiary_entry = next(
                        (
                            entry
                            for entry in secondary_entry.get("tertiary_list", [])
                            if entry["key"] == key
                        ),
                        None,
                    )
        refs = tertiary_entry.get("refs", []) if tertiary_entry else []
        self._ws_update_leaf_tabs(refs, preserve_selection=False)
        self._ws_update_fetch_button_state()

    def _ws_on_leaf_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        refs: list[WallpaperCategoryRef] = data.get("refs", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(refs):
            return
        self._ws_active_leaf_index = index
        self._ws_select_leaf(refs[index], force_refresh=False)
        self._ws_update_fetch_button_state()

    def _ws_on_search_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        raw = getattr(event.control, "value", "") or ""
        self._ws_search_text = raw.strip().lower()
        self._ws_recompute_ui(preserve_selection=False)

    def _ws_fetch_active_category(self, force: bool = False) -> None:
        if self._ws_fetch_in_progress:
            return
        ref = self._ws_get_active_category_ref()
        if ref is None:
            self._ws_set_status("请选择分类", error=False)
            return
        if force:
            self._ws_cached_results.pop(ref.category_id, None)
        try:
            params = self._ws_collect_parameters(ref)
        except ValueError as exc:
            self._ws_set_status(str(exc), error=True)
            return
        self._ws_fetch_in_progress = True
        self._ws_update_fetch_button_state()
        self._ws_start_loading("正在下载壁纸…")
        self.page.run_task(
            self._ws_fetch_category_items,
            ref.category_id,
            params or None,
        )

    def _ws_start_loading(self, message: str) -> None:
        if self._ws_loading_indicator is not None:
            self._ws_loading_indicator.visible = True
            if self._ws_loading_indicator.page is not None:
                self._ws_loading_indicator.update()
        self._ws_set_status(message, error=False)

    def _ws_stop_loading(self) -> None:
        if self._ws_loading_indicator is None:
            return
        self._ws_loading_indicator.visible = False
        if self._ws_loading_indicator.page is not None:
            self._ws_loading_indicator.update()

    def _ws_set_status(self, message: str, *, error: bool = False) -> None:
        if self._ws_status_text is None:
            return
        self._ws_status_text.value = message
        self._ws_status_text.color = ft.Colors.ERROR if error else ft.Colors.GREY
        if self._ws_status_text.page is not None:
            self._ws_status_text.update()

    async def _ws_fetch_category_items(
        self,
        category_id: str,
        params: dict[str, Any] | None,
    ) -> None:
        try:
            items = await self._wallpaper_source_manager.fetch_category_items(
                category_id,
                params=params,
            )
        except WallpaperSourceFetchError as exc:
            logger.error("加载壁纸源失败: {error}", error=str(exc))
            self._ws_stop_loading()
            self._ws_set_status(f"加载失败：{exc}", error=True)
            return
        else:
            self._ws_cached_results[category_id] = items
            if self._ws_active_category_id == category_id:
                self._ws_display_results(category_id, items)
            else:
                self._ws_stop_loading()
        finally:
            self._ws_fetch_in_progress = False
            self._ws_update_fetch_button_state()

    def _ws_display_results(
        self,
        category_id: str,
        items: list[WallpaperItem],
        *,
        status_override: str | None = None,
    ) -> None:
        if self._ws_result_list is None:
            return
        self._ws_stop_loading()
        if self._ws_active_category_id != category_id:
            return
        self._ws_result_list.controls.clear()
        filtered = self._ws_filtered_items(items)
        if not filtered:
            self._ws_item_index = {}
            self._ws_set_status("未找到符合条件的壁纸。", error=False)
        else:
            self._ws_item_index = {item.id: item for item in filtered}
            status_message = status_override or f"共 {len(filtered)} 项壁纸。"
            self._ws_set_status(status_message, error=False)
            for item in filtered:
                self._ws_result_list.controls.append(self._ws_build_result_card(item))
        if self._ws_result_list.page is not None:
            self._ws_result_list.update()

    def _ws_filtered_items(self, items: list[WallpaperItem]) -> list[WallpaperItem]:
        if not self._ws_search_text:
            return items
        term = self._ws_search_text.lower()
        return [item for item in items if self._ws_item_matches(item, term)]

    def _ws_item_matches(self, item: WallpaperItem, term: str) -> bool:
        fields = [
            item.title or "",
            item.description or "",
            item.category_label or "",
            item.api_name or "",
            item.original_url or "",
            item.footer_text or "",
        ]
        return any(term in field.lower() for field in fields if field)

    def _ws_build_result_card(self, item: WallpaperItem) -> ft.Control:
        record = self._wallpaper_source_manager.get_record(item.source_id)
        header = ft.Row(
            [
                ft.Container(
                    content=self._ws_build_logo_control(record, size=36),
                    width=40,
                    height=40,
                    alignment=ft.alignment.center,
                ),
                ft.Column(
                    [
                        ft.Text(
                            record.spec.name if record else item.source_id,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            selectable=False,
                        ),
                        ft.Text(
                            f"{item.category_label} · {item.api_name}",
                            size=11,
                            color=ft.Colors.PRIMARY,
                            selectable=False,
                        ),
                    ],
                    spacing=2,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        if item.preview_base64:
            preview: ft.Control = ft.Image(
                src_base64=item.preview_base64,
                width=220,
                height=124,
                fit=ft.ImageFit.COVER,
            )
        elif item.local_path and item.local_path.exists():
            preview = ft.Image(
                src=str(item.local_path),
                width=220,
                height=124,
                fit=ft.ImageFit.COVER,
            )
        else:
            preview = ft.Container(
                width=220,
                height=124,
                bgcolor=self._bgcolor_surface_low,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.GREY),
            )

        info_blocks: list[ft.Control] = [header]
        if item.title:
            info_blocks.append(
                ft.Text(
                    item.title,
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    selectable=True,
                )
            )
        if item.description:
            info_blocks.append(
                ft.Text(
                    item.description,
                    size=12,
                    selectable=True,
                )
            )
        if item.copyright:
            info_blocks.append(
                ft.Text(
                    item.copyright,
                    size=11,
                    color=ft.Colors.GREY,
                    selectable=True,
                )
            )
        if item.footer_text:
            info_blocks.append(
                ft.Text(
                    item.footer_text,
                    size=11,
                    color=ft.Colors.GREY,
                    selectable=False,
                )
            )

        actions: list[ft.Control] = [
            ft.FilledTonalButton(
                "预览",
                icon=ft.Icons.VISIBILITY,
                on_click=lambda _, wid=item.id: self._ws_open_preview(wid),
            )
        ]
        if item.original_url:
            actions.append(
                ft.TextButton(
                    "打开原始链接",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _, url=item.original_url: self.page.launch_url(url),
                )
            )

        card_body = ft.Column(
            [
                preview,
                ft.Column(info_blocks, spacing=4),
                ft.Row(actions, spacing=8, wrap=True),
            ],
            spacing=12,
            tight=True,
        )
        return ft.Card(content=ft.Container(card_body, padding=12))

    def _ws_open_preview(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if item is None:
            self._show_snackbar("未找到该壁纸。", error=True)
            return
        self._ws_preview_item = item
        self._ws_preview_item_id = item_id
        self.page.go("/resource/wallpaper-preview")

    def _ws_build_preview_image(self, item: WallpaperItem) -> ft.Control:
        if item.local_path and item.local_path.exists():
            return ft.Image(
                src=str(item.local_path),
                fit=ft.ImageFit.CONTAIN,
                expand=True,
            )
        if item.preview_base64:
            return ft.Image(
                src_base64=item.preview_base64,
                fit=ft.ImageFit.CONTAIN,
                expand=True,
            )
        return ft.Container(
            alignment=ft.alignment.center,
            bgcolor=self._bgcolor_surface_low,
            border_radius=8,
            padding=24,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, size=48, color=ft.Colors.GREY),
                    ft.Text("预览不可用", size=12, color=ft.Colors.GREY),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
        )

    def build_wallpaper_preview_view(self) -> ft.View:
        item = self._ws_preview_item

        if item is None:
            placeholder = ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.IMAGE_SEARCH, size=72, color=ft.Colors.OUTLINE),
                        ft.Text("未找到预览内容，请返回资源页面重新选择。", size=14),
                        ft.FilledButton(
                            "返回资源页面",
                            icon=ft.Icons.ARROW_BACK,
                            on_click=lambda _: self.page.go("/"),
                        ),
                    ],
                    spacing=16,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
            )

            body_controls = [placeholder]
            if SHOW_WATERMARK:
                body_controls = [ft.Stack([placeholder, build_watermark()], expand=True)]

            return ft.View(
                "/resource/wallpaper-preview",
                [
                    ft.AppBar(
                        title=ft.Text("壁纸预览"),
                        leading=ft.IconButton(
                            ft.Icons.ARROW_BACK,
                            tooltip="返回",
                            on_click=lambda _: self.page.go("/"),
                        ),
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    ),
                    *body_controls,
                ],
            )

        record = self._wallpaper_source_manager.get_record(item.source_id)
        source_name = record.spec.name if record else item.source_id

        preview_container = ft.Container(
            content=self._ws_build_preview_image(item),
            bgcolor=ft.Colors.SURFACE,
            border_radius=12,
            padding=16,
            expand=True,
            height=420,
        )

        description_blocks: list[ft.Control] = []
        if item.title:
            description_blocks.append(
                ft.Text(item.title, size=20, weight=ft.FontWeight.BOLD)
            )
        description_blocks.append(
            ft.Text(
                f"来源：{source_name} · 分类：{item.category_label} · 接口：{item.api_name}",
                size=12,
                color=ft.Colors.GREY,
                selectable=True,
            )
        )
        if item.description:
            description_blocks.append(
                ft.Text(item.description, size=13, selectable=True)
            )
        if item.copyright:
            description_blocks.append(
                ft.Text(item.copyright, size=12, color=ft.Colors.GREY, selectable=True)
            )
        if item.local_path:
            description_blocks.append(
                ft.Text(
                    f"文件：{item.local_path}",
                    size=12,
                    color=ft.Colors.GREY,
                    selectable=True,
                )
            )

        actions: list[ft.Control] = [
            ft.FilledButton(
                "设为壁纸",
                icon=ft.Icons.WALLPAPER,
                on_click=lambda _: self.page.run_task(self._ws_set_wallpaper, item.id),
            ),
            ft.FilledTonalButton(
                "复制图片",
                icon=ft.Icons.CONTENT_COPY,
                on_click=lambda _: self.page.run_task(self._ws_copy_image, item.id),
            ),
            ft.FilledTonalButton(
                "加入收藏",
                icon=ft.Icons.BOOKMARK_ADD,
                on_click=lambda _: self._ws_open_favorite_dialog(item.id),
            ),
        ]
        if item.local_path:
            actions.append(
                ft.TextButton(
                    "复制图片文件",
                    icon=ft.Icons.COPY_ALL,
                    on_click=lambda _: self.page.run_task(self._ws_copy_file, item.id),
                )
            )
        if item.original_url:
            actions.append(
                ft.TextButton(
                    "打开原始链接",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _: self.page.launch_url(item.original_url),
                )
            )

        footer_controls: list[ft.Control] = []
        if item.footer_text:
            footer_controls.append(
                ft.Container(
                    bgcolor=self._bgcolor_surface_low,
                    border_radius=8,
                    padding=12,
                    content=ft.Text(item.footer_text, size=12, selectable=True),
                )
            )

        content_column = ft.Column(
            [
                preview_container,
                ft.Row(actions, spacing=12, wrap=True),
                ft.Column(description_blocks, spacing=8, tight=True),
                *footer_controls,
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        preview_body = ft.Container(content_column, expand=True, padding=16)

        if SHOW_WATERMARK:
            body = ft.Stack([preview_body, build_watermark()], expand=True)
        else:
            body = preview_body

        return ft.View(
            "/resource/wallpaper-preview",
            [
                ft.AppBar(
                    title=ft.Text(item.title or "壁纸预览"),
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        tooltip="返回",
                        on_click=lambda _: self.page.go("/"),
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                body,
            ],
        )

    def _ws_build_logo_control(
        self,
        record: WallpaperSourceRecord | None,
        *,
        size: int = 44,
    ) -> ft.Control:
        if record is None:
            return ft.Icon(ft.Icons.COLOR_LENS, size=size * 0.75, color=ft.Colors.PRIMARY)
        logo = (record.spec.logo or "").strip()
        if not logo:
            return ft.Icon(ft.Icons.COLOR_LENS, size=size * 0.75, color=ft.Colors.PRIMARY)
        cached = self._ws_logo_cache.get(record.identifier)
        if cached is None:
            lower = logo.lower()
            if lower.startswith("data:") or lower.startswith("image;base64"):
                _, _, payload = logo.partition(",")
                self._ws_logo_cache[record.identifier] = (payload.strip(), True)
            else:
                self._ws_logo_cache[record.identifier] = (logo, False)
            cached = self._ws_logo_cache[record.identifier]
        payload, is_base64 = cached
        if is_base64 and payload:
            return ft.Image(
                src_base64=payload,
                width=size,
                height=size,
                fit=ft.ImageFit.CONTAIN,
            )
        if payload:
            return ft.Image(
                src=payload,
                width=size,
                height=size,
                fit=ft.ImageFit.CONTAIN,
            )
        return ft.Icon(ft.Icons.COLOR_LENS, size=size * 0.75, color=ft.Colors.PRIMARY)

    def _ws_find_item(self, item_id: str) -> WallpaperItem | None:
        return self._ws_item_index.get(item_id)

    async def _ws_set_wallpaper(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if not item or not item.local_path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        try:
            await asyncio.to_thread(ltwapi.set_wallpaper, str(item.local_path))
        except Exception as exc:
            logger.error("设置壁纸失败: {error}", error=str(exc))
            self._show_snackbar("设置壁纸失败，请查看日志。", error=True)
            return
        self._show_snackbar("已设置为壁纸。")

    async def _ws_copy_image(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if not item or not item.local_path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        success = await asyncio.to_thread(copy_image_to_clipboard, item.local_path)
        if success:
            self._show_snackbar("已复制图片到剪贴板。")
        else:
            self._show_snackbar("复制图片失败。", error=True)

    async def _ws_copy_file(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if not item or not item.local_path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        success = await asyncio.to_thread(
            copy_files_to_clipboard, [str(item.local_path)]
        )
        if success:
            self._show_snackbar("已复制图片文件到剪贴板。")
        else:
            self._show_snackbar("复制文件失败。", error=True)

    def _ws_open_favorite_dialog(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if item is None:
            self._show_snackbar("未找到该壁纸。", error=True)
            return
        payload = self._ws_make_favorite_payload(item)
        if not payload:
            self._show_snackbar("该壁纸暂无可收藏的内容。", error=True)
            return
        self._open_favorite_editor(payload)

    def _ws_make_favorite_payload(self, item: WallpaperItem) -> Dict[str, Any]:
        tags: list[str] = []
        if item.category_label:
            tags.append(item.category_label)
        tags = [tag for tag in dict.fromkeys(tag.strip() for tag in tags if tag)]

        preview_data: str | None = None
        if item.preview_base64:
            mime = item.mime_type or "image/jpeg"
            preview_data = f"data:{mime};base64,{item.preview_base64}"
        elif item.local_path:
            preview_data = str(item.local_path)
        elif item.original_url:
            preview_data = item.original_url

        source_preview = item.original_url or preview_data
        record = self._wallpaper_source_manager.get_record(item.source_id)
        source_title = record.spec.name if record else (item.title or item.source_id)
        source_identifier = f"{item.source_id}:{item.id}"

        favorite_source = FavoriteSource(
            type="wallpaper_source",
            identifier=source_identifier,
            title=source_title,
            url=item.original_url,
            preview_url=source_preview,
            local_path=str(item.local_path) if item.local_path else None,
            extra={
                "api_name": item.api_name,
                "category_label": item.category_label,
                "source_id": item.source_id,
            },
        )

        default_folder = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else "default"
        )

        title = item.title or (item.category_label or source_title)

        payload: Dict[str, Any] = {
            "folder_id": default_folder,
            "title": title,
            "description": item.description or "",
            "tags": tags,
            "source": favorite_source,
            "preview_url": preview_data,
            "local_path": str(item.local_path) if item.local_path else None,
            "extra": {
                "api_name": item.api_name,
                "category_label": item.category_label,
                "source_id": item.source_id,
                "original_url": item.original_url,
            },
        }
        return payload

    def _ws_open_source_details(self, record: WallpaperSourceRecord) -> None:
        spec = record.spec
        detail_text = spec.details or spec.description or spec.name
        info_rows: list[ft.Control] = [
            ft.Text(f"标识符：{spec.identifier}", size=12),
            ft.Text(
                f"来源：{'内置' if record.origin == 'builtin' else '用户导入'}",
                size=12,
            ),
            ft.Text(f"版本：{spec.version}", size=12),
            ft.Text(f"分类数量：{len(spec.categories)}", size=12),
            ft.Text(f"接口数量：{len(spec.apis)}", size=12),
            ft.Text(
                f"刷新间隔：{spec.refresh_interval_seconds} 秒",
                size=12,
            ),
        ]

        content_column = ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Container(
                            content=self._ws_build_logo_control(record, size=64),
                            width=72,
                            height=72,
                            alignment=ft.alignment.center,
                        ),
                        ft.Column(
                            [
                                ft.Text(spec.name, size=20, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    f"版本 {spec.version} · {len(spec.categories)} 个分类 · {len(spec.apis)} 个接口",
                                    size=12,
                                    color=ft.Colors.GREY,
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(),
                *info_rows,
                ft.Divider(),
                ft.Text(detail_text, size=13, selectable=True),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=False,
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("壁纸源详情"),
            content=content_column,
            actions=[
                ft.TextButton("关闭", on_click=lambda _: self._close_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._open_dialog(dialog)

    def _ws_open_wallpaper_source_settings(self) -> None:
        self.page.go("/settings")
        self.select_settings_tab("content")

    def _ws_refresh_settings_list(self) -> None:
        if self._ws_settings_list is None:
            return
        records = self._wallpaper_source_manager.list_records()
        self._ws_settings_list.controls.clear()
        if not records:
            self._ws_settings_list.controls.append(
                ft.Text("尚未导入任何壁纸源。", size=12, color=ft.Colors.GREY)
            )
        else:
            for record in records:
                self._ws_settings_list.controls.append(
                    self._build_ws_settings_card(record)
                )
        if self._ws_settings_summary_text is not None:
            enabled_count = sum(1 for record in records if record.enabled)
            self._ws_settings_summary_text.value = (
                f"当前共导入 {len(records)} 个源，已启用 {enabled_count} 个。"
            )
            if self._ws_settings_summary_text.page is not None:
                self._ws_settings_summary_text.update()
        if self._ws_settings_list.page is not None:
            self._ws_settings_list.update()

    def _build_wallpaper_source_settings_section(self) -> ft.Control:
        self._ensure_ws_file_picker()
        self._ws_settings_list = ft.Column(spacing=12, expand=True)
        self._ws_refresh_settings_list()
        records = self._wallpaper_source_manager.list_records()
        enabled_count = sum(1 for record in records if record.enabled)
        header = ft.Row(
            [
                ft.Text("壁纸源", size=18, weight=ft.FontWeight.BOLD),
                ft.Row(
                    [
                        ft.FilledButton(
                            "导入 TOML",
                            icon=ft.Icons.UPLOAD_FILE,
                            on_click=lambda _: self._open_ws_import_picker(),
                        ),
                        ft.TextButton(
                            "刷新",
                            icon=ft.Icons.REFRESH,
                            on_click=lambda _: self._ws_refresh_settings_list(),
                        ),
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._ws_settings_summary_text = ft.Text(
            f"当前共导入 {len(records)} 个源，已启用 {enabled_count} 个。",
            size=12,
            color=ft.Colors.GREY,
        )
        description_text = ft.Text(
            "支持 Little Tree Wallpaper Source Protocol v2.0",
            size=12,
            color=ft.Colors.GREY,
        )

        return ft.Column(
            [
                header,
                description_text,
                self._ws_settings_summary_text,
                ft.Container(
                    content=self._ws_settings_list,
                    bgcolor=self._bgcolor_surface_low,
                    border_radius=8,
                    padding=12,
                    expand=True,
                ),
            ],
            spacing=12,
        )

    def _build_ws_settings_card(self, record: WallpaperSourceRecord) -> ft.Control:
        spec = record.spec
        subtitle_parts = [
            f"ID: {spec.identifier}",
            f"版本: {spec.version}",
            f"来源: {'内置' if record.origin == 'builtin' else '用户'}",
        ]
        try:
            subtitle_parts.append(f"文件: {record.path}")
        except Exception:
            pass
        subtitle_text = " · ".join(subtitle_parts)
        description = spec.description or "未提供描述。"

        enabled_switch = ft.Switch(
            label="启用",
            value=record.enabled,
            on_change=lambda e, rid=record.identifier: self._ws_toggle_source(
                rid, bool(getattr(e.control, "value", False))
            ),
        )

        remove_button: ft.Control | None = None
        if record.origin == "user":
            remove_button = ft.TextButton(
                "移除",
                icon=ft.Icons.DELETE_OUTLINE,
                on_click=lambda _: self._ws_confirm_remove(record),
            )

        logo = self._ws_build_logo_control(record, size=40)
        info_column = ft.Column(
            [
                ft.Text(spec.name, size=16, weight=ft.FontWeight.BOLD),
                ft.Text(subtitle_text, size=12, color=ft.Colors.GREY, selectable=True),
                ft.Text(description, size=12, selectable=True),
            ],
            spacing=4,
        )

        header_row = ft.Row(
            [
                ft.Container(
                    content=logo,
                    width=44,
                    height=44,
                    alignment=ft.alignment.center,
                ),
                info_column,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        details_button = ft.TextButton(
            "显示详情",
            icon=ft.Icons.INFO,
            on_click=lambda _: self._ws_open_source_details(record),
        )

        action_row_controls: list[ft.Control] = [details_button, enabled_switch]
        if remove_button is not None:
            action_row_controls.append(remove_button)

        card_content = ft.Column(
            [
                header_row,
                ft.Row(action_row_controls, spacing=12, wrap=True),
            ],
            spacing=12,
        )

        return ft.Card(content=ft.Container(card_content, padding=12))

    def _ws_toggle_source(self, identifier: str, enabled: bool) -> None:
        try:
            self._wallpaper_source_manager.set_enabled(identifier, enabled)
        except WallpaperSourceError as exc:
            logger.error("更新壁纸源状态失败: {error}", error=str(exc))
            self._show_snackbar(f"更新失败：{exc}", error=True)
            self._ws_refresh_settings_list()
            return
        self._show_snackbar("已更新壁纸源状态。")
        self._ws_cached_results.clear()
        if not enabled and self._ws_active_source_id == identifier:
            self._ws_active_category_id = None
        self._ws_refresh_settings_list()
        self._ws_recompute_ui(preserve_selection=False)

    def _ws_confirm_remove(self, record: WallpaperSourceRecord) -> None:
        def _confirm(_: ft.ControlEvent | None = None) -> None:
            self._close_dialog()
            self._ws_remove_source(record.identifier)

        def _cancel(_: ft.ControlEvent | None = None) -> None:
            self._close_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("移除壁纸源"),
            content=ft.Text(f"确定要移除 {record.spec.name} 吗？该操作不可撤销。"),
            actions=[
                ft.TextButton("取消", on_click=_cancel),
                ft.FilledButton("移除", icon=ft.Icons.DELETE, on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._open_dialog(dialog)

    def _ws_remove_source(self, identifier: str) -> None:
        try:
            self._wallpaper_source_manager.remove_source(identifier)
        except WallpaperSourceError as exc:
            logger.error("移除壁纸源失败: {error}", error=str(exc))
            self._show_snackbar(f"移除失败：{exc}", error=True)
            return
        self._show_snackbar("已移除壁纸源。")
        if self._ws_active_source_id == identifier:
            self._ws_active_source_id = (
                self._wallpaper_source_manager.active_source_identifier()
            )
            self._ws_active_category_id = None
        self._ws_cached_results.clear()
        self._ws_refresh_settings_list()
        self._ws_recompute_ui(preserve_selection=False)

    def _ensure_ws_file_picker(self) -> None:
        if self._ws_file_picker is None:
            self._ws_file_picker = ft.FilePicker(
                on_result=self._handle_ws_import_result
            )
        if self._ws_file_picker not in self.page.overlay:
            self.page.overlay.append(self._ws_file_picker)
            self.page.update()

    def _open_ws_import_picker(self) -> None:
        self._ensure_ws_file_picker()
        if self._ws_file_picker:
            self._ws_file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["toml"],
            )

    def _handle_ws_import_result(self, event: ft.FilePickerResultEvent) -> None:
        if not event.files:
            return
        file = event.files[0]
        if not file.path:
            self._show_snackbar("未选择有效的文件。", error=True)
            return
        try:
            record = self._wallpaper_source_manager.import_source(Path(file.path))
        except WallpaperSourceImportError as exc:
            logger.error("导入壁纸源失败: {error}", error=str(exc))
            self._show_snackbar(f"导入失败：{exc}", error=True)
            return
        self._show_snackbar(f"已导入壁纸源 {record.spec.name}。")
        self._ws_active_source_id = record.identifier
        self._ws_cached_results.clear()
        self._ws_refresh_settings_list()
        self._ws_recompute_ui(preserve_selection=False)

    def _build_im_page(self):
        info_card = ft.Card(
            content=ft.Container(
                ft.Column(
                    controls=[
                        ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.INFO,
                                            size=25,
                                            color=ft.Colors.PRIMARY,
                                        ),
                                        ft.Text(
                                            spans=[
                                                ft.TextSpan("图片源的搜集和配置文件由"),
                                                ft.TextSpan(
                                                    "SR 思锐团队",
                                                    url="https://github.com/SRInternet-Studio/",
                                                    style=ft.TextStyle(
                                                        decoration=ft.TextDecoration.UNDERLINE,
                                                    ),
                                                ),
                                                ft.TextSpan(
                                                    "提供 ，图片内容责任由接口方承担"
                                                ),
                                            ],
                                        ),
                                    ]
                                ),
                                ft.Row(
                                    [
                                        ft.TextButton(
                                            "查看仓库",
                                            icon=ft.Icons.OPEN_IN_NEW,
                                            url="https://github.com/IntelliMarkets/Wallpaper_API_Index",
                                        )
                                    ]
                                ),
                            ],
                            expand=True,
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                ),
                padding=10,
                expand=True,
            ),
        )

        self._im_loading_indicator = ft.ProgressRing(width=22, height=22, visible=False)
        self._im_status_text = ft.Text("正在初始化 IntelliMarkets 图片源…", size=12)
        self._im_category_dropdown = ft.Dropdown(
            label="分类",
            options=[],
            on_change=self._on_im_category_change,
            expand=True,
        )
        self._im_sources_list = ft.ListView(
            expand=True,
            spacing=12,
            auto_scroll=False,
            controls=[],
        )

        self._im_search_field = ft.TextField(
            label="搜索",
            hint_text="按名称、简介或路径搜索",
            value=self._im_search_text,
            dense=True,
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_im_search_change,
            expand=False,
        )

        refresh_button = ft.TextButton(
            "刷新",
            icon=ft.Icons.REFRESH,
            on_click=lambda _: self.page.run_task(self._load_im_sources, True),
        )
        self._im_refresh_button = refresh_button

        status_row = ft.Row(
            [
                ft.Row(
                    [self._im_loading_indicator, self._im_status_text],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [refresh_button],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # 镜像优先级设置（默认优先 / 镜像优先）
        current_pref = str(
            app_config.get("im.mirror_preference", "default_first") or "default_first"
        )
        self._im_mirror_pref_dropdown = ft.Dropdown(
            label="镜像优先级",
            value=current_pref,
            options=[
                ft.DropdownOption(key="default_first", text="优先默认"),
                ft.DropdownOption(key="mirror_first", text="优先镜像"),
            ],
            on_change=self._on_im_mirror_pref_change,
            width=180,
        )

        filter_row = ft.Row(
            [
                self._im_category_dropdown,
                self._im_mirror_pref_dropdown,
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=12,
        )

        filter_section = ft.Column(
            [filter_row, self._im_search_field], spacing=6, expand=False
        )

        content_column = ft.Column(
            controls=[
                info_card,
                status_row,
                filter_section,
                ft.Container(
                    content=self._im_sources_list,
                    expand=True,
                ),
            ],
            expand=True,
            spacing=12,
        )

        self._refresh_im_ui()

        return ft.Container(
            content_column,
            padding=5,
            expand=True,
        )

    def _on_im_category_change(self, event: ft.ControlEvent) -> None:
        selected = (
            event.control.value if event and getattr(event, "control", None) else None
        )
        if not selected:
            return
        if selected == self._im_selected_category:
            return
        self._im_selected_category = selected
        self._refresh_im_ui()

    def _on_im_mirror_pref_change(self, event: ft.ControlEvent) -> None:
        """Handle mirror preference change and persist setting, then reload sources."""
        try:
            value = (event.control.value or "default_first").strip()
        except Exception:
            value = "default_first"
        if value not in ("default_first", "mirror_first"):
            value = "default_first"
        # persist setting without requiring DEFAULT_CONFIG changes
        app_config.set("im.mirror_preference", value)
        # trigger reloading sources to apply new order
        if self.page:
            self.page.run_task(self._load_im_sources, True)

    def _on_im_search_change(self, event: ft.ControlEvent) -> None:
        raw_value = ""
        if event and getattr(event, "control", None):
            raw_value = str(getattr(event.control, "value", "") or "")
        normalized = raw_value.strip()
        if normalized == self._im_search_text:
            return
        self._im_search_text = normalized
        self._refresh_im_ui()

    def _im_filtered_sources(
        self, search_term: str
    ) -> tuple[list[dict[str, Any]], str | None, int]:
        if not self._im_sources_by_category:
            return [], None, 0

        category = self._im_selected_category
        if category is None:
            category = self._im_all_category_key
            self._im_selected_category = category

        if category == self._im_all_category_key:
            aggregated: list[dict[str, Any]] = []
            for items in self._im_sources_by_category.values():
                aggregated.extend(items)
            base_sources = sorted(
                aggregated,
                key=lambda item: (
                    item.get("friendly_name") or item.get("file_name") or ""
                ).lower(),
            )
            resolved_category = self._im_all_category_key
        else:
            if category not in self._im_sources_by_category:
                category = next(iter(self._im_sources_by_category), None)
                if category is None:
                    return [], None, 0
                self._im_selected_category = category
            base_sources = list(self._im_sources_by_category.get(category, []))
            resolved_category = category

        if not search_term:
            return base_sources, resolved_category, len(base_sources)

        filtered = [
            item for item in base_sources if self._im_source_matches(item, search_term)
        ]
        return filtered, resolved_category, len(base_sources)

    def _im_source_matches(self, source: Dict[str, Any], term: str) -> bool:
        term_lower = term.strip().lower()
        if not term_lower:
            return True

        candidates: list[str] = []
        for key in ("friendly_name", "intro", "file_name", "path", "link", "category"):
            value = source.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

        parameters = source.get("parameters") or []
        if isinstance(parameters, Sequence):
            for param in parameters:
                if not isinstance(param, dict):
                    continue
                for param_key in ("friendly_name", "name"):
                    value = param.get(param_key)
                    if isinstance(value, str) and value:
                        candidates.append(value)

        for candidate in candidates:
            if term_lower in candidate.lower():
                return True

        return False

    # -----------------------------
    # IntelliMarkets 专用镜像策略
    # -----------------------------
    def _im_tarball_candidates(self) -> list[str]:
        logger.info("构建 IntelliMarkets 仓库 tarball 镜像候选列表...")
        owner = self._im_repo_owner
        repo = self._im_repo_name
        branch = self._im_repo_branch
        # Build official and mirror lists separately for easy reordering
        official = [
            f"https://api.github.com/repos/{owner}/{repo}/tarball/{branch}",
            f"https://codeload.github.com/{owner}/{repo}/tar.gz/{branch}",
        ]
        mirror = [
            f"https://api.kkgithub.com/repos/{owner}/{repo}/tarball/{branch}",
            f"https://codeload.kkgithub.com/{owner}/{repo}/tar.gz/{branch}",
        ]
        fallback = [
            # kkgithub HTML archive as a final fallback
            f"https://kkgithub.com/{owner}/{repo}/archive/refs/heads/{branch}.tar.gz",
        ]
        preference = str(
            app_config.get("im.mirror_preference", "default_first") or "default_first"
        )
        logger.info(f"使用镜像优先级设置：{preference}")
        if preference == "mirror_first":
            return [*mirror, *official, *fallback]
        return [*official, *mirror, *fallback]

    def _im_raw_mirrors(self, relative_path: str) -> list[str]:
        # 为 raw 文件构建镜像候选：jsDelivr、Statically
        owner = self._im_repo_owner
        repo = self._im_repo_name
        branch = self._im_repo_branch
        encoded_path = quote(relative_path, safe="/")
        return [
            f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{encoded_path}",
            f"https://cdn.statically.io/gh/{owner}/{repo}/{branch}/{encoded_path}",
        ]

    def _im_request_headers(self, *, binary: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "User-Agent": f"LittleTreeWallpaperNext/{BUILD_VERSION}",
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token.strip()}"
        if not binary:
            headers["Accept"] = "application/vnd.github+json"
        return headers

    async def _fetch_bytes_with_mirrors(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        binary: bool = False,
        timeout: float = 30.0,
        candidates: list[str] | None = None,
    ) -> bytes:
        errors: list[str] = []
        headers = self._im_request_headers(binary=binary)
        trial_list = candidates if candidates else [url]
        for candidate in trial_list:
            try:
                async with session.get(
                    candidate, headers=headers, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    errors.append(f"{candidate} -> HTTP {resp.status}")
            except Exception as exc:  # pragma: no cover - network variability
                errors.append(f"{candidate}: {exc}")
        raise RuntimeError("; ".join(errors))

    def _build_github_raw_url(self, relative_path: str) -> str:
        encoded = quote(relative_path, safe="/")
        return (
            f"https://raw.githubusercontent.com/{self._im_repo_owner}/"
            f"{self._im_repo_name}/{self._im_repo_branch}/{encoded}"
        )

    def _build_github_html_url(self, relative_path: str) -> str:
        encoded = quote(relative_path, safe="/")
        return (
            f"https://github.com/{self._im_repo_owner}/"
            f"{self._im_repo_name}/blob/{self._im_repo_branch}/{encoded}"
        )

    def _build_mirror_url(self, mirror: str, raw_url: str) -> str:
        base = mirror.rstrip("/")
        return f"{base}/{raw_url}"

    def _copy_im_link(self, url: str, label: str) -> None:
        if not url:
            self._show_snackbar("链接不可用", error=True)
            return
        try:
            pyperclip.copy(url)
        except Exception as exc:  # pragma: no cover - clipboard issues
            logger.error(f"复制链接失败: {exc}")
            self._show_snackbar("复制失败，请手动复制", error=True)
            return
        self._show_snackbar(f"{label}已复制")

    def _build_im_source_card(self, source: Dict[str, Any]) -> ft.Control:
        friendly_name = (
            source.get("friendly_name") or source.get("file_name") or "未命名"
        )
        intro = source.get("intro") or ""
        http_method = (source.get("func") or "GET").upper()
        parameter_count = len(source.get("parameters") or [])
        apicore_version = source.get("apicore_version") or "未知"
        html_url = source.get("html_url") or ""

        action_controls: list[ft.Control] = []
        action_controls.append(
            ft.FilledTonalButton(
                "打开",
                icon=ft.Icons.PLAY_ARROW,
                on_click=lambda _=None, item=source: self._open_im_source_dialog(item),
            )
        )
        if html_url:
            action_controls.append(
                ft.TextButton("查看 JSON", icon=ft.Icons.OPEN_IN_NEW, url=html_url)
            )

        meta_row = ft.Row(
            [
                ft.Container(
                    ft.Text(http_method, color=ft.Colors.ON_PRIMARY),
                    bgcolor=ft.Colors.PRIMARY,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=6,
                ),
                ft.Text(f"APICORE {apicore_version}", size=12, color=ft.Colors.GREY),
                ft.Text(f"参数 {parameter_count}", size=12, color=ft.Colors.GREY),
            ],
            spacing=12,
        )

        # 尝试展示来源 logo（来自 source['icon']，通常为链接），若不存在则显示占位图标
        logo_src = source.get("icon")
        if isinstance(logo_src, str) and logo_src.strip():
            # 直接使用远程/本地链接，Flet 会在运行时加载
            logo_control: ft.Control = ft.Container(
                ft.Image(
                    src=logo_src,
                    width=48,
                    height=48,
                    fit=ft.ImageFit.COVER,
                ),
                width=56,
                height=56,
                padding=ft.padding.all(4),
                border_radius=6,
            )
        else:
            logo_control = ft.Container(
                ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, size=28, color=ft.Colors.GREY),
                width=56,
                height=56,
                alignment=ft.alignment.center,
                bgcolor=self._bgcolor_surface_low,
                border_radius=6,
            )

        body_controls: list[ft.Control] = [
            ft.Row(
                [
                    logo_control,
                    ft.Column(
                        [
                            ft.Text(friendly_name, size=16, weight=ft.FontWeight.BOLD),
                            ft.Text(intro, size=12, color=ft.Colors.GREY),
                        ],
                        expand=True,
                        spacing=4,
                    ),
                    ft.Row(
                        action_controls, spacing=8, alignment=ft.MainAxisAlignment.END
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            meta_row,
        ]

        return ft.Card(
            content=ft.Container(
                ft.Column(body_controls, spacing=8),
                padding=12,
            )
        )

    def _im_source_id(self, source: Dict[str, Any]) -> str:
        candidate = (
            source.get("path") or source.get("file_name") or source.get("friendly_name")
        )
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        return f"source-{hashlib.sha1(json.dumps(source, sort_keys=True).encode('utf-8')).hexdigest()}"

    def _open_im_source_dialog(self, source: Dict[str, Any]) -> None:
        self._im_active_source = source
        self._im_last_results = []
        friendly_name = (
            source.get("friendly_name") or source.get("file_name") or "未命名图片源"
        )
        intro = source.get("intro") or ""
        method = (source.get("func") or "GET").upper()
        endpoint = source.get("link") or "未提供"
        parameter_controls = self._build_im_parameter_controls(source)
        if not parameter_controls:
            params_section: ft.Control = ft.Text(
                "此图片源无需额外参数。", size=12, color=ft.Colors.GREY
            )
        else:
            params_section = ft.Column(
                [control.display for control in parameter_controls],
                spacing=12,
                tight=True,
            )

        self._im_param_controls = parameter_controls
        self._im_run_button = ft.FilledButton(
            "执行图片源",
            icon=ft.Icons.PLAY_ARROW,
            on_click=lambda _: self.page.run_task(self._execute_im_source),
        )
        self._im_result_status_text = ft.Text("尚未执行", size=12, color=ft.Colors.GREY)
        self._im_result_spinner = ft.ProgressRing(width=20, height=20, visible=False)
        self._im_result_container = ft.Column(
            spacing=12, expand=True, scroll=ft.ScrollMode.AUTO
        )

        header_section = ft.Column(
            [
                ft.Text(friendly_name, size=18, weight=ft.FontWeight.BOLD),
                ft.Text(intro, size=12, color=ft.Colors.GREY),
                ft.Text(
                    f"接口：{method} {endpoint}",
                    size=12,
                    color=ft.Colors.GREY,
                    selectable=True,
                ),
            ],
            spacing=4,
            tight=True,
        )

        status_row = ft.Row(
            [self._im_result_spinner, self._im_result_status_text],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        results_panel = ft.Container(
            content=self._im_result_container,
            height=320,
            bgcolor=self._bgcolor_surface_low,
            border_radius=ft.border_radius.all(8),
            padding=ft.padding.all(12),
            expand=True,
        )

        content = ft.Container(
            width=720,
            content=ft.Column(
                [
                    header_section,
                    ft.Text("参数", size=14, weight=ft.FontWeight.W_500),
                    params_section,
                    ft.Row(
                        [self._im_run_button],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                    ft.Divider(),
                    ft.Text("执行结果", size=14, weight=ft.FontWeight.W_500),
                    status_row,
                    results_panel,
                ],
                spacing=16,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("IntelliMarkets 图片源"),
            content=content,
            actions=[
                ft.TextButton("关闭", on_click=lambda _: self._close_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._im_source_dialog = dialog
        self._open_dialog(dialog)

    def _set_im_status(self, message: str, *, error: bool = False) -> None:
        if self._im_result_status_text is None:
            return
        self._im_result_status_text.value = message
        self._im_result_status_text.color = ft.Colors.ERROR if error else ft.Colors.GREY
        if self._im_result_status_text.page is not None:
            self._im_result_status_text.update()

    def _build_im_parameter_controls(
        self, source: Dict[str, Any]
    ) -> list[_IMParameterControl]:
        parameters = (source.get("content") or {}).get("parameters") or []
        source_id = self._im_source_id(source)
        cached = self._im_cached_inputs.get(source_id, {})
        controls: list[_IMParameterControl] = []
        for index, param in enumerate(parameters):
            try:
                control = self._make_im_parameter_control(param or {}, cached, index)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"构建参数控件失败: {exc}")
                continue
            controls.append(control)
        return controls

    def _make_im_parameter_control(
        self,
        param: Dict[str, Any],
        cached: Dict[str, Any],
        index: int,
    ) -> _IMParameterControl:
        param_type = str(param.get("type") or "string").lower()
        name = param.get("name")
        key = name or f"__path_segment_{index}"
        friendly = param.get("friendly_name") or name or f"参数 {index + 1}"
        required = bool(param.get("required"))
        split_str = param.get("split_str")
        default_value = self._im_initial_param_value(param, cached.get(key))

        def apply_default(setter: Callable[[Any], None]) -> None:
            try:
                setter(default_value)
            except Exception:
                pass

        if param_type == "enum":
            values = param.get("value") or []
            friendly_values = param.get("friendly_value") or []
            value_map: Dict[str, Any] = {}
            options: list[ft.dropdown.Option] = []
            for idx, raw in enumerate(values):
                label = friendly_values[idx] if idx < len(friendly_values) else str(raw)
                option_key = str(idx)
                options.append(ft.dropdown.Option(text=label, key=option_key))
                value_map[option_key] = raw

            dropdown = ft.Dropdown(
                label=friendly,
                options=options,
                value=None,
                dense=True,
            )

            def getter() -> Any:
                selected = dropdown.value
                if selected is None:
                    if required:
                        raise ValueError("请选择一个选项")
                    return None
                return value_map.get(selected)

            def setter(value: Any) -> None:
                target_key = None
                for option_key, raw in value_map.items():
                    if raw == value or str(raw) == str(value):
                        target_key = option_key
                        break
                dropdown.value = target_key
                if dropdown.page is not None:
                    dropdown.update()

            apply_default(setter)
            return _IMParameterControl(param, dropdown, dropdown, getter, setter, key)

        if param_type in {"boolean", "bool"}:
            switch = ft.Switch(label=friendly, value=bool(default_value or False))

            def getter() -> bool:
                return bool(switch.value)

            def setter(value: Any) -> None:
                switch.value = bool(value)
                if switch.page is not None:
                    switch.update()

            apply_default(setter)
            return _IMParameterControl(param, switch, switch, getter, setter, key)

        if param_type in {"integer", "int"}:
            field = ft.TextField(
                label=friendly,
                value="",
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
            )

            def getter() -> Any:
                raw = (field.value or "").strip()
                if not raw:
                    if required:
                        raise ValueError("请输入数值")
                    return None
                try:
                    value = int(raw)
                except ValueError:
                    raise ValueError("请输入合法的整数") from None
                if param.get("min_value") is not None and value < int(
                    param.get("min_value")
                ):
                    raise ValueError(f"最小值为 {param.get('min_value')}")
                if param.get("max_value") is not None and value > int(
                    param.get("max_value")
                ):
                    raise ValueError(f"最大值为 {param.get('max_value')}")
                return value

            def setter(value: Any) -> None:
                field.value = "" if value is None else str(value)
                if field.page is not None:
                    field.update()

            apply_default(setter)
            return _IMParameterControl(param, field, field, getter, setter, key)

        if param_type in {"number", "float", "double"}:
            field = ft.TextField(
                label=friendly,
                value="",
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
            )

            def getter() -> Any:
                raw = (field.value or "").strip()
                if not raw:
                    if required:
                        raise ValueError("请输入数值")
                    return None
                try:
                    value = float(raw)
                except ValueError:
                    raise ValueError("请输入合法的数值") from None
                if param.get("min_value") is not None and value < float(
                    param.get("min_value")
                ):
                    raise ValueError(f"最小值为 {param.get('min_value')}")
                if param.get("max_value") is not None and value > float(
                    param.get("max_value")
                ):
                    raise ValueError(f"最大值为 {param.get('max_value')}")
                return value

            def setter(value: Any) -> None:
                field.value = "" if value is None else str(value)
                if field.page is not None:
                    field.update()

            apply_default(setter)
            return _IMParameterControl(param, field, field, getter, setter, key)

        if param_type in {"list", "array"}:
            field = ft.TextField(
                label=friendly,
                value="",
                dense=True,
                multiline=True,
                min_lines=1,
                max_lines=4,
                hint_text=f"使用{split_str or '换行'}分隔多个取值",
            )

            def getter() -> Any:
                raw = (field.value or "").strip()
                if not raw:
                    if required:
                        raise ValueError("请输入至少一个值")
                    return []
                values: list[str]
                if split_str:
                    values = [
                        segment.strip()
                        for segment in raw.split(split_str)
                        if segment.strip()
                    ]
                else:
                    tokens = re.split(r"[\s,;]+", raw)
                    values = [segment.strip() for segment in tokens if segment.strip()]
                if required and not values:
                    raise ValueError("请输入至少一个值")
                return values

            def setter(value: Any) -> None:
                if isinstance(value, list):
                    field.value = (split_str or "\n").join(str(item) for item in value)
                elif value is None:
                    field.value = ""
                else:
                    field.value = str(value)
                if field.page is not None:
                    field.update()

            apply_default(setter)
            return _IMParameterControl(param, field, field, getter, setter, key)

        # default: string parameter
        field = ft.TextField(
            label=friendly,
            value="",
            dense=True,
        )

        def getter() -> Any:
            raw = field.value or ""
            raw = raw.strip()
            if not raw and required:
                raise ValueError("请输入参数值")
            return raw or None

        def setter(value: Any) -> None:
            field.value = "" if value in (None, "") else str(value)
            if field.page is not None:
                field.update()

        apply_default(setter)
        return _IMParameterControl(param, field, field, getter, setter, key)

    def _im_initial_param_value(self, param: Dict[str, Any], cached_value: Any) -> Any:
        if cached_value not in (None, ""):
            return cached_value
        param_type = str(param.get("type") or "string").lower()
        value = param.get("value")
        if param_type == "enum":
            if isinstance(value, list) and value:
                return value[0]
            return None
        if param_type in {"list", "array"}:
            if isinstance(value, list):
                return value
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []
        if isinstance(value, (str, int, float, bool)):
            return value
        return None

    def _im_set_control_error(self, control: ft.Control, message: str | None) -> None:
        if hasattr(control, "error_text"):
            try:
                control.error_text = message
            except Exception:
                pass
            if control.page is not None:
                control.update()

    def _im_is_empty_value(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, Sequence) and not value:
            return True
        return False

    def _collect_im_parameters(self) -> list[tuple[Dict[str, Any], Any]]:
        collected: list[tuple[Dict[str, Any], Any]] = []
        errors = False
        current_cache: dict[str, Any] = {}
        for control in self._im_param_controls:
            param = control.config
            required = bool(param.get("required"))
            try:
                value = control.getter()
            except ValueError as exc:
                self._im_set_control_error(control.control, str(exc))
                errors = True
                continue
            self._im_set_control_error(control.control, None)
            if self._im_is_empty_value(value):
                current_cache[control.key] = None
                if required:
                    self._im_set_control_error(control.control, "此参数为必填")
                    errors = True
                continue
            current_cache[control.key] = value
            collected.append((param, value))

        if self._im_active_source is not None:
            source_id = self._im_source_id(self._im_active_source)
            self._im_cached_inputs[source_id] = current_cache

        if errors:
            raise ValueError("invalid parameters")
        return collected

    def _im_param_summary(
        self, param_pairs: list[tuple[Dict[str, Any], Any]]
    ) -> Dict[str, str]:
        summary: Dict[str, str] = {}
        for param, value in param_pairs:
            label = param.get("friendly_name") or param.get("name") or "参数"
            summary[label] = self._im_format_value(value)
        return summary

    def _build_im_request(
        self,
        source: Dict[str, Any],
        param_pairs: list[tuple[Dict[str, Any], Any]],
    ) -> Dict[str, Any]:
        method = (source.get("func") or "GET").upper()
        raw_url = (source.get("link") or "").strip()
        if not raw_url:
            raise ValueError("图片源缺少请求链接")

        base_url, _, query_part = raw_url.partition("?")
        base_url = base_url.rstrip("/")
        query_pairs: list[tuple[str, str]] = []
        if query_part:
            existing_pairs = parse_qsl(query_part, keep_blank_values=True)
            query_pairs.extend(existing_pairs)

        path_segments: list[str] = []
        body_payload: Dict[str, Any] = {}
        headers = (source.get("content") or {}).get("headers") or {}

        for param, value in param_pairs:
            name = param.get("name")
            prepared_query = self._im_prepare_param_value(param, value, as_query=True)
            prepared_body = self._im_prepare_param_value(param, value, as_query=False)
            if name in (None, ""):
                values = (
                    prepared_query
                    if isinstance(prepared_query, list)
                    else [prepared_query]
                )
                for segment in values:
                    if segment is None:
                        continue
                    encoded = quote(str(segment).strip("/"))
                    if encoded:
                        path_segments.append(encoded)
                continue

            if method in {"GET", "DELETE"}:
                if isinstance(prepared_query, list):
                    for item in prepared_query:
                        if item is None:
                            continue
                        query_pairs.append((name, str(item)))
                elif prepared_query is not None:
                    query_pairs.append((name, str(prepared_query)))
            else:
                if prepared_body is not None:
                    body_payload[name] = prepared_body

        final_url = base_url
        if path_segments:
            final_url = "/".join(
                segment for segment in [base_url, *path_segments] if segment
            )
        if query_pairs:
            final_url = f"{final_url}?{urlencode(query_pairs, doseq=True)}"

        return {
            "url": final_url,
            "method": method,
            "body": body_payload if body_payload else None,
            "headers": headers,
            "query_pairs": query_pairs,
        }

    def _im_prepare_param_value(
        self, param: Dict[str, Any], value: Any, *, as_query: bool
    ) -> Any:
        split_str = param.get("split_str")
        if isinstance(value, list):
            if split_str and as_query:
                return split_str.join(str(item) for item in value)
            return [self._im_format_scalar(item, as_query=as_query) for item in value]
        if isinstance(value, tuple):
            return [self._im_format_scalar(item, as_query=as_query) for item in value]
        return self._im_format_scalar(value, as_query=as_query)

    def _im_format_scalar(self, value: Any, *, as_query: bool) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value and as_query else ("false" if as_query else value)
        if isinstance(value, (int, float)):
            return str(value) if as_query else value
        if isinstance(value, (str, bytes)):
            return (
                value.decode("utf-8", errors="ignore")
                if isinstance(value, bytes)
                else value
            )
        if isinstance(value, Sequence):
            return [self._im_format_scalar(item, as_query=as_query) for item in value]
        return json.dumps(value, ensure_ascii=False)

    async def _execute_im_source(self) -> None:
        if self._im_active_source is None:
            self._show_snackbar("请先选择图片源。", error=True)
            return
        if self._im_running:
            return

        self._im_running = True
        if self._im_run_button is not None:
            self._im_run_button.disabled = True
            if self._im_run_button.page is not None:
                self._im_run_button.update()

        if self._im_result_spinner is not None:
            self._im_result_spinner.visible = True
            if self._im_result_spinner.page is not None:
                self._im_result_spinner.update()

        self._set_im_status("正在执行图片源...")

        try:
            param_pairs = self._collect_im_parameters()
        except ValueError:
            self._set_im_status("参数填写不完整，请检查后重试。", error=True)
            self._im_running = False
            if self._im_run_button is not None:
                self._im_run_button.disabled = False
                if self._im_run_button.page is not None:
                    self._im_run_button.update()
            if self._im_result_spinner is not None:
                self._im_result_spinner.visible = False
                if self._im_result_spinner.page is not None:
                    self._im_result_spinner.update()
            return

        try:
            request_info = self._build_im_request(self._im_active_source, param_pairs)
        except Exception as exc:
            logger.error(f"构建请求失败: {exc}")
            self._set_im_status(f"构建请求失败：{exc}", error=True)
            self._im_running = False
            if self._im_run_button is not None:
                self._im_run_button.disabled = False
                if self._im_run_button.page is not None:
                    self._im_run_button.update()
            if self._im_result_spinner is not None:
                self._im_result_spinner.visible = False
                if self._im_result_spinner.page is not None:
                    self._im_result_spinner.update()
            return

        try:
            result_payload = await self._fetch_im_source_result(
                self._im_active_source, request_info, param_pairs
            )
        except Exception as exc:  # pragma: no cover - network errors
            logger.error(f"执行图片源失败: {exc}")
            self._set_im_status(f"执行失败：{exc}", error=True)
            self._emit_im_source_event(
                "resource.im_source.executed",
                {
                    "success": False,
                    "source": self._im_active_source,
                    "request": request_info,
                    "error": str(exc),
                    "timestamp": time.time(),
                },
            )
        else:
            images = result_payload.get("images", [])
            self._im_last_results = images
            count = len(images)
            if count:
                self._set_im_status(f"执行成功，获取到 {count} 张图片。")
            else:
                self._set_im_status("执行成功，但未返回图片。", error=True)
            self._update_im_results_view(result_payload)
            event_payload = {
                "success": True,
                "source": self._im_active_source,
                "request": request_info,
                "images": [image.get("local_path") for image in images],
                "timestamp": time.time(),
                "parameters": self._im_param_summary(param_pairs),
            }
            self._emit_im_source_event("resource.im_source.executed", event_payload)
        finally:
            self._im_running = False
            if self._im_run_button is not None:
                self._im_run_button.disabled = False
                if self._im_run_button.page is not None:
                    self._im_run_button.update()
            if self._im_result_spinner is not None:
                self._im_result_spinner.visible = False
                if self._im_result_spinner.page is not None:
                    self._im_result_spinner.update()

    async def _fetch_im_source_result(
        self,
        source: Dict[str, Any],
        request_info: Dict[str, Any],
        param_pairs: list[tuple[Dict[str, Any], Any]],
    ) -> Dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=90)
        method = request_info["method"]
        url = request_info["url"]
        headers = request_info.get("headers") or {}
        body = request_info.get("body")

        request_kwargs: dict[str, Any] = {"headers": headers}
        if body and method not in {"GET", "HEAD"}:
            request_kwargs["json"] = body

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **request_kwargs) as resp:
                status = resp.status
                response_headers = {k: v for k, v in resp.headers.items()}
                content_type = response_headers.get("Content-Type", "")
                raw_bytes = await resp.read()

                if status >= 400:
                    snippet = raw_bytes.decode("utf-8", errors="ignore")[:200]
                    raise RuntimeError(f"HTTP {status}: {snippet}")

                image_cfg = ((source.get("content") or {}).get("response") or {}).get(
                    "image"
                ) or {}
                response_type = (image_cfg.get("content_type") or "URL").upper()
                content_type_main = (content_type or "").split(";")[0].lower()

                payload: Any | None = None
                binary_payload: bytes | None = None

                if response_type == "BINARY" and not content_type_main.startswith(
                    "application/json"
                ):
                    binary_payload = raw_bytes
                else:
                    text_payload = (
                        raw_bytes.decode("utf-8", errors="ignore") if raw_bytes else ""
                    )
                    if text_payload:
                        try:
                            payload = json.loads(text_payload)
                        except json.JSONDecodeError as exc:
                            if response_type == "BINARY":
                                binary_payload = raw_bytes
                            else:
                                raise RuntimeError(f"解析接口响应失败：{exc}") from exc
                    else:
                        payload = {}

                return await self._process_im_response(
                    source,
                    request_info,
                    param_pairs,
                    payload,
                    binary_payload,
                    response_headers,
                    content_type_main,
                )

    async def _process_im_response(
        self,
        source: Dict[str, Any],
        request_info: Dict[str, Any],
        param_pairs: list[tuple[Dict[str, Any], Any]],
        payload: Any,
        binary_content: bytes | None,
        headers: Dict[str, str],
        content_type: str,
    ) -> Dict[str, Any]:
        response_cfg = (source.get("content") or {}).get("response") or {}
        image_cfg = response_cfg.get("image") or {}
        response_type = (image_cfg.get("content_type") or "URL").upper()
        storage_dir = self._im_storage_dir(source)
        timestamp = time.time()
        param_summary = self._im_param_summary(param_pairs)

        images: list[Dict[str, Any]] = []

        if response_type == "BINARY":
            if not binary_content:
                raise RuntimeError("接口未返回图片数据")
            path = await asyncio.to_thread(
                self._im_save_image_bytes,
                storage_dir,
                binary_content,
                0,
                headers.get("Content-Type"),
            )
            preview = self._im_make_preview_data(path)
            image_entry = {
                "id": uuid.uuid4().hex,
                "local_path": str(path),
                "original_url": None,
                "source_id": self._im_source_id(source),
                "source_path": source.get("path"),
                "source_title": source.get("friendly_name") or source.get("file_name"),
                "parameters": param_summary,
                "executed_at": timestamp,
                "preview_mime": preview[0] if preview else None,
                "preview_base64": preview[1] if preview else None,
                "details": [],
            }
            images.append(image_entry)
        else:
            if payload is None:
                raise RuntimeError("接口未返回 JSON 数据")
            image_values = self._extract_im_path_values(payload, image_cfg.get("path"))
            if not image_values:
                raise RuntimeError("未在响应中找到图片链接")

            for idx, raw in enumerate(image_values):
                if raw in (None, ""):
                    continue
                if isinstance(raw, dict):
                    raw = (
                        raw.get("url")
                        or raw.get("src")
                        or raw.get("image")
                        or raw.get("href")
                    )
                if raw in (None, ""):
                    continue

                local_path: Path | None = None
                original_url: str | None = None

                if image_cfg.get("is_base64"):
                    try:
                        data_bytes = base64.b64decode(str(raw))
                    except Exception as exc:  # pragma: no cover - invalid payload
                        logger.error(f"解码 Base64 图片失败: {exc}")
                        continue
                    local_path = await asyncio.to_thread(
                        self._im_save_image_bytes,
                        storage_dir,
                        data_bytes,
                        idx,
                        headers.get("Content-Type"),
                    )
                else:
                    original_url = str(raw)
                    download_path = await asyncio.to_thread(
                        self._im_download_via_url,
                        original_url,
                        storage_dir,
                    )
                    if not download_path:
                        continue
                    local_path = Path(download_path)

                if local_path is None:
                    continue

                preview = self._im_make_preview_data(local_path)
                image_entry = {
                    "id": uuid.uuid4().hex,
                    "local_path": str(local_path),
                    "original_url": original_url,
                    "source_id": self._im_source_id(source),
                    "source_path": source.get("path"),
                    "source_title": source.get("friendly_name")
                    or source.get("file_name"),
                    "parameters": param_summary,
                    "executed_at": timestamp,
                    "preview_mime": preview[0] if preview else None,
                    "preview_base64": preview[1] if preview else None,
                    "details": [],
                }
                images.append(image_entry)

        per_image_details: list[list[tuple[str, str]]] = [
            [] for _ in range(len(images))
        ]
        global_details: list[tuple[str, str]] = []

        others_sections = response_cfg.get("others") or []
        if payload is not None:
            for section in others_sections:
                entries = section.get("data") or []
                for item in entries:
                    label = (
                        item.get("friendly_name")
                        or section.get("friendly_name")
                        or item.get("name")
                        or "附加信息"
                    )
                    values = self._extract_im_path_values(payload, item.get("path"))
                    if not values:
                        continue
                    mapping = bool(
                        item.get("one-to-one-mapping") or item.get("one_to_one_mapping")
                    )
                    if mapping:
                        for idx, value in enumerate(values):
                            if idx < len(per_image_details):
                                formatted = self._im_format_value(value)
                                if formatted:
                                    per_image_details[idx].append((label, formatted))
                    else:
                        formatted = self._im_format_value(values)
                        if formatted:
                            global_details.append((label, formatted))

        for idx, image in enumerate(images):
            image["details"] = (
                per_image_details[idx] if idx < len(per_image_details) else []
            )
            image["global_details"] = global_details
            image["favorite_identifier"] = f"{image['source_id']}:{image['id']}"

        return {
            "images": images,
            "global_details": global_details,
            "parameters": param_summary,
            "headers": headers,
            "source": source,
            "request": request_info,
            "timestamp": timestamp,
        }

    def _im_storage_dir(self, source: Dict[str, Any]) -> Path:
        slug = self._favorite_filename_slug(
            source.get("friendly_name") or source.get("file_name") or "intellimarkets",
            "intellimarkets",
        )
        directory = (CACHE_DIR / "intellimarkets" / slug).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _im_save_image_bytes(
        self,
        directory: Path,
        data: bytes,
        index: int,
        content_type: str | None,
    ) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        ext = None
        if content_type:
            ext = mimetypes.guess_extension(content_type)
        if not ext:
            ext = ".jpg"
        filename = f"{int(time.time())}-{index}{ext}"
        path = directory / filename
        path.write_bytes(data)
        return path

    def _im_download_via_url(self, url: str, directory: Path) -> str | None:
        try:
            return ltwapi.download_file(url, save_path=str(directory))
        except Exception as exc:  # pragma: no cover - network errors
            logger.error(f"下载图片失败：{exc}")
            return None

    def _im_make_preview_data(self, path: Path) -> tuple[str, str] | None:
        try:
            data = path.read_bytes()
        except Exception as exc:  # pragma: no cover - filesystem errors
            logger.error(f"读取图片失败：{exc}")
            return None
        mime, _ = mimetypes.guess_type(path.name)
        if not mime:
            mime = "image/jpeg"
        encoded = base64.b64encode(data).decode("ascii")
        return mime, encoded

    def _im_parse_path_tokens(self, path: str | None) -> list[tuple[str, Any]]:
        if not path:
            return []
        tokens: list[tuple[str, Any]] = []
        buffer = []
        i = 0
        while i < len(path):
            ch = path[i]
            if ch == ".":
                if buffer:
                    tokens.append(("key", "".join(buffer)))
                    buffer.clear()
                i += 1
                continue
            if ch == "[":
                if buffer:
                    tokens.append(("key", "".join(buffer)))
                    buffer.clear()
                j = path.find("]", i)
                if j == -1:
                    break
                content = path[i + 1 : j]
                if content == "*":
                    tokens.append(("wildcard", None))
                else:
                    try:
                        tokens.append(("index", int(content)))
                    except ValueError:
                        tokens.append(("key", content))
                i = j + 1
                continue
            buffer.append(ch)
            i += 1
        if buffer:
            tokens.append(("key", "".join(buffer)))
        return tokens

    def _extract_im_path_values(self, payload: Any, path: str | None) -> list[Any]:
        tokens = self._im_parse_path_tokens(path)
        if not tokens:
            if payload in (None, ""):
                return []
            if isinstance(payload, list):
                return payload
            return [payload]

        results: list[Any] = []

        def traverse(current: Any, index: int) -> None:
            if index >= len(tokens):
                results.append(current)
                return
            token_type, token_value = tokens[index]
            if token_type == "key":
                if isinstance(current, dict) and token_value in current:
                    traverse(current[token_value], index + 1)
            elif token_type == "index":
                if isinstance(current, Sequence) and not isinstance(
                    current, (str, bytes)
                ):
                    try:
                        traverse(current[token_value], index + 1)
                    except (IndexError, TypeError):
                        return
            elif token_type == "wildcard":
                if isinstance(current, dict):
                    for value in current.values():
                        traverse(value, index + 1)
                elif isinstance(current, Sequence) and not isinstance(
                    current, (str, bytes)
                ):
                    for value in current:
                        traverse(value, index + 1)

        traverse(payload, 0)
        return results

    def _im_format_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, (int, float, str)):
            return str(value)
        if isinstance(value, dict):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            formatted = [
                self._im_format_value(item) for item in value if item not in (None, "")
            ]
            return "、".join(filter(None, formatted))
        return str(value)

    def _update_im_results_view(self, payload: Dict[str, Any]) -> None:
        if self._im_result_container is None:
            return
        self._im_result_container.controls.clear()
        images = payload.get("images") or []
        if not images:
            self._im_result_container.controls.append(
                ft.Text("暂无图片结果。", size=12, color=ft.Colors.GREY)
            )
        else:
            for image in images:
                self._im_result_container.controls.append(
                    self._build_im_result_card(image, payload)
                )
        if self._im_result_container.page is not None:
            self._im_result_container.update()

    def _build_im_result_card(
        self,
        result: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> ft.Control:
        preview_base64 = result.get("preview_base64")
        preview_control: ft.Control
        if preview_base64:
            preview_control = ft.Image(
                src_base64=preview_base64,
                width=220,
                height=124,
                fit=ft.ImageFit.COVER,
            )
        else:
            preview_control = ft.Container(
                width=220,
                height=124,
                bgcolor=self._bgcolor_surface_low,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.GREY),
            )

        local_path = result.get("local_path")
        file_name = Path(local_path).name if local_path else "未知文件"
        original_url = result.get("original_url")

        parameter_texts: list[ft.Control] = []
        parameters = payload.get("parameters") or result.get("parameters") or {}
        if parameters:
            parameter_texts.append(
                ft.Text("请求参数", size=12, weight=ft.FontWeight.W_500)
            )
            for key, value in parameters.items():
                parameter_texts.append(
                    ft.Text(f"{key}：{value}", size=12, selectable=True)
                )

        detail_texts: list[ft.Control] = []
        for label, value in result.get("details") or []:
            detail_texts.append(ft.Text(f"{label}：{value}", size=12, selectable=True))

        for label, value in payload.get("global_details") or []:
            detail_texts.append(ft.Text(f"{label}：{value}", size=12, selectable=True))

        result_id = result.get("id")

        actions: list[ft.Control] = [
            ft.IconButton(
                icon=ft.Icons.WALLPAPER,
                tooltip="设为壁纸",
                on_click=lambda _, rid=result_id: self.page.run_task(
                    self._handle_im_set_wallpaper,
                    rid,
                ),
            ),
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY,
                tooltip="复制图片",
                on_click=lambda _, rid=result_id: self.page.run_task(
                    self._handle_im_copy_image,
                    rid,
                ),
            ),
            ft.IconButton(
                icon=ft.Icons.COPY_ALL,
                tooltip="复制图片文件",
                on_click=lambda _, rid=result_id: self.page.run_task(
                    self._handle_im_copy_file,
                    rid,
                ),
            ),
            ft.IconButton(
                icon=ft.Icons.BOOKMARK_ADD,
                tooltip="加入收藏",
                on_click=lambda _, rid=result_id: self._handle_im_add_favorite(rid),
            ),
        ]

        if original_url:
            actions.append(
                ft.IconButton(
                    icon=ft.Icons.OPEN_IN_NEW,
                    tooltip="打开原始链接",
                    on_click=lambda _, url=original_url: self.page.launch_url(url),
                )
            )

        # 移除“打开所在文件夹”操作，按需保留其他操作

        info_column = ft.Column(
            [
                ft.Text(file_name, size=14, weight=ft.FontWeight.BOLD, selectable=True),
                ft.Text(
                    original_url or "本地文件",
                    size=12,
                    color=ft.Colors.GREY,
                    selectable=True,
                ),
                ft.Column(parameter_texts, spacing=4),
                ft.Column(detail_texts, spacing=4),
                ft.Row(actions, spacing=8, wrap=True),
            ],
            spacing=8,
            expand=True,
        )

        return ft.Card(
            content=ft.Container(
                ft.Row(
                    [preview_control, info_column],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=12,
            )
        )

    def _find_im_result(self, result_id: str | None) -> Dict[str, Any] | None:
        if result_id is None:
            return None
        for item in self._im_last_results:
            if item.get("id") == result_id:
                return item
        return None

    async def _handle_im_set_wallpaper(self, result_id: str | None) -> None:
        result = self._find_im_result(result_id)
        if not result:
            self._show_snackbar("未找到图片。", error=True)
            return
        path = result.get("local_path")
        if not path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        try:
            await asyncio.to_thread(ltwapi.set_wallpaper, path)
        except Exception as exc:  # pragma: no cover - platform specific errors
            logger.error(f"设置壁纸失败：{exc}")
            self._show_snackbar("设置壁纸失败，请查看日志。", error=True)
            self._emit_im_source_event(
                "resource.im_source.action",
                {
                    "action": "set_wallpaper",
                    "success": False,
                    "result": result,
                    "error": str(exc),
                },
            )
            return
        self._show_snackbar("已设置为壁纸。")
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "set_wallpaper",
                "success": True,
                "result": result,
            },
        )

    async def _handle_im_copy_image(self, result_id: str | None) -> None:
        result = self._find_im_result(result_id)
        if not result:
            self._show_snackbar("未找到图片。", error=True)
            return
        path = result.get("local_path")
        if not path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        try:
            await asyncio.to_thread(copy_image_to_clipboard, path)
        except Exception as exc:  # pragma: no cover - platform dependent
            logger.error(f"复制图片失败：{exc}")
            self._show_snackbar("复制图片失败。", error=True)
            self._emit_im_source_event(
                "resource.im_source.action",
                {
                    "action": "copy_image",
                    "success": False,
                    "result": result,
                    "error": str(exc),
                },
            )
            return
        self._show_snackbar("已复制图片到剪贴板。")
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "copy_image",
                "success": True,
                "result": result,
            },
        )

    async def _handle_im_copy_file(self, result_id: str | None) -> None:
        result = self._find_im_result(result_id)
        if not result:
            self._show_snackbar("未找到图片。", error=True)
            return
        path = result.get("local_path")
        if not path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        try:
            await asyncio.to_thread(copy_files_to_clipboard, [path])
        except Exception as exc:  # pragma: no cover - platform dependent
            logger.error(f"复制图片文件失败：{exc}")
            self._show_snackbar("复制图片文件失败。", error=True)
            self._emit_im_source_event(
                "resource.im_source.action",
                {
                    "action": "copy_file",
                    "success": False,
                    "result": result,
                    "error": str(exc),
                },
            )
            return
        self._show_snackbar("已将图片文件复制到剪贴板。")
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "copy_file",
                "success": True,
                "result": result,
            },
        )

    def _handle_im_add_favorite(self, result_id: str | None) -> None:
        result = self._find_im_result(result_id)
        if not result:
            self._show_snackbar("未找到图片。", error=True)
            return
        local_path = result.get("local_path")
        if not local_path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        folder_id = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else None
        )
        favorite_source = FavoriteSource(
            type="intellimarkets",
            identifier=result.get("favorite_identifier") or uuid.uuid4().hex,
            title=result.get("source_title") or "IntelliMarkets",
            url=result.get("original_url"),
            preview_url=result.get("original_url"),
            local_path=str(local_path),
            extra={
                "executed_at": result.get("executed_at"),
                "source_path": result.get("source_path"),
                "parameters": result.get("parameters"),
            },
        )
        item, created = self._favorite_manager.add_or_update_item(
            folder_id=folder_id,
            title=Path(local_path).name,
            source=favorite_source,
            local_path=str(local_path),
            extra=dict(favorite_source.extra or {}),
            description="",
            tags=None,
        )
        self._favorite_manager.update_localization(
            item.id,
            status="completed",
            local_path=str(local_path),
            folder_path=None,
            message=None,
        )
        if created:
            self._show_snackbar("已添加到收藏。")
        else:
            self._show_snackbar("已更新收藏记录。")
        self._refresh_favorite_tabs()
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "favorite",
                "success": True,
                "result": result,
            },
        )

    # 不再提供“打开所在文件夹”的行为

    def _emit_im_source_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        try:
            self._emit_resource_event(event_name, payload)
        except Exception as exc:  # pragma: no cover - event bus errors
            logger.error(f"分发事件 {event_name} 失败：{exc}")

    def _refresh_im_ui(self) -> None:
        search_term = (self._im_search_text or "").strip()
        filtered_sources, resolved_category, base_count = self._im_filtered_sources(
            search_term
        )
        match_count = len(filtered_sources)
        search_active = bool(search_term)
        display_term = (
            search_term.replace("\r", " ").replace("\n", " ")
            if search_active
            else ""
        )
        if search_active and len(display_term) > 24:
            display_term = f"{display_term[:21]}..."

        if self._im_search_field:
            self._im_search_field.value = self._im_search_text
            if self._im_search_field.page is not None:
                self._im_search_field.update()

        if self._im_loading_indicator:
            self._im_loading_indicator.visible = self._im_loading
        if self._im_refresh_button:
            self._im_refresh_button.disabled = self._im_loading

        if self._im_status_text:
            if self._im_error:
                self._im_status_text.value = f"加载失败：{self._im_error}"
                self._im_status_text.color = ft.Colors.ERROR
            elif self._im_loading and not self._im_sources_by_category:
                self._im_status_text.value = "正在加载 IntelliMarkets 图片源…"
                self._im_status_text.color = ft.Colors.GREY
            elif self._im_sources_by_category:
                category_count = len(self._im_sources_by_category)
                summary = (
                    f"共 {category_count} 个分类 / {self._im_total_sources} 个图片源"
                )
                if self._im_last_updated:
                    formatted = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(self._im_last_updated)
                    )
                    summary += f" · 更新于 {formatted}"
                if search_active:
                    summary += f" · 搜索 \"{display_term}\" 匹配 {match_count} 项"
                self._im_status_text.value = summary
                self._im_status_text.color = ft.Colors.GREY
            else:
                self._im_status_text.value = "尚未加载图片源"
                self._im_status_text.color = ft.Colors.GREY

        if self._im_category_dropdown:
            options: list[ft.dropdown.Option] = [
                ft.dropdown.Option(
                    key=self._im_all_category_key, text=self._im_all_category_label
                )
            ]
            options.extend(
                ft.dropdown.Option(key=name, text=name)
                for name in self._im_sources_by_category.keys()
            )
            self._im_category_dropdown.options = options
            if self._im_sources_by_category:
                if resolved_category is None:
                    resolved_category = self._im_all_category_key
                self._im_category_dropdown.value = resolved_category
                self._im_category_dropdown.disabled = False
            else:
                self._im_category_dropdown.value = self._im_all_category_key
                self._im_category_dropdown.disabled = True

        if self._im_sources_list:
            if self._im_loading and not self._im_sources_by_category:
                self._im_sources_list.controls = [
                    ft.Container(
                        ft.Column(
                            [
                                ft.ProgressRing(width=32, height=32),
                                ft.Text("正在拉取图片源列表…"),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=20,
                    )
                ]
            elif self._im_error and not self._im_sources_by_category:
                self._im_sources_list.controls = [
                    ft.Container(
                        ft.Text(self._im_error, color=ft.Colors.ERROR),
                        padding=20,
                    )
                ]
            else:
                if filtered_sources:
                    self._im_sources_list.controls = [
                        self._build_im_source_card(item) for item in filtered_sources
                    ]
                else:
                    if self._im_sources_by_category:
                        if search_active and base_count > 0:
                            message = f"未找到与 \"{display_term}\" 匹配的图片源"
                        else:
                            message = "该分类暂无图片源"
                    else:
                        message = "尚未加载图片源"
                    self._im_sources_list.controls = [
                        ft.Container(ft.Text(message), padding=20)
                    ]

        if self.page:
            self.page.update()

    async def _load_im_sources(self, force: bool = False) -> None:
        if self._im_loading:
            return
        self._im_loading = True
        self._im_error = None
        self._refresh_im_ui()

        # 构建 tarball 候选列表（官方与镜像）
        tarball_candidates = self._im_tarball_candidates()
        logger.info(f"IntelliMarkets 图片源下载候选：{tarball_candidates}")

        timeout = aiohttp.ClientTimeout(total=60)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                tarball_bytes = await self._fetch_bytes_with_mirrors(
                    session,
                    tarball_candidates[0],
                    binary=True,
                    timeout=timeout.total,
                    candidates=tarball_candidates,
                )
            logger.info("成功获取 IntelliMarkets 图片源数据，开始解析内容…")

            categories: dict[str, list[dict[str, Any]]] = {}
            total_sources = 0
            tar_stream = io.BytesIO(tarball_bytes)
            with tarfile.open(fileobj=tar_stream, mode="r:gz") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    if not member.name.lower().endswith(".json"):
                        continue
                    parts = member.name.split("/", 1)
                    if len(parts) < 2:
                        continue
                    relative_path = parts[1]
                    if not relative_path:
                        continue
                    relative_segments = relative_path.split("/")
                    if not relative_segments:
                        continue

                    if len(relative_segments) == 1:
                        category_name = "未分类"
                        file_name = relative_segments[0]
                    else:
                        category_name = relative_segments[0]
                        file_name = relative_segments[-1]

                    if not file_name.lower().endswith(".json"):
                        continue

                    extracted = tar.extractfile(member)
                    if extracted is None:
                        continue
                    raw_bytes = extracted.read()
                    text = raw_bytes.decode("utf-8-sig", errors="ignore")
                    try:
                        config_payload = json.loads(text)
                    except json.JSONDecodeError as exc:
                        logger.error(
                            "解析 IntelliMarkets 图片源失败: {path} -> {error}",
                            path=relative_path,
                            error=str(exc),
                        )
                        continue

                    raw_url = self._build_github_raw_url(relative_path)
                    html_url = self._build_github_html_url(relative_path)
                    # 专用于程序内部的 raw 镜像候选（不展示给用户）
                    raw_mirror_candidates = self._im_raw_mirrors(relative_path)

                    source_info: Dict[str, Any] = {
                        "category": category_name,
                        "path": relative_path,
                        "file_name": file_name,
                        "friendly_name": config_payload.get("friendly_name")
                        or file_name,
                        "intro": config_payload.get("intro") or "",
                        "icon": config_payload.get("icon"),
                        "link": config_payload.get("link"),
                        "func": config_payload.get("func") or "GET",
                        "apicore_version": config_payload.get("APICORE_version"),
                        "parameters": config_payload.get("parameters"),
                        "response": config_payload.get("response"),
                        "raw_url": raw_url,
                        "html_url": html_url,
                        "raw_mirror_candidates": raw_mirror_candidates,
                        "size": member.size,
                        "content": config_payload,
                    }

                    categories.setdefault(category_name, []).append(source_info)
                    total_sources += 1
            logger.info("IntelliMarkets 图片源解析完成，共加载 {count} 个图片源。", count=total_sources)
            for items in categories.values():
                items.sort(
                    key=lambda item: (
                        item.get("friendly_name") or item.get("file_name") or ""
                    ).lower()
                )

            self._im_sources_by_category = categories
            self._im_total_sources = total_sources
            if (
                self._im_selected_category is None
                or (
                    self._im_selected_category != self._im_all_category_key
                    and self._im_selected_category not in categories
                )
            ):
                self._im_selected_category = (
                    self._im_all_category_key if categories else None
                )
            self._im_last_updated = time.time()
        except Exception as exc:  # pragma: no cover - network variability
            logger.error(f"加载 IntelliMarkets 图片源失败: {exc}")
            self._im_error = str(exc)
            self._im_sources_by_category = {}
            self._im_total_sources = 0
        finally:
            self._im_loading = False
            self._refresh_im_ui()

    # ------------------------------------------------------------------
    # favorite helpers
    # ------------------------------------------------------------------
    def _favorite_folders(self) -> List[FavoriteFolder]:
        try:
            return self._favorite_manager.list_folders()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"加载收藏夹失败: {exc}")
            return []

    def _favorite_tab_ids(self, folders: List[FavoriteFolder]) -> List[str]:
        return ["__all__"] + [folder.id for folder in folders]

    def _build_favorite_tabs_list(self, folders: List[FavoriteFolder]) -> List[ft.Tab]:
        self._favorite_item_localize_controls = {}
        self._favorite_item_wallpaper_buttons = {}
        self._favorite_item_export_buttons = {}
        tabs: List[ft.Tab] = [
            ft.Tab(
                text="全部",
                icon=ft.Icons.ALL_INBOX,
                content=self._build_favorite_folder_view("__all__"),
            )
        ]
        for folder in folders:
            icon = ft.Icons.STAR if folder.id == "default" else ft.Icons.FOLDER_SPECIAL
            tabs.append(
                ft.Tab(
                    text=folder.name,
                    icon=icon,
                    content=self._build_favorite_folder_view(folder.id),
                )
            )
        return tabs

    def _favorite_preview_source(self, item: FavoriteItem) -> tuple[str, str] | None:
        for candidate in (
            item.localization.local_path,
            item.local_path,
        ):
            if not candidate:
                continue
            try:
                path = Path(candidate)
                if not path.exists():
                    continue
                resolved = path.resolve()
                try:
                    mtime = resolved.stat().st_mtime
                except Exception:
                    mtime = time.time()
                cached = self._favorite_preview_cache.get(item.id)
                if cached and abs(cached[0] - mtime) < 1e-6:
                    return ("base64", cached[1])
                data = resolved.read_bytes()
                encoded = base64.b64encode(data).decode("ascii")
                if len(self._favorite_preview_cache) >= 32:
                    oldest_key = next(iter(self._favorite_preview_cache))
                    self._favorite_preview_cache.pop(oldest_key, None)
                self._favorite_preview_cache[item.id] = (mtime, encoded)
                return ("base64", encoded)
            except Exception as exc:
                logger.warning("加载本地预览失败: {error}", error=str(exc))
        if item.preview_url:
            return ("url", item.preview_url)
        if item.source.url:
            return ("url", item.source.url)
        return None

    def _favorite_filename_slug(self, raw: str, fallback: str) -> str:
        cleaned = "".join(
            ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_"
            for ch in (raw or "").strip()
        ).strip()
        cleaned = re.sub(r"\s+", "-", cleaned)
        return cleaned or fallback

    def _favorite_default_package_path(self, item: FavoriteItem) -> Path:
        exports_dir = self._favorite_manager.localization_root().parent / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        base_name = self._favorite_filename_slug(item.title or "favorite", item.id[:8])
        candidate = (exports_dir / f"{base_name}.ltwfav").resolve()
        counter = 1
        while candidate.exists():
            candidate = (exports_dir / f"{base_name}-{counter}.ltwfav").resolve()
            counter += 1
        return candidate

    def _favorite_default_asset_path(
        self, item: FavoriteItem, source_path: Path
    ) -> Path:
        exports_dir = self._favorite_manager.localization_root().parent / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        suffix = source_path.suffix or ""
        base_name = self._favorite_filename_slug(item.title or "favorite", item.id[:8])
        candidate = (exports_dir / f"{base_name}{suffix}").resolve()
        counter = 1
        while candidate.exists():
            candidate = (exports_dir / f"{base_name}-{counter}{suffix}").resolve()
            counter += 1
        return candidate

    def _set_item_localizing(self, item_id: str, active: bool) -> None:
        if active:
            self._favorite_localizing_items.add(item_id)
            self._favorite_preview_cache.pop(item_id, None)
        else:
            self._favorite_localizing_items.discard(item_id)
        button: ft.IconButton | None = None
        indicator: ft.Control | None = None
        controls = self._favorite_item_localize_controls.get(item_id)
        if controls:
            button, indicator = controls
        if indicator is not None:
            indicator.visible = active
            if indicator.page is not None:
                indicator.update()
        if button is not None:
            button.visible = not active
            if not active:
                current_item = self._favorite_manager.get_item(item_id)
                has_localized = (
                    current_item is not None
                    and current_item.localization.status == "completed"
                    and current_item.localization.local_path
                    and Path(current_item.localization.local_path).exists()
                )
                button.disabled = has_localized
                button.tooltip = "已完成本地化" if has_localized else "本地化此收藏"
            if button.page is not None:
                button.update()
        wallpaper_button = self._favorite_item_wallpaper_buttons.get(item_id)
        if wallpaper_button is not None:
            wallpaper_button.disabled = active
            if wallpaper_button.page is not None:
                wallpaper_button.update()
        export_button = self._favorite_item_export_buttons.get(item_id)
        if export_button is not None:
            export_button.disabled = active
            if export_button.page is not None:
                export_button.update()

    def _show_localization_progress(self, total: int) -> None:
        self._favorite_batch_total = max(total, 0)
        self._favorite_batch_done = 0
        if self._favorite_localization_spinner is not None:
            self._favorite_localization_spinner.visible = True
        if self._favorite_localization_progress_bar is not None:
            self._favorite_localization_progress_bar.value = 0.0
            self._favorite_localization_progress_bar.visible = True
        if self._favorite_localization_status_text is not None:
            self._favorite_localization_status_text.value = (
                f"正在本地化 0/{total} 项收藏…" if total else "正在本地化…"
            )
        if self._favorite_localization_status_row is not None:
            self._favorite_localization_status_row.visible = True
        for control in (
            self._favorite_localization_status_text,
            self._favorite_localization_progress_bar,
            self._favorite_localization_spinner,
            self._favorite_localization_status_row,
        ):
            if control is not None and control.page is not None:
                control.update()

    def _update_localization_progress(self, increment: int = 1) -> None:
        if self._favorite_batch_total <= 0:
            return
        self._favorite_batch_done = min(
            self._favorite_batch_total,
            self._favorite_batch_done + max(0, increment),
        )
        if self._favorite_localization_progress_bar is not None:
            self._favorite_localization_progress_bar.value = (
                self._favorite_batch_done / self._favorite_batch_total
            )
        if self._favorite_localization_status_text is not None:
            self._favorite_localization_status_text.value = f"已本地化 {self._favorite_batch_done}/{self._favorite_batch_total} 项收藏"
        for control in (
            self._favorite_localization_status_text,
            self._favorite_localization_progress_bar,
        ):
            if control is not None and control.page is not None:
                control.update()

    def _finish_localization_progress(self, success: int, total: int) -> None:
        if self._favorite_localization_spinner is not None:
            self._favorite_localization_spinner.visible = False
        if self._favorite_localization_progress_bar is not None:
            self._favorite_localization_progress_bar.value = 1.0 if total else 0.0
            self._favorite_localization_progress_bar.visible = total > 0
        if self._favorite_localization_status_text is not None:
            self._favorite_localization_status_text.value = (
                f"本地化完成：成功 {success}/{total} 项" if total else "本地化完成"
            )
        for control in (
            self._favorite_localization_status_text,
            self._favorite_localization_progress_bar,
            self._favorite_localization_spinner,
            self._favorite_localization_status_row,
        ):
            if control is not None and control.page is not None:
                control.update()

        async def _hide_row_later() -> None:
            await asyncio.sleep(2)
            if self._favorite_localization_status_row is not None:
                self._favorite_localization_status_row.visible = False
                if self._favorite_localization_status_row.page is not None:
                    self._favorite_localization_status_row.update()

        if total > 0:
            self.page.run_task(_hide_row_later)

    def _build_favorite_folder_view(self, folder_id: str) -> ft.Control:
        items = self._favorite_manager.list_items(
            None if folder_id in (None, "__all__") else folder_id
        )
        if not items:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.INBOX, size=48, color=ft.Colors.OUTLINE),
                        ft.Text("这里还没有收藏，去添加一个吧~"),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                padding=32,
                expand=True,
            )

        list_view = ft.ListView(spacing=12, expand=True)
        for item in items:
            list_view.controls.append(self._build_favorite_card(item))

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        f"共 {len(items)} 项收藏",
                        size=12,
                        color=ft.Colors.GREY,
                    ),
                    list_view,
                ],
                spacing=12,
                expand=True,
            ),
            padding=16,
            expand=True,
        )

    def _build_favorite_card(self, item: FavoriteItem) -> ft.Card:
        preview_src = self._favorite_preview_source(item)
        if preview_src:
            source_type, value = preview_src
            preview_kwargs: dict[str, Any] = {
                "width": 160,
                "height": 90,
                "fit": ft.ImageFit.COVER,
                "border_radius": 8,
            }
            if source_type == "base64":
                preview_control = ft.Image(src_base64=value, **preview_kwargs)
            else:
                preview_control = ft.Image(src=value, **preview_kwargs)
        else:
            preview_control = ft.Container(
                width=160,
                height=90,
                border_radius=8,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.OUTLINE),
            )

        if item.tags:
            tag_controls: List[ft.Control] = [
                ft.Chip(label=ft.Text(tag), bgcolor=ft.Colors.SECONDARY_CONTAINER)
                for tag in item.tags
            ]
        else:
            tag_controls = [ft.Text("未添加标签", size=11, color=ft.Colors.GREY)]

        ai_controls: List[ft.Control] = []
        if item.ai.suggested_tags:
            ai_controls.append(
                ft.Text(
                    f"AI 建议：{', '.join(item.ai.suggested_tags)}",
                    size=11,
                    color=ft.Colors.SECONDARY,
                )
            )
        elif item.ai.status in {"pending", "running"}:
            ai_controls.append(
                ft.Text("AI 正在分析…", size=11, color=ft.Colors.SECONDARY)
            )
        elif item.ai.status == "failed":
            ai_controls.append(ft.Text("AI 分析失败", size=11, color=ft.Colors.ERROR))

        info_column = ft.Column(
            [
                ft.Text(item.title, size=16, weight=ft.FontWeight.BOLD),
                ft.Text(
                    item.description or "暂无描述",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Row(
                    tag_controls,
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                ),
            ],
            spacing=6,
            expand=True,
        )

        if item.source.title or item.source.type:
            info_column.controls.append(
                ft.Text(
                    f"来源：{item.source.title or item.source.type}",
                    size=11,
                    color=ft.Colors.GREY,
                )
            )

        localization = item.localization
        if localization.status == "completed" and localization.local_path:
            info_column.controls.append(
                ft.Text(
                    "已本地化",
                    size=11,
                    color=getattr(ft.Colors, "GREEN_400", ft.Colors.GREEN),
                )
            )
        elif localization.status == "pending":
            info_column.controls.append(
                ft.Text("正在本地化…", size=11, color=ft.Colors.SECONDARY)
            )
        elif localization.status == "failed":
            info_column.controls.append(
                ft.Text(
                    localization.message or "本地化失败",
                    size=11,
                    color=ft.Colors.ERROR,
                )
            )
        else:
            info_column.controls.append(
                ft.Text("未本地化", size=11, color=ft.Colors.GREY)
            )

        if ai_controls:
            info_column.controls.extend(ai_controls)

        is_localized = (
            item.localization.status == "completed"
            and item.localization.local_path
            and Path(item.localization.local_path).exists()
        )

        localize_button = ft.IconButton(
            icon=ft.Icons.DOWNLOAD_FOR_OFFLINE,
            tooltip="本地化此收藏",
            on_click=lambda _, item_id=item.id: self._handle_localize_single_item(
                item_id
            ),
        )
        if is_localized:
            localize_button.disabled = True
            localize_button.tooltip = "已完成本地化"
        localize_indicator = ft.Container(
            content=ft.ProgressRing(width=20, height=20),
            alignment=ft.alignment.center,
            width=40,
            height=40,
        )
        is_localizing = (
            item.id in self._favorite_localizing_items
            or item.localization.status in {"pending"}
        )
        localize_button.visible = not is_localizing
        localize_indicator.visible = is_localizing
        localization_stack = ft.Stack(
            controls=[localize_button, localize_indicator],
            width=40,
            height=40,
        )
        self._favorite_item_localize_controls[item.id] = (
            localize_button,
            localize_indicator,
        )

        set_wallpaper_button = ft.IconButton(
            icon=ft.Icons.WALLPAPER,
            tooltip="设为壁纸",
            on_click=lambda _, item_id=item.id: self._handle_set_favorite_wallpaper(
                item_id
            ),
            disabled=is_localizing,
        )
        export_button = ft.IconButton(
            icon=ft.Icons.UPLOAD_FILE,
            tooltip="导出此收藏",
            on_click=lambda _, item_id=item.id: self._handle_export_single_item(
                item_id
            ),
            disabled=is_localizing,
        )
        self._favorite_item_wallpaper_buttons[item.id] = set_wallpaper_button
        self._favorite_item_export_buttons[item.id] = export_button

        action_buttons: List[ft.Control] = [
            localization_stack,
            set_wallpaper_button,
            export_button,
            ft.IconButton(
                icon=ft.Icons.EDIT,
                tooltip="编辑收藏",
                on_click=lambda _, item_id=item.id: self._edit_favorite(item_id),
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                tooltip="移除收藏",
                on_click=lambda _, item_id=item.id: self._remove_favorite(item_id),
            ),
        ]

        if item.source.url:
            action_buttons.append(
                ft.IconButton(
                    icon=ft.Icons.OPEN_IN_NEW,
                    tooltip="打开来源链接",
                    on_click=lambda _, url=item.source.url: self.page.launch_url(url),
                )
            )

        # 移除“打开本地文件/所在位置”的入口，避免直接跳转到文件夹

        body_row = ft.Row(
            [preview_control, info_column],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        actions_row = ft.Row(
            action_buttons,
            alignment=ft.MainAxisAlignment.END,
            spacing=4,
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [body_row, actions_row],
                    spacing=12,
                ),
                padding=16,
            )
        )

    def _parse_tag_input(self, raw: str) -> List[str]:
        if not raw:
            return []
        normalized = raw.replace("，", ",").replace("、", ",")
        tokens = re.split(r"[\s,;]+", normalized)
        return [token.strip() for token in tokens if token.strip()]

    def _update_favorite_folder_toolbar(self) -> None:
        edit_button = self._favorite_edit_folder_button
        delete_button = self._favorite_delete_folder_button
        current_folder = self._favorite_selected_folder
        manage_enabled = current_folder not in (None, "__all__")
        if edit_button is not None:
            edit_button.disabled = not manage_enabled
            if edit_button.page is not None:
                edit_button.update()
        if delete_button is not None:
            delete_enabled = manage_enabled and current_folder != "default"
            delete_button.disabled = not delete_enabled
            if delete_button.page is not None:
                delete_button.update()

    async def _localize_favorite_item(self, item: FavoriteItem) -> bool:
        if (
            item.localization.status == "completed"
            and item.localization.local_path
            and Path(item.localization.local_path).exists()
        ):
            return True
        if item.local_path and Path(item.local_path).exists():
            destination = await asyncio.to_thread(
                self._favorite_manager.localize_item_from_file,
                item.id,
                item.local_path,
            )
            return destination is not None
        download_url = item.preview_url or item.source.preview_url or item.source.url
        if not download_url:
            logger.warning("收藏缺少可下载地址，跳过本地化: {item}", item=item.id)
            return False
        downloads_dir = (
            self._favorite_manager.localization_root() / "__downloads"
        ).resolve()
        downloads_dir.mkdir(parents=True, exist_ok=True)
        temp_name = f"{item.id}-{uuid.uuid4().hex}"
        downloaded_path = await asyncio.to_thread(
            ltwapi.download_file,
            download_url,
            downloads_dir,
            temp_name,
        )
        if not downloaded_path:
            return False
        destination = await asyncio.to_thread(
            self._favorite_manager.localize_item_from_file,
            item.id,
            str(downloaded_path),
        )
        # 清理临时文件
        try:
            Path(downloaded_path).unlink(missing_ok=True)
        except Exception:
            pass
        return destination is not None

    async def _ensure_favorite_local_copy(self, item: FavoriteItem) -> str | None:
        for candidate in (item.localization.local_path, item.local_path):
            if candidate and Path(candidate).exists():
                return str(Path(candidate))
        success = await self._localize_favorite_item(item)
        if not success:
            return None
        refreshed = self._favorite_manager.get_item(item.id) or item
        for candidate in (refreshed.localization.local_path, refreshed.local_path):
            if candidate and Path(candidate).exists():
                return str(Path(candidate))
        return None

    def _handle_localize_current_folder(self, _: ft.ControlEvent | None = None) -> None:
        folder_id = self._favorite_selected_folder
        items = self._favorite_manager.list_items(
            None if folder_id in (None, "__all__") else folder_id
        )
        if not items:
            self._show_snackbar("当前视图没有可本地化的收藏。")
            return

        button = self._favorite_localize_button
        if button is not None:
            button.disabled = True
            button.update()

        async def _runner() -> None:
            success = 0
            self._show_localization_progress(len(items))
            for item in items:
                self._favorite_manager.update_localization(
                    item.id,
                    status="pending",
                    local_path=item.localization.local_path,
                    folder_path=item.localization.folder_path,
                )
                self._set_item_localizing(item.id, True)
                try:
                    current_item = self._favorite_manager.get_item(item.id) or item
                    if await self._localize_favorite_item(current_item):
                        success += 1
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error(f"本地化收藏失败: {exc}")
                finally:
                    self._set_item_localizing(item.id, False)
                    self._update_localization_progress()
            self._refresh_favorite_tabs()
            if button is not None:
                button.disabled = False
                button.update()
            self._finish_localization_progress(success, len(items))
            self._show_snackbar(f"已本地化 {success}/{len(items)} 项收藏。")

        self.page.run_task(_runner)

    def _handle_localize_single_item(self, item_id: str) -> None:
        item = self._favorite_manager.get_item(item_id)
        if not item:
            self._show_snackbar("未找到指定的收藏。", error=True)
            return

        self._favorite_manager.update_localization(
            item_id,
            status="pending",
            local_path=item.localization.local_path,
            folder_path=item.localization.folder_path,
        )
        self._set_item_localizing(item_id, True)

        async def _runner() -> None:
            try:
                target_item = self._favorite_manager.get_item(item_id) or item
                success = await self._localize_favorite_item(target_item)
                if success:
                    self._show_snackbar(f"收藏“{item.title}”已本地化。")
                else:
                    self._show_snackbar("本地化失败，请检查网络或文件。", error=True)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"本地化收藏失败: {exc}")
                self._show_snackbar("本地化失败，请查看日志。", error=True)
            finally:
                self._set_item_localizing(item_id, False)
                self._refresh_favorite_tabs()

        self.page.run_task(_runner)

    def _handle_set_favorite_wallpaper(self, item_id: str) -> None:
        item = self._favorite_manager.get_item(item_id)
        if not item:
            self._show_snackbar("未找到指定的收藏。", error=True)
            return

        button = self._favorite_item_wallpaper_buttons.get(item_id)
        if button is not None:
            button.disabled = True
            if button.page is not None:
                button.update()

        pre_existing_local = False
        for candidate in (
            item.localization.local_path,
            item.local_path,
        ):
            if candidate and Path(candidate).exists():
                pre_existing_local = True
                break

        async def _runner() -> None:
            if not pre_existing_local:
                self._set_item_localizing(item_id, True)
            try:
                target_item = self._favorite_manager.get_item(item_id) or item
                local_path = await self._ensure_favorite_local_copy(target_item)
                if not local_path:
                    self._show_snackbar(
                        "无法准备壁纸文件，请尝试先本地化。", error=True
                    )
                    return
                await asyncio.to_thread(ltwapi.set_wallpaper, local_path)
                self._show_snackbar("壁纸设置成功。")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"设置收藏壁纸失败: {exc}")
                self._show_snackbar("设置壁纸失败，请查看日志。", error=True)
            finally:
                if not pre_existing_local:
                    self._set_item_localizing(item_id, False)
                    self._refresh_favorite_tabs()
                refreshed_button = self._favorite_item_wallpaper_buttons.get(item_id)
                if refreshed_button is not None:
                    refreshed_button.disabled = False
                    if refreshed_button.page is not None:
                        refreshed_button.update()

        self.page.run_task(_runner)

    def _handle_export_single_item(self, item_id: str) -> None:
        item = self._favorite_manager.get_item(item_id)
        if not item:
            self._show_snackbar("未找到指定的收藏。", error=True)
            return

        export_button = self._favorite_item_export_buttons.get(item_id)
        if export_button is not None:
            export_button.disabled = True
            if export_button.page is not None:
                export_button.update()

        pre_existing_local = False
        for candidate in (
            item.localization.local_path,
            item.local_path,
        ):
            if candidate and Path(candidate).exists():
                pre_existing_local = True
                break

        if not pre_existing_local:
            self._set_item_localizing(item_id, True)

        package_path = self._favorite_default_package_path(item)

        async def _runner() -> None:
            try:
                target_item = self._favorite_manager.get_item(item_id) or item
                local_path = await self._ensure_favorite_local_copy(target_item)
                if local_path:
                    source = Path(local_path)
                    export_path = self._favorite_default_asset_path(target_item, source)
                    await asyncio.to_thread(shutil.copy2, source, export_path)
                    self._show_snackbar(f"收藏文件已复制到 {export_path}。")
                    return

                exported_path = await asyncio.to_thread(
                    self._favorite_manager.export_items,
                    package_path,
                    [item_id],
                )
                self._show_snackbar(f"收藏已导出到 {exported_path}。")
            except ValueError as exc:
                logger.error(f"导出收藏失败: {exc}")
                self._show_snackbar(str(exc), error=True)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"导出收藏失败: {exc}")
                self._show_snackbar("导出失败，请查看日志。", error=True)
            finally:
                if not pre_existing_local:
                    self._set_item_localizing(item_id, False)
                    self._refresh_favorite_tabs()
                refreshed = self._favorite_item_export_buttons.get(item_id)
                if refreshed is not None:
                    refreshed.disabled = False
                    if refreshed.page is not None:
                        refreshed.update()

        self.page.run_task(_runner)

    def _open_export_dialog(self) -> None:
        folders = self._favorite_folders()
        if not folders:
            self._show_snackbar("没有可导出的收藏夹。", error=True)
            return

        default_folder = self._favorite_selected_folder
        selected_ids: set[str] = set()
        if default_folder and default_folder not in ("__all__", ""):
            selected_ids.add(default_folder)
        elif default_folder == "__all__":
            selected_ids.update(folder.id for folder in folders)

        folder_checkboxes: list[tuple[ft.Checkbox, str]] = []
        select_all_checkbox = ft.Checkbox(
            label="全部收藏夹",
            value=default_folder == "__all__",
        )
        export_button_holder: dict[str, ft.Control | None] = {"button": None}

        def _sync_selection(_: ft.ControlEvent | None = None) -> None:
            if select_all_checkbox.value:
                selected_ids.clear()
                selected_ids.update(folder.id for folder in folders)
                for checkbox, _ in folder_checkboxes:
                    checkbox.value = True
            else:
                selected_ids.clear()
                for checkbox, folder_id in folder_checkboxes:
                    if checkbox.value:
                        selected_ids.add(folder_id)
            button_control = export_button_holder["button"]
            if isinstance(button_control, ft.Control):
                button_control.disabled = not bool(selected_ids)
                button_control.update()

        for folder in folders:
            checkbox = ft.Checkbox(
                label=folder.name,
                value=folder.id in selected_ids or not selected_ids,
            )
            checkbox.on_change = _sync_selection
            folder_checkboxes.append((checkbox, folder.id))

        select_all_checkbox.on_change = _sync_selection

        exports_dir = self._favorite_manager.localization_root().parent / "exports"
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        default_path = (exports_dir / f"favorites-{timestamp}.ltwfav").resolve()
        path_field = ft.TextField(
            label="导出文件 (.ltwfav)",
            value=str(default_path),
            autofocus=True,
            expand=True,
        )

        status_text = ft.Text("选择要导出的收藏夹，并指定导出文件路径。", size=12)

        def _submit(_: ft.ControlEvent | None = None) -> None:
            if not selected_ids:
                self._show_snackbar("请至少选择一个收藏夹。", error=True)
                return
            target = Path(path_field.value).expanduser()

            async def _runner() -> None:
                export_button = export_button_holder["button"]
                if isinstance(export_button, ft.Control):
                    export_button.disabled = True
                    export_button.update()
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    folder_list = list(selected_ids)
                    await asyncio.to_thread(
                        self._favorite_manager.export_folders,
                        target,
                        folder_list,
                    )
                    self._show_snackbar(f"收藏已导出到 {target}。")
                    self._close_dialog()
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error(f"导出收藏失败: {exc}")
                    self._show_snackbar("导出失败，请检查日志。", error=True)
                finally:
                    if isinstance(export_button, ft.Control):
                        export_button.disabled = False
                        export_button.update()

            self.page.run_task(_runner)

        export_button = ft.FilledButton(
            "导出",
            icon=ft.Icons.CLOUD_UPLOAD,
            on_click=_submit,
        )
        export_button_holder["button"] = export_button

        content = ft.Container(
            width=420,
            content=ft.Column(
                [
                    status_text,
                    select_all_checkbox,
                    ft.Column([cb for cb, _ in folder_checkboxes], spacing=4),
                    path_field,
                ],
                spacing=12,
                tight=True,
            ),
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("导出收藏"),
            content=content,
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                export_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)
        _sync_selection()  # 初始化按钮状态

    def _open_import_dialog(self) -> None:
        path_field = ft.TextField(
            label="导入文件 (.ltwfav)",
            autofocus=True,
            expand=True,
        )

        status_text = ft.Text("选择导入包后，系统会合并收藏夹及收藏记录。", size=12)

        def _submit(_: ft.ControlEvent | None = None) -> None:
            path = Path(path_field.value).expanduser()
            if not path.exists():
                self._show_snackbar("指定的导入文件不存在。", error=True)
                return

            async def _runner() -> None:
                import_button.disabled = True
                import_button.update()
                try:
                    folders, items = await asyncio.to_thread(
                        self._favorite_manager.import_folders,
                        path,
                    )
                    self._show_snackbar(
                        f"导入完成：新增收藏夹 {folders} 个，收藏 {items} 条。"
                    )
                    self._favorite_selected_folder = "__all__"
                    self._refresh_favorite_tabs()
                    self._close_dialog()
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error(f"导入收藏失败: {exc}")
                    self._show_snackbar("导入失败，请检查日志。", error=True)
                finally:
                    import_button.disabled = False
                    import_button.update()

            self.page.run_task(_runner)

        import_button = ft.FilledButton(
            "导入",
            icon=ft.Icons.FILE_UPLOAD,
            on_click=_submit,
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("导入收藏"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    [status_text, path_field],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                import_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _on_favorite_tab_change(self, event: ft.ControlEvent) -> None:
        folders = self._favorite_folders()
        index = getattr(event.control, "selected_index", 0) if event.control else 0
        if index <= 0 or not folders:
            self._favorite_selected_folder = "__all__"
        else:
            normalized_index = min(index - 1, len(folders) - 1)
            self._favorite_selected_folder = folders[normalized_index].id
        self._update_favorite_folder_toolbar()
        self.page.update()

    def _refresh_favorite_tabs(self) -> None:
        if not self._favorite_tabs:
            return
        folders = self._favorite_folders()
        tab_ids = self._favorite_tab_ids(folders)
        if self._favorite_selected_folder not in tab_ids:
            self._favorite_selected_folder = "__all__"
        tabs_control = self._favorite_tabs
        tabs_control.tabs = self._build_favorite_tabs_list(folders)
        tabs_control.selected_index = tab_ids.index(self._favorite_selected_folder)
        if tabs_control.page is not None:
            tabs_control.update()
        self._update_favorite_folder_toolbar()
        if self.page is not None and tabs_control.page is not None:
            self.page.update()

    def _select_favorite_folder(self, folder_id: str) -> None:
        self._favorite_selected_folder = folder_id
        self._refresh_favorite_tabs()

    def _remove_favorite(self, item_id: str) -> None:
        if self._favorite_manager.remove_item(item_id):
            self._show_snackbar("已移除收藏。")
            self._favorite_preview_cache.pop(item_id, None)
            self._refresh_favorite_tabs()
        else:
            self._show_snackbar("未找到指定的收藏。", error=True)

    def _edit_favorite(self, item_id: str) -> None:
        item = self._favorite_manager.get_item(item_id)
        if not item:
            self._show_snackbar("未找到指定的收藏。", error=True)
            return
        payload = {
            "title": item.title,
            "description": item.description,
            "tags": list(item.tags),
            "source": item.source,
            "preview_url": item.preview_url,
            "local_path": item.local_path,
            "extra": dict(item.extra),
            "folder_id": item.folder_id,
        }
        self._open_favorite_editor(payload, item_id=item.id)

    def _schedule_favorite_classification(self, item_id: str) -> None:
        async def _runner() -> None:
            await self._favorite_manager.maybe_classify_item(item_id)
            self._refresh_favorite_tabs()

        self.page.run_task(_runner)

    def _open_new_folder_dialog(
        self,
        on_created: Callable[[FavoriteFolder], None] | None = None,
    ) -> None:
        name_field = ft.TextField(label="收藏夹名称", autofocus=True)
        description_field = ft.TextField(
            label="描述 (可选)",
            multiline=True,
            max_lines=3,
        )

        def _submit(_: ft.ControlEvent | None = None) -> None:
            folder = self._favorite_manager.create_folder(
                name_field.value or "",
                description=description_field.value or "",
            )
            self._close_dialog()
            self._show_snackbar("收藏夹已创建。")
            self._favorite_selected_folder = folder.id
            self._refresh_favorite_tabs()
            if on_created:
                on_created(folder)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("新建收藏夹"),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    [name_field, description_field],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledTonalButton("创建", icon=ft.Icons.CHECK, on_click=_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _handle_edit_current_folder(self, _: ft.ControlEvent | None = None) -> None:
        folder_id = self._favorite_selected_folder
        if folder_id in (None, "__all__"):
            self._show_snackbar("请先选择一个具体的收藏夹。", error=True)
            return
        self._open_edit_folder_dialog(folder_id)

    def _open_edit_folder_dialog(self, folder_id: str) -> None:
        folder = self._favorite_manager.get_folder(folder_id)
        if not folder:
            self._show_snackbar("未找到要编辑的收藏夹。", error=True)
            return

        name_field = ft.TextField(
            label="收藏夹名称",
            value=folder.name,
            autofocus=True,
        )
        description_field = ft.TextField(
            label="描述 (可选)",
            value=folder.description,
            multiline=True,
            max_lines=3,
        )

        def _submit(_: ft.ControlEvent | None = None) -> None:
            updated = self._favorite_manager.rename_folder(
                folder_id,
                name=name_field.value,
                description=description_field.value,
            )
            self._close_dialog()
            if updated:
                self._favorite_selected_folder = folder_id
                self._show_snackbar("收藏夹已更新。")
                self._refresh_favorite_tabs()
            else:
                self._show_snackbar("收藏夹更新失败。", error=True)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑收藏夹"),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    [name_field, description_field],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledButton("保存", icon=ft.Icons.SAVE, on_click=_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _handle_delete_current_folder(self, _: ft.ControlEvent | None = None) -> None:
        folder_id = self._favorite_selected_folder
        if folder_id in (None, "__all__"):
            self._show_snackbar("请选择要删除的收藏夹。", error=True)
            return
        if folder_id == "default":
            self._show_snackbar("默认收藏夹无法删除。", error=True)
            return
        self._confirm_delete_folder(folder_id)

    def _confirm_delete_folder(self, folder_id: str) -> None:
        folder = self._favorite_manager.get_folder(folder_id)
        if not folder:
            self._show_snackbar("未找到要删除的收藏夹。", error=True)
            return

        def _delete(_: ft.ControlEvent | None = None) -> None:
            success = self._favorite_manager.delete_folder(folder_id)
            self._close_dialog()
            if success:
                self._favorite_selected_folder = "default"
                self._show_snackbar("收藏夹已删除，内容已移动到默认收藏夹。")
                self._refresh_favorite_tabs()
            else:
                self._show_snackbar("删除收藏夹失败。", error=True)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("删除收藏夹"),
            content=ft.Text(
                f"确定要删除收藏夹“{folder.name}”吗？该收藏夹中的所有收藏将被移动到默认收藏夹。"
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledTonalButton(
                    "删除",
                    icon=ft.Icons.DELETE_FOREVER,
                    bgcolor=ft.Colors.ERROR_CONTAINER,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    on_click=_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _open_favorite_editor(
        self,
        payload: Dict[str, Any] | None,
        item_id: str | None = None,
    ) -> None:
        if not payload:
            self._show_snackbar("当前没有可收藏的内容。", error=True)
            return

        folders = self._favorite_folders()

        def _refresh_dropdown(selected: str | None = None) -> None:
            folder_dropdown.options = [
                ft.DropdownOption(key=folder.id, text=folder.name)
                for folder in self._favorite_folders()
            ]
            valid_values = {option.key for option in folder_dropdown.options}
            if selected and selected in valid_values:
                folder_dropdown.value = selected
            elif folder_dropdown.value not in valid_values and valid_values:
                folder_dropdown.value = next(iter(valid_values))
            folder_dropdown.update()

        initial_folder = payload.get("folder_id")
        if not initial_folder or initial_folder == "__all__":
            initial_folder = (
                self._favorite_selected_folder
                if self._favorite_selected_folder != "__all__"
                else "default"
            )

        folder_dropdown = ft.Dropdown(
            label="收藏夹",
            value=initial_folder,
            options=[
                ft.DropdownOption(key=folder.id, text=folder.name) for folder in folders
            ]
            or [ft.DropdownOption(key="default", text="默认收藏夹")],
            expand=True,
        )

        def _create_folder(_: ft.ControlEvent | None = None) -> None:
            self._open_new_folder_dialog(
                on_created=lambda folder: _refresh_dropdown(folder.id)
            )

        title_field = ft.TextField(
            label="标题",
            value=payload.get("title", ""),
            autofocus=True,
        )
        description_field = ft.TextField(
            label="描述",
            value=payload.get("description", ""),
            multiline=True,
            max_lines=4,
        )
        tags_field = ft.TextField(
            label="标签",
            value=", ".join(payload.get("tags", [])),
            helper_text="使用逗号、空格或分号分隔多个标签",
        )

        preview_src = payload.get("preview_url") or payload.get("local_path")
        if not preview_src and isinstance(payload.get("source"), FavoriteSource):
            preview_src = payload["source"].url

        preview_control: ft.Control
        if preview_src:
            preview_control = ft.Image(
                src=preview_src,
                width=200,
                height=110,
                fit=ft.ImageFit.COVER,
                border_radius=8,
            )
        else:
            preview_control = ft.Container(
                width=200,
                height=110,
                border_radius=8,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_OUTLINED, color=ft.Colors.OUTLINE),
            )

        def _submit(_: ft.ControlEvent | None = None) -> None:
            selected_folder = folder_dropdown.value or "default"
            tags = self._parse_tag_input(tags_field.value)

            if item_id:
                self._favorite_manager.update_item(
                    item_id,
                    folder_id=selected_folder,
                    title=title_field.value,
                    description=description_field.value,
                    tags=tags,
                )
                result_item = self._favorite_manager.get_item(item_id)
                created = False
                if result_item is None:
                    self._show_snackbar("收藏更新失败。", error=True)
                    return
            else:
                result_item, created = self._favorite_manager.add_or_update_item(
                    folder_id=selected_folder,
                    title=title_field.value or payload.get("title", ""),
                    description=description_field.value or "",
                    tags=tags,
                    source=payload.get("source"),
                    preview_url=payload.get("preview_url"),
                    local_path=payload.get("local_path"),
                    extra=payload.get("extra"),
                    merge_tags=True,
                )

            self._favorite_selected_folder = selected_folder
            self._close_dialog()
            message = "收藏成功！" if created else "收藏已更新。"
            self._show_snackbar(message)
            self._refresh_favorite_tabs()
            self._schedule_favorite_classification(result_item.id)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑收藏" if item_id else "添加到收藏"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                folder_dropdown,
                                ft.IconButton(
                                    icon=ft.Icons.CREATE_NEW_FOLDER,
                                    tooltip="新建收藏夹",
                                    on_click=_create_folder,
                                ),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                        preview_control,
                        title_field,
                        description_field,
                        tags_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledButton("保存", icon=ft.Icons.CHECK, on_click=_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _make_current_wallpaper_payload(self) -> Dict[str, Any] | None:
        path = self.wallpaper_path
        if not path:
            return None
        try:
            resolved = Path(path).resolve()
            preview_uri = resolved.as_uri()
        except Exception:
            resolved = Path(path)
            preview_uri = path
        source = FavoriteSource(
            type="system_wallpaper",
            identifier=f"file::{resolved}",
            title="当前系统壁纸",
            url=None,
            preview_url=preview_uri,
            local_path=path,
            extra={"origin": "home"},
        )
        return {
            "title": resolved.name,
            "description": "来自当前桌面的壁纸",
            "tags": ["系统壁纸"],
            "source": source,
            "preview_url": preview_uri,
            "local_path": path,
            "extra": {"path": path},
        }

    def _make_bing_favorite_payload(self) -> Dict[str, Any] | None:
        if not self.bing_wallpaper_url or not self.bing_wallpaper:
            return None
        identifier = self.bing_wallpaper.get("startdate") or self.bing_wallpaper_url
        title = self.bing_wallpaper.get("title", "Bing 每日壁纸")
        description = self.bing_wallpaper.get("copyright", "")
        source = FavoriteSource(
            type="bing",
            identifier=str(identifier),
            title=title,
            url=self.bing_wallpaper_url,
            preview_url=self.bing_wallpaper_url,
            extra=dict(self.bing_wallpaper),
        )
        return {
            "title": title,
            "description": description,
            "tags": ["Bing", "每日壁纸"],
            "source": source,
            "preview_url": self.bing_wallpaper_url,
            "extra": {"bing": dict(self.bing_wallpaper)},
        }

    def _make_spotlight_favorite_payload(self) -> Dict[str, Any] | None:
        if not self.spotlight_wallpaper or not self.spotlight_wallpaper_url:
            return None
        index = min(self.spotlight_current_index, len(self.spotlight_wallpaper) - 1)
        data = self.spotlight_wallpaper[index]
        url = data.get("url")
        identifier = url or data.get("ctaUri") or f"spotlight-{index}"
        title = data.get("title", "Windows 聚焦壁纸")
        description = data.get("description", "")
        source = FavoriteSource(
            type="windows_spotlight",
            identifier=str(identifier),
            title=title,
            url=url,
            preview_url=url,
            extra=dict(data),
        )
        return {
            "title": title,
            "description": description,
            "tags": ["Windows Spotlight"],
            "source": source,
            "preview_url": url,
            "extra": {"spotlight": dict(data)},
        }

    def _build_bing_daily_content(self):
        copy_menu = None

        def _set_wallpaper(url):
            nonlocal bing_loading_info, bing_pb

            def progress_callback(value, value1):
                nonlocal bing_pb
                bing_pb.value = value / value1
                self.page.update()

            bing_loading_info.visible = True
            bing_pb.visible = True

            set_button.disabled = True
            favorite_button.disabled = True
            download_button.disabled = True

            _disable_copy_button()

            self.resource_tabs.disabled = True

            self.page.update()

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("获取Bing壁纸数据时出现问题"),
                content=ft.Text(
                    "你可以重试或手动下载壁纸后设置壁纸，若无法解决请联系开发者。"
                ),
                actions=[
                    ft.TextButton(
                        "关闭", on_click=lambda e: setattr(dlg, "open", False)
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                open=False,
            )

            wallpaper_path = ltwapi.download_file(
                url,
                CACHE_DIR / "wallpapers",
                "Ltw-Wallpaper",
                progress_callback=progress_callback,
            )
            if wallpaper_path:
                self._emit_download_completed("bing", "set_wallpaper", wallpaper_path)
                ltwapi.set_wallpaper(wallpaper_path)
                self._emit_bing_action(
                    "set_wallpaper",
                    True,
                    {"file_path": str(wallpaper_path)},
                )

            else:
                setattr(dlg, "open", True)
                logger.error("Bing 壁纸下载失败")
                self._emit_bing_action("set_wallpaper", False)

            bing_pb.value = 0
            bing_loading_info.visible = False
            bing_pb.visible = False
            set_button.disabled = False
            favorite_button.disabled = False
            download_button.disabled = False
            _enable_copy_button()

            self.resource_tabs.disabled = False

            self.page.update()

        def _sanitize_filename(raw: str, fallback: str) -> str:
            cleaned = "".join(
                ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_"
                for ch in (raw or "").strip()
            ).strip()
            return cleaned or fallback

        def _copy_link():
            if not self.bing_wallpaper_url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("当前没有可用的链接哦~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )
                self._emit_bing_action("copy_link", False)
                return
            pyperclip.copy(self.bing_wallpaper_url)
            self.page.open(
                ft.SnackBar(
                    ft.Text("链接已复制，快去分享吧~"),
                )
            )
            self._emit_bing_action("copy_link", True)

        def _handle_copy(action: str):
            nonlocal bing_loading_info, bing_pb
            nonlocal \
                set_button, \
                favorite_button, \
                download_button, \
                copy_button, \
                copy_menu

            if action == "link":
                _copy_link()
                return

            if not self.bing_wallpaper_url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("当前没有可用的壁纸资源~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )
                self._emit_bing_action(action, False)
                return

            def progress_callback(value, total):
                if total:
                    bing_pb.value = value / total
                    self.page.update()

            bing_loading_info.value = (
                "正在准备复制…" if action.startswith("copy_") else "正在下载壁纸…"
            )
            bing_loading_info.visible = True
            bing_pb.visible = True

            set_button.disabled = True
            favorite_button.disabled = True
            download_button.disabled = True
            _disable_copy_button()
            if copy_menu:
                copy_menu.disabled = True
            self.resource_tabs.disabled = True

            self.page.update()

            filename = _sanitize_filename(title, "Bing-Wallpaper")
            wallpaper_path = ltwapi.download_file(
                self.bing_wallpaper_url,
                CACHE_DIR / "wallpapers",
                filename,
                progress_callback=progress_callback,
            )

            if not wallpaper_path:
                logger.error("Bing 壁纸复制时下载失败")
                self.page.open(
                    ft.SnackBar(
                        ft.Text("下载失败，请稍后再试~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )
                self._emit_bing_action(action, False)
            else:
                self._emit_download_completed("bing", action, wallpaper_path)
                if action == "copy_image":
                    if copy_image_to_clipboard(wallpaper_path):
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("图片已复制，可直接粘贴~"),
                            )
                        )
                        self._emit_bing_action(action, True)
                    else:
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("复制图片失败，请稍后再试~"),
                                bgcolor=ft.Colors.ON_ERROR,
                            )
                        )
                        self._emit_bing_action(action, False)
                elif action == "copy_file":
                    if copy_files_to_clipboard([wallpaper_path]):
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("文件已复制到剪贴板~"),
                            )
                        )
                        self._emit_bing_action(action, True)
                    else:
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("复制文件失败，请稍后再试~"),
                                bgcolor=ft.Colors.ON_ERROR,
                            )
                        )
                        self._emit_bing_action(action, False)

            bing_pb.value = 0
            bing_loading_info.visible = False
            bing_pb.visible = False
            set_button.disabled = False
            favorite_button.disabled = False
            download_button.disabled = False
            _enable_copy_button()
            self.resource_tabs.disabled = False

            self.page.update()

        def _disable_copy_button():
            nonlocal copy_menu, copy_button
            copy_menu.disabled = True
            setattr(copy_button, "bgcolor", ft.Colors.OUTLINE_VARIANT)
            copy_button.content.controls[0].color = ft.Colors.OUTLINE
            copy_button.content.controls[1].color = ft.Colors.OUTLINE
            self.page.update()

        def _enable_copy_button():
            nonlocal copy_menu, copy_button
            copy_menu.disabled = False
            setattr(copy_button, "bgcolor", ft.Colors.SECONDARY_CONTAINER)
            copy_button.content.controls[0].color = ft.Colors.ON_SECONDARY_CONTAINER
            copy_button.content.controls[1].color = ft.Colors.ON_SECONDARY_CONTAINER
            self.page.update()

        if self.bing_loading:
            return self._build_bing_loading_indicator()
        if not self.bing_wallpaper_url:
            return ft.Container(ft.Text("Bing 壁纸加载失败，请稍后再试～"), padding=16)
        title = self.bing_wallpaper.get("title", "Bing 每日壁纸")
        desc = self.bing_wallpaper.get("copyright", "")
        bing_loading_info = ft.Text("正在获取信息……")
        bing_pb = ft.ProgressBar(value=0)
        bing_pb.visible = False
        bing_loading_info.visible = False
        set_button = ft.FilledTonalButton(
            "设为壁纸",
            icon=ft.Icons.WALLPAPER,
            on_click=lambda e: _set_wallpaper(self.bing_wallpaper_url),
        )
        favorite_button = ft.FilledTonalButton(
            "收藏",
            icon=ft.Icons.STAR,
            on_click=lambda _: self._open_favorite_editor(
                self._make_bing_favorite_payload()
            ),
        )
        download_button = ft.FilledTonalButton("下载", icon=ft.Icons.DOWNLOAD)
        copy_button_content = ft.Row(
            controls=[
                ft.Icon(ft.Icons.COPY, ft.Colors.ON_SECONDARY_CONTAINER, size=17),
                ft.Text("复制"),
            ],
            spacing=7,
        )
        copy_button = ft.Container(
            content=copy_button_content,
            padding=7.5,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=50,
        )
        copy_menu = ft.PopupMenuButton(
            content=copy_button,
            tooltip="复制壁纸链接、图片或图片文件",
            items=[
                ft.PopupMenuItem(
                    icon=ft.Icons.LINK,
                    text="复制链接",
                    on_click=lambda _: _handle_copy("link"),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.IMAGE,
                    text="复制图片",
                    on_click=lambda _: _handle_copy("copy_image"),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.FOLDER_COPY,
                    text="复制图片文件",
                    on_click=lambda _: _handle_copy("copy_file"),
                ),
            ],
        )

        extra_actions = self._build_plugin_actions(self.bing_action_factories)
        actions_row = ft.Row(
            [
                *[
                    set_button,
                    favorite_button,
                    download_button,
                    copy_menu,
                ],
                *extra_actions,
            ]
        )

        return ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Image(
                                src=self.bing_wallpaper_url,
                                width=160,
                                height=90,
                                fit=ft.ImageFit.COVER,
                                border_radius=8,
                            ),
                            ft.Column(
                                [
                                    ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
                                    ft.Text(desc, size=12, color=ft.Colors.GREY),
                                    ft.Row(
                                        [
                                            ft.TextButton("测验", icon=ft.Icons.LAUNCH),
                                            ft.TextButton("详情", icon=ft.Icons.LAUNCH),
                                        ]
                                    ),
                                ],
                                spacing=6,
                            ),
                        ]
                    ),
                    actions_row,
                    bing_loading_info,
                    bing_pb,
                ]
            ),
            padding=16,
        )

    def _build_spotlight_daily_content(self):
        copy_menu = None
        copy_button = None
        copy_icon = None
        copy_text = None

        def _sanitize_filename(raw: str, fallback: str) -> str:
            cleaned = "".join(
                ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_"
                for ch in (raw or "").strip()
            ).strip()
            return cleaned or fallback

        def _update_details(idx: int):
            nonlocal title, description, copy_rights, info_button
            self.spotlight_current_index = idx
            spotlight = self.spotlight_wallpaper[idx]
            title.value = spotlight.get("title", "无标题")
            description.value = spotlight.get("description", "无描述")
            copy_rights.value = spotlight.get("copyright", "无版权信息")

            info_url = spotlight.get("ctaUri")
            if info_url:
                info_button.text = "了解详情"
                info_button.disabled = False
                info_button.on_click = lambda e, url=info_url: self.page.launch_url(url)
            else:
                info_button.text = "了解详情"
                info_button.disabled = True
                info_button.on_click = None
            self._emit_resource_event(
                "resource.spotlight.updated",
                self._spotlight_event_payload(),
            )

        def _change_photo(e):
            data = json.loads(e.data)
            if not data:
                return
            idx = int(data[0])
            _update_details(idx)
            self.page.update()

        def _copy_link():
            spotlight = (
                self.spotlight_wallpaper[self.spotlight_current_index]
                if self.spotlight_wallpaper
                else {}
            )
            url = spotlight.get("url") if isinstance(spotlight, dict) else None
            if not url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("当前壁纸缺少下载链接，暂时无法复制~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )
                self._emit_spotlight_action("copy_link", False)
                return
            pyperclip.copy(url)
            self.page.open(
                ft.SnackBar(
                    ft.Text("壁纸链接已复制，快去分享吧~"),
                )
            )
            self._emit_spotlight_action("copy_link", True)

        def _handle_download(action: str):
            nonlocal spotlight_loading_info, spotlight_pb
            nonlocal set_button, favorite_button, download_button, copy_button
            nonlocal segmented_button, copy_menu

            normalized_action = "set_wallpaper" if action == "set" else action

            spotlight = (
                self.spotlight_wallpaper[self.spotlight_current_index]
                if self.spotlight_wallpaper
                else {}
            )
            url = spotlight.get("url")
            if not url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("未找到壁纸地址，暂时无法下载~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )
                self._emit_spotlight_action(normalized_action, False)
                return

            def progress_callback(value, total):
                if total:
                    spotlight_pb.value = value / total
                    self.page.update()

            spotlight_loading_info.value = (
                "正在准备复制…" if action.startswith("copy_") else "正在下载壁纸…"
            )
            spotlight_loading_info.visible = True
            spotlight_pb.visible = True

            set_button.disabled = True
            favorite_button.disabled = True
            download_button.disabled = True
            _disable_copy_button()
            segmented_button.disabled = True
            self.resource_tabs.disabled = True

            self.page.update()

            filename = _sanitize_filename(
                spotlight.get("title"),
                f"Windows-Spotlight-{self.spotlight_current_index + 1}",
            )

            wallpaper_path = ltwapi.download_file(
                url,
                CACHE_DIR / "wallpapers",
                filename,
                progress_callback=progress_callback,
            )

            success = wallpaper_path is not None
            handled = False
            if success:
                self._emit_download_completed(
                    "spotlight", normalized_action, wallpaper_path
                )
            if success and action == "set":
                try:
                    ltwapi.set_wallpaper(wallpaper_path)
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("壁纸设置成功啦~ (๑•̀ㅂ•́)و✧"),
                        )
                    )
                except Exception as exc:
                    logger.error(f"设置壁纸失败: {exc}")
                    success = False
                handled = True
                self._emit_spotlight_action(
                    normalized_action,
                    success,
                    {"file_path": str(wallpaper_path) if wallpaper_path else None},
                )
            elif success and action == "download":
                self.page.open(
                    ft.SnackBar(
                        ft.Text("壁纸下载完成，快去看看吧~"),
                    )
                )
                handled = True
                self._emit_spotlight_action(
                    normalized_action,
                    success,
                    {"file_path": str(wallpaper_path) if wallpaper_path else None},
                )
            elif success and action == "copy_image":
                handled = True
                if copy_image_to_clipboard(wallpaper_path):
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("图片已复制，可直接粘贴~"),
                        )
                    )
                    self._emit_spotlight_action(normalized_action, True)
                else:
                    success = False
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("复制图片失败，请稍后再试~"),
                            bgcolor=ft.Colors.ON_ERROR,
                        )
                    )
                    self._emit_spotlight_action(normalized_action, False)
            elif success and action == "copy_file":
                handled = True
                if copy_files_to_clipboard([wallpaper_path]):
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("文件已复制到剪贴板~"),
                        )
                    )
                    self._emit_spotlight_action(normalized_action, True)
                else:
                    success = False
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("复制文件失败，请稍后再试~"),
                            bgcolor=ft.Colors.ON_ERROR,
                        )
                    )
                    self._emit_spotlight_action(normalized_action, False)

            if not success and not handled:
                logger.error("Windows 聚焦壁纸下载失败")
                self.page.open(
                    ft.SnackBar(
                        ft.Text("下载失败，请稍后再试~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )
                self._emit_spotlight_action(normalized_action, False)

            spotlight_loading_info.visible = False
            spotlight_pb.visible = False
            spotlight_pb.value = 0

            set_button.disabled = False
            favorite_button.disabled = False
            download_button.disabled = False
            _enable_copy_button()
            segmented_button.disabled = False
            self.resource_tabs.disabled = False

            self.page.update()

        def _handle_copy_action(option: str):
            if option == "link":
                _copy_link()
            else:
                _handle_download(option)

        def _disable_copy_button():
            nonlocal copy_menu, copy_button, copy_icon, copy_text
            if copy_menu:
                copy_menu.disabled = True
            if copy_button:
                setattr(copy_button, "bgcolor", ft.Colors.OUTLINE_VARIANT)
                copy_button.disabled = True
            if copy_icon:
                copy_icon.color = ft.Colors.OUTLINE
            if copy_text:
                copy_text.color = ft.Colors.OUTLINE
            self.page.update()

        def _enable_copy_button():
            nonlocal copy_menu, copy_button, copy_icon, copy_text
            if copy_menu:
                copy_menu.disabled = False
            if copy_button:
                setattr(copy_button, "bgcolor", ft.Colors.SECONDARY_CONTAINER)
                copy_button.disabled = False
            if copy_icon:
                copy_icon.color = ft.Colors.ON_SECONDARY_CONTAINER
            if copy_text:
                copy_text.color = ft.Colors.ON_SECONDARY_CONTAINER
            self.page.update()

        if self.spotlight_loading:
            return self._build_spotlight_loading_indicator()
        if not self.spotlight_wallpaper_url:
            return ft.Container(
                ft.Text("Windows 聚焦壁纸加载失败，请稍后再试～"), padding=16
            )
        title = ft.Text()
        description = ft.Text(size=12)
        copy_rights = ft.Text(size=12, color=ft.Colors.GREY)
        info_button = ft.FilledTonalButton(
            "了解详情", icon=ft.Icons.INFO, disabled=True
        )
        set_button = ft.FilledTonalButton(
            "设为壁纸",
            icon=ft.Icons.WALLPAPER,
            on_click=lambda e: _handle_download("set"),
        )
        favorite_button = ft.FilledTonalButton(
            "收藏",
            icon=ft.Icons.STAR,
            on_click=lambda _: self._open_favorite_editor(
                self._make_spotlight_favorite_payload()
            ),
        )
        download_button = ft.FilledTonalButton(
            "下载",
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda e: _handle_download("download"),
        )
        copy_icon = ft.Icon(
            ft.Icons.COPY, color=ft.Colors.ON_SECONDARY_CONTAINER, size=17
        )
        copy_text = ft.Text("复制", color=ft.Colors.ON_SECONDARY_CONTAINER)
        copy_button = ft.Container(
            content=ft.Row(
                controls=[copy_icon, copy_text],
                spacing=7,
            ),
            padding=7.5,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=50,
        )
        copy_menu = ft.PopupMenuButton(
            content=copy_button,
            tooltip="复制壁纸链接、图片或图片文件",
            items=[
                ft.PopupMenuItem(
                    icon=ft.Icons.LINK,
                    text="复制链接",
                    on_click=lambda _: _handle_copy_action("link"),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.IMAGE,
                    text="复制图片",
                    on_click=lambda _: _handle_copy_action("copy_image"),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.FOLDER_COPY,
                    text="复制图片文件",
                    on_click=lambda _: _handle_copy_action("copy_file"),
                ),
            ],
        )

        spotlight_loading_info = ft.Text("正在获取信息……")
        spotlight_loading_info.visible = False
        spotlight_pb = ft.ProgressBar(value=0)
        spotlight_pb.visible = False

        segmented_button = ft.SegmentedButton(
            segments=[
                ft.Segment(
                    value=str(index),
                    label=ft.Text(f"图{index + 1}"),
                    icon=ft.Icon(ft.Icons.PHOTO),
                )
                for index in range(len(self.spotlight_wallpaper_url))
            ],
            allow_multiple_selection=False,
            selected={"0"},
            on_change=_change_photo,
        )

        _update_details(0)
        extra_spotlight_actions = self._build_plugin_actions(
            self.spotlight_action_factories
        )
        spotlight_actions_row = ft.Row(
            [
                *[
                    set_button,
                    favorite_button,
                    download_button,
                    copy_menu,
                ],
                *extra_spotlight_actions,
            ]
        )

        return ft.Container(
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Image(
                                src=url,
                                width=160,
                                height=90,
                                fit=ft.ImageFit.COVER,
                                border_radius=8,
                            )
                            for url in self.spotlight_wallpaper_url
                        ],
                    ),
                    segmented_button,
                    title,
                    description,
                    copy_rights,
                    ft.Row([info_button]),
                    spotlight_actions_row,
                    spotlight_loading_info,
                    spotlight_pb,
                ]
            ),
            padding=16,
        )

    def _build_sniff(self):
        return ft.Column(
            [
                ft.Text("嗅探", size=30),
                ft.Text("嗅探功能正在开发中，敬请期待~"),
            ],
            expand=True,
        )

    def _build_favorite(self):
        self._favorite_tabs = ft.Tabs(
            animation_duration=300,
            expand=True,
            on_change=self._on_favorite_tab_change,
        )

        self._favorite_edit_folder_button = ft.IconButton(
            icon=ft.Icons.EDIT_NOTE,
            tooltip="编辑当前收藏夹",
            disabled=True,
            on_click=self._handle_edit_current_folder,
        )
        self._favorite_delete_folder_button = ft.IconButton(
            icon=ft.Icons.DELETE_SWEEP,
            tooltip="删除当前收藏夹",
            disabled=True,
            on_click=self._handle_delete_current_folder,
        )
        self._favorite_localize_button = ft.IconButton(
            icon=ft.Icons.DOWNLOAD_FOR_OFFLINE,
            tooltip="本地化当前视图收藏",
            on_click=self._handle_localize_current_folder,
        )
        self._favorite_export_button = ft.IconButton(
            icon=ft.Icons.CLOUD_UPLOAD,
            tooltip="导出收藏",
            on_click=lambda _: self._open_export_dialog(),
        )
        self._favorite_import_button = ft.IconButton(
            icon=ft.Icons.FILE_UPLOAD,
            tooltip="导入收藏",
            on_click=lambda _: self._open_import_dialog(),
        )

        # 添加“本地图片到收藏”入口
        add_local_fav_button = ft.FilledTonalButton(
            "添加本地图片",
            icon=ft.Icons.ADD_PHOTO_ALTERNATE,
            on_click=lambda _: self._open_add_local_favorite_picker(),
        )

        navigation_row = ft.Row(
            [
                ft.TextButton(
                    "查看全部",
                    icon=ft.Icons.ALL_INBOX,
                    on_click=lambda _: self._select_favorite_folder("__all__"),
                ),
            ],
            spacing=8,
        )

        folder_actions = ft.Row(
            controls=[
                ft.FilledTonalButton(
                    "新建收藏夹",
                    icon=ft.Icons.CREATE_NEW_FOLDER,
                    on_click=lambda _: self._open_new_folder_dialog(),
                ),
                self._favorite_edit_folder_button,
                self._favorite_delete_folder_button,
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
            alignment=ft.MainAxisAlignment.START,
        )

        data_actions = ft.Row(
            controls=[
                add_local_fav_button,
                self._favorite_localize_button,
                self._favorite_export_button,
                self._favorite_import_button,
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="刷新收藏列表",
                    on_click=lambda _: self._refresh_favorite_tabs(),
                ),
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
            alignment=ft.MainAxisAlignment.START,
        )

        self._favorite_localization_spinner = ft.ProgressRing(width=18, height=18)
        self._favorite_localization_spinner.visible = False
        self._favorite_localization_status_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY,
        )
        self._favorite_localization_progress_bar = ft.ProgressBar(
            value=0.0,
            expand=True,
            height=6,
        )
        self._favorite_localization_progress_bar.visible = False
        progress_row = ft.Row(
            [
                self._favorite_localization_spinner,
                self._favorite_localization_status_text,
                ft.Container(
                    content=self._favorite_localization_progress_bar,
                    expand=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        progress_row.visible = False
        self._favorite_localization_status_row = progress_row

        toolbar = ft.Column(
            [
                navigation_row,
                folder_actions,
                data_actions,
                progress_row,
            ],
            spacing=8,
            tight=True,
        )

        self._refresh_favorite_tabs()

        return ft.Container(
            ft.Column(
                [
                    ft.Text("收藏", size=30),
                    ft.Text(
                        "管理你的收藏、标签和收藏夹。",
                        size=12,
                        color=ft.Colors.GREY,
                    ),
                    ft.Container(toolbar, padding=ft.Padding(0, 12, 0, 12)),
                    ft.Container(self._favorite_tabs, expand=True),
                ],
                spacing=8,
                expand=True,
            ),
            expand=True,
            padding=16,
        )

    def _build_test(self):
        return ft.Column(
            [
                ft.Text("测试和调试", size=30),
                ft.Text("这里是测试和调试专用区域"),
                ft.Button("打开初次运行向导", on_click=lambda _: self.page.go("/first-run")),
            ],
            expand=True,
        )

    def _handle_confirm_nsfw(self):
        app_config.set("wallpaper.allow_nsfw", True)

    def _confirm_nsfw(self):
        # Checkboxes and state sync
        adult_cb = ft.Checkbox(label="我已年满 18 周岁")
        legal_cb = ft.Checkbox(label="我确认我所在国家或地区的法律允许浏览包含成人内容")

        confirm_btn = ft.TextButton(
            "确认",
            disabled=True,
            on_click=lambda _: self._handle_confirm_nsfw(),
        )

        def _sync_state(_: ft.ControlEvent | None = None) -> None:
            confirm_btn.disabled = not (bool(adult_cb.value) and bool(legal_cb.value))
            if confirm_btn.page is not None:
                confirm_btn.update()

        adult_cb.on_change = _sync_state
        legal_cb.on_change = _sync_state

        self._confirm_nsfw_dialog = ft.AlertDialog(
            title=ft.Text("确认允许显示可能包含成人内容"),
            content=ft.Column(
                [
                    ft.Text(
                        "为遵守相关法律法规，我们不会向法律禁止地区和未成年人提供此类内容。继续之前，请确认以下事项："
                    ),
                    adult_cb,
                    legal_cb,
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                confirm_btn,
            ],
        )
        self._open_dialog(self._confirm_nsfw_dialog)

    def _refresh_theme_profiles(
        self, *, initial: bool = False, show_feedback: bool = False
    ) -> None:
        if self._theme_list_handler is None:
            if not initial and show_feedback:
                self._show_snackbar("主题接口不可用。", error=True)
            self._theme_profiles = []
            self._render_theme_cards()
            return

        try:
            result = self._theme_list_handler()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"刷新主题列表失败: {exc}")
            if show_feedback:
                self._show_snackbar("刷新主题列表失败。", error=True)
            return

        profiles: list[Dict[str, Any]] | None = None
        message: str | None = None
        if isinstance(result, PluginOperationResult):
            message = result.message
            if isinstance(result.data, list):
                profiles = result.data
        elif isinstance(result, list):
            profiles = result

        if profiles is not None:
            self._theme_profiles = list(profiles)
            self._render_theme_cards()
            if show_feedback:
                note = message or "主题列表已更新。"
                self._show_snackbar(note)
        else:
            if show_feedback or not initial:
                self._show_snackbar(message or "无法获取主题列表。", error=True)
            self._theme_profiles = []
            self._render_theme_cards()

    def _find_theme_profile(self, identifier: str | None) -> Dict[str, Any] | None:
        if not identifier:
            return None
        for profile in self._theme_profiles:
            if str(profile.get("id")) == identifier:
                return profile
        return None

    @staticmethod
    def _theme_preview_text(
        text: Optional[str], limit: int = 80
    ) -> tuple[str, Optional[str]]:
        if not isinstance(text, str) or not text.strip():
            return "暂无简介", None
        clean = text.strip()
        if len(clean) <= limit:
            return clean, clean
        head = clean[: max(0, limit - 1)]
        return head + "…", clean

    def _render_theme_cards(self) -> None:
        wrap = self._theme_cards_wrap
        if wrap is None:
            return

        cards: list[ft.Control] = []
        for profile in self._theme_profiles:
            card = self._build_theme_card(profile)
            if card is not None:
                cards.append(card)

        if not cards:
            placeholder = ft.Container(
                content=ft.Column(
                    [
                        ft.Text("暂无可用主题。", size=12),
                        ft.Text(
                            "导入主题文件或检查主题目录。",
                            size=11,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    spacing=4,
                    tight=True,
                ),
                bgcolor=self._bgcolor_surface_low,
                width=260,
                height=220,
                padding=ft.padding.all(20),
                border_radius=ft.border_radius.all(12),
            )
            cards.append(placeholder)

        wrap.controls = cards
        if wrap.page is not None and self.page is not None:
            self.page.update()

    def _build_theme_card(self, profile: Dict[str, Any]) -> ft.Control | None:
        identifier = str(profile.get("id") or "").strip()
        if not identifier:
            return None

        name = str(profile.get("name") or identifier)
        is_active = bool(profile.get("is_active"))
        author = profile.get("author")
        description = profile.get("summary") or profile.get("description")
        details = (
            profile.get("details") if isinstance(profile.get("details"), str) else None
        )
        preview_text, tooltip_text = self._theme_preview_text(description)
        if tooltip_text is None and details:
            tooltip_text = details.strip()

        logo_src = profile.get("logo")
        if isinstance(logo_src, str) and logo_src.strip():
            logo_control: ft.Control = ft.Container(
                content=ft.Image(
                    src=logo_src.strip(),
                    width=42,
                    height=42,
                    fit=ft.ImageFit.COVER,
                ),
                width=42,
                height=42,
                border_radius=ft.border_radius.all(8),
            )
        else:
            logo_control = ft.Container(
                content=ft.Icon(ft.Icons.PALETTE),
                width=42,
                height=42,
                border_radius=ft.border_radius.all(8),
                alignment=ft.alignment.center,
            )

        name_column_controls: list[ft.Control] = [
            ft.Text(name, weight=ft.FontWeight.BOLD, size=15),
        ]
        if isinstance(author, str) and author.strip():
            name_column_controls.append(
                ft.Text(f"作者：{author.strip()}", size=12, color=ft.Colors.GREY)
            )

        name_column = ft.Column(
            controls=name_column_controls,
            spacing=2,
            expand=True,
            tight=True,
        )

        status_badge: ft.Control | None = None
        if is_active:
            status_badge = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE,
                            size=16,
                            color=ft.Colors.ON_PRIMARY_CONTAINER,
                        ),
                        ft.Text("当前", size=12, color=ft.Colors.ON_PRIMARY_CONTAINER),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=ft.border_radius.all(12),
                bgcolor=ft.Colors.PRIMARY_CONTAINER,
            )

        title_row_children: list[ft.Control] = [logo_control, name_column]
        if status_badge is not None:
            title_row_children.append(status_badge)

        source = str(profile.get("source") or "").strip()
        source_label = ""
        if source == "builtin":
            source_label = "来源：内置主题"
        elif source == "file":
            source_label = "来源：主题目录"
        elif source == "custom":
            source_label = "来源：自定义路径"

        description_text = ft.Text(
            preview_text,
            size=12,
            color=ft.Colors.GREY,
            tooltip=tooltip_text,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        body_controls: list[ft.Control] = [
            ft.Row(
                title_row_children,
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.START,
            ),
            description_text,
        ]

        if source_label:
            body_controls.append(ft.Text(source_label, size=11, color=ft.Colors.GREY))

        website = (
            profile.get("website") if isinstance(profile.get("website"), str) else None
        )

        actions: list[ft.Control] = [
            ft.FilledButton(
                "应用",
                icon=ft.Icons.CHECK_CIRCLE,
                disabled=is_active,
                on_click=lambda _=None, pid=identifier: self._apply_theme_profile(pid),
            ),
            ft.OutlinedButton(
                "详情",
                icon=ft.Icons.INFO_OUTLINE,
                on_click=lambda _=None, pid=identifier: self._open_theme_detail_dialog(
                    pid
                ),
            ),
        ]

        if website and website.strip():
            actions.append(
                ft.TextButton(
                    "访问主页",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _=None, url=website.strip(): self.page.launch_url(
                        url
                    ),
                )
            )

        body_controls.append(ft.Container(expand=True))
        body_controls.append(
            ft.Row(
                spacing=8,
                run_spacing=8,
                controls=actions,
            )
        )

        bgcolor = (
            ft.Colors.SECONDARY_CONTAINER if is_active else self._bgcolor_surface_low
        )
        border_color = ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE_VARIANT
        border_width = 2 if is_active else 1

        return ft.Container(
            content=ft.Column(body_controls, spacing=10),
            width=260,
            height=220,
            padding=ft.padding.all(12),
            border=ft.border.all(border_width, border_color),
            border_radius=ft.border_radius.all(12),
            bgcolor=bgcolor,
        )

    def _apply_theme_profile(self, identifier: str) -> None:
        if self._theme_apply_handler is None:
            self._show_snackbar("主题应用接口不可用。", error=True)
            return
        try:
            result = self._theme_apply_handler(identifier)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"应用主题失败: {exc}")
            self._show_snackbar("应用主题失败。", error=True)
            return

        if isinstance(result, PluginOperationResult):
            if result.success:
                self._show_snackbar(result.message or "主题已应用。")
            elif result.error == "permission_pending":
                self._show_snackbar(result.message or "等待用户授权。")
                return
            else:
                self._show_snackbar(result.message or "主题应用失败。", error=True)
                return
        else:
            self._show_snackbar("主题已应用。")

        self._refresh_theme_profiles(initial=True)

    def _open_theme_detail_dialog(self, identifier: str) -> None:
        profile = self._find_theme_profile(identifier)
        if not profile:
            self._show_snackbar("未找到主题详情。", error=True)
            return

        name = str(profile.get("name") or identifier)
        author = profile.get("author")
        website = (
            profile.get("website") if isinstance(profile.get("website"), str) else None
        )
        description = profile.get("description")
        details = profile.get("details")
        path = profile.get("path")
        source = profile.get("source")
        is_active = bool(profile.get("is_active"))

        info_lines: list[str] = []
        if isinstance(author, str) and author.strip():
            info_lines.append(f"作者：{author.strip()}")
        if source == "builtin":
            info_lines.append("来源：内置主题")
        elif source == "file":
            info_lines.append("来源：主题目录")
        elif source == "custom":
            info_lines.append("来源：自定义路径")
        if isinstance(path, str) and path:
            info_lines.append(f"文件：{path}")

        summary_text = description or "暂无简介"

        content_controls: list[ft.Control] = [
            ft.Text(summary_text, size=13),
        ]
        if details and isinstance(details, str) and details.strip():
            content_controls.append(
                ft.Markdown(
                    details.strip(),
                    selectable=True,
                    auto_follow_links=True,
                )
            )

        if info_lines:
            content_controls.append(
                ft.Column(
                    [
                        ft.Text(line, size=12, color=ft.Colors.GREY)
                        for line in info_lines
                    ],
                    spacing=4,
                    tight=True,
                )
            )

        actions: list[ft.Control] = [
            ft.TextButton("关闭", on_click=lambda _: self._close_dialog()),
        ]

        if website and website.strip():
            actions.insert(
                0,
                ft.TextButton(
                    "打开网站",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _=None, url=website.strip(): self.page.launch_url(
                        url
                    ),
                ),
            )

        if not is_active:

            def _apply_and_close(_: ft.ControlEvent | None = None) -> None:
                self._close_dialog()
                self._apply_theme_profile(identifier)

            actions.append(
                ft.FilledButton(
                    "应用此主题",
                    icon=ft.Icons.CHECK_CIRCLE,
                    on_click=_apply_and_close,
                )
            )

        dialog = ft.AlertDialog(
            title=ft.Text(name, weight=ft.FontWeight.BOLD),
            content=ft.Column(content_controls, spacing=12, tight=True, width=420),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._theme_detail_dialog = dialog
        self._open_dialog(dialog)

    def _handle_refresh_theme_list(self, _: ft.ControlEvent | None = None) -> None:
        self._refresh_theme_profiles(show_feedback=True)

    def _ensure_theme_file_picker(self) -> None:
        if self._theme_file_picker is None:
            self._theme_file_picker = ft.FilePicker(
                on_result=self._handle_theme_import_result
            )
        if self._theme_file_picker not in self.page.overlay:
            self.page.overlay.append(self._theme_file_picker)
            self.page.update()

    def _open_theme_import_picker(self, _: ft.ControlEvent | None = None) -> None:
        if self._theme_manager is None:
            self._show_snackbar("主题目录不可用。", error=True)
            return
        self._ensure_theme_file_picker()
        if self._theme_file_picker:
            self._theme_file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
            )

    def _handle_theme_import_result(self, event: ft.FilePickerResultEvent) -> None:
        if self._theme_manager is None or not event.files:
            return
        file = event.files[0]
        if not file.path:
            self._show_snackbar("未选择有效的主题文件。", error=True)
            return
        try:
            result = self._theme_manager.import_theme(Path(file.path))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"导入主题失败: {exc}")
            self._show_snackbar(f"导入主题失败：{exc}", error=True)
            return

        metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
        name = metadata.get("name") or Path(file.path).stem
        self._show_snackbar(f"已导入主题：{name}")
        self._refresh_theme_profiles(initial=True)

    def _open_theme_directory(self, _: ft.ControlEvent | None = None) -> None:
        if self._theme_manager is None:
            self._show_snackbar("主题目录不可用。", error=True)
            return
        try:
            directory = self._theme_manager.themes_dir.resolve()
            self.page.launch_url(directory.as_uri())
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"打开主题目录失败: {exc}")
            self._show_snackbar("无法打开主题目录。", error=True)

    def _build_theme_settings_controls(self) -> list[ft.Control]:
        refresh_button = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="刷新",
            on_click=self._handle_refresh_theme_list,
        )

        controls_row: list[ft.Control] = [refresh_button]

        if self._theme_manager is not None:
            controls_row.append(
                ft.FilledButton(
                    "导入主题 (.json)",
                    icon=ft.Icons.UPLOAD_FILE,
                    on_click=self._open_theme_import_picker,
                )
            )
            controls_row.append(
                ft.TextButton(
                    "打开主题目录",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=self._open_theme_directory,
                )
            )

        actions_wrap = ft.Row(
            spacing=8, run_spacing=8, controls=controls_row, wrap=True
        )

        helper_text = ft.Text(
            "选择下方卡片可查看主题详情，点击“应用”即可生效。",
            size=12,
            color=ft.Colors.GREY,
        )

        cards_wrap = ft.Row(
            spacing=12, run_spacing=12, wrap=True, scroll=ft.ScrollMode.AUTO
        )
        self._theme_cards_wrap = cards_wrap
        self._render_theme_cards()

        return [
            ft.Column(
                controls=[actions_wrap, helper_text, cards_wrap],
                spacing=12,
                tight=True,
            )
        ]

    def build_settings_view(self):
        def _change_nsfw(e: ft.ControlEvent):
            switch = getattr(e, "control", None)
            if switch is None:
                return
            new_val = bool(getattr(switch, "value", False))

            # Turning off: no confirmation needed.
            if not new_val:
                app_config.set("wallpaper.allow_nsfw", False)
                return

            # Turning on: require confirmation. Revert switch to off first.
            switch.value = False
            if switch.page is not None:
                switch.update()

            # Show confirm dialog.
            self._confirm_nsfw()

            # Wire dialog buttons to apply/revert the switch value.
            dlg = getattr(self, "_confirm_nsfw_dialog", None)
            try:
                if dlg and getattr(dlg, "actions", None):
                    # actions = [cancel_btn, confirm_btn]
                    cancel_btn = dlg.actions[0] if len(dlg.actions) > 0 else None
                    confirm_btn = dlg.actions[1] if len(dlg.actions) > 1 else None

                    if confirm_btn:

                        def _on_confirm(_: ft.ControlEvent | None = None):
                            self._handle_confirm_nsfw()
                            switch.value = True
                            if switch.page is not None:
                                switch.update()
                            self._close_dialog()

                        confirm_btn.on_click = _on_confirm

                    if cancel_btn:

                        def _on_cancel(_: ft.ControlEvent | None = None):
                            switch.value = False
                            if switch.page is not None:
                                switch.update()
                            self._close_dialog()

                        cancel_btn.on_click = _on_cancel
            except Exception:
                logger.error("Failed to wire dialog buttons")

        def tab_content(title: str, *controls: ft.Control):
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(title, size=24),
                        ft.Column(list(controls), spacing=12),
                    ],
                    spacing=16,
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=20,
                expand=True,
            )

        third_party_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text("第三方用户协议(部分)", weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [
                                ft.Button(
                                    "IntelliMarkets用户协议",
                                    icon=ft.Icons.OPEN_IN_NEW,
                                    on_click=lambda _: self.page.launch_url(
                                        "https://github.com/SRInternet-Studio/Wallpaper-generator/blob/NEXT-PREVIEW/DISCLAIMER.md"
                                    ),
                                ),
                                ft.Button(
                                    "pollinations.ai 用户协议",
                                    icon=ft.Icons.OPEN_IN_NEW,
                                    on_click=lambda _: self.page.launch_url(
                                        "https://enter.pollinations.ai/terms"
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.TextButton(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda _: setattr(third_party_sheet, "open", False)
                            or self.page.update(),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=50,
            ),
            open=False,
        )
        license_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text("依赖版权信息", weight=ft.FontWeight.BOLD),
                        ft.Markdown(
                            self._get_license_text(),
                            selectable=True,
                            auto_follow_links=True,
                        ),
                        ft.TextButton(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda _: setattr(license_sheet, "open", False)
                            or self.page.update(),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                    scroll=ft.ScrollMode.ALWAYS,
                ),
                padding=50,
            ),
            open=False,
        )
        thank_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text(
                            "感谢以下朋友对开发工作的支持",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Markdown(
                            """@[炫饭的芙芙](https://space.bilibili.com/1669914811) ❤️""",
                            selectable=True,
                            auto_follow_links=True,
                        ),
                        ft.Markdown(
                            """@[Giampaolo-zzp](https://github.com/Giampaolo-zzp) | @茜语茜寻""",
                            selectable=True,
                            auto_follow_links=True,
                        ),
                        ft.TextButton(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda _: setattr(thank_sheet, "open", False)
                            or self.page.update(),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                    scroll=ft.ScrollMode.ALWAYS,
                ),
                padding=50,
            ),
            open=False,
        )
        spoon_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text(
                            "特别感谢以下人员在本程序开发阶段的赞助",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text("（按照金额排序 | 相同金额按昵称排序）", size=10),
                        ft.Markdown(
                            """炫饭的芙芙 | 130￥ 👑\n\nGiampaolo-zzp | 50￥\n\nKyle | 30￥\n\n昊阳（漩涡7人） | 8.88￥\n\n蔡亩 | 6￥\n\n小苗 | 6￥\n\nZero | 6￥\n\n遮天s忏悔 | 5.91￥\n\n青山如岱 | 5￥\n\nLYC(luis) | 1￥\n\nFuruya | 0.01￥\n\nwzr | 0.01￥""",
                            selectable=True,
                            auto_follow_links=False,
                        ),
                        ft.TextButton(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda _: setattr(spoon_sheet, "open", False)
                            or self.page.update(),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                    scroll=ft.ScrollMode.ALWAYS,
                ),
                padding=50,
            ),
            open=False,
        )
        general = tab_content("通用")
        download = tab_content("下载")
        resource = tab_content(
            "内容",
            ft.Text("是否允许 NSFW 内容？"),
            ft.Switch(
                value=app_config.get("wallpaper.allow_nsfw", False),
                on_change=_change_nsfw,
            ),
            ft.Divider(),
            self._build_wallpaper_source_settings_section(),
        )

        theme_dropdown = ft.Dropdown(
            label="界面主题",
            value=app_config.get("ui.theme", "auto"),
            options=[
                ft.DropdownOption(key="auto", text="跟随系统/主题"),
                ft.DropdownOption(key="light", text="浅色"),
                ft.DropdownOption(key="dark", text="深色"),
            ],
            on_change=self._change_theme_mode,
            width=220,
        )

        # 提示：当使用非默认主题配置时，建议将界面主题设为“跟随系统/主题”
        current_theme_profile = (
            str(app_config.get("ui.theme_profile", "default")).strip().lower()
        )
        use_custom_theme_profile = current_theme_profile != "default"

        reminder_text = (
            ft.Row(
                [
                    ft.Icon(ft.Icons.INFO, size=15),
                    ft.Text(
                        "已启用主题配置，建议将“界面主题”设置为“跟随系统/主题”，否则可能与主题配色冲突。",
                        size=12,
                    ),
                ]
            )
            if use_custom_theme_profile
            else None
        )

        theme_controls = self._build_theme_settings_controls()
        theme_section = ft.Column(
            controls=[ft.Text("主题", size=18, weight=ft.FontWeight.BOLD)]
            + theme_controls,
            spacing=8,
        )
        appearance = tab_content(
            "外观",
            # 界面主题
            ft.Column(
                [
                    ft.Text("界面", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [theme_dropdown],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    *([reminder_text] if reminder_text else []),
                ],
                spacing=8,
            ),
            # 主题配置
            ft.Container(height=8),
            theme_section,
        )
        about = tab_content(
            "关于",
            ft.Text(f"小树壁纸 Next v{VER}", size=16),
            ft.Text(
                f"{BUILD_VERSION}\nCopyright © 2023-2025 Little Tree Studio",
                size=12,
                color=ft.Colors.GREY,
            ),
            ft.Text(
                "部分壁纸源由 小树壁纸资源中心 和 IntelliMarkets-壁纸源市场 提供\nAI 生成由 pollinations.ai 提供\n\n当您使用本软件时，即表示您接受小树工作室用户协议及第三方数据提供方条款。",
                size=12,
                color=ft.Colors.GREY,
            ),
            ft.Row(
                controls=[
                    ft.TextButton(
                        "查看特别鸣谢",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(thank_sheet, "open", True)
                        or self.page.update(),
                    ),
                    ft.TextButton(
                        "查看赞助列表",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(spoon_sheet, "open", True)
                        or self.page.update(),
                    ),
                ]
            ),
            ft.Row(
                controls=[
                    ft.TextButton(
                        "查看许可证",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: self.page.launch_url(
                            "https://www.gnu.org/licenses/agpl-3.0.html"
                        ),
                    ),
                    ft.TextButton(
                        "查看依赖版权信息",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(license_sheet, "open", True)
                        or self.page.update(),
                    ),
                    ft.TextButton(
                        "查看用户协议",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: self.page.launch_url(
                            "https://docs.zsxiaoshu.cn/terms/wallpaper/user_agreement/"
                        ),
                    ),
                    ft.TextButton(
                        "查看二次开发协议",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: self.page.launch_url(
                            "https://docs.zsxiaoshu.cn/terms/wallpaper/secondary_development_agreement/"
                        ),
                    ),
                    ft.TextButton(
                        "查看数据提供方条款",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(third_party_sheet, "open", True)
                        or self.page.update(),
                    ),
                ]
            ),
        )

        settings_tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            padding=12,
            tabs=[
                ft.Tab(text="通用", icon=ft.Icons.SETTINGS, content=general),
                ft.Tab(text="资源", icon=ft.Icons.WALLPAPER, content=resource),
                ft.Tab(text="下载", icon=ft.Icons.DOWNLOAD, content=download),
                ft.Tab(text="外观", icon=ft.Icons.PALETTE, content=appearance),
                ft.Tab(text="关于", icon=ft.Icons.INFO, content=about),
                ft.Tab(
                    text="插件",
                    icon=ft.Icons.EXTENSION,
                    content=self._build_plugin_settings_content(),
                ),
            ],
            expand=True,
        )
        self._settings_tabs = settings_tabs
        self._settings_tab_indices = {
            "general": 0,
            "resource": 1,
            "content": 1,
            "download": 2,
            "ui": 3,
            "appearance": 3,
            "about": 4,
            "plugins": 5,
            "plugin": 5,
        }
        if self._pending_settings_tab:
            pending = None
            # Try numeric pending index first
            try:
                pending_idx = int(self._pending_settings_tab)
                if 0 <= pending_idx < len(settings_tabs.tabs):
                    pending = pending_idx
            except Exception:
                pass
            if pending is None:
                pending = self._settings_tab_indices.get(self._pending_settings_tab)
            if pending is not None:
                settings_tabs.selected_index = pending
            self._pending_settings_tab = None

        settings_body_controls = [settings_tabs]
        if SHOW_WATERMARK:
            settings_body_controls.append(build_watermark())

        return ft.View(
            "/settings",
            [
                ft.AppBar(
                    title=ft.Text("设置"),
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        tooltip="返回",
                        on_click=lambda _: self.page.go("/"),
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                ft.Stack(controls=settings_body_controls, expand=True),
                license_sheet,
                thank_sheet,
                spoon_sheet,
                third_party_sheet,
            ],
        )

    def build_test_warning_page(self):
        countdown_seconds = 5
        countdown_hint = ft.Text(
            f"请认真阅读提示，{countdown_seconds} 秒后可继续。",
            text_align=ft.TextAlign.CENTER,
        )
        enter_button = ft.Button(
            text=f"{countdown_seconds} 秒后可进入首页",
            icon=ft.Icons.HOME,
            disabled=True,
            on_click=lambda _: self.page.go("/"),
        )

        async def _count_down():
            remaining = countdown_seconds
            while remaining > 0:
                enter_button.text = f"{remaining} 秒后可进入首页"
                countdown_hint.value = f"请认真阅读提示，{remaining} 秒后可继续。"
                self.page.update()
                await asyncio.sleep(1)
                remaining -= 1
            enter_button.text = "进入首页"
            countdown_hint.value = "已确认提示，现在可以返回首页。"
            enter_button.disabled = False
            self.page.update()

        self.page.run_task(_count_down)

        return ft.View(
            "/test-warning",
            [
                ft.AppBar(
                    title=ft.Text("测试版警告"),
                    leading=ft.Icon(ft.Icons.WARNING),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.WARNING, color=ft.Colors.ORANGE, size=40),
                            ft.Text("测试版警告", size=30, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                "您正在使用小树壁纸 Next 的测试版。测试版可能包含不稳定的功能，甚至会导致数据丢失等严重问题。\n如果您不确定自己在做什么，请前往官网下载稳定版应用。",
                                text_align=ft.TextAlign.CENTER,
                            ),
                            countdown_hint,
                            enter_button,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                    alignment=ft.alignment.center,
                    padding=50,
                    expand=True,
                ),
            ],
        )
    def build_first_run_page(self):

        return ft.View(
            "/first-run",
            [
                ft.AppBar(
                    title=ft.Text("首次运行"),
                    leading=ft.Icon(ft.Icons.WARNING),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Column([]),
                            ft.Row(
                                [
                                    ft.Text("欢迎使用小树壁纸 Next！"),
                                    ft.TextButton("跳过引导",on_click=lambda _:self.page.go("/"))
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    alignment=ft.alignment.center,
                    padding=50,
                    expand=True,
                ),
            ],
        )

    def _change_theme_mode(self, e: ft.ControlEvent) -> None:
        value = e.control.value
        if value == "dark":
            self.page.theme_mode = ft.ThemeMode.DARK
            app_config.set("ui.theme", "dark")

        elif value == "light":
            self.page.theme_mode = ft.ThemeMode.LIGHT
            app_config.set("ui.theme", "light")
        else:
            self.page.theme_mode = ft.ThemeMode.SYSTEM
            app_config.set("ui.theme", "auto")
        self.page.update()
