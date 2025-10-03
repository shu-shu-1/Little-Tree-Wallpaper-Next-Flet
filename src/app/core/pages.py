"""Core page implementations for Little Tree Wallpaper Next."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import aiohttp
import flet as ft
import pyperclip
from loguru import logger

import ltwapi

from app.constants import BUILD_VERSION, HITOKOTO_API, SHOW_WATERMARK, VER
from app.paths import DATA_DIR, LICENSE_PATH
from app.ui_utils import build_watermark, copy_files_to_clipboard, copy_image_to_clipboard
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
    PermissionState,
    KNOWN_PERMISSIONS,
)
from app.plugins.events import EventDefinition, PluginEventBus

if TYPE_CHECKING:
    from app.plugins.base import PluginSettingsPage


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
    ):
        self.page = page
        self.event_bus = event_bus
        self.plugin_service = plugin_service
        self._plugin_runtime_cache: List[PluginRuntimeInfo] = list(plugin_runtime or [])
        self._known_permissions: Dict[str, PluginPermission] = dict(known_permissions or {})
        self._sync_known_permissions()
        # Flet Colors compatibility: some versions may not expose SURFACE_CONTAINER_LOW
        self._bgcolor_surface_low = getattr(ft.Colors, "SURFACE_CONTAINER_LOW", ft.Colors.SURFACE_CONTAINER_HIGHEST)
        self._event_definitions: List[EventDefinition] = list(event_definitions or [])
        self._plugin_list_column: Optional[ft.Column] = None
        self._plugin_file_picker: Optional[ft.FilePicker] = None
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
        self._reload_banner: ft.Banner | None = None
        self._reload_banner_open = False
        self._route_register: Callable[[AppRouteView], None] | None = None

        self._ensure_global_namespaces()

        self.home = self._build_home()
        self.resource = self._build_resource()
        self.sniff = self._build_sniff()
        self.favorite = self._build_favorite()
        self.test = self._build_test()

        self.page.run_task(self._load_bing_wallpaper)
        self.page.run_task(self._load_spotlight_wallpaper)

    def _sync_known_permissions(self) -> None:
        self._known_permissions.update(KNOWN_PERMISSIONS)

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
        # plugin-specific settings pages are available from the plugin card buttons

        # Only show the management panel here; plugin-specific pages are available
        # via the per-plugin "插件设置" button which navigates to a dedicated view.
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
        except Exception as exc:  # pragma: no cover - defensive logging
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
        logger.info(f"切换设置页面标签到 {normalized}")
        self._settings_tabs.selected_index = self._settings_tab_indices[normalized]
        self.page.update()
        return True

    def select_settings_tab_index(self, index: int) -> bool:
        # Allow selecting by numeric index. If tabs not yet created, save pending index.
        try:
            if index < 0:
                return False
        except Exception:
            return False
        if self._settings_tabs is None:
            logger.info(f"延迟切换设置页面索引到 {index}")
            # store as normalized string so existing pending logic can handle it
            self._pending_settings_tab = str(index)
            return True
        # guard against out-of-range
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
        self._hide_reload_banner()
        self._reload_plugins()

    def _show_reload_banner(self) -> None:
        if not self.page:
            return
        if self._reload_banner is None:
            self._reload_banner = ft.Banner(
                bgcolor=ft.Colors.AMBER_100,
                leading=ft.Icon(ft.Icons.RESTART_ALT, color=ft.Colors.AMBER_800),
                content=ft.Text("插件权限已更新，需要重新加载后生效。"),
                actions=[
                    ft.FilledButton(
                        "重新加载",
                        icon=ft.Icons.RESTART_ALT,
                        on_click=self._handle_reload_request,
                    )
                ],
            )
        if not self._reload_banner_open:
            self.page.open(self._reload_banner)
            self._reload_banner_open = True
        else:
            self.page.update()

    def _hide_reload_banner(self) -> None:
        if self.page and self._reload_banner and self._reload_banner_open:
            self.page.close(self._reload_banner)
            self._reload_banner_open = False
            self.page.update()

    def _sync_reload_banner(self) -> None:
        if not self.plugin_service or not hasattr(self.plugin_service, "is_reload_required"):
            self._hide_reload_banner()
            return
        try:
            pending = self.plugin_service.is_reload_required()
        except Exception:
            pending = False
        if pending:
            self._show_reload_banner()
        else:
            self._hide_reload_banner()

    def build_plugin_settings_view(self, plugin_id: str) -> ft.View:
        self._refresh_settings_registry()
        registration = self._settings_page_map.get(plugin_id)
        runtime = self._resolve_plugin_runtime(plugin_id)

        display_name = runtime.name if runtime else plugin_id
        description_text = (runtime.description if runtime else "") or ""
        if registration:
            try:
                plugin_control = registration.builder()
            except Exception as exc:  # pragma: no cover - defensive logging
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
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            tooltip="刷新插件状态",
                            on_click=lambda _: self._refresh_plugin_list(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.RESTART_ALT,
                            tooltip="重新加载所有插件",
                            on_click=lambda _: self._reload_plugins(),
                        ),
                        ft.FilledTonalButton(
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
        self._sync_reload_banner()

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

        all_permissions = set(runtime.permissions_required) | set(runtime.permissions_granted.keys())
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
                        f"每次询问：{', '.join(prompt_permissions)}",
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

        controls.append(ft.Text(f"权限：{permissions_summary}", size=12, color=ft.Colors.GREY))
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

    def _dependency_detail_controls(self, runtime: PluginRuntimeInfo) -> list[ft.Control]:
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
        keys = sorted(set(runtime.permission_states.keys()) | set(runtime.permissions_required))
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
                subtitle=ft.Text(manifest.description if manifest else runtime.description or "无"),
            ),
            ft.ListTile(title=ft.Text("作者"), subtitle=ft.Text(manifest.author if manifest else "未知")),
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
                        str(runtime.source_path) if runtime.source_path else runtime.module_name or "未知"
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
                subtitle=ft.Column(self._dependency_detail_controls(runtime), spacing=4),
            )
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"插件详情 - {runtime.name}"),
            content=ft.Container(
                width=400,
                content=ft.Column(info_rows, tight=True, spacing=4),
            ),
            actions=[
                ft.TextButton("关闭", on_click=lambda _: self._close_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _show_permission_dialog(self, runtime: PluginRuntimeInfo) -> None:
        self._sync_known_permissions()
        requested = sorted(set(runtime.permission_states.keys()) | set(runtime.permissions_required))

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
                if not self._update_permission_state(runtime.identifier, permission_id, new_state):
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
                            ft.DropdownOption(key="prompt", text="每次询问"),
                            ft.DropdownOption(key="allow", text="允许"),
                        ],
                        on_change=_on_choice,
                    ),
                )
            )

        apply_button = ft.FilledButton("确定", icon=ft.Icons.CHECK, disabled=True, on_click=_submit)
        action_holder["button"] = apply_button

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"权限管理 - {runtime.name}"),
            content=ft.Container(
                width=420,
                content=ft.Column(rows, tight=True, spacing=4, scroll=ft.ScrollMode.AUTO),
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
            self._sync_reload_banner()
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
            self._sync_reload_banner()
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
            self._sync_reload_banner()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"删除插件失败: {exc}")
            self._show_snackbar(f"删除失败：{exc}", error=True)
        finally:
            self._close_dialog()

    def _reload_plugins(self) -> None:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            return
        try:
            self._hide_reload_banner()
            self.plugin_service.reload()
            self._show_snackbar("插件正在重新加载…")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"重新加载插件失败: {exc}")
            self._show_snackbar(f"重新加载失败：{exc}", error=True)

    def _open_dialog(self, dialog: ft.AlertDialog) -> None:
        self.page.dialog = dialog
        self.page.open(self.page.dialog)

    def _close_dialog(self) -> None:
        if self.page.dialog is not None:
            self.page.close(self.page.dialog)

    def _ensure_plugin_file_picker(self) -> None:
        if self._plugin_file_picker is None:
            self._plugin_file_picker = ft.FilePicker(on_result=self._handle_import_result)
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
            self._show_snackbar("插件已导入，但无法识别 manifest，将使用默认设置重新加载。")
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
                        ft.DropdownOption(key="prompt", text="每次询问"),
                        ft.DropdownOption(key="allow", text="允许"),
                    ],
                )
                toggles[perm] = selector
                permission_controls.append(
                    ft.Column(
                        [
                            selector,
                            ft.Text(f"权限 ID：{perm}\n{detail}", size=12, color=ft.Colors.GREY),
                        ],
                        spacing=4,
                    )
                )
        else:
            permission_controls.append(
                ft.Text("该插件未请求额外权限，可直接加载。", size=12, color=ft.Colors.GREY)
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
            self._sync_reload_banner()

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
                        ft.Text(description, size=12) if description else ft.Container(),
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

    def _apply_import_permissions(self, identifier: str, toggles: dict[str, ft.Dropdown]) -> None:
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
        self._sync_reload_banner()

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
            for permission in sorted(self._known_permissions.values(), key=lambda p: p.identifier)
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
            snapshot = self._global_data.publish("resource.bing", entry_id, payload_with_meta)
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

    def _emit_bing_action(self, action: str, success: bool, extra: Dict[str, Any] | None = None) -> None:
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
        with open(LICENSE_PATH / "LXGWNeoXiHeiPlus-IPA-1.0.md", encoding="utf-8") as f1:
            with open(LICENSE_PATH / "aiohttp.txt", encoding="utf-8") as f2:
                with open(LICENSE_PATH / "Flet-Apache-2.0.txt", encoding="utf-8") as f3:
                    with open(
                        LICENSE_PATH / "LXGWWenKaiLite-OFL-1.1.txt", encoding="utf-8"
                    ) as f4:
                        return f"# LXGWNeoXiHeiPlus 字体\n\n{f1.read()}\n\n# aiohttp 库\n\n{f2.read()}\n\n# Flet 库\n\n{f3.read()}\n\n# LXGWWenKaiLite 字体\n\n{f4.read()}"

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
            self._emit_resource_event("resource.bing.updated", self._bing_event_payload())
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
            self._emit_resource_event("resource.spotlight.updated", self._spotlight_event_payload())
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
        )
        self.hitokoto_loading = ft.ProgressRing(visible=False, width=24, height=24)
        self.hitokoto_text = ft.Text("", size=16, font_family="HITOKOTOFont")
        refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH, tooltip="刷新一言", on_click=self.refresh_hitokoto
        )
        return ft.Column(
            [
                ft.Text("当前壁纸", size=30),
                ft.Row(
                    [
                        self.img,
                        ft.Column(
                            [
                                ft.TextButton("导出", icon=ft.Icons.SAVE_ALT),
                                ft.TextButton("更换", icon=ft.Icons.PHOTO_LIBRARY),
                                ft.TextButton("收藏", icon=ft.Icons.STAR),
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
            expand=True,
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
                ft.Tab(text="其他", icon=ft.Icons.SUBJECT),
            ],
            animation_duration=300,
        )
        return ft.Column(
            [
                ft.Text("资源", size=30),
                ft.Container(
                    content=self.resource_tabs,
                    expand=True,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ],
            expand=True,
        )

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
                DATA_DIR / "Wallpaper",
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
            nonlocal set_button, favorite_button, download_button, copy_button, copy_menu

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
                DATA_DIR / "Wallpaper",
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
        favorite_button = ft.FilledTonalButton("收藏", icon=ft.Icons.STAR)
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
                spotlight.get("title"), f"Windows-Spotlight-{self.spotlight_current_index + 1}"
            )

            wallpaper_path = ltwapi.download_file(
                url,
                DATA_DIR / "Wallpaper",
                filename,
                progress_callback=progress_callback,
            )

            success = wallpaper_path is not None
            handled = False
            if success:
                self._emit_download_completed("spotlight", normalized_action, wallpaper_path)
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
        favorite_button = ft.FilledTonalButton("收藏", icon=ft.Icons.STAR)
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
        extra_spotlight_actions = self._build_plugin_actions(self.spotlight_action_factories)
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
        return ft.Column(
            [
                ft.Text("收藏", size=30),
                ft.Text("收藏夹功能正在开发中，敬请期待~"),
            ],
            expand=True,
        )

    def _build_test(self):
        from app.paths import ASSET_DIR

        return ft.Column(
            [
                ft.Text("测试和调试", size=30),
                ft.Text("这里是测试和调试专用区域"),
                ft.Image(src=ASSET_DIR / "images" / "test.gif"),
            ],
            expand=True,
        )

    def build_settings_view(self):
        def tab_content(title: str, *controls: ft.Control):
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(title, size=24),
                        ft.Column(list(controls), spacing=12),
                    ],
                    spacing=16,
                    expand=True,
                ),
                padding=20,
                expand=True,
            )

        license_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text("版权信息", weight=ft.FontWeight.BOLD),
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
                            """Aimer | 200￥ 👑\n\nXiaoMu | 150￥""",
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
                            """炫饭的芙芙 | 100￥ 👑\n\nGiampaolo-zzp | 50￥\n\nKyle | 30￥\n\n昊阳（漩涡7人） | 8.88￥\n\n蔡亩 | 6￥\n\n小苗 | 6￥\n\nZero | 6￥\n\n遮天s忏悔 | 5.91￥\n\n青山如岱 | 5￥\n\nLYC(luis) | 1￥\n\nFuruya | 0.01￥\n\nwzr | 0.01￥""",
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
        general = tab_content(
            "通用",
        )
        download = tab_content(
            "下载",
        )

        ui = tab_content(
            "界面",
            ft.Dropdown(
                label="界面主题",
                value="auto",
                options=[
                    ft.DropdownOption(key="auto", text="跟随系统"),
                    ft.DropdownOption(key="light", text="浅色"),
                    ft.DropdownOption(key="dark", text="深色"),
                ],
                on_change=self._change_theme_mode,
            ),
        )
        about = tab_content(
            "关于",
            ft.Text(f"小树壁纸 Next v{VER}", size=16),
            ft.Text(
                f"{BUILD_VERSION}\nCopyright © 2023-2025 Little Tree Studio",
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
                        "查看版权信息",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(license_sheet, "open", True)
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
                ft.Tab(text="下载", icon=ft.Icons.DOWNLOAD, content=download),
                ft.Tab(text="界面", icon=ft.Icons.PALETTE, content=ui),
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
            "download": 1,
            "ui": 2,
            "about": 3,
            "plugins": 4,
            "plugin": 4,
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
                            ft.Icon(ft.Icons.WARNING, color=ft.Colors.ORANGE),
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

    def _change_theme_mode(self, e: ft.ControlEvent) -> None:
        value = e.control.value
        if value == "dark":
            self.page.theme_mode = ft.ThemeMode.DARK
        elif value == "light":
            self.page.theme_mode = ft.ThemeMode.LIGHT
        else:
            self.page.theme_mode = None
        self.page.update()