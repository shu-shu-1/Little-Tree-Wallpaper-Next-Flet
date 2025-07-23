# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: AGPL-3.0-only
#
# File: main.py
# Project: Little Tree Wallpaper Next
# Description: Entry point for the Little Tree Wallpaper Next application.
#              本文件为 小树壁纸Next 程序入口文件。
#
# Little Tree Wallpaper Next is a free and open-source program released under the
# GNU Affero General Public License Version 3, 19 November 2007.
# 小树壁纸Next 是一个自由和开源程序，基于 GNU AFFERO GENERAL PUBLIC LICENSE v3（2007年11月19日）发布。
#
# If you make any changes to this code or use any code of this program,
# you must open source the code of your program and keep the copyright
# information of Little Tree Wallpaper.
# 如果你对该代码做出任何修改或使用了本项目的任何代码，必须开源你的程序代码，并保留 小树壁纸 的版权声明。
#
# Please abide by the content of this agreement (AGPLv3), otherwise we have
# the right to pursue legal responsibility.
# 请遵守 AGPL v3 协议，否则我们有权追究法律责任。
#
# Copyright (c) 2023-2025 Little Tree Wallpaper Project Group.
# Copyright (c) 2022-2025 Little Tree Studio.
# Copyright (c) 2023-2025 Xiaoshu.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 本程序为自由软件；你可以遵循 GNU Affero General Public License 3.0 或更高版本，
# 重新发布和（或）修改本程序。
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
# 本程序以希望对他人有用为目标而发布，但不做任何担保；
# 也没有适销性或针对特定目的适用性的默示担保。详见许可证全文。
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/agpl-3.0.html>.
# 你应该已经收到了一份 GNU AGPL 许可证的副本，如果没有，请访问 <https://www.gnu.org/licenses/agpl-3.0.html> 查看。
#
# Project repository / 项目仓库: https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet

"""
Little Tree Wallpaper Next

main.py is the primary entry point to start and manage the Little Tree Wallpaper Next application.

Use:
    python main.py [options]

For more information, see the project repository and README.

----------------------------

小树壁纸Next

main.py 是启动和管理 小树壁纸Next 应用程序的主入口文件。

用法示例:
    python main.py [参数]

更多信息请参见项目仓库和README。
"""

from pathlib import Path
from loguru import logger
import flet as ft
import ltwapi
import aiohttp
import shutil
import platformdirs

VER = "0.1.0-alpha4"
BUILD = "20250721-001"
MODE = "TEST"
BUILD_VERSION = f"v{VER} ({BUILD})"

logger.info(f"Little Tree Wallpaper Next {BUILD_VERSION} 初始化")

ASSET_DIR = Path(__file__).parent / "assets"
UI_FONT_PATH = ASSET_DIR / "fonts" / "LXGWNeoXiHeiPlus.ttf"
HITO_FONT_PATH = ASSET_DIR / "fonts" / "LXGWWenKaiLite.ttf"
ICO_PATH = ASSET_DIR / "images" / "icon.ico"
HITOKOTO_API = ["https://v1.hitokoto.cn", "https://international.v1.hitokoto.cn/"]
LICENSE_PATH = Path(__file__).parent / "LICENSES"

CACHE_DIR = Path(
    platformdirs.user_cache_dir(
        "Little-Tree-Wallpaper", "Little Tree Studio", "Next", ensure_exists=True
    )
)
RUNTIME_DIR = Path(
    platformdirs.user_runtime_dir(
        "Little-Tree-Wallpaper", "Little Tree Studio", "Next", ensure_exists=True
    )
)
CONFIG_DIR = Path(
    platformdirs.user_config_dir(
        "Little-Tree-Wallpaper", "Little Tree Studio", "Next", ensure_exists=True
    )
)
DATA_DIR = Path(
    platformdirs.user_data_dir(
        "Little-Tree-Wallpaper", "Little Tree Studio", "Next", ensure_exists=True
    )
)


