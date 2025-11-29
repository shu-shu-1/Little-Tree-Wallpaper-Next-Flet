import platform

from loguru import logger

from .constants import APP_NAME
from .paths import SOFTWARE_DIR

if platform.system() == "Windows":
    import winreg


class StartupManager:
    def __init__(self, app_name=APP_NAME, app_path=SOFTWARE_DIR, arguments="--startup"):
        self.app_name = app_name
        # store the path that will be written to registry (as string)
        self.app_path = str(app_path)
        self.arguments = arguments

    def enable_startup(self):
        if platform.system() == "Windows":
            self._enable_startup_windows()
            logger.info("Startup enabled")
        else:
            raise NotImplementedError(
                "Startup management is only implemented for Windows.",
            )

    def disable_startup(self):
        if platform.system() == "Windows":
            self._disable_startup_windows()
        else:
            raise NotImplementedError(
                "Startup management is only implemented for Windows.",
            )

    def is_startup_enabled(self):
        if platform.system() == "Windows":
            return self._is_startup_enabled_windows()
        raise NotImplementedError(
            "Startup management is only implemented for Windows.",
        )

    def _enable_startup_windows(self):
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_WRITE,
        ) as key:
            winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, self.app_path)
        logger.info(
            f"添加Windows开启启动项: \n\t注册表 -> HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\n\t名称 -> {self.app_name}\n\t路径 -> {self.app_path}",
        )
    def _disable_startup_windows(self):
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            try:
                winreg.DeleteValue(key, self.app_name)
            except FileNotFoundError:
                pass  # Value does not exist
        logger.info(
            f"移除Windows开启启动项: \n\t注册表 -> HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\n\t名称 -> {self.app_name}",
        )

    def _is_startup_enabled_windows(self):
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            try:
                value, _ = winreg.QueryValueEx(key, self.app_name)
                enabled = value == self.app_path
                logger.info(
                    f"检查Windows开启启动项: \n\t注册表 -> HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\n\t名称 -> {self.app_name}\n\t状态 -> {'已启用' if enabled else '未启用'}",
                )
                return enabled
            except FileNotFoundError:
                logger.info(
                    f"检查Windows开启启动项: 未找到注册表项 -> {self.app_name}",
                )
                return False
