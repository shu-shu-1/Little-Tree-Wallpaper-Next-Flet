"""Auto wallpaper rotation management for Little Tree Wallpaper Next."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import random
import re
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import parse_qsl, quote, quote_plus

import aiohttp
from loguru import logger

import ltwapi
from app.favorites import FavoriteItem, FavoriteManager
from app.paths import CACHE_DIR, DATA_DIR
from app.settings import SettingsStore
from app.wallpaper_sources import (
    WallpaperSourceError,
    WallpaperSourceFetchError,
    WallpaperSourceManager,
)

__all__ = [
    "UNIT_SECONDS",
    "AutoChangeList",
    "AutoChangeListEntry",
    "AutoChangeListStore",
    "AutoChangeMode",
    "AutoChangeService",
    "IntervalSettings",
    "ScheduleEntry",
    "ScheduleSettings",
    "SlideshowItem",
    "SlideshowSettings",
]

AUTO_LISTS_VERSION = 1
AUTO_LISTS_PATH = DATA_DIR / "auto_change" / "lists.json"
AUTO_CACHE_DIR = CACHE_DIR / "auto_change"
AUTO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

UNIT_SECONDS: dict[str, int] = {
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
}

IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

ORDER_RANDOM = "random"
ORDER_RANDOM_NO_REPEAT = "random_no_repeat"
ORDER_SEQUENTIAL = "sequential"

VALID_LIST_ORDERS = {ORDER_RANDOM, ORDER_RANDOM_NO_REPEAT, ORDER_SEQUENTIAL}
VALID_SLIDESHOW_ORDERS = {ORDER_SEQUENTIAL, ORDER_RANDOM, ORDER_RANDOM_NO_REPEAT}


def _normalize_list_order(value: str | None) -> str:
    raw = str(value or "").lower()
    if raw == "shuffle":
        return ORDER_RANDOM
    if raw in VALID_LIST_ORDERS:
        return raw
    return ORDER_RANDOM


def _normalize_slideshow_order(value: str | None) -> str:
    raw = str(value or "").lower()
    if raw == "shuffle":
        raw = ORDER_RANDOM
    if raw in VALID_SLIDESHOW_ORDERS:
        return raw
    return ORDER_SEQUENTIAL


def _entry_identity(entry: AutoChangeListEntry, index: int) -> str:
    return entry.id or f"{entry.type}:{index}"


class AutoChangeMode(str, Enum):
    OFF = "off"
    INTERVAL = "interval"
    SCHEDULE = "schedule"
    SLIDESHOW = "slideshow"


@dataclass(slots=True)
class AutoChangeListEntry:
    """Single auto-change entry definition."""

    id: str
    type: str
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoChangeListEntry:
        return cls(
            id=str(data.get("id") or _random_id()),
            type=str(data.get("type") or "unknown"),
            config=dict(data.get("config") or {}),
        )


@dataclass(slots=True)
class AutoChangeList:
    """Collection of auto-change entries."""

    id: str
    name: str
    description: str = ""
    entries: list[AutoChangeListEntry] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "entries": [entry.to_dict() for entry in self.entries],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoChangeList:
        entries = [AutoChangeListEntry.from_dict(raw) for raw in data.get("entries", [])]
        for entry in entries:
            entry.id = entry.id or _random_id()
        return cls(
            id=str(data.get("id") or _random_id()),
            name=str(data.get("name") or "未命名列表"),
            description=str(data.get("description") or ""),
            entries=entries,
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


class AutoChangeListStore:
    """Persistent storage for auto-change lists."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or AUTO_LISTS_PATH
        self._lock = RLock()
        self._lists: dict[str, AutoChangeList] = {}
        self.load()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._lists = {}
                return
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("读取自动更换列表失败: {error}", error=str(exc))
                self._lists = {}
                return
            version = int(payload.get("version", 1))
            if version != AUTO_LISTS_VERSION:
                logger.warning("自动更换列表版本 {version} 未知，尝试兼容加载。", version=version)
            lists: dict[str, AutoChangeList] = {}
            for raw in payload.get("lists", []):
                try:
                    parsed = AutoChangeList.from_dict(raw)
                    lists[parsed.id] = parsed
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("解析自动更换列表失败: {error}", error=str(exc))
            self._lists = lists

    def save(self) -> None:
        with self._lock:
            payload = {
                "version": AUTO_LISTS_VERSION,
                "lists": [auto_list.to_dict() for auto_list in self._lists.values()],
            }
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("保存自动更换列表失败: {error}", error=str(exc))

    def all(self) -> list[AutoChangeList]:
        with self._lock:
            return [AutoChangeList.from_dict(auto_list.to_dict()) for auto_list in self._lists.values()]

    def get(self, list_id: str) -> AutoChangeList | None:
        with self._lock:
            auto_list = self._lists.get(list_id)
            return AutoChangeList.from_dict(auto_list.to_dict()) if auto_list else None

    def upsert(self, auto_list: AutoChangeList) -> None:
        with self._lock:
            auto_list.updated_at = time.time()
            self._lists[auto_list.id] = AutoChangeList.from_dict(auto_list.to_dict())
            self.save()

    def delete(self, list_id: str) -> bool:
        with self._lock:
            if list_id not in self._lists:
                return False
            self._lists.pop(list_id, None)
            self.save()
            return True

    def export_all(self, target: Path) -> None:
        with self._lock:
            payload = {
                "version": AUTO_LISTS_VERSION,
                "lists": [auto_list.to_dict() for auto_list in self._lists.values()],
            }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_list(self, list_id: str, target: Path) -> None:
        auto_list = self.get(list_id)
        if auto_list is None:
            raise ValueError("列表不存在")
        payload = {
            "version": AUTO_LISTS_VERSION,
            "lists": [auto_list.to_dict()],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_file(self, source: Path) -> list[AutoChangeList]:
        text = source.read_text(encoding="utf-8")
        payload = json.loads(text)
        raw_lists = payload.get("lists") or []
        imported: list[AutoChangeList] = []
        for raw in raw_lists:
            auto_list = AutoChangeList.from_dict(raw)
            imported.append(auto_list)
        return imported

    def replace_all(self, lists: Sequence[AutoChangeList]) -> None:
        with self._lock:
            self._lists = {item.id: AutoChangeList.from_dict(item.to_dict()) for item in lists}
            self.save()


@dataclass(slots=True)
class IntervalSettings:
    value: int = 30
    unit: str = "minutes"
    list_ids: list[str] = field(default_factory=list)
    fixed_image: str | None = None
    order: str = ORDER_RANDOM

    def seconds(self) -> int:
        factor = UNIT_SECONDS.get(self.unit, 60)
        raw = int(self.value) if self.value else 0
        seconds = raw * factor
        return max(seconds, 1)


@dataclass(slots=True)
class ScheduleEntry:
    time_str: str
    list_ids: list[str] = field(default_factory=list)
    fixed_image: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time_str,
            "list_ids": list(self.list_ids),
            "fixed_image": self.fixed_image,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduleEntry:
        list_ids = [str(item) for item in data.get("list_ids", []) if item]
        fixed_image = data.get("fixed_image")
        if fixed_image in {"", None}:
            fixed_image = None
        return cls(
            time_str=str(data.get("time") or "00:00"),
            list_ids=list_ids,
            fixed_image=fixed_image,
        )


@dataclass(slots=True)
class ScheduleSettings:
    entries: list[ScheduleEntry] = field(default_factory=list)
    order: str = ORDER_RANDOM

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "order": _normalize_list_order(self.order),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduleSettings:
        entries = [ScheduleEntry.from_dict(raw) for raw in data.get("entries", [])]
        entries.sort(key=lambda entry: entry.time_str)
        return cls(entries=entries, order=_normalize_list_order(data.get("order")))


@dataclass(slots=True)
class SlideshowItem:
    id: str
    kind: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SlideshowItem:
        return cls(
            id=str(data.get("id") or _random_id()),
            kind=str(data.get("kind") or "file"),
            path=str(data.get("path") or ""),
        )


@dataclass(slots=True)
class SlideshowSettings:
    value: int = 5
    unit: str = "minutes"
    items: list[SlideshowItem] = field(default_factory=list)
    order: str = ORDER_SEQUENTIAL

    def seconds(self) -> int:
        factor = UNIT_SECONDS.get(self.unit, 60)
        raw = int(self.value) if self.value else 0
        seconds = raw * factor
        return max(seconds, 1)

    def to_dict(self) -> dict[str, Any]:
        order = _normalize_slideshow_order(self.order)
        return {
            "value": self.value,
            "unit": self.unit,
            "items": [item.to_dict() for item in self.items],
            "order": order,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SlideshowSettings:
        items = [SlideshowItem.from_dict(raw) for raw in data.get("items", [])]
        return cls(
            value=int(data.get("value", 5) or 5),
            unit=str(data.get("unit") or "minutes"),
            items=items,
            order=_normalize_slideshow_order(data.get("order")),
        )


@dataclass(slots=True)
class AutoChangeSettings:
    enabled: bool
    mode: AutoChangeMode
    interval: IntervalSettings
    schedule: ScheduleSettings
    slideshow: SlideshowSettings

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode.value,
            "interval": {
                "value": self.interval.value,
                "unit": self.interval.unit,
                "list_ids": list(self.interval.list_ids),
                "fixed_image": self.interval.fixed_image,
                "order": _normalize_list_order(self.interval.order),
            },
            "schedule": self.schedule.to_dict(),
            "slideshow": self.slideshow.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoChangeSettings:
        enabled = bool(data.get("enabled", False))
        raw_mode = str(data.get("mode") or "off")
        try:
            mode = AutoChangeMode(raw_mode)
        except ValueError:
            mode = AutoChangeMode.INTERVAL if enabled else AutoChangeMode.OFF
        interval_data = data.get("interval") or {}
        interval = IntervalSettings(
            value=int(interval_data.get("value", 30) or 30),
            unit=str(interval_data.get("unit") or "minutes"),
            list_ids=[str(item) for item in interval_data.get("list_ids", []) if item],
            fixed_image=(interval_data.get("fixed_image") or None),
            order=_normalize_list_order(interval_data.get("order")),
        )
        schedule = ScheduleSettings.from_dict(data.get("schedule") or {})
        slideshow = SlideshowSettings.from_dict(data.get("slideshow") or {})
        return cls(
            enabled=enabled,
            mode=mode,
            interval=interval,
            schedule=schedule,
            slideshow=slideshow,
        )


class AutoChangeService:
    """Background service that performs automatic wallpaper changes."""

    def __init__(
        self,
        *,
        settings_store: SettingsStore,
        list_store: AutoChangeListStore,
        wallpaper_source_manager: WallpaperSourceManager,
        favorite_manager: FavoriteManager,
    ) -> None:
        self._settings_store = settings_store
        self._list_store = list_store
        self._wallpaper_source_manager = wallpaper_source_manager
        self._favorite_manager = favorite_manager
        self._refresh_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self._slideshow_index = 0
        self._slideshow_cycle: list[Path] = []
        self._slideshow_snapshot: list[str] = []
        self._list_order_state: dict[tuple[str, ...], dict[str, Any]] = {}
        self._im_executor = _IntelliMarketsExecutor()

    async def ensure_running(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopped = False
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run())

    async def shutdown(self) -> None:
        self._stopped = True
        self._refresh_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    def refresh(self) -> None:
        logger.debug("收到自动更换刷新请求，通知后台任务。")
        self._refresh_event.set()

    def trigger_immediate_change(self) -> bool:
        try:
            settings = self._load_settings()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("立即更换前加载设置失败: {error}", error=str(exc))
            return False
        if not settings.enabled or settings.mode not in {
            AutoChangeMode.INTERVAL,
            AutoChangeMode.SLIDESHOW,
        }:
            logger.debug(
                "忽略立即更换请求：enabled={} mode={}",
                settings.enabled,
                settings.mode.value,
            )
            return False
        if self._task is None or self._task.done():
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.ensure_running())
            except RuntimeError:
                # 如果当前不在事件循环中，则等待下一次刷新后自动启动。
                pass
        self.refresh()
        logger.info("已触发立即更换请求。")
        return True

    async def perform_custom_change(
        self,
        list_ids: Sequence[str],
        fixed_image: str | None = None,
        *,
        order: str | None = ORDER_RANDOM,
    ) -> bool:
        """Execute a one-off wallpaper change using the provided lists."""
        return await self._perform_change(list_ids, fixed_image, order=order)

    async def _run(self) -> None:
        while not self._stopped:
            try:
                settings = self._load_settings()
                if not settings.enabled or settings.mode is AutoChangeMode.OFF:
                    await self._wait_for_refresh()
                    continue
                if settings.mode is AutoChangeMode.INTERVAL:
                    await self._handle_interval(settings)
                elif settings.mode is AutoChangeMode.SCHEDULE:
                    await self._handle_schedule(settings)
                elif settings.mode is AutoChangeMode.SLIDESHOW:
                    await self._handle_slideshow(settings)
                else:
                    await self._wait_for_refresh()
            except Exception as exc:  # pragma: no cover - defensive loop guard
                logger.error("自动更换服务出现异常: {error}", error=str(exc))
                await asyncio.sleep(10)

    def _load_settings(self) -> AutoChangeSettings:
        data = self._settings_store.get("wallpaper.auto_change", {})
        if not isinstance(data, dict):
            data = {}
        try:
            settings = AutoChangeSettings.from_dict(data)
            logger.debug(
                "加载自动更换设置：enabled={} mode={} interval={}{} lists={} order={} schedule_entries={} schedule_order={} slideshow={}{} order={}",
                settings.enabled,
                settings.mode.value,
                settings.interval.value,
                settings.interval.unit,
                len(settings.interval.list_ids),
                settings.interval.order,
                len(settings.schedule.entries),
                settings.schedule.order,
                settings.slideshow.value,
                settings.slideshow.unit,
                settings.slideshow.order,
            )
            return settings
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.error("读取自动更换设置失败: {error}", error=str(exc))
            return AutoChangeSettings.from_dict({})

    async def _handle_interval(self, settings: AutoChangeSettings) -> None:
        logger.debug(
            "间隔模式执行：间隔={}{} 列表数={} 固定图片={} 顺序={}",
            settings.interval.value,
            settings.interval.unit,
            len(settings.interval.list_ids),
            bool(settings.interval.fixed_image),
            settings.interval.order,
        )
        success = await self._perform_change(
            settings.interval.list_ids,
            settings.interval.fixed_image,
            order=settings.interval.order,
        )
        if not success:
            logger.info("间隔模式在本轮未成功更换壁纸。")
        else:
            logger.info("间隔模式已完成一次壁纸切换。")
        await self._wait_for_refresh(timeout=settings.interval.seconds())

    async def _handle_schedule(self, settings: AutoChangeSettings) -> None:
        now = time.localtime()
        upcoming = self._next_schedule(now, settings.schedule.entries)
        if upcoming is None:
            logger.debug("定时模式当前无可执行任务，5 分钟后重试。")
            await self._wait_for_refresh(timeout=300)
            return
        run_at, entry = upcoming
        delay = run_at - time.time()
        if delay > 0:
            logger.debug(
                "定时模式下一次执行：时间={} 距离={:.1f} 秒 列表数={} 固定图片={} 顺序={}",
                entry.time_str,
                delay,
                len(entry.list_ids),
                bool(entry.fixed_image),
                settings.schedule.order,
            )
            triggered = await self._wait_for_refresh(timeout=delay)
            if triggered:
                logger.debug("定时模式因外部刷新而中断等待，将立即重新评估任务。")
                return
        else:
            logger.debug(
                "定时模式下一次执行时间已到或已过期，将立即执行。时间={} 延迟={:.1f} 列表数={} 固定图片={} 顺序={}",
                entry.time_str,
                delay,
                len(entry.list_ids),
                bool(entry.fixed_image),
                settings.schedule.order,
            )
        change_ok = await self._perform_change(
            entry.list_ids,
            entry.fixed_image,
            order=settings.schedule.order,
        )
        if change_ok:
            logger.info("定时模式已根据任务 {} 完成壁纸切换。", entry.time_str)
        else:
            logger.info("定时模式任务 {} 未能成功切换壁纸。", entry.time_str)

    async def _handle_slideshow(self, settings: AutoChangeSettings) -> None:
        order = _normalize_slideshow_order(settings.slideshow.order)
        candidates = self._collect_slideshow_candidates(settings.slideshow.items)
        logger.debug(
            "轮播模式执行：模式={}，候选数量={}，间隔={}{}",
            order,
            len(candidates),
            settings.slideshow.value,
            settings.slideshow.unit,
        )
        if not candidates:
            logger.info("轮播模式暂无可用图片，等待 120 秒后重试。")
            await self._wait_for_refresh(timeout=120)
            return
        snapshot = [str(path) for path in candidates]
        if snapshot != self._slideshow_snapshot:
            self._slideshow_snapshot = snapshot
            self._slideshow_index = 0
            self._slideshow_cycle = []
        if order == ORDER_RANDOM:
            self._slideshow_cycle = []
            target = random.choice(candidates)
        elif order == ORDER_RANDOM_NO_REPEAT:
            if not self._slideshow_cycle:
                self._slideshow_cycle = random.sample(candidates, len(candidates))
            target = self._slideshow_cycle.pop(0)
        else:
            self._slideshow_cycle = []
            self._slideshow_index %= len(candidates)
            target = candidates[self._slideshow_index]
            self._slideshow_index += 1
        logger.info("轮播模式切换壁纸：{}", target)
        await self._set_wallpaper_path(target)
        await self._wait_for_refresh(timeout=settings.slideshow.seconds())

    async def _wait_for_refresh(self, *, timeout: float | None = None) -> bool:
        self._refresh_event.clear()
        if timeout is None or timeout <= 0:
            await self._refresh_event.wait()
            return True
        try:
            await asyncio.wait_for(self._refresh_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _perform_change(
        self,
        list_ids: Sequence[str],
        fixed_image: str | None,
        *,
        order: str | None = ORDER_RANDOM,
    ) -> bool:
        order_mode = _normalize_list_order(order)
        if fixed_image:
            logger.debug("尝试应用固定图片：{}", fixed_image)
            if await self._set_wallpaper_path(Path(fixed_image)):
                logger.info("已应用固定图片：{}", fixed_image)
                return True
            logger.warning("固定图片应用失败，改为使用列表条目。")
        entries = self._collect_entries(list_ids)
        if not entries:
            logger.debug("未找到可用条目：结合的列表为空或不存在。")
            return False
        if order_mode == ORDER_RANDOM:
            for entry in random.sample(entries, len(entries)):
                if await self._attempt_entry(entry):
                    return True
            return False
        key = self._list_state_key(list_ids)
        state = self._ensure_list_state(key, entries)
        if order_mode == ORDER_SEQUENTIAL:
            start = state.get("index", 0)
            if entries:
                start %= len(entries)
            success_index: int | None = None
            for offset in range(len(entries)):
                idx = (start + offset) % len(entries)
                entry = entries[idx]
                if await self._attempt_entry(entry):
                    success_index = idx
                    break
            if success_index is not None:
                state["index"] = (success_index + 1) % len(entries)
                return True
            if entries:
                state["index"] = (start + 1) % len(entries)
            return False
        # ORDER_RANDOM_NO_REPEAT
        ids = state.get("ids", [])
        if not ids:
            state["pool"] = []
            return False
        pool = state.setdefault("pool", [])
        if not pool:
            pool.extend(ids)
            random.shuffle(pool)
        entry_lookup = {identity: entries[idx] for idx, identity in enumerate(ids)}
        while pool:
            identity = pool.pop(0)
            entry = entry_lookup.get(identity)
            if entry is None:
                continue
            if await self._attempt_entry(entry):
                state["pool"] = pool
                return True
        state["pool"] = pool
        return False

    def _collect_entries(self, list_ids: Sequence[str]) -> list[AutoChangeListEntry]:
        entries: list[AutoChangeListEntry] = []
        for list_id in list_ids:
            auto_list = self._list_store.get(list_id)
            if not auto_list:
                logger.debug("指定的自动更换列表不存在：{}", list_id)
                continue
                logger.debug(
                    "载入列表条目：list_id={} name={} count={}",
                    auto_list.id,
                    auto_list.name,
                    len(auto_list.entries),
                )
            entries.extend(auto_list.entries)
        return entries

    def _list_state_key(self, list_ids: Sequence[str]) -> tuple[str, ...]:
        return tuple(list_ids)

    def _ensure_list_state(
        self,
        key: tuple[str, ...],
        entries: Sequence[AutoChangeListEntry],
    ) -> dict[str, Any]:
        identities = [_entry_identity(entry, idx) for idx, entry in enumerate(entries)]
        state = self._list_order_state.get(key)
        if state is None or state.get("ids") != identities:
            state = {"ids": identities, "index": 0, "pool": []}
            self._list_order_state[key] = state
        return state

    async def _attempt_entry(self, entry: AutoChangeListEntry) -> bool:
        try:
            logger.debug("开始执行条目：id={} type={}", entry.id, entry.type)
            if await self._execute_entry(entry):
                return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("自动更换执行条目失败: {error}", error=str(exc))
        return False

    async def _execute_entry(self, entry: AutoChangeListEntry) -> bool:
        entry_type = entry.type
        config = entry.config
        result = False
        if entry_type == "bing":
            result = await self._apply_bing()
        elif entry_type == "spotlight":
            result = await self._apply_spotlight()
        elif entry_type == "favorite_folder":
            folder_id = config.get("folder_id")
            result = await self._apply_favorite(folder_id)
        elif entry_type == "wallpaper_source":
            category_id = config.get("category_id")
            params = config.get("params") or {}
            result = await self._apply_wallpaper_source(category_id, params)
        elif entry_type == "im_source":
            source = config.get("source")
            params = config.get("parameters") or []
            result = await self._apply_intellimarkets(source, params)
        elif entry_type == "ai":
            result = await self._apply_ai(config)
        elif entry_type == "local_image":
            path = config.get("path")
            result = await self._set_wallpaper_path(Path(path)) if path else False
        elif entry_type == "local_folder":
            path = config.get("path")
            if path:
                folder = Path(path)
                if folder.exists() and folder.is_dir():
                    candidates = [p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS]
                    if candidates:
                        target = random.choice(candidates)
                        result = await self._set_wallpaper_path(target)
        if result:
            logger.info("自动更换条目成功：type={} id={}", entry_type, entry.id)
        else:
            logger.debug("自动更换条目未成功：type={} id={}", entry_type, entry.id)
        return result

    async def _apply_bing(self) -> bool:
        data = await ltwapi.get_bing_wallpaper_async()
        if not data:
            return False
        raw_url = data.get("url")
        if not raw_url:
            return False
        url = _normalize_bing_url(raw_url)
        return await self._download_and_apply(url, prefix="bing")

    async def _apply_spotlight(self) -> bool:
        payload = await ltwapi.get_spotlight_wallpaper_async()
        if not payload:
            return False
        choices = [item for item in payload if item.get("url")]
        if not choices:
            return False
        item = random.choice(choices)
        return await self._download_and_apply(item.get("url"), prefix="spotlight")

    async def _apply_favorite(self, folder_id: str | None) -> bool:
        items = await asyncio.to_thread(self._favorite_manager.list_items, folder_id)
        if not items:
            return False
        random.shuffle(items)
        for item in items:
            path = await self._resolve_favorite_path(item)
            if path is not None and await self._set_wallpaper_path(path):
                return True
        return False

    async def _apply_wallpaper_source(self, category_id: str | None, params: dict[str, Any]) -> bool:
        if not category_id:
            return False
        try:
            items = await self._wallpaper_source_manager.fetch_category_items(category_id, params)
        except WallpaperSourceFetchError as exc:
            logger.error("壁纸源拉取失败: {error}", error=str(exc))
            return False
        except WallpaperSourceError as exc:
            logger.error("壁纸源不可用: {error}", error=str(exc))
            return False
        random.shuffle(items)
        for item in items:
            local_path = item.local_path
            if local_path and await self._set_wallpaper_path(local_path):
                return True
        return False

    async def _apply_intellimarkets(self, source: dict[str, Any] | None, params: list[dict[str, Any]]) -> bool:
        if not source:
            return False
        try:
            paths = await self._im_executor.execute(source, params)
        except Exception as exc:  # pragma: no cover - network variability
            logger.error("IntelliMarkets 源执行失败: {error}", error=str(exc))
            return False
        random.shuffle(paths)
        for path in paths:
            if await self._set_wallpaper_path(path):
                return True
        return False

    async def _apply_ai(self, config: dict[str, Any]) -> bool:
        provider = str(config.get("provider") or "pollinations")
        prompt = str(config.get("prompt") or "").strip()
        if not prompt:
            return False
        width = config.get("width")
        height = config.get("height")
        allow_nsfw = bool(self._settings_store.get("wallpaper.allow_nsfw", False))
        params: dict[str, str] = {}
        if width:
            params["width"] = str(width)
        if height:
            params["height"] = str(height)
        params["safe"] = "false" if allow_nsfw else "true"
        seed = config.get("seed")
        if seed:
            params["seed"] = str(seed)
        enhance = config.get("enhance")
        if enhance:
            params["enhance"] = "true"
        url = _build_ai_url(provider, prompt, params)
        return await self._download_and_apply(url, prefix="ai")

    async def _download_and_apply(self, url: str | None, *, prefix: str) -> bool:
        if not url:
            return False
        cache_dir = AUTO_CACHE_DIR / prefix
        cache_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{prefix}-{int(time.time())}-{_random_id()[:8]}"
        try:
            logger.debug("下载壁纸：url={} prefix={}", url, prefix)
            path_str = await asyncio.to_thread(
                ltwapi.download_file,
                url,
                str(cache_dir),
                filename,
                120,
                3,
                {"Accept": "image/*"},
                None,
                False,
            )
        except Exception as exc:  # pragma: no cover - network errors
            logger.error("下载图片失败: {error}", error=str(exc))
            return False
        if not path_str:
            return False
        logger.debug("图片下载完成：{}", path_str)
        return await self._set_wallpaper_path(Path(path_str))

    async def _set_wallpaper_path(self, path: Path) -> bool:
        if not path.exists():
            logger.debug("壁纸路径不存在：{}", path)
            return False
        try:
            logger.debug("开始设置壁纸：{}", path)
            await asyncio.to_thread(ltwapi.set_wallpaper, str(path))
            return True
        except Exception as exc:  # pragma: no cover - platform dependent
            logger.error("设置壁纸失败: {error}", error=str(exc))
            return False

    async def _resolve_favorite_path(self, item: FavoriteItem) -> Path | None:
        candidates: list[str] = []
        if item.local_path:
            candidates.append(item.local_path)
        if item.localization.local_path:
            candidates.append(item.localization.local_path)
        if item.source.local_path:
            candidates.append(item.source.local_path)
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return Path(candidate)
        preview = item.preview_url or item.source.preview_url or item.source.url
        if not preview:
            return None
        if preview.startswith("data:"):
            try:
                return await asyncio.to_thread(_save_data_url, preview, AUTO_CACHE_DIR / "favorites")
            except Exception:  # pragma: no cover - invalid payload
                return None
        return await self._download_to_cache(preview, AUTO_CACHE_DIR / "favorites")

    async def _download_to_cache(self, url: str, directory: Path) -> Path | None:
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"fav-{int(time.time())}-{_random_id()[:6]}"
        try:
            path_str = await asyncio.to_thread(
                ltwapi.download_file,
                url,
                str(directory),
                filename,
                120,
                2,
                {"Accept": "image/*"},
                None,
                False,
            )
        except Exception as exc:  # pragma: no cover - network
            logger.error("收藏图片下载失败: {error}", error=str(exc))
            return None
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        return path

    def _next_schedule(
        self,
        now_struct: time.struct_time,
        entries: Sequence[ScheduleEntry],
    ) -> tuple[float, ScheduleEntry] | None:
        if not entries:
            return None
        now = datetime.now()
        best_dt: datetime | None = None
        best_entry: ScheduleEntry | None = None
        for entry in entries:
            try:
                hour, minute = [int(part) for part in entry.time_str.split(":", 1)]
            except Exception:
                logger.debug("跳过无效的定时任务时间：{}", entry.time_str)
                continue
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            if best_dt is None or candidate < best_dt:
                best_dt = candidate
                best_entry = entry
        if best_dt is None or best_entry is None:
            return None
        return best_dt.timestamp(), best_entry

    def _collect_slideshow_candidates(self, items: Sequence[SlideshowItem]) -> list[Path]:
        paths: list[Path] = []
        for item in items:
            raw_path = item.path
            if not raw_path:
                continue
            path = Path(raw_path)
            if item.kind == "file" and path.exists() and path.is_file():
                if path.suffix.lower() in IMAGE_EXTENSIONS:
                    paths.append(path)
            elif item.kind == "folder" and path.exists() and path.is_dir():
                paths.extend(_iter_folder_images(path))
        paths.sort(key=lambda path: (path.parent.as_posix().lower(), path.name.lower()))
        return paths


class _IntelliMarketsExecutor:
    """Execute IntelliMarkets wallpaper sources independently of the UI."""

    def __init__(self) -> None:
        self._session_timeout = aiohttp.ClientTimeout(total=90)

    async def execute(
        self,
        source: dict[str, Any],
        params: Sequence[dict[str, Any]],
    ) -> list[Path]:
        param_pairs: list[tuple[dict[str, Any], Any]] = []
        for item in params:
            config = item.get("config") or item.get("parameter") or {}
            value = item.get("value")
            if not isinstance(config, dict):
                continue
            param_pairs.append((config, value))
        request = self._build_request(source, param_pairs)
        async with aiohttp.ClientSession(timeout=self._session_timeout) as session:
            async with session.request(
                request["method"],
                request["url"],
                headers=request.get("headers"),
                json=request.get("body"),
            ) as resp:
                status = resp.status
                headers = {k: v for k, v in resp.headers.items()}
                content_type = headers.get("Content-Type", "")
                raw = await resp.read()
                if status >= 400:
                    snippet = raw.decode("utf-8", errors="ignore")[:200]
                    raise RuntimeError(f"HTTP {status}: {snippet}")
                response_cfg = ((source.get("content") or {}).get("response") or {})
                image_cfg = response_cfg.get("image") or {}
                payload: Any | None = None
                binary_payload: bytes | None = None
                if image_cfg.get("content_type", "URL").upper() == "BINARY" and not content_type.lower().startswith("application/json"):
                    binary_payload = raw
                else:
                    text = raw.decode("utf-8", errors="ignore") if raw else ""
                    payload = json.loads(text) if text else {}
                return await self._process_response(
                    source,
                    image_cfg,
                    payload,
                    binary_payload,
                    headers,
                    param_pairs,
                )

    def _build_request(
        self,
        source: dict[str, Any],
        param_pairs: Sequence[tuple[dict[str, Any], Any]],
    ) -> dict[str, Any]:
        method = str(source.get("func") or "GET").upper()
        raw_url = str(source.get("link") or "").strip()
        if not raw_url:
            raise ValueError("图片源缺少请求链接")
        base_url, _, raw_query = raw_url.partition("?")
        base_url = base_url.rstrip("/")
        query_pairs: list[tuple[str, str]] = []
        if raw_query:
            query_pairs.extend(parse_qsl(raw_query, keep_blank_values=True))
        path_segments: list[str] = []
        body_payload: dict[str, Any] = {}
        headers = (source.get("content") or {}).get("headers") or {}
        for param, value in param_pairs:
            name = param.get("name")
            prepared_query = self._prepare_value(param, value, as_query=True)
            prepared_body = self._prepare_value(param, value, as_query=False)
            if name in (None, ""):
                values = prepared_query if isinstance(prepared_query, list) else [prepared_query]
                for segment in values:
                    if segment in (None, ""):
                        continue
                    encoded = quote(str(segment).strip("/"), safe="")
                    if encoded:
                        path_segments.append(encoded)
                continue
            if method in {"GET", "DELETE"}:
                if isinstance(prepared_query, list):
                    for item in prepared_query:
                        if item in (None, ""):
                            continue
                        query_pairs.append((name, str(item)))
                elif prepared_query not in (None, ""):
                    query_pairs.append((name, str(prepared_query)))
            elif prepared_body is not None:
                body_payload[name] = prepared_body
        final_url = base_url
        if path_segments:
            final_url = "/".join(segment for segment in [base_url, *path_segments] if segment)
        if query_pairs:
            final_url = (
                f"{final_url}?"
                + "&".join(
                    f"{quote(str(key), safe='')}={quote(str(value), safe='')}"
                    for key, value in query_pairs
                )
            )
        return {
            "url": final_url,
            "method": method,
            "body": body_payload if body_payload else None,
            "headers": headers,
        }

    def _prepare_value(self, param: dict[str, Any], value: Any, *, as_query: bool) -> Any:
        split_str = param.get("split_str")
        if isinstance(value, list):
            if split_str and as_query:
                return split_str.join(str(item) for item in value)
            return [self._format_scalar(item, as_query=as_query) for item in value]
        if isinstance(value, tuple):
            return [self._format_scalar(item, as_query=as_query) for item in value]
        return self._format_scalar(value, as_query=as_query)

    def _format_scalar(self, value: Any, *, as_query: bool) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value and as_query else ("false" if as_query else value)
        if isinstance(value, (int, float)):
            return str(value) if as_query else value
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", errors="ignore")
        if isinstance(value, str):
            return value
        if isinstance(value, Sequence):
            return [self._format_scalar(item, as_query=as_query) for item in value]
        return json.dumps(value, ensure_ascii=False)

    async def _process_response(
        self,
        source: dict[str, Any],
        image_cfg: dict[str, Any],
        payload: Any,
        binary: bytes | None,
        headers: dict[str, str],
        param_pairs: Sequence[tuple[dict[str, Any], Any]],
    ) -> list[Path]:
        storage_dir = AUTO_CACHE_DIR / "intellimarkets" / _slugify(
            source.get("friendly_name") or source.get("file_name") or "intellimarkets",
        )
        storage_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        image_type = str(image_cfg.get("content_type") or "URL").upper()
        if image_type == "BINARY":
            if not binary:
                raise RuntimeError("接口未返回图片数据")
            path = await asyncio.to_thread(
                _save_bytes,
                storage_dir,
                binary,
                headers.get("Content-Type"),
                timestamp,
            )
            return [path]
        values = _extract_path_values(payload, image_cfg.get("path"))
        if image_cfg.get("is_list"):
            values = _flatten_sequence_values(values)
        results: list[Path] = []
        for idx, raw in enumerate(values):
            if raw in (None, ""):
                continue
            url = raw
            if isinstance(raw, dict):
                url = raw.get("url") or raw.get("src") or raw.get("image") or raw.get("href")
            if not url:
                continue
            if image_cfg.get("is_base64"):
                try:
                    data = base64.b64decode(str(url))
                except Exception:
                    continue
                path = await asyncio.to_thread(
                    _save_bytes,
                    storage_dir,
                    data,
                    headers.get("Content-Type"),
                    timestamp + idx,
                )
                results.append(path)
                continue
            download = await asyncio.to_thread(
                ltwapi.download_file,
                str(url),
                str(storage_dir),
                f"im-{timestamp}-{idx}",
                120,
                2,
                {"Accept": "image/*"},
                None,
                False,
            )
            if download:
                candidate = Path(download)
                if candidate.exists():
                    results.append(candidate)
        return results


def _random_id() -> str:
    return os.urandom(8).hex()


def _slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    return text or "item"


def _normalize_bing_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://cn.bing.com{url}" if url.startswith("/") else f"https://cn.bing.com/{url}"


def _build_ai_url(provider: str, prompt: str, params: dict[str, str]) -> str:
    encoded_prompt = quote_plus(prompt)
    if provider == "pollinations":
        base = f"https://image.pollinations.ai/prompt/{encoded_prompt}&nologo=true"
    else:
        base = f"https://image.pollinations.ai/prompt/{encoded_prompt}&nologo=true"
    if not params:
        return base
    suffix = "&".join(f"{key}={quote_plus(value)}" for key, value in params.items())
    return f"{base}?{suffix}"


def _save_bytes(directory: Path, data: bytes, content_type: str | None, seed: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ext = None
    if content_type:
        ext = mimetypes.guess_extension(content_type)
    if not ext:
        ext = ".jpg"
    path = directory / f"{seed}{ext}"
    path.write_bytes(data)
    return path


def _extract_path_values(payload: Any, path: str | None) -> list[Any]:
    if payload is None:
        return []
    if not path:
        if isinstance(payload, list):
            return payload
        return [payload]
    tokens = _parse_path_tokens(path)
    results: list[Any] = []

    def traverse(current: Any, index: int) -> None:
        if index >= len(tokens):
            results.append(current)
            return
        token_type, token_value = tokens[index]
        if token_type == "key":
            if isinstance(current, dict) and token_value in current:
                traverse(current[token_value], index + 1)
        elif token_type == "index":
            if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
                try:
                    traverse(current[token_value], index + 1)
                except (IndexError, TypeError):
                    return
        elif token_type == "wildcard":
            if isinstance(current, dict):
                for value in current.values():
                    traverse(value, index + 1)
            elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
                for value in current:
                    traverse(value, index + 1)

    traverse(payload, 0)
    return results


def _flatten_sequence_values(values: Sequence[Any]) -> list[Any]:
    flattened: list[Any] = []
    for value in values:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            flattened.extend(_flatten_sequence_values(list(value)))
        else:
            flattened.append(value)
    return flattened


def _parse_path_tokens(path: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    buffer: list[str] = []
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if buffer:
                tokens.append(("key", "".join(buffer)))
                buffer.clear()
            i += 1
            continue
        if ch == "[":
            if buffer:
                tokens.append(("key", "".join(buffer)))
                buffer.clear()
            j = path.find("]", i)
            if j == -1:
                break
            content = path[i + 1 : j]
            if content == "*":
                tokens.append(("wildcard", None))
            else:
                try:
                    tokens.append(("index", int(content)))
                except ValueError:
                    tokens.append(("key", content))
            i = j + 1
            continue
        buffer.append(ch)
        i += 1
    if buffer:
        tokens.append(("key", "".join(buffer)))
    return tokens


def _iter_folder_images(folder: Path) -> Iterator[Path]:
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def _save_data_url(data_url: str, directory: Path) -> Path:
    header, _, payload = data_url.partition(",")
    if not payload:
        raise ValueError("无效的数据 URL")
    mime = "image/jpeg"
    if header.startswith("data:"):
        meta = header[5:]
        if ";" in meta:
            mime = meta.split(";", 1)[0] or mime
        elif meta:
            mime = meta
    directory.mkdir(parents=True, exist_ok=True)
    data = base64.b64decode(payload)
    ext = mimetypes.guess_extension(mime) or ".jpg"
    path = directory / f"data-{int(time.time())}-{_random_id()[:6]}{ext}"
    path.write_bytes(data)
    return path
