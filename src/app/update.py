# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Little Tree Studio <studio@zsxiaoshu.cn>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""应用更新服务：负责通过安装包触发自更新。

该服务用于在主进程退出后调用安装包（Inno Setup 等）完成更新，
默认使用静默参数组合，并可在安装完成后重新启动应用。
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import aiohttp
from loguru import logger

from app.paths import CACHE_DIR


# --------------------------- 更新检查 ---------------------------


def _detect_platform_arch() -> tuple[str, str]:
    """返回 (platform, arch) 映射给更新接口使用。"""
    system = platform.system().lower()
    if system.startswith("win"):
        plat = "windows"
    elif system.startswith("darwin") or system.startswith("mac"):
        plat = "macos"
    elif system.startswith("linux"):
        plat = "linux"
    else:
        plat = system or "unknown"

    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64", "x64"}:
        arch = "x64"
    elif machine in {"arm64", "aarch64"}:
        arch = "arm64"
    elif machine in {"arm", "armv7", "armv8"}:
        arch = "arm"
    else:
        arch = machine or "unknown"
    return plat, arch


def _parse_semver(version: str) -> tuple[int, int, int]:
    """粗略解析 SemVer，无法解析时返回 (0,0,0)。"""
    try:
        parts = (version or "0.0.0").split(".")
        nums = [int(p) for p in parts[:3]]
        while len(nums) < 3:
            nums.append(0)
        return nums[0], nums[1], nums[2]
    except Exception:
        return (0, 0, 0)


def is_remote_newer(local: str, remote: str) -> bool:
    """比较本地与远端版本是否远端更新。"""
    return _parse_semver(remote) > _parse_semver(local)


@dataclass(slots=True)
class UpdateChannel:
    id: str
    name: str
    description: str | None = None
    order: int = 0


@dataclass(slots=True)
class UpdatePackage:
    download_url: str
    size_bytes: int
    sha256: str
    platform: str
    arch: str


@dataclass(slots=True)
class UpdateInfo:
    version: str
    channel: str
    release_note: str | None
    release_notes_url: str | None
    release_date: str | None
    force_update: bool
    minimum_supported_version: str | None
    update_supported_version: str | None
    package: UpdatePackage | None
    download_url: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None

    def is_newer_than(self, local_version: str) -> bool:
        return is_remote_newer(local_version, self.version)

    def is_force_for(self, local_version: str) -> bool:
        if self.force_update:
            return True
        if self.minimum_supported_version:
            return is_remote_newer(self.minimum_supported_version, local_version)
        return False

    def is_supported_for(self, local_version: str) -> bool:
        if self.update_supported_version:
            return not is_remote_newer(self.update_supported_version, local_version)
        return True


class UpdateChecker:
    """负责拉取更新频道与更新信息。"""

    def __init__(self, base_url: str = "https://wallpaper.api.zsxiaoshu.cn/core/update") -> None:
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch_channels(self) -> list[UpdateChannel]:
        url = f"{self.base_url}/channel.json"
        session = await self._get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            data: list[dict[str, Any]] = await resp.json()
        channels: list[UpdateChannel] = []
        for item in data:
            cid = str(item.get("id") or "").strip()
            if not cid:
                continue
            channels.append(
                UpdateChannel(
                    id=cid,
                    name=str(item.get("name") or cid),
                    description=item.get("description"),
                    order=int(item.get("order", 0) or 0),
                )
            )
        channels.sort(key=lambda c: c.order)
        return channels

    async def fetch_update(self, channel: str) -> UpdateInfo:
        plat, arch = _detect_platform_arch()
        url = f"{self.base_url}/{channel}/update.json"
        session = await self._get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json()

        pkg = None
        platforms = data.get("platforms") or {}
        plat_entry = platforms.get(plat) or {}
        arch_entry = plat_entry.get(arch) or {}
        if arch_entry:
            pkg = UpdatePackage(
                download_url=str(arch_entry.get("download_url") or data.get("download_url") or ""),
                size_bytes=int(arch_entry.get("size_bytes") or data.get("size_bytes") or 0),
                sha256=str(arch_entry.get("sha256") or data.get("sha256") or ""),
                platform=plat,
                arch=arch,
            )
        elif data.get("download_url"):
            # fallback：未按平台分发时直接用顶层下载地址
            pkg = UpdatePackage(
                download_url=str(data.get("download_url")),
                size_bytes=int(data.get("size_bytes") or 0),
                sha256=str(data.get("sha256") or ""),
                platform=plat,
                arch=arch,
            )
        return UpdateInfo(
            version=str(data.get("version") or "0.0.0"),
            channel=str(data.get("channel") or channel),
            release_note=data.get("release_note"),
            release_notes_url=data.get("release_notes_url"),
            release_date=data.get("release_date"),
            force_update=bool(data.get("force_update", False)),
            minimum_supported_version=data.get("minimum_supported_version"),
            update_supported_version=data.get("update_supported_version"),
            package=pkg,
            download_url=str(data.get("download_url") or ""),
            size_bytes=int(data.get("size_bytes") or 0),
            sha256=str(data.get("sha256") or ""),
        )


