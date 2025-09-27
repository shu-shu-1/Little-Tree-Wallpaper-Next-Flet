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

import json
import platform
import subprocess
from pathlib import Path
from loguru import logger
import flet as ft
import ltwapi
import aiohttp
import pyperclip
import platformdirs
import asyncio

VER = "0.1.0-alpha5"
BUILD = "20250927-017"
MODE = "TEST"
BUILD_VERSION = f"v{VER} ({BUILD})"

logger.info(f"Little Tree Wallpaper Next {BUILD_VERSION} 初始化")

ASSET_DIR = Path(__file__).parent / "assets"
UI_FONT_PATH = ASSET_DIR / "fonts" / "LXGWNeoXiHeiPlus.ttf"
HITO_FONT_PATH = ASSET_DIR / "fonts" / "LXGWWenKaiLite.ttf"
IMAGE_PATH = ASSET_DIR / "images"
ICO_PATH = IMAGE_PATH / "icon.ico"
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

# 是否显示右下角“测试版”水印（稳定版不显示）
SHOW_WATERMARK = MODE != "STABLE"


def build_watermark(
    text: str = "小树壁纸Next alpha测试版\n测试版本，不代表最终品质",
    opacity: float = 0.7,
    padding: int = 8,
    margin_rb: tuple[int, int] = (12, 12),
):
    """构建一个右下角的小角标水印。

    参数:
        text: 角标文字
        opacity: 透明度 (0~1)
        padding: 内边距（像素）
        margin_rb: 右、下外边距（像素）
    """
    badge = ft.Container(
        content=ft.Text(
            text,
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ON_SECONDARY_CONTAINER,
        ),
        padding=padding,
        border_radius=9999,
        opacity=opacity,
        tooltip="测试版软件，可能存在不稳定因素，请谨慎使用~",
    )
    # 采用 Stack 子项的绝对定位属性（right/bottom），不设置 alignment 以免拉伸
    return ft.Container(
        content=badge,
        right=margin_rb[0],
        bottom=margin_rb[1],
    )


def _ps_escape(value: str) -> str:
    return value.replace("'", "''")


