"""Sample plugin demonstrating the Little Tree Wallpaper plugin API."""

from __future__ import annotations

import json
from datetime import datetime

import flet as ft

from app.plugins import (
    AppNavigationView,
    AppRouteView,
    Plugin,
    PluginContext,
    PluginManifest,
)


class SamplePlugin(Plugin):
    manifest = PluginManifest(
        identifier="sample",
        name="示例插件",
        version="0.1.0",
        description="演示 Little Tree Wallpaper Next 插件 API 的主要功能。",
        author="Little Tree Studio",
        homepage="https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet",
        permissions=("resource_data",),
    )

    # 向后兼容旧代码路径
    name = manifest.name
    version = manifest.version

    def activate(self, context: PluginContext) -> None:  # type: ignore[override]
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
                context.logger.warning("配置文件损坏，已使用默认配置", config_path=str(config_path))

        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

        data_dir = context.plugin_data_dir(create=True)
        cache_dir = context.plugin_cache_dir(create=True)
        context.add_metadata(
            "sample.storage",
            {"data": str(data_dir), "config": str(config_path), "cache": str(cache_dir)},
        )

        def open_details(_: ft.ControlEvent) -> None:
            context.page.go("/sample/details")

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

            return ft.Container(
                expand=True,
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Text("Little Tree Wallpaper 示例插件", size=20),
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
                        ft.Text(""),
                        ft.Text("全局数据演示:"),
                        ft.Text(f"最新 Bing 标题: {bing_title}"),
                        ft.Text(f"数据 ID: {bing_id}" if bing_id else "数据 ID: 未知"),
                        ft.Divider(),
                        ft.Text("演示功能: 点击下方按钮跳转到自定义路由。"),
                        ft.FilledButton(
                            text="打开示例路由",
                            icon=ft.Icons.ARROW_FORWARD,
                            on_click=open_details,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    spacing=10,
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

        context.register_settings_page(
            label="示例插件",
            icon=ft.Icons.EMOJI_OBJECTS,
            button_label="插件设置",
            description="本页面演示如何通过 register_settings_page 提供插件专属的设置视图。",
            builder=lambda: ft.Container(
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Text("这里是示例插件的设置页"),
                        ft.Text("可以在此展示自定义配置或状态。"),
                        ft.Text(f"配置文件: {config_path}", selectable=True),
                    ],
                    spacing=12,
                ),
            ),
        )

        def announce_ready() -> None:
            context.logger.info(
                "示例插件已加载，配置文件位于 {config_path}",
                config_path=str(config_path),
            )

        context.add_startup_hook(announce_ready)


PLUGIN = SamplePlugin()
