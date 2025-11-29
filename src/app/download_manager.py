"""下载管理器 - 处理壁纸下载位置、统计和管理功能。"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from loguru import logger


class DownloadLocationType:
    """下载位置类型常量。"""

    SYSTEM_DOWNLOAD = "system_download"
    SYSTEM_PICTURES = "system_pictures"
    CUSTOM = "custom"


class DownloadStats(NamedTuple):
    """下载统计数据。"""

    total_files: int
    total_size: int  # 字节
    last_download_time: float | None
    location: Path


@dataclass
class DownloadLocation:
    """下载位置配置。"""

    type: str
    path: Path
    display_name: str


class DownloadManager:
    """下载管理器。"""

    def __init__(self):
        self._platform = platform.system()
        self._download_marker_file = "小树壁纸下载文件夹.txt"
        self._download_folder_name = "小树壁纸"  # 专用下载文件夹名称
        self._config_key_prefix = "download"

    def get_system_download_location(self) -> Path:
        """获取系统下载文件夹路径。"""
        if self._platform == "Windows":
            # Windows: 用户下载文件夹
            return Path.home() / "Downloads"
        if self._platform == "Darwin":  # macOS
            # macOS: 下载文件夹
            return Path.home() / "Downloads"
        # Linux
        # Linux: 用户下载文件夹
        return Path.home() / "Downloads"

    def get_system_pictures_location(self) -> Path:
        """获取系统图片文件夹路径。"""
        if self._platform == "Windows":
            # Windows: 用户图片文件夹
            return Path.home() / "Pictures"
        if self._platform == "Darwin":  # macOS
            # macOS: 图片文件夹
            return Path.home() / "Pictures"
        # Linux
        # Linux: 图片文件夹
        return Path.home() / "Pictures"

    def get_available_locations(self, app_config=None) -> list[DownloadLocation]:
        """获取可用的下载位置选项。"""
        # 获取基础路径
        system_download_base = self.get_system_download_location()
        system_pictures_base = self.get_system_pictures_location()

        locations = [
            DownloadLocation(
                type=DownloadLocationType.SYSTEM_DOWNLOAD,
                path=system_download_base / self._download_folder_name,
                display_name=f"系统下载 ({system_download_base})",
            ),
            DownloadLocation(
                type=DownloadLocationType.SYSTEM_PICTURES,
                path=system_pictures_base / self._download_folder_name,
                display_name=f"系统图片 ({system_pictures_base})",
            ),
            DownloadLocation(
                type=DownloadLocationType.CUSTOM,
                path=Path(),  # 将在设置中自定义
                display_name="自定义位置",
            ),
        ]

        # 如果提供了app_config，更新自定义路径的显示
        if app_config:
            custom_path = app_config.get("download.custom_path", "")
            if custom_path:
                custom_base_path = Path(custom_path)
                # 找到自定义位置并更新路径显示
                for location in locations:
                    if location.type == DownloadLocationType.CUSTOM:
                        location.path = custom_base_path / self._download_folder_name
                        location.display_name = f"自定义位置 ({custom_base_path})"
                        break

        return locations

    def get_current_location(self, app_config) -> DownloadLocation:
        """获取当前下载位置配置。"""
        location_type = app_config.get(f"{self._config_key_prefix}.location_type", DownloadLocationType.SYSTEM_DOWNLOAD)
        custom_path = app_config.get(f"{self._config_key_prefix}.custom_path", "")
        base_path = app_config.get(f"{self._config_key_prefix}.base_path", "")

        if location_type == DownloadLocationType.CUSTOM and custom_path:
            base_path = Path(custom_path) if custom_path else Path()
        elif location_type == DownloadLocationType.SYSTEM_PICTURES:
            base_path = self.get_system_pictures_location()
        else:
            base_path = self.get_system_download_location()

        download_folder_path = base_path / self._download_folder_name if base_path else Path()
        display_path = download_folder_path if base_path else Path()

        if location_type == DownloadLocationType.CUSTOM:
            display_name = f"自定义位置 ({base_path})" if base_path else "自定义位置"
        elif location_type == DownloadLocationType.SYSTEM_PICTURES:
            display_name = f"系统图片 ({base_path})"
        else:
            display_name = f"系统下载 ({base_path})"

        return DownloadLocation(
            type=location_type,
            path=display_path,
            display_name=display_name,
        )

    def set_download_location(self, app_config, location_type: str, custom_path: str = "") -> bool:
        """设置下载位置。"""
        try:
            if location_type == DownloadLocationType.CUSTOM:
                if not custom_path:
                    return False
                base_path = Path(custom_path)
            elif location_type == DownloadLocationType.SYSTEM_PICTURES:
                base_path = self.get_system_pictures_location()
            else:
                base_path = self.get_system_download_location()

            # 确保基础路径存在
            base_path.mkdir(parents=True, exist_ok=True)

            # 创建专用下载文件夹路径
            download_folder_path = base_path / self._download_folder_name
            download_folder_path.mkdir(parents=True, exist_ok=True)

            # 在专用文件夹内创建标识文件
            marker_path = download_folder_path / self._download_marker_file
            marker_path.write_text("小树壁纸 Next 下载文件夹\n此文件夹由小树壁纸 Next 创建用于管理壁纸下载。", encoding="utf-8")

            # 保存配置
            app_config.set(f"{self._config_key_prefix}.location_type", location_type)
            app_config.set(f"{self._config_key_prefix}.custom_path", custom_path)
            app_config.set(f"{self._config_key_prefix}.base_path", str(base_path))
            app_config.set(f"{self._config_key_prefix}.download_folder_path", str(download_folder_path))

            logger.info(f"下载位置已设置为: {download_folder_path}")
            return True

        except Exception as e:
            logger.error(f"设置下载位置失败: {e}")
            return False

    def get_download_folder_path(self, app_config) -> Path | None:
        """获取当前下载文件夹路径（在用户选择位置内的专用文件夹）。"""
        # 直接从配置中获取已创建的专用文件夹路径
        download_folder_path_str = app_config.get(f"{self._config_key_prefix}.download_folder_path", "")
        if download_folder_path_str:
            return Path(download_folder_path_str)

        # 如果配置中没有，尝试从当前位置计算
        location = self.get_current_location(app_config)
        return location.path

    def get_download_stats(self, app_config) -> DownloadStats:
        """获取下载统计数据。"""
        folder_path = self.get_download_folder_path(app_config)
        if not folder_path or not folder_path.exists():
            return DownloadStats(0, 0, None, Path())

        total_files = 0
        total_size = 0
        last_download_time = None

        try:
            # 统计专用文件夹中的所有文件（排除标识文件）
            marker_path = folder_path / self._download_marker_file

            for file_path in folder_path.rglob("*"):
                if file_path.is_file() and file_path != marker_path:
                    total_files += 1
                    try:
                        total_size += file_path.stat().st_size
                        file_mtime = file_path.stat().st_mtime
                        if last_download_time is None or file_mtime > last_download_time:
                            last_download_time = file_mtime
                    except (OSError, PermissionError):
                        continue
        except Exception as e:
            logger.error(f"统计下载文件夹时出错: {e}")

        return DownloadStats(total_files, total_size, last_download_time, folder_path)

    def format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小。"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)

        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.1f} {size_names[i]}"

    def open_download_folder(self, app_config) -> bool:
        """打开下载文件夹。"""
        folder_path = self.get_download_folder_path(app_config)
        if not folder_path or not folder_path.exists():
            return False

        try:
            if self._platform == "Windows":
                # Windows: 使用 explorer 打开
                subprocess.run(["explorer", str(folder_path)], check=True)
            elif self._platform == "Darwin":  # macOS
                # macOS: 使用 open 打开
                subprocess.run(["open", str(folder_path)], check=True)
            else:  # Linux
                # Linux: 根据发行版选择文件管理器
                file_managers = ["xdg-open", "nautilus", "dolphin", "thunar"]
                for fm in file_managers:
                    try:
                        subprocess.run([fm, str(folder_path)], check=True)
                        break
                    except (subprocess.SubprocessError, FileNotFoundError):
                        continue
                else:
                    # 如果都失败了，使用 xdg-open
                    subprocess.run(["xdg-open", str(folder_path)], check=True)

            logger.info(f"已打开下载文件夹: {folder_path}")
            return True

        except Exception as e:
            logger.error(f"打开下载文件夹失败: {e}")
            return False

    def clear_download_folder(self, app_config) -> tuple[bool, str]:
        """清空下载文件夹（保留标识文件）。"""
        folder_path = self.get_download_folder_path(app_config)
        if not folder_path or not folder_path.exists():
            return False, "下载文件夹不存在"

        try:
            # 获取标识文件路径
            marker_path = folder_path / self._download_marker_file

            # 获取要删除的文件列表（包括子文件夹）
            files_to_delete = []
            for file_path in folder_path.rglob("*"):
                if file_path.is_file() and file_path != marker_path:
                    files_to_delete.append(file_path)

            # 删除子文件夹
            folders_to_delete = []
            for folder_path_item in folder_path.iterdir():
                if folder_path_item.is_dir() and folder_path_item.name != self._download_folder_name:
                    folders_to_delete.append(folder_path_item)

            if not files_to_delete and not folders_to_delete:
                return True, "文件夹已经是空的"

            # 删除文件
            deleted_count = 0
            for file_path in files_to_delete:
                try:
                    file_path.unlink()
                    deleted_count += 1
                except (OSError, PermissionError) as e:
                    logger.warning(f"无法删除文件 {file_path}: {e}")

            # 删除子文件夹
            for folder_path_item in folders_to_delete:
                try:
                    shutil.rmtree(folder_path_item)
                    deleted_count += 1
                except (OSError, PermissionError) as e:
                    logger.warning(f"无法删除文件夹 {folder_path_item}: {e}")

            logger.info(f"已清空下载文件夹，删除了 {deleted_count} 个文件/文件夹")
            return True, f"已删除 {deleted_count} 个项目"

        except Exception as e:
            error_msg = f"清空文件夹时出错: {e}"
            logger.error(error_msg)
            return False, error_msg

    def validate_custom_path(self, path_str: str) -> tuple[bool, str]:
        """验证自定义路径是否有效。"""
        if not path_str or not path_str.strip():
            return False, "路径不能为空"

        try:
            path = Path(path_str)
            # 检查路径是否有效
            if not path.is_absolute():
                return False, "请使用绝对路径"

            # 尝试创建路径
            path.mkdir(parents=True, exist_ok=True)

            # 检查是否有写入权限
            test_file = path / ".test_write_permission"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except PermissionError:
                return False, "没有写入权限"

            return True, "路径有效"

        except Exception as e:
            return False, f"路径无效: {e}"


# 创建全局实例
download_manager = DownloadManager()