class Pages:
    def __init__(self, page: ft.Page):
        self.page = page
        self.wallpaper_path = ltwapi.get_sys_wallpaper()
        self.bing_wallpaper = None
        self.bing_wallpaper_url = None
        self.bing_loading = True

        self.home = self._build_home()
        self.resource = self._build_resource()
        self.sniff = self._build_sniff()
        self.favorite = self._build_favorite()
        
        self.page.run_task(self._load_bing_wallpaper)

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

    def _refresh_home(self, _):
        self._update_wallpaper()
        self.img.src = self.wallpaper_path
        self.file_name.value = f"当前壁纸：{Path(self.wallpaper_path).name}"
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
            self._refresh_bing_tab()

    def _refresh_bing_tab(self):
        for tab in self.resource_tabs.tabs:
            if tab.text == "Bing 每日":
                tab.content = self._build_bing_daily_content()
                break
        self.page.update()

    def _build_home(self):
        self.file_name = ft.Text(
            f"当前壁纸：{Path(self.wallpaper_path).name}",
            style=ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE),
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
                ft.Tab(text="Windows 聚焦", icon=ft.Icons.WINDOW),
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

    def _build_bing_daily_content(self):
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
            copy_button.disabled = True

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
                ltwapi.set_wallpaper(wallpaper_path)

            else:
                setattr(dlg, "open", True)
                logger.error("Bing 壁纸下载失败")

            bing_pb.value = 0
            bing_loading_info.visible = False
            bing_pb.visible = False
            set_button.disabled = False
            favorite_button.disabled = False
            download_button.disabled = False
            copy_button.disabled = False

            self.resource_tabs.disabled = False

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
        set_button = ft.ElevatedButton(
            "设为壁纸",
            icon=ft.Icons.WALLPAPER,
            on_click=lambda e: _set_wallpaper(self.bing_wallpaper_url),
        )
        favorite_button = ft.ElevatedButton("收藏", icon=ft.Icons.STAR)
        download_button = ft.ElevatedButton("下载", icon=ft.Icons.DOWNLOAD)
        copy_button = ft.ElevatedButton("复制", icon=ft.Icons.COPY)

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
                    ft.Row(
                        [
                            set_button,
                            favorite_button,
                            download_button,
                            copy_button,
                        ]
                    ),
                    bing_loading_info,
                    bing_pb,
                ]
            ),
            padding=16,
        )

    def _build_bing_loading_indicator(self):
        return ft.Column(
            [
                ft.Row(
                    [ft.ProgressRing(), ft.Text("正在加载 Bing 每日壁纸 …")],
                    alignment=ft.MainAxisAlignment.CENTER,
                )
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

    def _build_sniff(self):
        return ft.Column(
            [
                ft.Text("嗅探", size=30),
                ft.Row(
                    [
                        ft.TextField(
                            label="请输入网址", prefix_text="https://", expand=True
                        ),
                        ft.IconButton(
                            icon=ft.Icons.SEARCH, icon_size=30, tooltip="开始嗅探"
                        ),
                    ]
                ),
            ]
        )

    def _build_favorite(self):
        return ft.Column(
            controls=[
                ft.Text("收藏", size=30),
            ],
        )

    def _change_theme_mode(self, e):
        self.page.theme_mode = (
            ft.ThemeMode.DARK if e.data == "true" else ft.ThemeMode.LIGHT
        )
        self.page.update()

    def build_settings_view(self):
        def tab_content(title, *controls):
            return ft.Container(
                content=ft.Column(list(controls), spacing=12, expand=True), padding=16
            )

        license_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text("版权信息"),
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
                        ft.Text("特别鸣谢"),
                        ft.Markdown(
                            """@[炫饭的芙芙](https://space.bilibili.com/1669914811) | @[wsrscx](https://github.com/wsrscx) | @[kylemarvin884](https://github.com/kylemarvin884) | @[Giampaolo-zzp](https://github.com/Giampaolo-zzp)""",
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

        general = tab_content(
            "通用",
            ft.Switch(label="开机自启"),
            ft.Switch(label="自动检查更新", value=True),
        )
        download = tab_content(
            "下载",
            ft.Dropdown(
                label="默认保存位置",
                options=[
                    ft.dropdown.Option("下载"),
                    ft.dropdown.Option("图片"),
                    ft.dropdown.Option("自定义…"),
                ],
                value="下载",
                width=220,
            ),
            ft.Switch(label="仅 Wi-Fi 下载", value=True),
        )

        ui = tab_content(
            "界面",
            ft.Slider(min=0.5, max=2, divisions=3, label="界面缩放: {value}", value=1),
            # ft.Switch(
            #     label="深色模式",
            #     on_change=self._change_theme_mode,
            #     value=True if self.page.theme_mode == ft.ThemeMode.DARK else False,
            # ),
            ft.Dropdown(
                label="界面主题",
                value="auto",
                options=[
                    ft.DropdownOption(key="auto", text="跟随系统"),
                    ft.DropdownOption(key="light", text="浅色"),
                    ft.DropdownOption(key="dark", text="深色"),
                ],
            ),
        )
        about = tab_content(
            "关于",
            ft.Text("小树壁纸 Next v0.1.0-alpha3", size=16),
            ft.Text(
                "Copyright © 2023-2025 Little Tree Studio",
                size=12,
                color=ft.Colors.GREY,
            ),
            ft.TextButton(
                "查看特别鸣谢",
                icon=ft.Icons.OPEN_IN_NEW,
                on_click=lambda _: setattr(thank_sheet, "open", True)
                or self.page.update(),
            ),
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
        )

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
                ft.Tabs(
                    selected_index=0,
                    animation_duration=300,
                    padding=12,
                    tabs=[
                        ft.Tab(text="通用", icon=ft.Icons.SETTINGS, content=general),
                        ft.Tab(text="下载", icon=ft.Icons.DOWNLOAD, content=download),
                        ft.Tab(text="界面", icon=ft.Icons.PALETTE, content=ui),
                        ft.Tab(text="关于", icon=ft.Icons.INFO, content=about),
                    ],
                    expand=True,
                ),
                license_sheet,
                thank_sheet,
            ],
        )


def main(page: ft.Page):
    page.title = f"小树壁纸 Next (Flet) | {VER if MODE == 'STABLE' else BUILD_VERSION}"
    if UI_FONT_PATH.exists() and HITO_FONT_PATH.exists():
        page.fonts = {"UIFont": str(UI_FONT_PATH), "HITOKOTOFont": str(HITO_FONT_PATH)}
        page.theme = ft.Theme(font_family="UIFont")

    pages = Pages(page)

    home_view = ft.View(
        "/",
        [
            ft.Row(
                [
                    ft.NavigationRail(
                        selected_index=0,
                        label_type=ft.NavigationRailLabelType.ALL,
                        min_width=80,
                        destinations=[
                            ft.NavigationRailDestination(
                                icon=ft.Icons.HOME_OUTLINED,
                                selected_icon=ft.Icons.HOME,
                                label="首页",
                            ),
                            ft.NavigationRailDestination(
                                icon=ft.Icons.ARCHIVE_OUTLINED,
                                selected_icon=ft.Icons.ARCHIVE,
                                label="资源",
                            ),
                            ft.NavigationRailDestination(
                                icon=ft.Icons.WIFI_FIND_OUTLINED,
                                selected_icon=ft.Icons.WIFI_FIND,
                                label="嗅探",
                            ),
                            ft.NavigationRailDestination(
                                icon=ft.Icons.STAR_OUTLINE,
                                selected_icon=ft.Icons.STAR,
                                label="收藏",
                            ),
                        ],
                        on_change=lambda e: [
                            setattr(
                                content,
                                "content",
                                [pages.home, pages.resource, pages.sniff, pages.favorite][
                                    e.control.selected_index
                                ],
                            ),
                            page.update(),
                        ],
                    ),
                    ft.VerticalDivider(width=1),
                    (content := ft.Container(expand=True, content=pages.home)),
                ],
                expand=True,
            )
        ],
        appbar=ft.AppBar(
            leading=ft.Image(
                str(ICO_PATH), width=24, height=24, fit=ft.ImageFit.CONTAIN
            ),
            title=ft.Text("小树壁纸 Next - Flet"),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            actions=[
                ft.TextButton("帮助", icon=ft.Icons.HELP),
                ft.TextButton(
                    "设置",
                    icon=ft.Icons.SETTINGS,
                    on_click=lambda _: page.go("/settings"),
                ),
            ],
        ),
    )

    def route_change(_):
        page.views.clear()
        if page.route == "/settings":
            page.views.append(pages.build_settings_view())
        else:
            page.views.append(home_view)
        page.update()

    page.on_route_change = route_change
    page.go("/")
    pages.refresh_hitokoto()


if __name__ == "__main__":
    ft.app(main)
