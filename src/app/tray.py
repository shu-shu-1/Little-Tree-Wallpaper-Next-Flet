from __future__ import annotations

import os
import threading
from typing import Any, Callable, Optional

try:
    import pystray
    from pystray import MenuItem as MenuItem
except Exception:  # pragma: no cover - optional dependency
    pystray = None  # type: ignore
    MenuItem = None  # type: ignore

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore


class TrayIcon:
    """System tray helper backed by pystray."""

    def __init__(self, app: Any, icon_path: Optional[str] = None) -> None:
        self._app = app
        self._icon_path = icon_path
        self._icon: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _make_image(self) -> Optional[Any]:
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
                except Exception:
                    pass
                for action in ("restore", "show", "bring_to_front"):
                    try:
                        getattr(window, action)()
                    except Exception:
                        pass
            try:
                page.update()
            except Exception:
                pass

        self._with_page(_handler)

    def _on_hide(self, _icon, _item) -> None:
        def _handler(page: Any) -> None:
            window = getattr(page, "window", None)
            if window is not None:
                for action in ("minimize", "hide"):
                    try:
                        getattr(window, action)()
                    except Exception:
                        pass
                try:
                    window.visible = False
                except Exception:
                    pass
            try:
                page.update()
            except Exception:
                pass

        self._with_page(_handler)

    def _on_quit(self, _icon, _item) -> None:
        def _handler(page: Any) -> None:
            window = getattr(page, "window", None)
            if window is not None:
                try:
                    window.close()
                    return
                except Exception:
                    pass
            try:
                page.window_close()
            except Exception:
                pass

        self._with_page(_handler)

        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
        try:
            os._exit(0)
        except Exception:
            pass

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
                        # MenuItem("退出", self._on_quit),
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
