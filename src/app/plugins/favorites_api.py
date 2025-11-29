"""Plugin-facing favorites API facade."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from app.favorites import (
    FavoriteAIResult,
    FavoriteClassifier,
    FavoriteFolder,
    FavoriteItem,
    FavoriteManager,
    FavoriteSource,
)


class FavoriteService:
    """Restrictive façade over :class:`FavoriteManager` for plugins."""

    def __init__(
        self,
        manager: FavoriteManager,
        ensure_permission: Callable[[str], None],
    ) -> None:
        self._manager = manager
        self._ensure_permission = ensure_permission

    # ------------------------------------------------------------------
    # folder operations
    # ------------------------------------------------------------------
    def list_folders(self) -> list[FavoriteFolder]:
        self._ensure_permission("favorites_read")
        return self._manager.list_folders()

    def get_folder(self, folder_id: str) -> FavoriteFolder | None:
        self._ensure_permission("favorites_read")
        return self._manager.get_folder(folder_id)

    def create_folder(
        self,
        name: str,
        *,
        description: str = "",
        metadata: dict | None = None,
    ) -> FavoriteFolder:
        self._ensure_permission("favorites_write")
        return self._manager.create_folder(
            name,
            description=description,
            metadata=metadata,
        )

    def update_folder(
        self,
        folder_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> bool:
        self._ensure_permission("favorites_write")
        return self._manager.rename_folder(
            folder_id,
            name=name,
            description=description,
        )

    def delete_folder(
        self,
        folder_id: str,
        *,
        move_items_to: str | None = "default",
    ) -> bool:
        self._ensure_permission("favorites_write")
        return self._manager.delete_folder(folder_id, move_items_to=move_items_to)

    def reorder_folders(self, ordered_ids: Sequence[str]) -> None:
        self._ensure_permission("favorites_write")
        self._manager.reorder_folders(ordered_ids)

    # ------------------------------------------------------------------
    # item operations
    # ------------------------------------------------------------------
    def list_items(self, folder_id: str | None = None) -> list[FavoriteItem]:
        self._ensure_permission("favorites_read")
        return self._manager.list_items(folder_id)

    def get_item(self, item_id: str) -> FavoriteItem | None:
        self._ensure_permission("favorites_read")
        return self._manager.get_item(item_id)

    def find_by_source(self, source: FavoriteSource | dict) -> FavoriteItem | None:
        self._ensure_permission("favorites_read")
        normalized = source if isinstance(source, FavoriteSource) else FavoriteSource.from_dict(source)
        return self._manager.find_by_source(normalized)

    def add_or_update_item(
        self,
        *,
        folder_id: str | None,
        title: str,
        description: str = "",
        tags: Sequence[str] | None = None,
        source: FavoriteSource | dict | None = None,
        preview_url: str | None = None,
        local_path: str | None = None,
        extra: dict | None = None,
        merge_tags: bool = True,
    ) -> tuple[FavoriteItem, bool]:
        self._ensure_permission("favorites_write")
        normalized_source = (
            source if isinstance(source, FavoriteSource) else FavoriteSource.from_dict(source)
        )
        return self._manager.add_or_update_item(
            folder_id=folder_id,
            title=title,
            description=description,
            tags=tags,
            source=normalized_source,
            preview_url=preview_url,
            local_path=local_path,
            extra=extra,
            merge_tags=merge_tags,
        )

    def add_local_item(
        self,
        *,
        path: str,
        folder_id: str | None = None,
        title: str | None = None,
        description: str = "",
        tags: Sequence[str] | None = None,
        source_title: str | None = None,
        extra: dict | None = None,
        merge_tags: bool = True,
    ) -> tuple[FavoriteItem, bool]:
        self._ensure_permission("favorites_write")
        return self._manager.add_local_item(
            path=path,
            folder_id=folder_id,
            title=title,
            description=description,
            tags=tags,
            source_title=source_title,
            extra=extra,
            merge_tags=merge_tags,
        )

    def update_item(
        self,
        item_id: str,
        *,
        folder_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: Sequence[str] | None = None,
        extra: dict | None = None,
    ) -> bool:
        self._ensure_permission("favorites_write")
        return self._manager.update_item(
            item_id,
            folder_id=folder_id,
            title=title,
            description=description,
            tags=tags,
            extra=extra,
        )

    def remove_item(self, item_id: str) -> bool:
        self._ensure_permission("favorites_write")
        return self._manager.remove_item(item_id)

    # ------------------------------------------------------------------
    # localization & AI helpers
    # ------------------------------------------------------------------
    def localize_items_from_files(self, mapping: dict[str, str]) -> dict[str, Path | None]:
        self._ensure_permission("favorites_export")
        results: dict[str, Path | None] = {}
        for item_id, source_path in mapping.items():
            results[item_id] = self._manager.localize_item_from_file(item_id, source_path)
        return results

    def reset_localization(self, item_ids: Iterable[str]) -> None:
        self._ensure_permission("favorites_write")
        for item_id in item_ids:
            self._manager.reset_localization(item_id)

    def register_classifier(self, classifier: FavoriteClassifier | None) -> None:
        self._ensure_permission("favorites_write")
        self._manager.set_classifier(classifier)

    async def classify_item(self, item_id: str) -> FavoriteAIResult | None:
        self._ensure_permission("favorites_write")
        return await self._manager.maybe_classify_item(item_id)

    # ------------------------------------------------------------------
    # import / export
    # ------------------------------------------------------------------
    def export_folders(
        self,
        target_path: str | Path,
        folder_ids: Sequence[str] | None = None,
        *,
        include_assets: bool = True,
    ) -> Path:
        self._ensure_permission("favorites_export")
        return self._manager.export_folders(Path(target_path), folder_ids, include_assets=include_assets)

    def export_items(
        self,
        target_path: str | Path,
        item_ids: Sequence[str],
        *,
        include_assets: bool = True,
    ) -> Path:
        self._ensure_permission("favorites_export")
        return self._manager.export_items(Path(target_path), item_ids, include_assets=include_assets)

    def import_package(self, source_path: str | Path) -> tuple[int, int]:
        self._ensure_permission("favorites_export")
        return self._manager.import_folders(Path(source_path))

    # ------------------------------------------------------------------
    # utility
    # ------------------------------------------------------------------
    def localization_root(self) -> Path:
        self._ensure_permission("favorites_read")
        return self._manager.localization_root()


__all__ = ["FavoriteService"]
