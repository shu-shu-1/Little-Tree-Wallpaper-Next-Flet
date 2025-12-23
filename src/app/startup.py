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

    def enable_startup(self, hide_on_launch: bool | None = None):
        """启用开机自启动，可选择是否附带隐藏参数。"""
        if platform.system() == "Windows":
            self._enable_startup_windows(hide_on_launch)
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

    def is_startup_enabled(self, hide_on_launch: bool | None = None):
        if platform.system() == "Windows":
            enabled, _ = self._describe_windows(hide_on_launch)
            return enabled
        raise NotImplementedError(
            "Startup management is only implemented for Windows.",
        )

    def describe_startup(self, hide_on_launch: bool | None = None) -> tuple[bool, bool]:
        """返回 (是否启用, 是否包含 --hide)。"""
        if platform.system() == "Windows":
            return self._describe_windows(hide_on_launch)
        raise NotImplementedError(
            "Startup management is only implemented for Windows.",
        )

    def _build_command(self, hide_on_launch: bool | None = None) -> str:
        parts = [f'"{self.app_path}"']
        args: list[str] = []
        base_arg = (self.arguments or "").strip()
        if base_arg:
            args.append(base_arg)
        if hide_on_launch:
            args.append("--hide")
        if args:
            parts.append(" ".join(args))
        return " ".join(parts).strip()

    def _enable_startup_windows(self, hide_on_launch: bool | None = None):
        command = self._build_command(hide_on_launch)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_WRITE,
        ) as key:
            winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, command)
        logger.info(
            f"添加Windows开启启动项: \n\t注册表 -> HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\n\t名称 -> {self.app_name}\n\t命令 -> {command}",
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

    def _describe_windows(self, hide_on_launch: bool | None = None) -> tuple[bool, bool]:
        desired = self._build_command(hide_on_launch)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            try:
                value, _ = winreg.QueryValueEx(key, self.app_name)
            except FileNotFoundError:
                logger.info(
                    f"检查Windows开启启动项: 未找到注册表项 -> {self.app_name}",
                )
                return False, False

        raw = str(value or "")
        normalized = raw.lower()
        enabled = self.app_path.lower() in normalized
        hide_flag = "--hide" in normalized
        matches_desired = normalized == desired.lower()
        if enabled:
            logger.info(
                "检查Windows开启启动项: 已启用 (匹配: {match}, 隐藏: {hide})\n\t值 -> {value}",
                match="是" if matches_desired else "否",
                hide="是" if hide_flag else "否",
                value=raw,
            )
        else:
            logger.info(
                "检查Windows开启启动项: 未启用或路径不匹配\n\t值 -> {value}",
                value=raw,
            )
        # 如果存在旧格式（仅路径），仍视为启用
        if not enabled and raw.strip() == self.app_path:
            enabled = True
        return enabled, hide_flag