# --------------------------- 安装包触发更新 ---------------------------


class InstallerUpdateService:
    """管理安装包触发的更新流程。"""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._workspace = (cache_dir or CACHE_DIR) / "updater"
        self._workspace.mkdir(parents=True, exist_ok=True)

    def _build_installer_args(
        self,
        mode: str = "verysilent",
        log_path: Path | None = None,
        extra_args: Sequence[str] | None = None,
    ) -> list[str]:
        """生成安装包参数列表。"""
        args: list[str] = []
        if mode == "verysilent":
            args.append("/VERYSILENT")
        elif mode == "silent":
            args.append("/SILENT")
        else:
            # 未指定时走交互安装
            pass

        # 默认参数：关闭提示、抑制重启，尝试关闭并重启相关应用
        args.extend(
            [
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/CLOSEAPPLICATIONS",
                "/RESTARTAPPLICATIONS",
            ]
        )
        if log_path:
            args.append(f"/LOG=\"{log_path}\"")
        if extra_args:
            args.extend(list(extra_args))
        return args

    def _write_runner_script(self) -> Path:
        """生成 PowerShell 执行脚本。"""
        script_path = self._workspace / "run_installer.ps1"
        content = textwrap.dedent(
            r'''
            param(
                [int]$TargetPid,
                [string]$InstallerPath,
                [string]$InstallerArgs,
                [string]$PostStartExe,
                [string]$PostStartArgs
            )
            $ErrorActionPreference = "Stop"
            # 等待主进程退出，避免文件被占用
            while (Get-Process -Id $TargetPid -ErrorAction SilentlyContinue) {
                Start-Sleep -Seconds 1
            }
            Start-Process -FilePath $InstallerPath -ArgumentList $InstallerArgs -Wait
            if ($PostStartExe) {
                Start-Process -FilePath $PostStartExe -ArgumentList $PostStartArgs
            }
            '''
        ).strip()
        script_path.write_text(content, encoding="utf-8")
        return script_path

    def launch_installer(
        self,
        installer_path: Path,
        mode: str = "verysilent",
        extra_args: Sequence[str] | None = None,
        restart_after: bool = True,
        log_to_cache: bool = True,
    ) -> bool:
        """启动安装包并准备退出当前应用。

        Args:
            installer_path: 安装包路径。
            mode: 安装模式，支持 verysilent/silent/interactive。
            extra_args: 额外透传给安装包的参数。
            restart_after: 安装完成后是否重新启动应用。
            log_to_cache: 是否输出安装日志到缓存目录。
        """
        if os.name != "nt":
            raise RuntimeError("当前仅支持在 Windows 上触发安装包更新。")
        if not installer_path.exists():
            raise FileNotFoundError(installer_path)

        # 交互式安装有时会因日志路径解析失败导致安装程序报错，直接禁用日志输出
        if mode == "interactive":
            log_to_cache = False
        log_path = (self._workspace / "installer.log") if log_to_cache else None
        args = self._build_installer_args(mode=mode, log_path=log_path, extra_args=extra_args)
        arg_string = subprocess.list2cmdline(args)

        script_path = self._write_runner_script()
        target_pid = os.getpid()
        post_start_exe: Path | None = None
        post_start_args: list[str] = []
        if restart_after and getattr(sys, "frozen", False):
            post_start_exe = Path(sys.executable)

        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-TargetPid",
            str(target_pid),
            "-InstallerPath",
            str(installer_path),
            "-InstallerArgs",
            arg_string,
            "-PostStartExe",
            str(post_start_exe) if post_start_exe else "",
            "-PostStartArgs",
            subprocess.list2cmdline(post_start_args),
        ]

        creation_flags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags = subprocess.CREATE_NO_WINDOW

        try:
            subprocess.Popen(cmd, creationflags=creation_flags)
            logger.info("已启动更新安装包: {}", installer_path)
            return True
        except Exception as exc:
            logger.error("启动更新安装包失败: {error}", error=str(exc))
            raise


__all__ = ["InstallerUpdateService"]
