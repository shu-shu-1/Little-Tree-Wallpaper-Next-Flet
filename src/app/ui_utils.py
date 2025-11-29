"""Shared UI helpers."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import flet as ft
from loguru import logger

from .constants import BUILD_VERSION, SHOW_WATERMARK


def build_watermark(
    text: str = f"小树壁纸Next测试版\n测试版本，不代表最终品质\n{BUILD_VERSION}",
    opacity: float = 0.7,
    padding: int = 8,
    margin_rb: tuple[int, int] = (12, 12),
):
    """构建一个右下角的测试版水印。"""
    if not SHOW_WATERMARK:
        return ft.Container()

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
    return ft.Container(content=badge, right=margin_rb[0], bottom=margin_rb[1])


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
            check=False, capture_output=True,
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
            f"复制图片失败：{result.stderr.strip() or result.stdout.strip()}",
        )
        return False
    return True


def copy_files_to_clipboard(paths: list[str]) -> bool:
    resolved: list[Path] = []
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
            check=False, capture_output=True,
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
            f"复制文件失败：{result.stderr.strip() or result.stdout.strip()}",
        )
        return False
    return True
