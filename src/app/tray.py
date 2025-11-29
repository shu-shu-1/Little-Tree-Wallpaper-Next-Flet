from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

import pystray
from loguru import logger
from PIL import Image
from pystray import Menu, MenuItem


class TrayIcon:
    """System tray helper backed by pystray."""

    def __init__(self, app: Any, icon_path: str | None = None) -> None:
        self._app = app
        self._icon_path = icon_path
        self._icon: Any | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _make_image(self) -> Any | None:
        if pystray is None or Image is None:
            return None
        if self._icon_path and os.path.exists(self._icon_path):
            try:
                return Image.open(self._icon_path)
            except Exception:
                pass
        try:
            return Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        except Exception:
            return None

    def _with_page(self, handler: Callable[[Any], None]) -> None:
        page = getattr(self._app, "_page", None)
        if page is None:
            return

        def _run() -> None:
            try:
                handler(page)
            except Exception:
                pass

        invoker = getattr(page, "invoke_later", None)
        if callable(invoker):
            try:
                invoker(_run)
                return
            except Exception:
                pass
        _run()

    # ------------------------------------------------------------------
    # callbacks
    # ------------------------------------------------------------------
    def _on_show(self, _icon, _item) -> None:
        def _handler(page: Any) -> None:
            window = getattr(page, "window", None)
            if window is not None:
                try:
                    window.visible = True
                    window.minimized = False
                    window.to_front()
                except Exception as e:
                    logger.error(f"显示窗口遇到错误: {e}")

            try:
                page.update()
            except Exception as e:
                logger.error(f"刷新页面遇到错误: {e}")

        self._with_page(_handler)

    def _on_hide(self, _icon, _item) -> None:
        def _handler(page: Any) -> None:
            window = getattr(page, "window", None)
            if window is not None:
                try:
                    window.visible = False
                except Exception as e:
                    logger.error(f"隐藏窗口遇到错误: {e}")
            try:
                page.update()
            except Exception as e:
                logger.error(f"刷新页面遇到错误: {e}")

        self._with_page(_handler)

    def _on_change_wallpaper(self, _icon, _item) -> None:
        def _handler(page: Any) -> None:  # noqa: ARG001 - required by tray callback
            app = self._app
            if app is None:
                return
            pages = getattr(app, "_core_pages", None)
            if pages is None and hasattr(app, "_extract_core_pages"):
                try:
                    pages = app._extract_core_pages()
                except Exception:
                    pages = None
            if pages is None:
                return
            service = getattr(pages, "auto_change_service", None)
            if service is None:
                return
            try:
                success = service.trigger_immediate_change()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("托盘更换壁纸失败: {error}", error=str(exc))
                success = False
            try:
                if success:
                    pages._show_snackbar("已触发自动更换，将立即刷新壁纸。")
                else:
                    pages._show_snackbar(
                        "请先启用间隔或轮播模式后再使用该功能。",
                        error=True,
                    )
            except Exception:
                pass

        self._with_page(_handler)

    def _on_quit(self, _icon, _item) -> None:
        def _handler(page: Any) -> None:
            window = getattr(page, "window", None)
            if window is not None:
                try:
                    logger.info("关闭程序")
                    window.close()
                    window.close()
                    window.close()
                    window.destroy()
                    window.destroy()
                    window.destroy()
                    return
                except Exception as e:
                    logger.error(f"注销窗口遇到错误: {e}")


        self._with_page(_handler)

        # if self._icon is not None:
        #     try:
        #         self._icon.stop()
        #     except Exception:
        #         pass
        # try:
        #     logger.info("退出程序")
        #     os._exit(0)
        # except Exception as e:
        #     logger.error(f"退出程序遇到错误: {e}")

    # ------------------------------------------------------------------
    # public api
    # ------------------------------------------------------------------
    def start(self) -> None:
        if pystray is None or MenuItem is None:
            return
        if self._thread is not None and self._thread.is_alive():
            return

        def _run() -> None:
            image = self._make_image()
            if image is None:
                return
            try:
                self._icon = pystray.Icon(
                    "little-tree-wallpaper",
                    image,
                    "小树壁纸",
                    (
                        MenuItem("显示", self._on_show),
                        MenuItem("隐藏", self._on_hide),
                        MenuItem("立即更换壁纸", self._on_change_wallpaper),
                        Menu.SEPARATOR,
                        MenuItem("退出", self._on_quit),
                    ),
                )
                self._icon.run()
            except Exception:
                pass

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is None:
            return
        try:
            self._icon.stop()
        except Exception:
            pass


__all__ = ["TrayIcon"]
