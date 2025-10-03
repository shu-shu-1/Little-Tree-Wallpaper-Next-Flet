"""Sample plugin demonstrating the Little Tree Wallpaper plugin API."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

import flet as ft

from app.plugins import (
    AppNavigationView,
    AppRouteView,
    Plugin,
    PluginContext,
    PluginManifest,
    PluginEvent,
    PermissionState,
)
from app.constants import SETTINGS_TAB_PLUGINS


class SamplePlugin(Plugin):
    manifest = PluginManifest(
        identifier="sample",
        name="示例插件",
        version="0.1.0",
        description="演示 Little Tree Wallpaper Next 插件 API 的主要功能。",
        author="Little Tree Studio",
        homepage="https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet",
        permissions=
        (
            "resource_data",
            "app_route",
            "app_home",
            "app_settings",
            "wallpaper_control",
        ),
    )

    # 向后兼容旧代码路径
    name = manifest.name
    version = manifest.version

    def __init__(self) -> None:
        self._download_unsubscribe = None
        self._latest_download_path: str | None = None
        self._download_log: list[str] = []

    def activate(self, context: PluginContext) -> None:  # type: ignore[override]
        if self._download_unsubscribe:
            try:
                self._download_unsubscribe()
            except Exception as exc:  # pragma: no cover - defensive logging
                context.logger.warning(
                    "取消旧的下载完成事件订阅失败: {error}",
                    error=str(exc),
                )
            self._download_unsubscribe = None

        config_path = context.plugin_config_path("settings.json", create=True)
        config: dict[str, object] = {
            "welcome_message": "欢迎使用 Little Tree Wallpaper 示例插件！",
            "activated_at": datetime.now().isoformat(timespec="seconds"),
        }

        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    config.update(existing)
            except json.JSONDecodeError:
                context.logger.warning(
                    "配置文件损坏，已使用默认配置",
                    config_path=str(config_path),
                )

        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        data_dir = context.plugin_data_dir(create=True)
        cache_dir = context.plugin_cache_dir(create=True)
        context.add_metadata(
            "sample.storage",
            {"data": str(data_dir), "config": str(config_path), "cache": str(cache_dir)},
        )
        context.add_metadata(
            "sample.permissions",
            {
                perm: context.permissions.get(perm, PermissionState.PROMPT).value
                for perm in self.manifest.permissions
            },
        )

        download_log_ref: ft.Ref[ft.ListView] = ft.Ref[ft.ListView]()
        last_download_ref: ft.Ref[ft.Text] = ft.Ref[ft.Text]()
        operation_status_ref: ft.Ref[ft.Text] = ft.Ref[ft.Text]()
        set_wallpaper_button_ref: ft.Ref[ft.FilledTonalButton] = ft.Ref[ft.FilledTonalButton]()

        def open_details(_: ft.ControlEvent) -> None:
            context.page.go("/sample/details")

        def update_operation_status(message: str, outcome: str = "info") -> None:
            label = operation_status_ref.current
            if label is None:
                return
            label.value = message
            if outcome == "success":
                label.color = ft.Colors.PRIMARY
            elif outcome == "pending":
                label.color = ft.Colors.AMBER
            elif outcome == "error":
                label.color = ft.Colors.ERROR
            else:
                label.color = ft.Colors.GREY
            context.page.update()

        def run_operation(label: str, executor: Callable[[], object]) -> None:
            try:
                result = executor()
            except Exception as exc:  # pragma: no cover - defensive logging
                context.logger.error(
                    "操作 {label} 执行失败: {error}",
                    label=label,
                    error=str(exc),
                )
                update_operation_status(f"❌ {label} 发生异常: {exc}", outcome="error")
                return
            if not hasattr(result, "success"):
                update_operation_status(
                    f"⚠️ {label}: 返回值 {type(result).__name__} 无法解析。",
                    outcome="error",
                )
                return
            success = bool(result.success)
            error_code = getattr(result, "error", None)
            permission = getattr(result, "permission", None)
            message = getattr(result, "message", "") or (
                "操作成功" if success else (error_code or "执行失败")
            )
            if error_code == "permission_denied":
                icon = "🚫"
                outcome = "error"
                if not message:
                    message = f"已拒绝权限：{permission or '未知权限'}"
            else:
                icon = "✅" if success else "⚠️"
                outcome = "success" if success else "error"
            if success:
                context.logger.info("操作 {label} 执行成功", label=label)
            else:
                context.logger.warning(
                    "操作 {label} 未成功: {error}",
                    label=label,
                    error=error_code or "unknown",
                )
            update_operation_status(f"{icon} {label}: {message}", outcome=outcome)

        def set_last_wallpaper(_: ft.ControlEvent) -> None:
            if not self._latest_download_path:
                update_operation_status(
                    "⚠️ 暂无可用的下载文件，请先在资源页完成一次下载。",
                    outcome="error",
                )
                return
            run_operation(
                "set_wallpaper(最近下载)",
                lambda: context.set_wallpaper(self._latest_download_path or ""),
            )

        def handle_download_event(event: PluginEvent) -> None:
            payload = event.payload or {}
            source = str(payload.get("source", "unknown"))
            action = str(payload.get("action", event.type))
            file_path = payload.get("file_path")
            timestamp = datetime.now().strftime("%H:%M:%S")
            summary = f"[{timestamp}] {source} · {action}"
            if file_path:
                summary += f" → {file_path}"
            self._download_log.append(summary)
            self._download_log = self._download_log[-12:]
            log_view = download_log_ref.current
            if log_view is not None:
                log_view.controls.clear()
                log_view.controls.extend(
                    ft.Text(item, size=12, selectable=True) for item in self._download_log
                )
            hint = last_download_ref.current
            if hint is not None:
                if file_path:
                    self._latest_download_path = str(file_path)
                    hint.value = self._latest_download_path
                    hint.color = ft.Colors.ON_SURFACE
                else:
                    hint.value = "事件未携带文件路径。"
                    hint.color = ft.Colors.AMBER
            button = set_wallpaper_button_ref.current
            if button is not None:
                button.disabled = not bool(file_path)
            context.page.update()
            context.logger.info(
                "示例插件收到下载完成事件，来源 {source}，动作 {action}",
                source=source,
                action=action,
            )

        if context.event_bus:
            self._download_unsubscribe = context.subscribe_event(
                "resource.download.completed",
                handle_download_event,
            )
            context.logger.info("示例插件已订阅 resource.download.completed 事件")
        else:
            context.logger.warning("事件总线不可用，示例插件无法记录下载完成事件。")

        def build_navigation_content() -> ft.Control:
            bing_snapshot = (
                context.latest_data("resource.bing")
                if context.has_permission("resource_data")
                else None
            )
            if bing_snapshot:
                bing_payload = bing_snapshot.get("payload", {}) or {}
                bing_title = bing_payload.get("title") or "未知"
                bing_id = bing_snapshot.get("identifier")
            else:
                bing_title = "暂无数据（需要授权资源数据权限）"
                bing_id = None

            permission_states = {
                PermissionState.GRANTED: ("已授权", ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN),
                PermissionState.PROMPT: ("待确认", ft.Icons.HOURGLASS_BOTTOM, ft.Colors.AMBER),
                PermissionState.DENIED: ("已拒绝", ft.Icons.BLOCK, ft.Colors.ERROR),
            }
            permission_rows: list[ft.Control] = []
            for perm in self.manifest.permissions:
                state = context.permissions.get(perm, PermissionState.PROMPT)
                label, icon_name, icon_color = permission_states[state]
                permission_rows.append(
                    ft.Row(
                        controls=[
                            ft.Icon(icon_name, color=icon_color, size=16),
                            ft.Text(f"{perm}（{label}）", size=12),
                        ],
                        spacing=6,
                    )
                )

            download_bg = getattr(ft.Colors, "SURFACE_CONTAINER_LOW", ft.Colors.ON_SURFACE_VARIANT)
            download_log_view = ft.ListView(
                ref=download_log_ref,
                controls=[
                    ft.Text(item, size=12, selectable=True) for item in self._download_log
                ],
                expand=True,
                spacing=6,
                auto_scroll=True,
            )
            last_download_value = ft.Text(
                self._latest_download_path or "(暂无下载记录)",
                size=12,
                color=ft.Colors.ON_SURFACE if self._latest_download_path else ft.Colors.GREY,
                selectable=True,
                ref=last_download_ref,
            )
            operation_status_text = ft.Text(
                "点击下方按钮测试插件运行时提供的操作接口。",
                size=12,
                color=ft.Colors.GREY,
                ref=operation_status_ref,
            )
            set_wallpaper_button = ft.FilledTonalButton(
                "使用插件接口设置最近下载的壁纸",
                icon=ft.Icons.WALLPAPER,
                disabled=not bool(self._latest_download_path),
                ref=set_wallpaper_button_ref,
                on_click=set_last_wallpaper,
            )
            operations_row = ft.Row(
                spacing=8,
                run_spacing=8,
                wrap=True,
                controls=[
                    ft.FilledButton(
                        text="打开示例路由",
                        icon=ft.Icons.ARROW_FORWARD,
                        on_click=open_details,
                    ),
                    ft.FilledButton(
                        text="跳转到设置页",
                        icon=ft.Icons.SETTINGS,
                        on_click=lambda _: run_operation(
                            "open_route('/settings')",
                            lambda: context.open_route("/settings"),
                        ),
                    ),
                    ft.OutlinedButton(
                        text="切换到资源导航",
                        icon=ft.Icons.ARCHIVE,
                        on_click=lambda _: run_operation(
                            "switch_home('resource')",
                            lambda: context.switch_home("resource"),
                        ),
                    ),
                    ft.OutlinedButton(
                        text="打开设置-插件标签",
                        icon=ft.Icons.EXTENSION,
                        # Flet Tabs are indexed by number (0-based). Use numeric index to switch reliably.
                        on_click=lambda _: run_operation(
                            f"open_settings_tab({SETTINGS_TAB_PLUGINS})",
                            lambda: context.open_settings_tab(SETTINGS_TAB_PLUGINS),
                        ),
                    ),
                    set_wallpaper_button,
                ],
            )

            return ft.Container(
                expand=True,
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Text("Little Tree Wallpaper 示例插件", size=20),
                        ft.Container(
                            padding=12,
                            bgcolor=getattr(ft.Colors, "SURFACE_CONTAINER_LOW", ft.Colors.AMBER_50),
                            border_radius=12,
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        "此插件包含一个专属设置页",
                                        size=13,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "在“设置 → 插件管理”中点击“插件设置”按钮，可修改欢迎语，并查看数据/配置/缓存路径。",
                                        size=12,
                                        color=ft.Colors.GREY,
                                    ),
                                ],
                                spacing=4,
                            ),
                        ),
                        ft.Text(str(config.get("welcome_message"))),
                        ft.Text(f"插件版本: {self.manifest.version}"),
                        ft.Text(
                            f"应用版本: {context.metadata.get('app_version', 'unknown')}"
                        ),
                        ft.Text("专属数据目录:"),
                        ft.Text(str(data_dir), selectable=True),
                        ft.Text("配置文件位置:"),
                        ft.Text(str(config_path), selectable=True),
                        ft.Text("缓存目录:"),
                        ft.Text(str(cache_dir), selectable=True),
                        ft.Divider(),
                        ft.Text("全局数据演示:", size=14, weight=ft.FontWeight.BOLD),
                        ft.Text(f"最新 Bing 标题: {bing_title}"),
                        ft.Text(f"数据 ID: {bing_id}" if bing_id else "数据 ID: 未知"),
                        ft.Divider(),
                        ft.Text("权限状态", size=14, weight=ft.FontWeight.BOLD),
                        ft.Column(permission_rows, spacing=4),
                        ft.Divider(),
                        ft.Text("下载完成事件日志", size=14, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=download_log_view,
                            height=180,
                            padding=12,
                            bgcolor=download_bg,
                            border_radius=12,
                        ),
                        ft.Text("最近一次下载文件:", size=12, color=ft.Colors.GREY),
                        last_download_value,
                        ft.Divider(),
                        ft.Text("插件操作沙盒", size=14, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "提示：操作会触发权限检查，首次使用时应用可能会弹出授权对话框。",
                            size=11,
                            color=ft.Colors.GREY,
                        ),
                        operation_status_text,
                        operations_row,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO
                ),
            )

        def build_details_view() -> ft.View:
            return ft.View(
                "/sample/details",
                controls=[
                    ft.Container(
                        expand=True,
                        padding=20,
                        content=ft.Column(
                            controls=[
                                ft.Text("示例路由页面"),
                                ft.Text("这里展示了如何注册自定义路由与视图。"),
                                ft.Text(
                                    f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                                ),
                                ft.ElevatedButton(
                                    "返回首页",
                                    icon=ft.Icons.HOME,
                                    on_click=lambda _: context.page.go("/"),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            horizontal_alignment=ft.CrossAxisAlignment.START,
                            spacing=12,
                        ),
                    )
                ],
                appbar=ft.AppBar(
                    title=ft.Text("示例插件"),
                    leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: context.page.go("/")),
                ),
            )

        context.add_navigation_view(
            AppNavigationView(
                id="sample",
                label="示例",
                icon=ft.Icons.EMOJI_OBJECTS_OUTLINED,
                selected_icon=ft.Icons.EMOJI_OBJECTS,
                content=build_navigation_content(),
            )
        )

        context.add_route_view(
            AppRouteView(
                route="/sample/details",
                builder=build_details_view,
            )
        )

        context.add_bing_action(
            lambda: ft.FilledTonalButton(
                "示例操作",
                icon=ft.Icons.EXTENSION,
                on_click=lambda _: context.logger.info("示例插件 Bing 扩展按钮被点击"),
            )
        )

        context.add_spotlight_action(
            lambda: ft.OutlinedButton(
                "查看示例路由",
                icon=ft.Icons.PAGEVIEW,
                on_click=lambda _: context.page.go("/sample/details"),
            )
        )

        def build_settings_page() -> ft.Control:
            welcome_field = ft.TextField(
                label="欢迎语",
                value=str(config.get("welcome_message", "")),
                expand=True,
            )
            status_text = ft.Text("", size=12, color=ft.Colors.GREY)

            def save_settings(_: ft.ControlEvent) -> None:
                message = welcome_field.value.strip() or "欢迎使用 Little Tree Wallpaper 示例插件！"
                config["welcome_message"] = message
                config["updated_at"] = datetime.now().isoformat(timespec="seconds")
                config_path.write_text(
                    json.dumps(config, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                status_text.value = f"✅ 已保存，最后更新：{datetime.now().strftime('%H:%M:%S')}"
                status_text.color = ft.Colors.GREEN
                context.logger.info("示例插件设置已更新，欢迎语为 {message}", message=message)
                context.page.update()

            save_button = ft.FilledButton(
                "保存设置",
                icon=ft.Icons.SAVE,
                on_click=save_settings,
            )

            return ft.Container(
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Text("示例插件设置", size=20, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "修改示例插件的欢迎语并了解配置文件所在位置。",
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                        welcome_field,
                        ft.Row([save_button], alignment=ft.MainAxisAlignment.END),
                        status_text,
                        ft.Divider(),
                        ft.Text("配置文件路径", size=12, color=ft.Colors.GREY),
                        ft.Text(str(config_path), selectable=True),
                        ft.Text("数据目录", size=12, color=ft.Colors.GREY),
                        ft.Text(str(data_dir), selectable=True),
                        ft.Text("缓存目录", size=12, color=ft.Colors.GREY),
                        ft.Text(str(cache_dir), selectable=True),
                    ],
                    spacing=12,
                    tight=True,
                ),
            )

        context.register_settings_page(
            label="示例插件",
            icon=ft.Icons.EMOJI_OBJECTS,
            button_label="插件设置",
            description="本页面演示如何通过 register_settings_page 提供插件专属的设置视图，并保存自定义配置。",
            builder=build_settings_page,
        )

        def announce_ready() -> None:
            context.logger.info(
                "示例插件已加载，配置文件位于 {config_path}",
                config_path=str(config_path),
            )

        context.add_startup_hook(announce_ready)


PLUGIN = SamplePlugin()
