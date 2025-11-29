"""Wallpaper source registry and fetch helpers."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import aiohttp
import rtoml
from loguru import logger

import ltwapi

from .paths import BASE_DIR, CACHE_DIR, CONFIG_DIR, DATA_DIR
from .source_parser import (
    API,
    Category,
    SourceSpec,
    SourceValidationError,
    parse_source_file,
    parse_source_string,
)


class WallpaperSourceError(Exception):
    """Base class for wallpaper source issues."""


class WallpaperSourceImportError(WallpaperSourceError):
    pass


class WallpaperSourceFetchError(WallpaperSourceError):
    pass


_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_CATEGORY_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii", "ignore")
    ascii_str = ascii_str.lower().strip()
    ascii_str = ascii_str.replace(" ", "-")
    ascii_str = _SLUG_RE.sub("-", ascii_str)
    ascii_str = ascii_str.strip("-")
    return ascii_str or "source"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _guess_extension(url: str | None, content_type: str | None) -> str:
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext
    if url:
        parsed = Path(url)
        ext = parsed.suffix
        if ext:
            return ext
    return ".jpg"


def _decode_base64_image(data: str) -> tuple[bytes, str | None]:
    raw = data.strip()
    mime_type: str | None = None
    if raw.lower().startswith("data:"):
        header, _, payload = raw.partition(",")
        meta = header.split(";", 1)[0]
        if meta.startswith("data:"):
            mime_type = meta[5:] or None
        raw = payload
    padding = len(raw) % 4
    if padding:
        raw = raw + "=" * (4 - padding)
    try:
        decoded = base64.b64decode(raw, validate=False)
    except Exception as exc:  # pragma: no cover - invalid base64 handled upstream
        raise WallpaperSourceFetchError(f"invalid base64 payload: {exc}") from exc
    return decoded, mime_type


def _json_pointer(data: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return data
    if not pointer.startswith("/"):
        raise WallpaperSourceFetchError(f"invalid json pointer: {pointer}")
    parts = pointer.lstrip("/").split("/")
    current = data
    for part in parts:
        token = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError as exc:
                raise WallpaperSourceFetchError(f"pointer segment '{token}' is not index") from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise WallpaperSourceFetchError(f"pointer segment '{token}' out of range") from exc
        elif isinstance(current, dict):
            if token not in current:
                raise WallpaperSourceFetchError(f"pointer segment '{token}' missing")
            current = current[token]
        else:
            raise WallpaperSourceFetchError(f"pointer segment '{token}' invalid for type")
    return current


def _dot_path(data: Any, path: str) -> Any:
    if not path:
        return data
    tokens = path.split(".")
    current = data
    for token in tokens:
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes)) and token.isdigit():
            index = int(token)
            try:
                current = current[index]
            except (IndexError, TypeError) as exc:
                raise WallpaperSourceFetchError(f"index '{token}' out of range") from exc
            continue
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        raise WallpaperSourceFetchError(f"path segment '{token}' missing")
    return current


def _resolve_path(data: Any, path: str, *, fmt: str) -> Any:
    if fmt == "json" or path.startswith("/"):
        return _json_pointer(data, path)
    return _dot_path(data, path)


@dataclass(slots=True)
class WallpaperSourceRecord:
    identifier: str
    spec: SourceSpec
    path: Path
    origin: Literal["builtin", "user"]
    enabled: bool
    error: str | None = None


@dataclass(slots=True)
class WallpaperCategoryRef:
    source_id: str
    category_id: str
    label: str
    api_name: str
    api: API
    category: Category
    source_name: str
    search_tokens: tuple[str, ...]
    footer_text: str | None


@dataclass(slots=True)
class WallpaperItem:
    id: str
    title: str | None
    description: str | None
    copyright: str | None
    attribution: str | None
    footer_text: str | None
    local_path: Path | None
    preview_base64: str | None
    mime_type: str | None
    original_url: str | None
    source_id: str
    api_name: str
    category_label: str
    extra: dict[str, Any] = field(default_factory=dict)


class WallpaperSourceManager:
    def __init__(self) -> None:
        self._builtin_dir = BASE_DIR / "wallpaper_sources"
        self._user_dir = DATA_DIR / "wallpaper_sources"
        self._cache_dir = CACHE_DIR / "wallpaper_sources"
        self._state_path = CONFIG_DIR / "wallpaper_sources.json"
        self._records: dict[str, WallpaperSourceRecord] = {}
        self._state: dict[str, Any] = {}
        _ensure_dir(self._user_dir)
        _ensure_dir(self._cache_dir)
        self.reload()

    # ------------------------------------------------------------------
    # state helpers
    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        if not self._state_path.exists():
            self._state = {"enabled": {}, "order": [], "active_source": None}
            return
        try:
            self._state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - fallback to defaults
            logger.warning("failed to read wallpaper source state, resetting")
            self._state = {"enabled": {}, "order": [], "active_source": None}

    def _save_state(self) -> None:
        try:
            self._state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - logging only
            logger.error(f"保存壁纸源状态失败: {exc}")

    # ------------------------------------------------------------------
    # public api
    # ------------------------------------------------------------------
    def reload(self) -> None:
        self._load_state()
        records: dict[str, WallpaperSourceRecord] = {}
        enabled_state: dict[str, bool] = dict(self._state.get("enabled", {}))

        def merge_source(path: Path, origin: Literal["builtin", "user"]) -> None:
            try:
                spec = parse_source_file(path)
            except SourceValidationError as exc:
                logger.error("壁纸源 {path} 校验失败: {error}", path=path, error=str(exc))
                return
            identifier = spec.identifier
            enabled = enabled_state.get(identifier)
            if enabled is None:
                enabled = True if origin == "builtin" else True
                enabled_state[identifier] = enabled
            record = WallpaperSourceRecord(
                identifier=identifier,
                spec=spec,
                path=path,
                origin=origin,
                enabled=enabled,
            )
            prev = records.get(identifier)
            if prev is not None:
                if prev.origin == "builtin" and origin == "user":
                    records[identifier] = record
                elif prev.origin == origin:
                    logger.warning(
                        "壁纸源 {identifier} 在 {origin} 中重复，保留首次解析的版本",
                        identifier=identifier,
                        origin=origin,
                    )
            else:
                records[identifier] = record

        if self._builtin_dir.exists():
            for path in sorted(self._builtin_dir.glob("*.toml")):
                merge_source(path, "builtin")
        for path in sorted(self._user_dir.glob("*.toml")):
            merge_source(path, "user")

        removed = set(enabled_state) - set(records)
        for identifier in removed:
            enabled_state.pop(identifier, None)
        self._records = records
        self._state["enabled"] = enabled_state
        order: list[str] = []
        seen: set[str] = set()
        for identifier in self._state.get("order", []):
            if identifier in records and identifier not in seen:
                order.append(identifier)
                seen.add(identifier)
        for identifier in records:
            if identifier not in seen:
                order.append(identifier)
        self._state["order"] = order
        active = self._state.get("active_source")
        if not active or active not in records or not records[active].enabled:
            self._state["active_source"] = self.first_enabled_identifier()
        self._save_state()

    def list_records(self, *, include_disabled: bool = True) -> list[WallpaperSourceRecord]:
        ordered: list[WallpaperSourceRecord] = []
        for identifier in self._state.get("order", []):
            record = self._records.get(identifier)
            if not record:
                continue
            if include_disabled or record.enabled:
                ordered.append(record)
        return ordered

    def enabled_records(self) -> list[WallpaperSourceRecord]:
        return [record for record in self.list_records(include_disabled=False) if record.enabled]

    def get_record(self, identifier: str) -> WallpaperSourceRecord | None:
        return self._records.get(identifier)

    def set_enabled(self, identifier: str, enabled: bool) -> None:
        record = self._records.get(identifier)
        if record is None:
            raise WallpaperSourceError(f"source '{identifier}' not found")
        record.enabled = enabled
        self._state.setdefault("enabled", {})[identifier] = enabled
        if enabled and identifier not in self._state.get("order", []):
            self._state.setdefault("order", []).append(identifier)
        if enabled and self._state.get("active_source") is None:
            self._state["active_source"] = identifier
        if not enabled and self._state.get("active_source") == identifier:
            self._state["active_source"] = self.first_enabled_identifier()
        self._save_state()

    def set_active_source(self, identifier: str | None) -> None:
        if identifier is None:
            self._state["active_source"] = None
        elif identifier in self._records and self._records[identifier].enabled:
            self._state["active_source"] = identifier
        else:
            raise WallpaperSourceError(f"source '{identifier}' unavailable")
        self._save_state()

    def first_enabled_identifier(self) -> str | None:
        for record in self.list_records(include_disabled=False):
            if record.enabled:
                return record.identifier
        return None

    def active_source_identifier(self) -> str | None:
        active = self._state.get("active_source")
        if active and active in self._records and self._records[active].enabled:
            return active
        return self.first_enabled_identifier()

    def import_source(self, file_path: Path) -> WallpaperSourceRecord:
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            raise WallpaperSourceImportError(f"读取文件失败: {exc}") from exc
        try:
            spec = parse_source_string(text, path_hint=str(file_path))
        except SourceValidationError as exc:
            raise WallpaperSourceImportError(str(exc)) from exc
        dest = self._user_dir / f"{spec.identifier}.toml"
        try:
            dest.write_text(text, encoding="utf-8")
        except Exception as exc:
            raise WallpaperSourceImportError(f"写入目标文件失败: {exc}") from exc
        self._state.setdefault("order", [])
        if spec.identifier not in self._state["order"]:
            self._state["order"].append(spec.identifier)
        self._state.setdefault("enabled", {})[spec.identifier] = True
        self._state["active_source"] = spec.identifier
        self._save_state()
        self.reload()
        record = self._records.get(spec.identifier)
        if not record:
            raise WallpaperSourceImportError("导入后未能加载该壁纸源")
        return record

    def remove_source(self, identifier: str) -> None:
        record = self._records.get(identifier)
        if record is None:
            raise WallpaperSourceError("未找到该壁纸源")
        if record.origin != "user":
            raise WallpaperSourceError("内置壁纸源不可移除")
        try:
            record.path.unlink(missing_ok=True)
        except Exception as exc:
            raise WallpaperSourceError(f"删除文件失败: {exc}") from exc
        self._state["enabled"].pop(identifier, None)
        if identifier in self._state.get("order", []):
            self._state["order"].remove(identifier)
        if self._state.get("active_source") == identifier:
            self._state["active_source"] = None
        self._save_state()
        self.reload()

    # ------------------------------------------------------------------
    # category helpers
    # ------------------------------------------------------------------
    def category_refs(self, identifier: str) -> list[WallpaperCategoryRef]:
        record = self._records.get(identifier)
        if record is None:
            return []
        if not record.enabled:
            return []
        refs: list[WallpaperCategoryRef] = []
        spec = record.spec
        for api in spec.apis:
            categories = spec.api_categories.get(api.name, [])
            for index, category in enumerate(categories):
                label = self._category_label(category)
                if category.name:
                    search_label = category.name
                else:
                    search_label = label
                tokens = {
                    identifier.lower(),
                    spec.name.lower(),
                    api.name.lower(),
                    label.lower(),
                    search_label.lower(),
                }
                if category.category:
                    tokens.add(category.category.lower())
                if category.subcategory:
                    tokens.add(category.subcategory.lower())
                if category.subsubcategory:
                    tokens.add(category.subsubcategory.lower())
                if category.param_preset_id:
                    tokens.add(category.param_preset_id.lower())
                raw_id = f"{identifier}:{api.name}:{index}:{category.id or category.param_preset_id or index}"
                cat_id = _CATEGORY_ID_RE.sub("-", raw_id)
                refs.append(
                    WallpaperCategoryRef(
                        source_id=identifier,
                        category_id=cat_id,
                        label=label,
                        api_name=api.name,
                        api=api,
                        category=category,
                        source_name=spec.name,
                        search_tokens=tuple(sorted(tokens)),
                        footer_text=spec.effective_footer_for_api(api),
                    ),
                )
        return refs

    def find_category(self, category_id: str) -> WallpaperCategoryRef | None:
        for record in self.enabled_records():
            for ref in self.category_refs(record.identifier):
                if ref.category_id == category_id:
                    return ref
        return None

    # ------------------------------------------------------------------
    # fetching
    # ------------------------------------------------------------------
    async def fetch_category_items(
        self,
        category_id: str,
        params: dict[str, Any] | None = None,
    ) -> list[WallpaperItem]:
        ref = self.find_category(category_id)
        if ref is None:
            raise WallpaperSourceFetchError("未找到该分类或分类已被禁用")
        record = self._records.get(ref.source_id)
        if record is None or not record.enabled:
            raise WallpaperSourceFetchError("壁纸源不可用")
        api = ref.api
        fmt = api.format
        if fmt == "static_list":
            return await self._fetch_static_list(ref, record)
        if fmt == "static_dict":
            return await self._fetch_static_dict(ref, record)
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(ssl=False) if record.spec.skip_ssl_verify else None
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            if fmt == "image_url":
                return await self._fetch_image_url(ref, record, session, params)
            if fmt == "image_raw":
                return await self._fetch_image_raw(ref, record, session, params)
            if fmt == "image_base64":
                return await self._fetch_image_base64(ref, record, session, params)
            if fmt in {"json", "toml"}:
                return await self._fetch_structured(ref, record, session, params)
            raise WallpaperSourceFetchError(f"不支持的格式: {fmt}")

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _category_label(self, category: Category) -> str:
        if category.name:
            return category.name
        parts = [category.category]
        if category.subcategory:
            parts.append(category.subcategory)
        if category.subsubcategory:
            parts.append(category.subsubcategory)
        label = " / ".join(filter(None, parts)) or category.id or "未命名"
        if category.param_preset_id:
            label = f"{label} ({category.param_preset_id})"
        return label

    def _preset_values(
        self,
        spec: SourceSpec,
        category: Category,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not category.param_preset_id:
            return {}
        preset = spec.parameters.get(category.param_preset_id)
        if not preset:
            return {}
        values: dict[str, Any] = {}
        for option in preset.options:
            value = option.default
            if value is None:
                continue
            values[option.key] = value
        if overrides:
            for key, value in overrides.items():
                if value is None:
                    values.pop(key, None)
                    continue
                values[key] = value
        return values

    async def _fetch_static_list(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
    ) -> list[WallpaperItem]:
        urls = ref.api.static_list.urls if ref.api.static_list else []
        if not urls:
            return []
        items: list[WallpaperItem] = []
        for index, url in enumerate(urls):
            try:
                item = await self._prepare_item_from_url(
                    ref,
                    record,
                    url,
                    f"static-{index}",
                )
            except WallpaperSourceFetchError as exc:
                logger.error("静态壁纸加载失败: {error}", error=str(exc))
                continue
            items.append(item)
        return items

    async def _fetch_static_dict(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
    ) -> list[WallpaperItem]:
        entries = ref.api.static_dict.items if ref.api.static_dict else []
        if not entries:
            return []
        items: list[WallpaperItem] = []
        for index, entry in enumerate(entries):
            try:
                item = await self._prepare_item_from_url(
                    ref,
                    record,
                    entry.url,
                    f"static-dict-{index}",
                    title=entry.title,
                    description=entry.description,
                )
            except WallpaperSourceFetchError as exc:
                logger.error("静态字典壁纸加载失败: {error}", error=str(exc))
                continue
            items.append(item)
        return items

    async def _fetch_image_url(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
        session: aiohttp.ClientSession,
        overrides: dict[str, Any] | None,
    ) -> list[WallpaperItem]:
        if not ref.api.url:
            raise WallpaperSourceFetchError("该 API 未提供 URL")
        params = self._preset_values(record.spec, ref.category, overrides)
        try:
            async with session.get(ref.api.url, params=params or None) as resp:
                text = await resp.text()
        except Exception as exc:
            raise WallpaperSourceFetchError(f"请求图片链接失败: {exc}") from exc
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise WallpaperSourceFetchError("接口未返回有效的图片链接")
        items: list[WallpaperItem] = []
        for index, line in enumerate(lines):
            try:
                items.append(
                    await self._prepare_item_from_url(
                        ref,
                        record,
                        line,
                        f"remote-url-{index}",
                    ),
                )
            except WallpaperSourceFetchError as exc:
                logger.warning("下载图片失败: {error}", error=str(exc))
        return items

    async def _fetch_image_raw(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
        session: aiohttp.ClientSession,
        overrides: dict[str, Any] | None,
    ) -> list[WallpaperItem]:
        if not ref.api.url:
            raise WallpaperSourceFetchError("该 API 未提供 URL")
        params = self._preset_values(record.spec, ref.category, overrides)
        try:
            async with session.request(ref.api.method, ref.api.url, params=params or None) as resp:
                if resp.status != 200:
                    raise WallpaperSourceFetchError(f"HTTP {resp.status}")
                data = await resp.read()
                content_type = resp.headers.get("Content-Type")
        except WallpaperSourceFetchError:
            raise
        except Exception as exc:
            raise WallpaperSourceFetchError(f"请求原始图片失败: {exc}") from exc
        path = await self._write_cached_bytes(ref, record, data, content_type, seed="image-raw")
        preview = base64.b64encode(data).decode("ascii")
        item = WallpaperItem(
            id=_sha1(path.name + ref.category_id),
            title=None,
            description=None,
            copyright=None,
            attribution=None,
            footer_text=ref.footer_text,
            local_path=path,
            preview_base64=preview,
            mime_type=content_type,
            original_url=ref.api.url,
            source_id=ref.source_id,
            api_name=ref.api_name,
            category_label=ref.label,
        )
        return [item]

    async def _fetch_image_base64(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
        session: aiohttp.ClientSession,
        overrides: dict[str, Any] | None,
    ) -> list[WallpaperItem]:
        if not ref.api.url:
            raise WallpaperSourceFetchError("该 API 未提供 URL")
        params = self._preset_values(record.spec, ref.category, overrides)
        method = ref.api.method.upper()
        request_kwargs: dict[str, Any] = {}
        if method == "GET":
            request_kwargs["params"] = params or None
        else:
            request_kwargs["json"] = params or {}
        try:
            async with session.request(method, ref.api.url, **request_kwargs) as resp:
                text = await resp.text()
                status = resp.status
                content_type = resp.headers.get("Content-Type")
        except Exception as exc:
            raise WallpaperSourceFetchError(f"请求 Base64 图片失败: {exc}") from exc
        if status != 200:
            raise WallpaperSourceFetchError(f"HTTP {status}")
        payload = text.strip()
        if not payload:
            raise WallpaperSourceFetchError("接口未返回有效的图片数据")
        data_bytes, mime_type = _decode_base64_image(payload)
        header_mime: str | None = None
        if content_type:
            header_mime = content_type.split(";", 1)[0].strip()
        effective_mime = mime_type or header_mime
        path = await self._write_cached_bytes(
            ref,
            record,
            data_bytes,
            effective_mime,
            seed=f"image-base64:{ref.api.url}:{ref.category_id}",
        )
        preview = base64.b64encode(data_bytes).decode("ascii")
        item = WallpaperItem(
            id=_sha1(path.name + ref.category_id),
            title=None,
            description=None,
            copyright=None,
            attribution=None,
            footer_text=ref.footer_text,
            local_path=path,
            preview_base64=preview,
            mime_type=effective_mime,
            original_url=ref.api.url,
            source_id=ref.source_id,
            api_name=ref.api_name,
            category_label=ref.label,
        )
        return [item]

    async def _fetch_structured(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
        session: aiohttp.ClientSession,
        overrides: dict[str, Any] | None,
    ) -> list[WallpaperItem]:
        if not ref.api.url:
            raise WallpaperSourceFetchError("该 API 未提供 URL")
        params = self._preset_values(record.spec, ref.category, overrides)
        method = ref.api.method
        request_kwargs: dict[str, Any] = {}
        if method.upper() == "GET":
            request_kwargs["params"] = params or None
        else:
            request_kwargs["json"] = params or {}
        try:
            async with session.request(method, ref.api.url, **request_kwargs) as resp:
                text = await resp.text()
                content_type = resp.headers.get("Content-Type", "")
                status = resp.status
        except Exception as exc:
            raise WallpaperSourceFetchError(f"请求失败: {exc}") from exc
        if status != 200:
            raise WallpaperSourceFetchError(f"HTTP {status}")
        data = self._parse_structured_payload(ref.api.format, text, content_type)
        items_data = self._extract_items_data(ref, data)
        items: list[WallpaperItem] = []
        for index, item_data in enumerate(items_data):
            try:
                items.append(
                    await self._build_item_from_structured(
                        ref,
                        record,
                        item_data,
                        index,
                    ),
                )
            except WallpaperSourceFetchError as exc:
                logger.warning("解析壁纸结果失败: {error}", error=str(exc))
        return items

    def _parse_structured_payload(self, fmt: str, text: str, content_type: str) -> Any:
        lowered = content_type.lower()
        if fmt == "toml" or ("toml" in lowered and fmt != "json"):
            try:
                return rtoml.loads(text)
            except Exception as exc:
                raise WallpaperSourceFetchError(f"解析 TOML 失败: {exc}") from exc
        if fmt == "json" or "json" in lowered:
            try:
                return json.loads(text)
            except Exception as exc:
                raise WallpaperSourceFetchError(f"解析 JSON 失败: {exc}") from exc
        # fallback: attempt json then toml
        try:
            return json.loads(text)
        except Exception:
            try:
                return rtoml.loads(text)
            except Exception as exc:
                raise WallpaperSourceFetchError(f"解析响应失败: {exc}") from exc

    def _extract_items_data(self, ref: WallpaperCategoryRef, payload: Any) -> list[Any]:
        api = ref.api
        multi = api.multi
        if multi and multi.enabled:
            path = multi.items_path or ""
            items = _resolve_path(payload, path, fmt=api.format)
            if isinstance(items, list):
                return items
            raise WallpaperSourceFetchError("multi.items_path 未返回数组")
        return [payload]

    async def _build_item_from_structured(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
        payload: Any,
        index: int,
    ) -> WallpaperItem:
        mapping = ref.api.field_mapping
        if not mapping:
            raise WallpaperSourceFetchError("该 API 缺少 field_mapping")
        image_value = _resolve_path(payload, mapping.image, fmt=ref.api.format)
        title = mapping.title
        description = mapping.description
        copyright_text = mapping.copyright
        if title:
            try:
                title_value = _resolve_path(payload, title, fmt=ref.api.format)
            except WallpaperSourceFetchError:
                title_value = None
        else:
            title_value = None
        if description:
            try:
                description_value = _resolve_path(payload, description, fmt=ref.api.format)
            except WallpaperSourceFetchError:
                description_value = None
        else:
            description_value = None
        if copyright_text:
            try:
                copyright_value = _resolve_path(payload, copyright_text, fmt=ref.api.format)
            except WallpaperSourceFetchError:
                copyright_value = None
        else:
            copyright_value = None
        if isinstance(image_value, list):
            image_value = image_value[0] if image_value else None
        if not isinstance(image_value, (str, bytes)):
            raise WallpaperSourceFetchError("field_mapping.image 未返回字符串")
        if isinstance(image_value, bytes):
            data_bytes = image_value
            mime_type = None
            path = await self._write_cached_bytes(ref, record, data_bytes, mime_type, seed=f"payload-{index}")
            preview = base64.b64encode(data_bytes).decode("ascii")
            original = None
        else:
            trimmed = image_value.strip()
            if trimmed.startswith("http://") or trimmed.startswith("https://"):
                item = await self._prepare_item_from_url(
                    ref,
                    record,
                    trimmed,
                    f"payload-url-{index}",
                    title=str(title_value) if title_value not in (None, "") else None,
                    description=str(description_value) if description_value not in (None, "") else None,
                    copyright_text=str(copyright_value) if copyright_value not in (None, "") else None,
                )
                return item
            data_bytes, mime_type = _decode_base64_image(trimmed)
            path = await self._write_cached_bytes(ref, record, data_bytes, mime_type, seed=f"payload-b64-{index}")
            preview = base64.b64encode(data_bytes).decode("ascii")
            original = None
        item = WallpaperItem(
            id=_sha1(path.name + ref.category_id),
            title=str(title_value) if title_value not in (None, "") else None,
            description=str(description_value) if description_value not in (None, "") else None,
            copyright=str(copyright_value) if copyright_value not in (None, "") else None,
            attribution=None,
            footer_text=ref.footer_text,
            local_path=path,
            preview_base64=preview,
            mime_type=mime_type,
            original_url=original,
            source_id=ref.source_id,
            api_name=ref.api_name,
            category_label=ref.label,
            extra={},
        )
        return item

    async def _download_image_with_ltwapi(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
        url: str,
        *,
        seed: str,
    ) -> tuple[Path, bytes, str | None]:
        download_dir = self._cache_dir / "_downloads"
        _ensure_dir(download_dir)
        try:
            path_str = await asyncio.to_thread(
                ltwapi.download_file,
                url,
                download_dir,
            )
        except Exception as exc:
            raise WallpaperSourceFetchError(f"下载图片失败: {exc}") from exc
        if not path_str:
            raise WallpaperSourceFetchError("下载图片失败")
        temp_path = Path(path_str)
        try:
            data = await asyncio.to_thread(temp_path.read_bytes)
        except Exception as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise WallpaperSourceFetchError(f"读取图片失败: {exc}") from exc
        mime_type = mimetypes.guess_type(str(temp_path))[0]
        final_path = await self._write_cached_bytes(
            ref,
            record,
            data,
            mime_type,
            seed=seed,
        )
        if final_path != temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        final_mime = mime_type or mimetypes.guess_type(str(final_path))[0]
        return final_path, data, final_mime

    async def _prepare_item_from_url(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
        url: str,
        seed: str,
        *,
        title: str | None = None,
        description: str | None = None,
        copyright_text: str | None = None,
    ) -> WallpaperItem:
        path, data, mime_type = await self._download_image_with_ltwapi(
            ref,
            record,
            url,
            seed=f"{seed}:{url}",
        )
        preview = base64.b64encode(data).decode("ascii")
        resolved_title = str(title) if title not in (None, "") else None
        resolved_description = str(description) if description not in (None, "") else None
        resolved_copyright = str(copyright_text) if copyright_text not in (None, "") else None
        return WallpaperItem(
            id=_sha1(path.name + ref.category_id),
            title=resolved_title,
            description=resolved_description,
            copyright=resolved_copyright,
            attribution=None,
            footer_text=ref.footer_text,
            local_path=path,
            preview_base64=preview,
            mime_type=mime_type,
            original_url=url,
            source_id=ref.source_id,
            api_name=ref.api_name,
            category_label=ref.label,
            extra={},
        )

    async def _write_cached_bytes(
        self,
        ref: WallpaperCategoryRef,
        record: WallpaperSourceRecord,
        data: bytes,
        content_type: str | None,
        *,
        seed: str,
    ) -> Path:
        source_dir = self._cache_dir / _slugify(record.identifier)
        _ensure_dir(source_dir)
        digest = hashlib.sha1(seed.encode("utf-8") + data).hexdigest()
        ext = _guess_extension(None, content_type)
        path = source_dir / f"{digest}{ext}"
        if not path.exists():
            await asyncio.to_thread(path.write_bytes, data)
        return path


__all__ = [
    "WallpaperCategoryRef",
    "WallpaperItem",
    "WallpaperSourceError",
    "WallpaperSourceFetchError",
    "WallpaperSourceImportError",
    "WallpaperSourceManager",
    "WallpaperSourceRecord",
]
