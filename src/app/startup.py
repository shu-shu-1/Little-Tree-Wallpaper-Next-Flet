import platform
import plistlib
from pathlib import Path

from loguru import logger

from .constants import APP_NAME
from .paths import SOFTWARE_DIR

if platform.system() == "Windows":
    import winreg


class StartupManager:
    def __init__(self, app_name=APP_NAME, app_path=SOFTWARE_DIR, arguments="--startup", bundle_id="com.littletreestudio"):
        self.app_name = app_name
        # store the path that will be written to registry (as string)
        self.app_path = str(app_path)
        self.arguments = arguments
        self.bundle_id = bundle_id

    def enable_startup(self, hide_on_launch: bool | None = None):
        """启用开机自启动，可选择是否附带隐藏参数。"""
        system = platform.system()
        if system == "Windows":
            self._enable_startup_windows(hide_on_launch)
        elif system == "Darwin":
            self._enable_startup_macos(hide_on_launch)
        elif system == "Linux":
            self._enable_startup_linux(hide_on_launch)
        else:
            raise NotImplementedError(
                f"Startup management is not implemented for {system}.",
            )
        logger.info("Startup enabled")

    def disable_startup(self):
        system = platform.system()
        if system == "Windows":
            self._disable_startup_windows()
        elif system == "Darwin":
            self._disable_startup_macos()
        elif system == "Linux":
            self._disable_startup_linux()
        else:
            raise NotImplementedError(
                f"Startup management is not implemented for {system}.",
            )
        logger.info("Startup disabled")

    def is_startup_enabled(self, hide_on_launch: bool | None = None):
        system = platform.system()
        if system == "Windows":
            enabled, _ = self._describe_windows(hide_on_launch)
            return enabled
        elif system == "Darwin":
            enabled, _ = self._describe_macos(hide_on_launch)
            return enabled
        elif system == "Linux":
            enabled, _ = self._describe_linux(hide_on_launch)
            return enabled
        raise NotImplementedError(
            f"Startup management is not implemented for {system}.",
        )

    def describe_startup(self, hide_on_launch: bool | None = None) -> tuple[bool, bool]:
        """返回 (是否启用, 是否包含 --hide)。"""
        system = platform.system()
        if system == "Windows":
            return self._describe_windows(hide_on_launch)
        elif system == "Darwin":
            return self._describe_macos(hide_on_launch)
        elif system == "Linux":
            return self._describe_linux(hide_on_launch)
        raise NotImplementedError(
            f"Startup management is not implemented for {system}.",
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
        legacy = self._build_command(False)
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

    # macOS 实现
    def _get_launchagent_path(self) -> Path:
        """获取 macOS LaunchAgent plist 文件路径。"""
        launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
        launch_agents_dir.mkdir(parents=True, exist_ok=True)
        # 使用反向域名风格命名，例如 com.littletreestudio.LittleTreeWallpaperNext
        plist_name = f"{self.bundle_id}.{self.app_name.replace(' ', '')}.plist"
        return launch_agents_dir / plist_name

    def _enable_startup_macos(self, hide_on_launch: bool | None = None):
        """在 macOS 上启用开机自启动（使用 LaunchAgent）。"""
        plist_path = self._get_launchagent_path()
        
        # 构建启动参数
        args = [self.app_path]
        # 将参数字符串拆分为单独的参数
        if self.arguments:
            args.extend(self.arguments.split())
        if hide_on_launch:
            args.append("--hide")
        
        # 创建 plist 配置
        plist_data = {
            "Label": f"{self.bundle_id}.{self.app_name.replace(' ', '')}",
            "ProgramArguments": args,
            "RunAtLoad": True,
            "KeepAlive": False,
        }
        
        # 写入 plist 文件
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)
        
        logger.info(
            f"添加 macOS 开机启动项:\n\t路径 -> {plist_path}\n\t命令 -> {' '.join(args)}",
        )

    def _disable_startup_macos(self):
        """在 macOS 上禁用开机自启动。"""
        plist_path = self._get_launchagent_path()
        if plist_path.exists():
            plist_path.unlink()
            logger.info(f"移除 macOS 开机启动项:\n\t路径 -> {plist_path}")
        else:
            logger.info(f"macOS 开机启动项不存在:\n\t路径 -> {plist_path}")

    def _describe_macos(self, hide_on_launch: bool | None = None) -> tuple[bool, bool]:
        """检查 macOS 开机自启动状态。"""
        plist_path = self._get_launchagent_path()
        
        if not plist_path.exists():
            logger.info(f"检查 macOS 开机启动项: 未找到 plist 文件 -> {plist_path}")
            return False, False
        
        try:
            with open(plist_path, "rb") as f:
                plist_data = plistlib.load(f)
            
            # 检查 ProgramArguments
            args = plist_data.get("ProgramArguments", [])
            if not args:
                return False, False
            
            # 检查第一个参数（可执行文件路径）是否匹配
            # 可能是完整路径或包含 app_path 作为子字符串
            enabled = (args[0] == self.app_path or self.app_path in args[0])
            
            # 检查是否包含 --hide 参数
            hide_flag = "--hide" in args
            
            logger.info(
                f"检查 macOS 开机启动项: {'已启用' if enabled else '未启用'} (隐藏: {'是' if hide_flag else '否'})\n\t路径 -> {plist_path}\n\t参数 -> {args}",
            )
            
            return enabled, hide_flag
        except Exception as e:
            logger.error(f"读取 macOS 启动项配置失败: {e}")
            return False, False

    # Linux 实现
    def _get_autostart_path(self) -> Path:
        """获取 Linux autostart desktop 文件路径。"""
        autostart_dir = Path.home() / ".config" / "autostart"
        autostart_dir.mkdir(parents=True, exist_ok=True)
        desktop_name = f"{self.app_name.replace(' ', '-')}.desktop"
        return autostart_dir / desktop_name

    def _enable_startup_linux(self, hide_on_launch: bool | None = None):
        """在 Linux 上启用开机自启动（使用 XDG autostart）。"""
        desktop_path = self._get_autostart_path()
        
        # 构建启动命令
        args = [self.app_path]
        # 将参数字符串拆分为单独的参数
        if self.arguments:
            args.extend(self.arguments.split())
        if hide_on_launch:
            args.append("--hide")
        exec_command = " ".join(args)
        
        # 创建 .desktop 文件内容
        desktop_content = f"""[Desktop Entry]
Type=Application
Name={self.app_name}
Exec={exec_command}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment={self.app_name} auto-start
"""
        
        # 写入 desktop 文件
        desktop_path.write_text(desktop_content, encoding="utf-8")
        desktop_path.chmod(0o755)
        
        logger.info(
            f"添加 Linux 开机启动项:\n\t路径 -> {desktop_path}\n\t命令 -> {exec_command}",
        )

    def _disable_startup_linux(self):
        """在 Linux 上禁用开机自启动。"""
        desktop_path = self._get_autostart_path()
        if desktop_path.exists():
            desktop_path.unlink()
            logger.info(f"移除 Linux 开机启动项:\n\t路径 -> {desktop_path}")
        else:
            logger.info(f"Linux 开机启动项不存在:\n\t路径 -> {desktop_path}")

    def _describe_linux(self, hide_on_launch: bool | None = None) -> tuple[bool, bool]:
        """检查 Linux 开机自启动状态。"""
        desktop_path = self._get_autostart_path()
        
        if not desktop_path.exists():
            logger.info(f"检查 Linux 开机启动项: 未找到 desktop 文件 -> {desktop_path}")
            return False, False
        
        try:
            content = desktop_path.read_text(encoding="utf-8")
            
            # 检查路径是否在 Exec 行中
            enabled = False
            hide_flag = False
            
            for line in content.splitlines():
                if line.startswith("Exec="):
                    exec_line = line[5:].strip()
                    enabled = self.app_path in exec_line
                    hide_flag = "--hide" in exec_line
                    break
            
            logger.info(
                f"检查 Linux 开机启动项: {'已启用' if enabled else '未启用'} (隐藏: {'是' if hide_flag else '否'})\n\t路径 -> {desktop_path}",
            )
            
            return enabled, hide_flag
        except Exception as e:
            logger.error(f"读取 Linux 启动项配置失败: {e}")
            return False, False
