"""Runtime helpers for detecting conflicting wallpaper applications."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

import psutil
from loguru import logger


@dataclass(slots=True)
class StartupConflict:
	"""Represents a running application that may interfere with the app."""

	identifier: str
	title: str
	processes: list[str]
	note: str | None = None


def _normalize_name(name: str | None, exe_path: str | None) -> str:
	if name:
		return name
	if exe_path:
		try:
			return Path(exe_path).name
		except Exception:
			return exe_path
	return ""


def detect_conflicts() -> list[StartupConflict]:
	"""Return a list of conflicting wallpaper applications currently running."""
	if platform.system().lower() != "windows":
		return []

	wallpaper_engine_variants: set[str] = set()
	wallpaper_generator_execs: set[str] = set()

	for proc in psutil.process_iter(["name", "exe"]):
		try:
			info = proc.info
		except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
			continue

		raw_name = info.get("name")
		exe_path = info.get("exe")
		name = _normalize_name(raw_name, exe_path).lower()

		if not name:
			continue

		if name in {"wallpaper32.exe", "wallpaper64.exe"}:
			wallpaper_engine_variants.add(_normalize_name(raw_name, exe_path))
			continue

		if name == "main.exe":
			parent_name = ""
			if exe_path:
				try:
					parent_name = Path(exe_path).resolve().parent.name.lower()
				except Exception:
					try:
						parent_name = Path(exe_path).parent.name.lower()
					except Exception:
						parent_name = ""
			if parent_name == "wallpaper-generator-next":
				display = _normalize_name(raw_name, exe_path)
				if exe_path:
					display = f"{display} ({exe_path})"
				wallpaper_generator_execs.add(display)

	conflicts: list[StartupConflict] = []

	if wallpaper_engine_variants:
		conflicts.append(
			StartupConflict(
				identifier="wallpaper_engine",
				title="Wallpaper Engine",
				processes=sorted(wallpaper_engine_variants),
				note="检测到 Wallpaper Engine 正在运行，可能无法正常显示壁纸。",
			),
		)

	if wallpaper_generator_execs:
		conflicts.append(
			StartupConflict(
				identifier="wallpaper_generator_next",
				title="壁纸生成器 Next",
				processes=sorted(wallpaper_generator_execs),
				note="检测到 壁纸生成器 Next 正在运行，可能会与自动更换壁纸功能冲突。",
			),
		)

	if conflicts:
		logger.info(
			"Startup conflicts detected: {}",
			", ".join(conflict.title for conflict in conflicts),
		)

	return conflicts
