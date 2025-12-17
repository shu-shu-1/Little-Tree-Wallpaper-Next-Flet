# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Little Tree Studio <studio@zsxiaoshu.cn>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
商店UI组件
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

import flet as ft
from loguru import logger

from .models import ResourceMetadata
from .service import StoreService, StoreServiceError

if TYPE_CHECKING:
    from app.settings import SettingsStore


class StoreUI:
    """商店页面UI管理器"""
    
    def __init__(
        self,
        page: ft.Page,
        settings: SettingsStore,
        on_install_theme: Callable[[ResourceMetadata], None] | None = None,
        on_install_plugin: Callable[[ResourceMetadata], None] | None = None,
        on_install_wallpaper_source: Callable[[ResourceMetadata], None] | None = None,
    ):
        """
        初始化商店UI
        
        Args:
            page: Flet页面对象
            settings: 设置存储
            on_install_theme: 主题安装回调
            on_install_plugin: 插件安装回调
            on_install_wallpaper_source: 壁纸源安装回调
        """
        self.page = page
        self.settings = settings
        self.on_install_theme = on_install_theme
        self.on_install_plugin = on_install_plugin
        self.on_install_wallpaper_source = on_install_wallpaper_source
        
        # 获取自定义源URL
        custom_url = settings.get("store.custom_source_url")
        self.service = StoreService(base_url=custom_url)
        
        # UI状态
        self._current_tab: Literal["theme", "resources", "plugins"] = "theme"
        self._loading = False
        self._error_message: str | None = None
        self._resources: list[ResourceMetadata] = []
        
        # UI组件引用
        self._tabs: ft.Tabs | None = None
        self._loading_indicator: ft.ProgressRing | None = None
        self._error_text: ft.Text | None = None
        self._content_column: ft.Column | None = None
        self._resource_grid: ft.GridView | None = None
    
    def build(self) -> ft.Control:
        """构建商店页面"""
        # 标签页
        self._tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            on_change=self._handle_tab_change,
            tabs=[
                ft.Tab(text="主题", icon=ft.Icons.PALETTE),
                ft.Tab(text="壁纸源", icon=ft.Icons.WALLPAPER),
                ft.Tab(text="插件", icon=ft.Icons.EXTENSION),
            ],
        )
        
        # 加载指示器
        self._loading_indicator = ft.ProgressRing(visible=False)
        
        # 错误提示
        self._error_text = ft.Text(
            "",
            color=ft.Colors.ERROR,
            visible=False,
        )
        
        # 资源网格
        self._resource_grid = ft.GridView(
            expand=True,
            runs_count=3,
            max_extent=350,
            child_aspect_ratio=0.85,
            spacing=16,
            run_spacing=16,
        )
        
        # 内容区域
        self._content_column = ft.Column(
            [
                ft.Row(
                    [
                        self._loading_indicator,
                        self._error_text,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                self._resource_grid,
            ],
            expand=True,
            spacing=16,
        )
        
        # 主容器
        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "资源商店",
                                size=24,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "获取主题、壁纸源和插件",
                                size=14,
                                color=ft.Colors.GREY,
                            ),
                        ],
                        spacing=4,
                    ),
                    padding=ft.padding.only(left=16, top=16, right=16, bottom=8),
                ),
                self._tabs,
                ft.Container(
                    content=self._content_column,
                    padding=16,
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
        )
    
    async def load_resources(self):
        """加载当前标签的资源"""
        if self._loading:
            return
        
        self._loading = True
        self._error_message = None
        
        if self._loading_indicator:
            self._loading_indicator.visible = True
        if self._error_text:
            self._error_text.visible = False
        if self._resource_grid:
            self._resource_grid.controls.clear()
        
        self.page.update()
        
        try:
            # 根据当前标签获取对应类型的资源
            resource_type = self._current_tab
            self._resources = await self.service.get_all_resources(resource_type)
            
            # 构建资源卡片
            if self._resource_grid:
                for resource in self._resources:
                    card = self._build_resource_card(resource)
                    self._resource_grid.controls.append(card)
            
        except StoreServiceError as e:
            self._error_message = str(e)
            if self._error_text:
                self._error_text.value = f"加载失败: {self._error_message}"
                self._error_text.visible = True
            logger.error(f"加载商店资源失败: {e}")
        
        finally:
            self._loading = False
            if self._loading_indicator:
                self._loading_indicator.visible = False
            self.page.update()
    
    def _build_resource_card(self, resource: ResourceMetadata) -> ft.Control:
        """构建资源卡片"""
        # 获取图标
        icon_url = self.service.resolve_icon_url(resource)
        
        # 图标组件
        if icon_url:
            if icon_url.startswith("data:"):
                # Base64图标
                icon_widget = ft.Image(
                    src_base64=icon_url.split(",")[1] if "," in icon_url else icon_url,
                    width=60,
                    height=60,
                    fit=ft.ImageFit.CONTAIN,
                )
            else:
                # URL图标
                icon_widget = ft.Image(
                    src=icon_url,
                    width=60,
                    height=60,
                    fit=ft.ImageFit.CONTAIN,
                    error_content=ft.Icon(ft.Icons.BROKEN_IMAGE, size=60),
                )
        else:
            # 默认图标
            icon_map = {
                "theme": ft.Icons.PALETTE,
                "wallpaper_source": ft.Icons.WALLPAPER,
                "plugin": ft.Icons.EXTENSION,
            }
            icon_widget = ft.Icon(
                icon_map.get(resource.type, ft.Icons.HELP),
                size=60,
            )
        
        # 标签
        tags_row = ft.Row(
            [
                ft.Container(
                    content=ft.Text(tag, size=10),
                    padding=ft.padding.symmetric(horizontal=8, vertical=2),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    border_radius=12,
                )
                for tag in resource.tags[:3]  # 最多显示3个标签
            ],
            spacing=4,
            wrap=True,
        )
        
        # 详情按钮
        def show_detail(_):
            self._show_resource_detail(resource)
        
        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        # 图标
                        ft.Container(
                            content=icon_widget,
                            alignment=ft.alignment.center,
                            padding=8,
                        ),
                        # 名称
                        ft.Text(
                            resource.name,
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        # 版本
                        ft.Text(
                            f"v{resource.version}",
                            size=12,
                            color=ft.Colors.GREY,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        # 简介
                        ft.Text(
                            resource.summary,
                            size=12,
                            text_align=ft.TextAlign.CENTER,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        # 标签
                        tags_row if resource.tags else ft.Container(height=20),
                        # 操作按钮
                        ft.Row(
                            [
                                ft.FilledButton(
                                    "查看详情",
                                    icon=ft.Icons.INFO_OUTLINED,
                                    on_click=show_detail,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=16,
            ),
        )
    
    def _show_resource_detail(self, resource: ResourceMetadata):
        """显示资源详情对话框"""
        # 获取图标
        icon_url = self.service.resolve_icon_url(resource)
        
        # 图标组件
        if icon_url:
            if icon_url.startswith("data:"):
                icon_widget = ft.Image(
                    src_base64=icon_url.split(",")[1] if "," in icon_url else icon_url,
                    width=80,
                    height=80,
                    fit=ft.ImageFit.CONTAIN,
                )
            else:
                icon_widget = ft.Image(
                    src=icon_url,
                    width=80,
                    height=80,
                    fit=ft.ImageFit.CONTAIN,
                    error_content=ft.Icon(ft.Icons.BROKEN_IMAGE, size=80),
                )
        else:
            icon_map = {
                "theme": ft.Icons.PALETTE,
                "wallpaper_source": ft.Icons.WALLPAPER,
                "plugin": ft.Icons.EXTENSION,
            }
            icon_widget = ft.Icon(
                icon_map.get(resource.type, ft.Icons.HELP),
                size=80,
            )
        
        # 作者信息
        author_text = "未知"
        if resource.author:
            author_text = resource.author.name
        
        # 构建详情内容
        detail_controls = [
            ft.Row(
                [
                    icon_widget,
                    ft.Column(
                        [
                            ft.Text(
                                resource.name,
                                size=24,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                f"版本: {resource.version}",
                                size=14,
                                color=ft.Colors.GREY,
                            ),
                            ft.Text(
                                f"作者: {author_text}",
                                size=14,
                                color=ft.Colors.GREY,
                            ),
                        ],
                        spacing=4,
                    ),
                ],
                spacing=16,
            ),
            ft.Divider(),
            ft.Text(resource.summary, size=16),
            ft.Divider(),
            ft.Markdown(
                resource.description_md,
                selectable=True,
                auto_follow_links=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            ),
        ]
        
        # 添加额外信息
        if resource.license:
            detail_controls.append(
                ft.Text(f"许可证: {resource.license}", size=12, color=ft.Colors.GREY)
            )
        
        # 添加链接
        links = []
        if resource.homepage_url:
            links.append(
                ft.TextButton(
                    "官方网站",
                    icon=ft.Icons.HOME,
                    on_click=lambda _: self.page.launch_url(resource.homepage_url),
                )
            )
        if resource.repository_url:
            links.append(
                ft.TextButton(
                    "源码仓库",
                    icon=ft.Icons.CODE,
                    on_click=lambda _: self.page.launch_url(resource.repository_url),
                )
            )
        if resource.changelog_url:
            links.append(
                ft.TextButton(
                    "更新日志",
                    icon=ft.Icons.HISTORY,
                    on_click=lambda _: self.page.launch_url(resource.changelog_url),
                )
            )
        
        if links:
            detail_controls.append(
                ft.Row(links, spacing=8, wrap=True)
            )
        
        # 安装按钮
        def handle_install(_):
            self._install_resource(resource)
            dialog.open = False
            self.page.update()
        
        install_button = ft.FilledButton(
            "安装",
            icon=ft.Icons.DOWNLOAD,
            on_click=handle_install,
        )
        
        close_button = ft.TextButton(
            "关闭",
            on_click=lambda _: setattr(dialog, "open", False) or self.page.update(),
        )
        
        # 创建对话框
        dialog = ft.AlertDialog(
            title=ft.Text("资源详情"),
            content=ft.Container(
                content=ft.Column(
                    detail_controls,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=600,
                height=500,
            ),
            actions=[
                close_button,
                install_button,
            ],
        )
        
        self.page.open(dialog)
    
    def _install_resource(self, resource: ResourceMetadata):
        """安装资源"""
        try:
            if resource.type == "theme" and self.on_install_theme:
                self.on_install_theme(resource)
            elif resource.type == "plugin" and self.on_install_plugin:
                self.on_install_plugin(resource)
            elif resource.type == "wallpaper_source" and self.on_install_wallpaper_source:
                self.on_install_wallpaper_source(resource)
            else:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("暂不支持此类型资源的安装"),
                        bgcolor=ft.Colors.ERROR,
                    )
                )
                return
            
            self.page.open(
                ft.SnackBar(
                    ft.Text(f"开始安装 {resource.name}..."),
                )
            )
        except Exception as e:
            logger.error(f"安装资源失败: {e}")
            self.page.open(
                ft.SnackBar(
                    ft.Text(f"安装失败: {e}"),
                    bgcolor=ft.Colors.ERROR,
                )
            )
    
    def _handle_tab_change(self, e: ft.ControlEvent):
        """处理标签切换"""
        if not self._tabs:
            return
        
        selected_index = self._tabs.selected_index
        
        # 映射标签索引到资源类型
        tab_map = {
            0: "theme",
            1: "resources",
            2: "plugins",
        }
        
        self._current_tab = tab_map.get(selected_index, "theme")
        
        # 重新加载资源
        asyncio.create_task(self.load_resources())