def copy_image_to_clipboard(image_path: Path) -> bool:
    image_path = Path(image_path).resolve()
    if not image_path.exists():
        logger.error(f"复制图片失败，文件不存在：{image_path}")
        return False
    if platform.system() != "Windows":
        logger.warning("当前系统不支持直接复制图片数据，已忽略")
        return False

    uri = image_path.as_uri()
    script = (
        "Add-Type -AssemblyName PresentationCore; "
        "Add-Type -AssemblyName WindowsBase; "
        "$img = New-Object System.Windows.Media.Imaging.BitmapImage; "
        "$img.BeginInit(); "
        "$img.CacheOption = [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad; "
        f"$img.UriSource = New-Object System.Uri('{_ps_escape(uri)}'); "
        "$img.EndInit(); "
        "[System.Windows.Clipboard]::SetImage($img);"
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.error("未找到 PowerShell，无法复制图片数据")
        return False
    except Exception as exc:
        logger.error(f"复制图片失败: {exc}")
        return False

    if result.returncode != 0:
        logger.error(
            "复制图片失败：{}".format(result.stderr.strip() or result.stdout.strip())
        )
        return False
    return True


def copy_files_to_clipboard(paths: list[str]) -> bool:
    resolved = []
    for p in paths:
        path_obj = Path(p).resolve()
        if path_obj.exists():
            resolved.append(path_obj)
        else:
            logger.warning(f"文件不存在，已跳过：{path_obj}")

    if not resolved:
        return False
    if platform.system() != "Windows":
        logger.warning("当前系统不支持复制文件到剪贴板，已忽略")
        return False

    ps_paths = ", ".join(f"'{_ps_escape(str(p))}'" for p in resolved)
    script = f"Set-Clipboard -Path @({ps_paths})"

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.error("未找到 PowerShell，无法复制文件")
        return False
    except Exception as exc:
        logger.error(f"复制文件失败: {exc}")
        return False

    if result.returncode != 0:
        logger.error(
            "复制文件失败：{}".format(result.stderr.strip() or result.stdout.strip())
        )
        return False
    return True


class Pages:
    def __init__(self, page: ft.Page):
        self.page = page
        self.wallpaper_path = ltwapi.get_sys_wallpaper()
        self.bing_wallpaper = None
        self.bing_wallpaper_url = None
        self.bing_loading = True
        self.spotlight_loading = True
        self.spotlight_wallpaper_url = None
        self.spotlight_wallpaper = list()

        self.home = self._build_home()
        self.resource = self._build_resource()
        self.sniff = self._build_sniff()
        self.favorite = self._build_favorite()
        self.test = self._build_test()

        self.page.run_task(self._load_bing_wallpaper)
        self.page.run_task(self._load_spotlight_wallpaper)

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
            self._refresh_bing_tab()

    async def _load_spotlight_wallpaper(self):
        try:
            self.spotlight_wallpaper = await ltwapi.get_spotlight_wallpaper_async()
            if self.spotlight_wallpaper and len(self.spotlight_wallpaper) > 0:
                self.spotlight_loading = self.spotlight_wallpaper
            if self.spotlight_loading:
                self.spotlight_wallpaper_url = [
                    item["url"] for item in self.spotlight_wallpaper
                ]

        except Exception as e:
            self.spotlight_wallpaper_url = None
            logger.error(f"加载 Windows 聚焦壁纸失败: {e}")
        finally:
            self.spotlight_loading = False
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
                return
            pyperclip.copy(self.bing_wallpaper_url)
            self.page.open(
                ft.SnackBar(
                    ft.Text("链接已复制，快去分享吧~"),
                )
            )

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
            else:
                if action == "copy_image":
                    if copy_image_to_clipboard(wallpaper_path):
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("图片已复制，可直接粘贴~"),
                            )
                        )
                    else:
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("复制图片失败，请稍后再试~"),
                                bgcolor=ft.Colors.ON_ERROR,
                            )
                        )
                elif action == "copy_file":
                    if copy_files_to_clipboard([wallpaper_path]):
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("文件已复制到剪贴板~"),
                            )
                        )
                    else:
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("复制文件失败，请稍后再试~"),
                                bgcolor=ft.Colors.ON_ERROR,
                            )
                        )

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
        # copy_button = ft.FilledTonalButton("复制", icon=ft.Icons.COPY)
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
                            copy_menu,
                        ]
                    ),
                    bing_loading_info,
                    bing_pb,
                ]
            ),
            padding=16,
        )

    def _build_spotlight_daily_content(self):
        current_index = 0
        copy_menu = None
        copy_button_content = None
        copy_icon = None
        copy_text = None

        def _sanitize_filename(raw: str, fallback: str) -> str:
            cleaned = "".join(
                ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_"
                for ch in (raw or "").strip()
            ).strip()
            return cleaned or fallback

        def _update_details(idx: int):
            nonlocal current_index, title, description, copy_rights, info_button
            current_index = idx
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

        def _change_photo(e):
            data = json.loads(e.data)
            if not data:
                return
            idx = int(data[0])
            _update_details(idx)
            self.page.update()

        def _copy_link():
            url = self.spotlight_wallpaper[current_index].get("url")
            if not url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("当前壁纸缺少下载链接，暂时无法复制~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )
                return
            pyperclip.copy(url)
            self.page.open(
                ft.SnackBar(
                    ft.Text("壁纸链接已复制，快去分享吧~"),
                )
            )

        def _handle_download(action: str):
            nonlocal current_index, spotlight_loading_info, spotlight_pb
            nonlocal set_button, favorite_button, download_button, copy_button
            nonlocal segmented_button, copy_menu

            spotlight = self.spotlight_wallpaper[current_index]
            url = spotlight.get("url")
            if not url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("未找到壁纸地址，暂时无法下载~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )
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
                spotlight.get("title"), f"Windows-Spotlight-{current_index + 1}"
            )

            wallpaper_path = ltwapi.download_file(
                url,
                DATA_DIR / "Wallpaper",
                filename,
                progress_callback=progress_callback,
            )

            success = wallpaper_path is not None
            handled = False
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
            elif success and action == "download":
                self.page.open(
                    ft.SnackBar(
                        ft.Text("壁纸下载完成，快去看看吧~"),
                    )
                )
                handled = True
            elif success and action == "copy_image":
                handled = True
                if copy_image_to_clipboard(wallpaper_path):
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("图片已复制，可直接粘贴~"),
                        )
                    )
                else:
                    success = False
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("复制图片失败，请稍后再试~"),
                            bgcolor=ft.Colors.ON_ERROR,
                        )
                    )
            elif success and action == "copy_file":
                handled = True
                if copy_files_to_clipboard([wallpaper_path]):
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("文件已复制到剪贴板~"),
                        )
                    )
                else:
                    success = False
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("复制文件失败，请稍后再试~"),
                            bgcolor=ft.Colors.ON_ERROR,
                        )
                    )

            if not success and not handled:
                logger.error("Windows 聚焦壁纸下载失败")
                self.page.open(
                    ft.SnackBar(
                        ft.Text("下载失败，请稍后再试~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    )
                )

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
        # print(self.spotlight_wallpaper_url)
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
        copy_button_content = ft.Row(
            controls=[copy_icon, copy_text],
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
                    ft.Row(
                        [
                            set_button,
                            favorite_button,
                            download_button,
                            copy_menu,
                        ]
                    ),
                    spotlight_loading_info,
                    spotlight_pb,
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

    def _build_spotlight_loading_indicator(self):
        return ft.Column(
            [
                ft.Row(
                    [ft.ProgressRing(), ft.Text("正在加载Windows 聚焦壁纸 …")],
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

    def _build_test(self):
        return ft.Column(
            controls=[
                ft.Text("测试", size=30),
                ft.Text(
                    "如果你看到这页，说明你运行的是测试版本，可能会有一些不稳定的情况，请谨慎使用。\n如果你发现了任何问题，请及时反馈给我们，谢谢！"
                ),
                ft.Text("页面路由跳转："),
                ft.Row(
                    [
                        route_change_input := ft.TextField(
                            hint_text="页面路由",
                            expand=True,
                            on_submit=lambda e: self.page.go(e.control.value),
                        ),
                        ft.Button(
                            "跳转",
                            on_click=lambda e: self.page.go(route_change_input.value),
                        ),
                    ]
                ),
                ft.Button("打开测试版警告页", ft.Icons.OPEN_IN_NEW, on_click=lambda e: self.page.go("/test-warning")),
            ],
        )

    def _change_theme_mode(self, e):
        match e.data:
            case "auto":
                self.page.theme_mode = ft.ThemeMode.SYSTEM
            case "light":
                self.page.theme_mode = ft.ThemeMode.LIGHT
            case "dark":
                self.page.theme_mode = ft.ThemeMode.DARK
            case _:
                return
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
            # ft.Switch(label="开机自启"),
            # ft.Switch(label="自动检查更新", value=True),
        )
        download = tab_content(
            "下载",
            # ft.Dropdown(
            #     label="默认保存位置",
            #     options=[
            #         ft.dropdown.Option("下载"),
            #         ft.dropdown.Option("图片"),
            #         ft.dropdown.Option("自定义…"),
            #     ],
            #     value="下载",
            #     width=220,
            # ),
            # ft.Switch(label="仅 Wi-Fi 下载", value=True),
        )

        ui = tab_content(
            "界面",
            # ft.Slider(min=0.5, max=2, divisions=3, label="界面缩放: {value}", value=1),
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

        # 设置页主体：用 Stack 叠加右下角水印
        settings_body_controls = [
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
            )
        ]
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


def main(page: ft.Page):
    page.title = f"小树壁纸 Next (Flet) | {VER if MODE == 'STABLE' else BUILD_VERSION}"
    if UI_FONT_PATH.exists() and HITO_FONT_PATH.exists():
        page.fonts = {"UIFont": str(UI_FONT_PATH), "HITOKOTOFont": str(HITO_FONT_PATH)}
        page.theme = ft.Theme(font_family="UIFont")

    pages = Pages(page)

    # 主界面内容
    main_row = ft.Row(
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
                    ft.NavigationRailDestination(
                        icon=ft.Icons.SCIENCE_OUTLINED,
                        selected_icon=ft.Icons.SCIENCE,
                        label="测试和调试\n(仅限测试版)",
                    ),
                ],
                on_change=lambda e: [
                    setattr(
                        content,
                        "content",
                        [
                            pages.home,
                            pages.resource,
                            pages.sniff,
                            pages.favorite,
                            pages.test,
                        ][e.control.selected_index],
                    ),
                    page.update(),
                ],
            ),
            ft.VerticalDivider(width=1),
            (content := ft.Container(expand=True, content=pages.home)),
        ],
        expand=True,
    )

    # 叠加右下角“测试版”角标
    main_stack_controls = [main_row]
    if SHOW_WATERMARK:
        main_stack_controls.append(build_watermark())

    home_view = ft.View(
        "/",
        [
            ft.Stack(
                controls=main_stack_controls,
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
        elif page.route == "/test-warning":
            page.views.append(pages.build_test_warning_page())
        else:
            page.views.append(home_view)
        page.update()

    page.on_route_change = route_change
    if MODE == "TEST":
        page.go("/test-warning")
    else:
        page.go("/")
    pages.refresh_hitokoto()


if __name__ == "__main__":
    ft.app(main)
