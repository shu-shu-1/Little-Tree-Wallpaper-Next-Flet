# -*- coding: utf-8 -*-
"""Favorite management subsystem for Little Tree Wallpaper Next."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import shutil
import tempfile
import time
import uuid
from zipfile import ZIP_DEFLATED, ZipFile
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Awaitable, Dict, List, Protocol, Sequence, Tuple, Union, Literal

from loguru import logger

from app.paths import DATA_DIR

ClassifierResult = Union["FavoriteAIResult", Awaitable["FavoriteAIResult | None"], None]


class FavoriteClassifier(Protocol):
    """Callable interface used to plug in AI-assisted classification."""

    def __call__(self, item: "FavoriteItem") -> ClassifierResult:  # pragma: no cover - Protocol signature
        ...


@dataclass(slots=True)
class FavoriteSource:
    """Origin metadata describing where a favorite entry comes from."""

    type: str = "unknown"
    identifier: str = ""
    title: str = ""
    url: str | None = None
    preview_url: str | None = None
    local_path: str | None = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "identifier": self.identifier,
            "title": self.title,
            "url": self.url,
            "preview_url": self.preview_url,
            "local_path": self.local_path,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "FavoriteSource":
        if not data:
            return cls()
        return cls(
            type=str(data.get("type", "unknown")),
            identifier=str(data.get("identifier", "")),
            title=str(data.get("title", "")),
            url=data.get("url"),
            preview_url=data.get("preview_url"),
            local_path=data.get("local_path"),
            extra=dict(data.get("extra", {})),
        )


@dataclass(slots=True)
class FavoriteAIInfo:
    """Stores AI metadata for a favorite entry."""

    status: Literal["idle", "pending", "running", "completed", "failed"] = "idle"
    suggested_tags: List[str] = field(default_factory=list)
    suggested_folder_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: float | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "suggested_tags": list(self.suggested_tags),
            "suggested_folder_id": self.suggested_folder_id,
            "metadata": dict(self.metadata),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "FavoriteAIInfo":
        if not data:
            return cls()
        info = cls()
        info.status = data.get("status", "idle")  # type: ignore[assignment]
        info.suggested_tags = list(data.get("suggested_tags", []))
        info.suggested_folder_id = data.get("suggested_folder_id")
        info.metadata = dict(data.get("metadata", {}))
        info.updated_at = data.get("updated_at")
        return info


@dataclass(slots=True)
class FavoriteLocalizationInfo:
    """Tracks localization (downloaded assets) for a favorite entry."""

    status: Literal["absent", "pending", "completed", "failed"] = "absent"
    local_path: str | None = None
    folder_path: str | None = None
    updated_at: float | None = None
    message: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "local_path": self.local_path,
            "folder_path": self.folder_path,
            "updated_at": self.updated_at,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "FavoriteLocalizationInfo":
        if not data:
            return cls()
        info = cls()
        info.status = data.get("status", "absent")  # type: ignore[assignment]
        info.local_path = data.get("local_path")
        info.folder_path = data.get("folder_path")
        info.updated_at = data.get("updated_at")
        info.message = data.get("message")
        return info


@dataclass(slots=True)
class FavoriteItem:
    """Single user favorite entry."""

    id: str
    folder_id: str
    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    source: FavoriteSource = field(default_factory=FavoriteSource)
    preview_url: str | None = None
    local_path: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ai: FavoriteAIInfo = field(default_factory=FavoriteAIInfo)
    localization: FavoriteLocalizationInfo = field(default_factory=FavoriteLocalizationInfo)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "folder_id": self.folder_id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "source": self.source.to_dict(),
            "preview_url": self.preview_url,
            "local_path": self.local_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ai": self.ai.to_dict(),
            "localization": self.localization.to_dict(),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FavoriteItem":
        return cls(
            id=str(data.get("id")),
            folder_id=str(data.get("folder_id", "default")),
            title=str(data.get("title", "未命名收藏")),
            description=str(data.get("description", "")),
            tags=list(data.get("tags", [])),
            source=FavoriteSource.from_dict(data.get("source")),
            preview_url=data.get("preview_url"),
            local_path=data.get("local_path"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            ai=FavoriteAIInfo.from_dict(data.get("ai")),
            localization=FavoriteLocalizationInfo.from_dict(data.get("localization")),
            extra=dict(data.get("extra", {})),
        )

    def update_timestamp(self) -> None:
        self.updated_at = time.time()


@dataclass(slots=True)
class FavoriteFolder:
    """User-defined folder grouping favorites."""

    id: str
    name: str
    description: str = ""
    order: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FavoriteFolder":
        return cls(
            id=str(data.get("id")),
            name=str(data.get("name", "收藏夹")),
            description=str(data.get("description", "")),
            order=int(data.get("order", 0)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            metadata=dict(data.get("metadata", {})),
        )

    def touch(self) -> None:
        self.updated_at = time.time()


@dataclass(slots=True)
class FavoriteAIResult:
    """Return value used by an AI classifier to provide suggestions."""

    tags: Sequence[str] = field(default_factory=list)
    folder_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FavoriteCollection:
    """Serialized representation of the favorites database."""

    version: int = 1
    folders: Dict[str, FavoriteFolder] = field(default_factory=dict)
    items: Dict[str, FavoriteItem] = field(default_factory=dict)
    folder_order: List[str] = field(default_factory=list)

    def ensure_default_folder(self) -> FavoriteFolder:
        folder = self.folders.get("default")
        if folder is None:
            folder = FavoriteFolder(
                id="default",
                name="默认收藏夹",
                description="系统自动创建的默认收藏夹",
                order=0,
            )
            self.folders[folder.id] = folder
        if "default" not in self.folder_order:
            self.folder_order.insert(0, "default")
        self._normalize_orders()
        return folder

    def _normalize_orders(self) -> None:
        cleaned_order: List[str] = []
        for folder_id in self.folder_order:
            if folder_id in self.folders and folder_id not in cleaned_order:
                cleaned_order.append(folder_id)
        for folder_id in self.folders.keys():
            if folder_id not in cleaned_order:
                cleaned_order.append(folder_id)
        self.folder_order = cleaned_order
        for index, folder_id in enumerate(self.folder_order):
            folder = self.folders.get(folder_id)
            if folder:
                folder.order = index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "folders": {fid: folder.to_dict() for fid, folder in self.folders.items()},
            "items": {iid: item.to_dict() for iid, item in self.items.items()},
            "folder_order": list(self.folder_order),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FavoriteCollection":
        collection = cls()
        collection.version = int(data.get("version", 1))
        folders = data.get("folders", {})
        if isinstance(folders, dict):
            collection.folders = {
                str(fid): FavoriteFolder.from_dict(folder_dict)
                for fid, folder_dict in folders.items()
            }
        items = data.get("items", {})
        if isinstance(items, dict):
            collection.items = {
                str(iid): FavoriteItem.from_dict(item_dict)
                for iid, item_dict in items.items()
            }
        order = data.get("folder_order", [])
        if isinstance(order, list):
            collection.folder_order = [str(fid) for fid in order]
        collection.ensure_default_folder()
        return collection


class FavoriteManager:
    """High-level API for managing favorites on disk."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._path = storage_path or DATA_DIR / "favorites" / "favorites.json"
        self._lock = RLock()
        self._collection = FavoriteCollection()
        self._classifier: FavoriteClassifier | None = None
        self.load()

    # ------------------------------------------------------------------
    # persistence helpers
    # ------------------------------------------------------------------
    def _ensure_storage_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        with self._lock:
            try:
                if not self._path.exists():
                    self._collection = FavoriteCollection()
                    self._collection.ensure_default_folder()
                    return
                with self._path.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
                self._collection = FavoriteCollection.from_dict(data)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"加载收藏数据失败: {exc}")
                self._collection = FavoriteCollection()
                self._collection.ensure_default_folder()

    def save(self) -> None:
        with self._lock:
            self._ensure_storage_dir()
            try:
                payload = self._collection.to_dict()
                with self._path.open("w", encoding="utf-8") as fp:
                    json.dump(payload, fp, ensure_ascii=False, indent=2)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"保存收藏数据失败: {exc}")

    # ------------------------------------------------------------------
    # folder ops
    # ------------------------------------------------------------------
    def list_folders(self) -> List[FavoriteFolder]:
        with self._lock:
            folders = [
                self._collection.folders[fid]
                for fid in self._collection.folder_order
                if fid in self._collection.folders
            ]
            return [FavoriteFolder.from_dict(folder.to_dict()) for folder in folders]

    def get_folder(self, folder_id: str) -> FavoriteFolder | None:
        with self._lock:
            folder = self._collection.folders.get(folder_id)
            return FavoriteFolder.from_dict(folder.to_dict()) if folder else None

    def create_folder(
        self,
        name: str,
        *,
        description: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> FavoriteFolder:
        normalized_name = name.strip() or "未命名收藏夹"
        metadata = metadata or {}
        with self._lock:
            folder_id = uuid.uuid4().hex
            folder = FavoriteFolder(
                id=folder_id,
                name=normalized_name,
                description=description.strip(),
                order=len(self._collection.folder_order),
                metadata=dict(metadata),
            )
            self._collection.folders[folder_id] = folder
            self._collection.folder_order.append(folder_id)
            self._collection.ensure_default_folder()
            self.save()
            return FavoriteFolder.from_dict(folder.to_dict())

    def rename_folder(
        self,
        folder_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> bool:
        with self._lock:
            folder = self._collection.folders.get(folder_id)
            if not folder:
                return False
            if name is not None:
                new_name = name.strip()
                if new_name:
                    folder.name = new_name
            if description is not None:
                folder.description = description.strip()
            folder.touch()
            self.save()
            return True

    def delete_folder(self, folder_id: str, *, move_items_to: str | None = "default") -> bool:
        if folder_id == "default":
            return False
        with self._lock:
            if folder_id not in self._collection.folders:
                return False
            destination = move_items_to or "default"
            if destination not in self._collection.folders:
                self._collection.ensure_default_folder()
                destination = "default"
            for item in self._collection.items.values():
                if item.folder_id == folder_id:
                    item.folder_id = destination
                    item.update_timestamp()
            del self._collection.folders[folder_id]
            self._collection.folder_order = [
                fid for fid in self._collection.folder_order if fid != folder_id
            ]
            self._collection.ensure_default_folder()
            self.save()
            return True

    def reorder_folders(self, ordered_ids: Sequence[str]) -> None:
        with self._lock:
            unique_ids = []
            for folder_id in ordered_ids:
                if folder_id in self._collection.folders and folder_id not in unique_ids:
                    unique_ids.append(folder_id)
            for folder_id in self._collection.folder_order:
                if folder_id not in unique_ids:
                    unique_ids.append(folder_id)
            self._collection.folder_order = list(unique_ids)
            self._collection.ensure_default_folder()
            self.save()

    # ------------------------------------------------------------------
    # localization helpers
    # ------------------------------------------------------------------
    def localization_root(self) -> Path:
        root = (self._path.parent / "localized").resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _sanitize_segment(self, value: str, fallback: str) -> str:
        normalized = value.strip()
        normalized = re.sub(r"[\\/:*?\"<>|]+", "-", normalized)
        normalized = re.sub(r"\s+", "-", normalized)
        sanitized = normalized.strip("-._")
        return sanitized or fallback

    def _localization_folder_segment(self, folder_id: str) -> str:
        folder = self._collection.folders.get(folder_id)
        base = folder.name if folder else folder_id
        return self._sanitize_segment(base or folder_id or "folder", folder_id or "folder")

    def _localization_filename(self, item: FavoriteItem, source_path: Path | None) -> str:
        suffix = source_path.suffix if source_path else ""
        if not suffix:
            suffix = ".bin"
        segment = self._sanitize_segment(item.title or "favorite", item.id[:8])
        return f"{segment}-{item.id[:8]}{suffix}"

    def localization_folder_path(self, folder_id: str, create: bool = True) -> Path:
        segment = self._localization_folder_segment(folder_id)
        target = self.localization_root() / segment
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    def localize_item_from_file(self, item_id: str, source_path: str) -> Path | None:
        source = Path(source_path)
        if not source.exists():
            return None
        with self._lock:
            item = self._collection.items.get(item_id)
            if not item:
                return None
            folder_id = item.folder_id
            filename = self._localization_filename(item, source)
            folder_segment = self._localization_folder_segment(folder_id)
        target_dir = (self.localization_root() / folder_segment).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = (target_dir / filename).resolve()
        try:
            shutil.copy2(source, destination)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"复制本地化文件失败: {exc}")
            self.update_localization(
                item_id,
                status="failed",
                local_path=None,
                folder_path="/".join([folder_segment]),
                message=str(exc),
            )
            return None
        rel_path = str(Path(folder_segment) / filename)
        self.update_localization(
            item_id,
            status="completed",
            local_path=str(destination),
            folder_path=rel_path,
            message=None,
        )
        return destination

    def _prepare_export(
        self,
        folder_ids: Sequence[str] | None,
        include_assets: bool = True,
        *,
        item_ids: Sequence[str] | None = None,
    ) -> tuple[Dict[str, Any], list[tuple[Path, str]]]:
        item_ids_set = {str(iid) for iid in item_ids} if item_ids else None
        with self._lock:
            if item_ids_set is None:
                if not folder_ids or "__all__" in folder_ids:
                    selected_folder_ids_list = list(self._collection.folders.keys())
                else:
                    selected_folder_ids_list = [
                        fid for fid in folder_ids if fid in self._collection.folders
                    ]
                if not selected_folder_ids_list:
                    selected_folder_ids_list = ["default"]
                selected_folder_ids_set = set(selected_folder_ids_list)
            else:
                selected_folder_ids_list = []
                selected_folder_ids_set: set[str] = set()

            item_payload: Dict[str, Dict[str, Any]] = {}
            asset_plan: list[tuple[Path, str]] = []
            timestamp = time.time()
            for item_id, item in self._collection.items.items():
                if item_ids_set is not None:
                    if item_id not in item_ids_set:
                        continue
                elif item.folder_id not in selected_folder_ids_set:
                    continue
                data = item.to_dict()
                folder_segment = self._localization_folder_segment(item.folder_id)
                data.setdefault("localization", {})["folder_path"] = folder_segment
                asset_source: Path | None = None
                if include_assets:
                    for candidate in (item.localization.local_path, item.local_path):
                        if candidate and Path(candidate).exists():
                            asset_source = Path(candidate)
                            break
                if include_assets and asset_source:
                    filename = self._localization_filename(item, asset_source)
                    rel_path = str(Path("assets") / folder_segment / filename)
                    data.setdefault("localization", {})["local_path"] = rel_path
                    asset_plan.append((asset_source, rel_path))
                item_payload[item_id] = data
                if item_ids_set is not None and item.folder_id not in selected_folder_ids_set:
                    selected_folder_ids_set.add(item.folder_id)

            if item_ids_set is not None and not item_payload:
                raise ValueError("指定的收藏不存在或已被移除。")

            folder_payload = {
                fid: self._collection.folders[fid].to_dict()
                for fid in selected_folder_ids_set
                if fid in self._collection.folders
            }
            order_payload = [
                fid
                for fid in self._collection.folder_order
                if fid in selected_folder_ids_set
            ]
            export_data = {
                "version": self._collection.version,
                "exported_at": timestamp,
                "folders": folder_payload,
                "items": item_payload,
                "folder_order": order_payload,
            }
        return export_data, asset_plan

    def _build_export_package(
        self,
        target_path: Path,
        export_data: Dict[str, Any],
        asset_plan: list[tuple[Path, str]],
    ) -> Path:
        target_path = Path(target_path)
        if target_path.is_dir():
            package_path = target_path / "favorites.ltwfav"
        else:
            package_path = target_path
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            for source, rel_path in asset_plan:
                destination = tmp_root / rel_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(source, destination)
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning(
                        "导出收藏时复制资源失败: {error}",
                        error=str(exc),
                    )
            json_path = tmp_root / "favorites.json"
            with json_path.open("w", encoding="utf-8") as fp:
                json.dump(export_data, fp, ensure_ascii=False, indent=2)
            package_path.parent.mkdir(parents=True, exist_ok=True)
            with ZipFile(package_path, "w", compression=ZIP_DEFLATED) as zf:
                for entry in tmp_root.rglob("*"):
                    arcname = entry.relative_to(tmp_root)
                    zf.write(entry, arcname)
        return package_path

    def export_folders(
        self,
        target_path: Path,
        folder_ids: Sequence[str] | None = None,
        *,
        include_assets: bool = True,
    ) -> Path:
        export_data, asset_plan = self._prepare_export(
            folder_ids,
            include_assets=include_assets,
        )
        return self._build_export_package(target_path, export_data, asset_plan)

    def export_items(
        self,
        target_path: Path,
        item_ids: Sequence[str],
        *,
        include_assets: bool = True,
    ) -> Path:
        if not item_ids:
            raise ValueError("需要至少选择一个收藏才能导出。")
        export_data, asset_plan = self._prepare_export(
            None,
            include_assets=include_assets,
            item_ids=item_ids,
        )
        return self._build_export_package(target_path, export_data, asset_plan)

    def import_folders(self, source_path: Path) -> tuple[int, int]:
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(str(source_path))
        tmp_dir = tempfile.TemporaryDirectory()
        tmp_root = Path(tmp_dir.name)
        try:
            if source_path.is_dir():
                for entry in source_path.rglob("*"):
                    destination = tmp_root / entry.relative_to(source_path)
                    if entry.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(entry, destination)
            else:
                with ZipFile(source_path, "r") as zf:
                    zf.extractall(tmp_root)
            json_path = tmp_root / "favorites.json"
            if not json_path.exists():
                raise FileNotFoundError("导入包缺少 favorites.json")
            with json_path.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)

            folders_data: Dict[str, Dict[str, Any]] = payload.get("folders", {}) or {}
            items_data: Dict[str, Dict[str, Any]] = payload.get("items", {}) or {}

            created_folders = 0
            imported_items = 0
            folder_mapping: Dict[str, str] = {}
            item_mapping: Dict[str, str] = {}

            with self._lock:
                for original_id, folder_dict in folders_data.items():
                    target_id = None
                    for existing_id, existing in self._collection.folders.items():
                        if existing.name == folder_dict.get("name"):
                            target_id = existing_id
                            existing.description = folder_dict.get("description", existing.description)
                            existing.metadata.update(folder_dict.get("metadata", {}))
                            existing.touch()
                            break
                    if not target_id:
                        target_id = uuid.uuid4().hex
                        new_folder = FavoriteFolder.from_dict(folder_dict)
                        new_folder.id = target_id
                        new_folder.created_at = time.time()
                        new_folder.updated_at = time.time()
                        self._collection.folders[target_id] = new_folder
                        self._collection.folder_order.append(target_id)
                        created_folders += 1
                    folder_mapping[original_id] = target_id

                for original_id, item_dict in items_data.items():
                    source_folder = item_dict.get("folder_id")
                    target_folder = folder_mapping.get(source_folder, "default")
                    new_id = uuid.uuid4().hex
                    new_item = FavoriteItem.from_dict(item_dict)
                    new_item.id = new_id
                    new_item.folder_id = target_folder
                    now = time.time()
                    new_item.created_at = now
                    new_item.updated_at = now
                    new_item.localization = FavoriteLocalizationInfo()
                    self._collection.items[new_id] = new_item
                    item_mapping[original_id] = new_id
                    imported_items += 1

                self._collection.ensure_default_folder()
                self.save()

            for original_id, new_id in item_mapping.items():
                item_dict = items_data.get(original_id) or {}
                localization_info = item_dict.get("localization") or {}
                rel_path = localization_info.get("local_path")
                if not rel_path:
                    continue
                asset_source = (tmp_root / rel_path).resolve()
                if asset_source.exists():
                    self.localize_item_from_file(new_id, str(asset_source))

            return created_folders, imported_items
        finally:
            tmp_dir.cleanup()

    def reset_localization(self, item_id: str) -> bool:
        with self._lock:
            item = self._collection.items.get(item_id)
            if not item:
                return False
            item.localization = FavoriteLocalizationInfo()
            item.update_timestamp()
            self.save()
            return True

    def update_localization(
        self,
        item_id: str,
        *,
        status: Literal["absent", "pending", "completed", "failed"],
        local_path: str | None = None,
        folder_path: str | None = None,
        message: str | None = None,
    ) -> bool:
        with self._lock:
            item = self._collection.items.get(item_id)
            if not item:
                return False
            item.localization.status = status
            item.localization.local_path = local_path
            item.localization.folder_path = folder_path
            item.localization.updated_at = time.time()
            item.localization.message = message
            item.update_timestamp()
            self.save()
            return True

    # ------------------------------------------------------------------
    # item ops
    # ------------------------------------------------------------------
    def _normalize_tags(self, tags: Sequence[str] | None) -> List[str]:
        if not tags:
            return []
        cleaned = []
        for tag in tags:
            value = str(tag).strip()
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned

    def _resolve_folder_id(self, folder_id: str | None) -> str:
        if not folder_id:
            return "default"
        if folder_id in self._collection.folders:
            return folder_id
        logger.warning("尝试写入不存在的收藏夹 {folder_id}，已自动切换到默认收藏夹", folder_id=folder_id)
        self._collection.ensure_default_folder()
        return "default"

    def list_items(self, folder_id: str | None = None) -> List[FavoriteItem]:
        with self._lock:
            items = list(self._collection.items.values())
            if folder_id and folder_id != "__all__":
                items = [item for item in items if item.folder_id == folder_id]
            items.sort(key=lambda item: item.updated_at, reverse=True)
            return [FavoriteItem.from_dict(item.to_dict()) for item in items]

    def get_item(self, item_id: str) -> FavoriteItem | None:
        with self._lock:
            item = self._collection.items.get(item_id)
            return FavoriteItem.from_dict(item.to_dict()) if item else None

    def find_by_source(self, source: FavoriteSource) -> FavoriteItem | None:
        if not source.identifier and not source.url:
            return None
        with self._lock:
            for item in self._collection.items.values():
                if item.source.identifier and source.identifier:
                    if item.source.identifier == source.identifier:
                        return FavoriteItem.from_dict(item.to_dict())
                if item.source.url and source.url:
                    if item.source.url == source.url:
                        return FavoriteItem.from_dict(item.to_dict())
        return None

    def add_or_update_item(
        self,
        *,
        folder_id: str | None,
        title: str,
        description: str = "",
        tags: Sequence[str] | None = None,
        source: FavoriteSource | Dict[str, Any] | None = None,
        preview_url: str | None = None,
        local_path: str | None = None,
        extra: Dict[str, Any] | None = None,
        merge_tags: bool = True,
    ) -> Tuple[FavoriteItem, bool]:
        resolved_source = (
            source
            if isinstance(source, FavoriteSource)
            else FavoriteSource.from_dict(source)
        )
        tags_list = self._normalize_tags(tags)
        normalized_title = title.strip() or "未命名收藏"
        normalized_description = description.strip()
        extra = dict(extra or {})
        with self._lock:
            self._collection.ensure_default_folder()
            resolved_folder_id = self._resolve_folder_id(folder_id)
            existing = None
            if resolved_source.identifier or resolved_source.url:
                existing = self.find_by_source(resolved_source)
            if existing:
                item = self._collection.items[existing.id]
                item.folder_id = resolved_folder_id
                item.title = normalized_title
                if normalized_description:
                    item.description = normalized_description
                if merge_tags:
                    merged = list({*item.tags, *tags_list}) if tags_list else item.tags
                    item.tags = self._normalize_tags(merged)
                else:
                    item.tags = tags_list
                if preview_url:
                    item.preview_url = preview_url
                if local_path:
                    item.local_path = local_path
                if extra:
                    item.extra.update(extra)
                item.update_timestamp()
                self.save()
                return FavoriteItem.from_dict(item.to_dict()), False

            item_id = uuid.uuid4().hex
            now = time.time()
            item = FavoriteItem(
                id=item_id,
                folder_id=resolved_folder_id,
                title=normalized_title,
                description=normalized_description,
                tags=tags_list,
                source=resolved_source,
                preview_url=preview_url,
                local_path=local_path,
                created_at=now,
                updated_at=now,
                extra=extra,
            )
            self._collection.items[item_id] = item
            self.save()
            return FavoriteItem.from_dict(item.to_dict()), True

    def add_local_item(
        self,
        *,
        path: str,
        folder_id: str | None = None,
        title: str | None = None,
        description: str = "",
        tags: Sequence[str] | None = None,
        source_title: str | None = None,
        extra: Dict[str, Any] | None = None,
        merge_tags: bool = True,
    ) -> tuple[FavoriteItem, bool]:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))

        identifier = "local::" + hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()
        source = FavoriteSource(
            type="local",
            identifier=identifier,
            title=source_title or resolved.stem,
            url=None,
            preview_url=None,
            local_path=str(resolved),
            extra=dict(extra or {}),
        )

        item, created = self.add_or_update_item(
            folder_id=folder_id,
            title=title or resolved.stem,
            description=description,
            tags=tags,
            source=source,
            preview_url=None,
            local_path=str(resolved),
            extra=extra,
            merge_tags=merge_tags,
        )

        self.update_localization(
            item.id,
            status="completed",
            local_path=str(resolved),
            folder_path=None,
            message=None,
        )

        refreshed = self.get_item(item.id) or item
        return refreshed, created

    def update_item(
        self,
        item_id: str,
        *,
        folder_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: Sequence[str] | None = None,
        extra: Dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            item = self._collection.items.get(item_id)
            if not item:
                return False
            if folder_id is not None:
                item.folder_id = self._resolve_folder_id(folder_id)
            if title is not None and title.strip():
                item.title = title.strip()
            if description is not None:
                item.description = description.strip()
            if tags is not None:
                item.tags = self._normalize_tags(tags)
            if extra:
                item.extra.update(extra)
            item.update_timestamp()
            self.save()
            return True

    def remove_item(self, item_id: str) -> bool:
        with self._lock:
            if item_id in self._collection.items:
                del self._collection.items[item_id]
                self.save()
                return True
            return False

    # ------------------------------------------------------------------
    # AI helpers
    # ------------------------------------------------------------------
    def set_classifier(self, classifier: FavoriteClassifier | None) -> None:
        with self._lock:
            self._classifier = classifier

    async def maybe_classify_item(self, item_id: str) -> FavoriteAIResult | None:
        classifier = None
        with self._lock:
            item = self._collection.items.get(item_id)
            if not item:
                return None
            classifier = self._classifier
            if classifier is None:
                return None
            item.ai.status = "pending"
            self.save()
        try:
            result = classifier(item)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"收藏 AI 分类失败: {exc}")
            with self._lock:
                item = self._collection.items.get(item_id)
                if item:
                    item.ai.status = "failed"
                    item.ai.metadata.update({"error": str(exc)})
                    item.ai.updated_at = time.time()
                    self.save()
            return None

        if result is None:
            with self._lock:
                item = self._collection.items.get(item_id)
                if item:
                    item.ai.status = "idle"
                    item.ai.updated_at = time.time()
                    self.save()
            return None

        with self._lock:
            item = self._collection.items.get(item_id)
            if not item:
                return result
            item.ai.status = "completed"
            item.ai.suggested_tags = self._normalize_tags(result.tags)
            item.ai.suggested_folder_id = result.folder_id
            item.ai.metadata = dict(result.metadata)
            item.ai.updated_at = time.time()
            self.save()
        return result


__all__ = [
    "FavoriteAIInfo",
    "FavoriteAIResult",
    "FavoriteCollection",
    "FavoriteFolder",
    "FavoriteItem",
    "FavoriteManager",
    "FavoriteSource",
    "FavoriteClassifier",
    "FavoriteLocalizationInfo",
]
