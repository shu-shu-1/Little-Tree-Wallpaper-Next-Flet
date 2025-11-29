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

import sys
import traceback

import flet as ft

from app import Application

_START_HIDDEN = any(arg.lower() in {"/hide", "--hide"} for arg in sys.argv[1:])


def main(page: ft.Page) -> None:
    """Delegate to the modular :class:`Application`."""
    Application(start_hidden=_START_HIDDEN)(page)


if __name__ == "__main__":
    try:
        ft.app(target=main)
    except Exception as e:
        # 获取完整的异常信息包括堆栈跟踪
        error_message = f"发生错误: {e!s}\n\n详细信息:\n{traceback.format_exc()}"
        try:
            with open("crush.log", "a", encoding="utf-8") as f:
                f.write(error_message + "\n")
        except Exception:
            pass


