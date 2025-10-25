# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: AGPL-3.0-only
#
# File: main.py
# Project: Little Tree Wallpaper Next
# Description: Thin entry point delegating to the modular application bootstrap.
#
# Little Tree Wallpaper Next is a free and open-source program released under the
# GNU Affero General Public License Version 3, 19 November 2007.
# 如果你对该代码做出任何修改或使用了本项目的任何代码，必须开源你的程序代码，并保留 小树壁纸 的版权声明。

from __future__ import annotations

import flet as ft
from tkinter import messagebox

from app import Application


def main(page: ft.Page) -> None:
    """Delegate to the modular :class:`Application`."""

    Application()(page)


if __name__ == "__main__":
    try:
        ft.app(target=main)
    except Exception as e:
        messagebox.showerror("Error", f"Error occurred: {str(e.with_traceback())}")
