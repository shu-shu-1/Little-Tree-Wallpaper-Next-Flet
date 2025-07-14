# -*- coding: utf-8 -*-
#
# File: main.py
# Project: Little Tree Wallpaper
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
import flet as ft
import ltwapi

VER = "0.1.0-alpha2"

# ---------- 资源路径 ----------
ASSET_DIR   = Path(__file__).parent / "assets"
FONT_PATH   = ASSET_DIR / "fonts" / "LXGWNeoXiHeiPlus.ttf"
ICO_PATH    = ASSET_DIR / "images" / "icon.ico"


class Pages:
    """缓存各页面组件"""
    def __init__(self, page: ft.Page):
        self.page = page
        self.wallpaper_path = ltwapi.get_sys_wallpaper()
        self.home = self._build_home()
        self.resource = self._build_resource()
        self.sniff   = self._build_sniff()
        self.unknown  = self._build_unknown()
        
    # --------------------------------------------------
    # 壁纸相关
    # --------------------------------------------------
    
    def _update_wallpaper(self):
        self.wallpaper_path = ltwapi.get_sys_wallpaper()
    def _refresh_home(self, _):
        """刷新按钮回调：重新获取壁纸并刷新 UI"""
        self._update_wallpaper()
        self.img.src = self.wallpaper_path
        self.file_name.value = f"当前壁纸：{Path(self.wallpaper_path).name}"
        self.page.update()
        
    # --------------------------------------------------
    # 页面构建
    # --------------------------------------------------
    
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
            tooltip="当前计算机的壁纸"
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
                                ft.TextButton("刷新", icon=ft.Icons.REFRESH, on_click=self._refresh_home)
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ]
                ),
                self.file_name,
            ],
            expand=True,
            # scroll=ft.ScrollMode.AUTO,
        )

    def _build_resource(self):
        return ft.Column(
            [
                ft.Text("资源", size=30),
                ft.Tabs(
                    tabs=[
                        ft.Tab(text="Bing 每日", icon=ft.Icons.TODAY),
                        ft.Tab(text="Windows 聚焦", icon=ft.Icons.WINDOW),
                        ft.Tab(text="其他", icon=ft.Icons.SUBJECT),
                    ],
                    animation_duration=300,
                ),
            ]
        )

    def _build_sniff(self):
        return ft.Column(
            [
                ft.Text("嗅探", size=30),
                ft.Row(
                    [
                        ft.TextField(label="请输入网址", prefix_text="https://", expand=True),
                        ft.IconButton(
                            icon=ft.Icons.SEARCH,
                            icon_size=30,
                            tooltip="开始嗅探",
                        ),
                    ]
                ),
            ]
        )

    def _build_unknown(self):
        return ft.Column(
            [
                ft.Icon(name=ft.Icons.ERROR, size=50, color=ft.Colors.RED),
                ft.Text("页面不存在或正在开发中", size=35),
                ft.Text(
                    "此错误不应出现在正式版中，若您看到此页面，请联系开发者",
                    size=10,
                    color=ft.Colors.GREY,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

# --------------------------------------------------
# 主入口
# --------------------------------------------------

def main(page: ft.Page):
    page.title = f"小树壁纸 Next (Flet) | {VER}"
    if FONT_PATH.exists():
        page.fonts = {"LXGWNeoXiHeiPlus": str(FONT_PATH)}
        page.theme = ft.Theme(font_family="LXGWNeoXiHeiPlus")

    pages = Pages(page)
    content = ft.Container(expand=True, content=pages.home)

    def switch_tab(e):
        idx = e.control.selected_index
        mapping = {0: pages.home, 1: pages.resource, 2: pages.sniff}
        content.content = mapping.get(idx, pages.nopage)
        page.update()

    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=80,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="首页"),
            ft.NavigationRailDestination(icon=ft.Icons.ARCHIVE_OUTLINED, selected_icon=ft.Icons.ARCHIVE, label="资源"),
            ft.NavigationRailDestination(icon=ft.Icons.WIFI_FIND_OUTLINED, selected_icon=ft.Icons.WIFI_FIND,label="嗅探"),
            ft.NavigationRailDestination(icon=ft.Icons.STAR_RATE_OUTLINED, selected_icon=ft.Icons.STAR_RATE,label="收藏"),
            ft.NavigationRailDestination(icon=ft.Icons.IMAGE_SEARCH_OUTLINED, selected_icon=ft.Icons.IMAGE_SEARCH, label="搜索"),
        ],
        on_change=switch_tab,
    )
    page.appbar = ft.AppBar(
        leading=ft.Image(str(ICO_PATH), width=24, height=24, fit=ft.ImageFit.CONTAIN),
        title=ft.Text("小树壁纸 Next - Flet"),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        actions=[
            ft.TextButton("帮助", icon=ft.Icons.HELP),
            ft.TextButton("设置", icon=ft.Icons.SETTINGS),
        ],
    )
    page.add(
        ft.Row(
            [
                rail,
                ft.VerticalDivider(width=1),
                content,
            ],
            expand=True,
        )
    )
    
# --------------------------------------------------
# 启动！！！
# --------------------------------------------------

if __name__ == "__main__":
    ft.app(main)