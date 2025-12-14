"""LTWS v3 parser bridge for Little Tree Wallpaper Next.

This module adapts the official LTWS parser output to the legacy data
structures used inside the application so the rest of the codebase can
continue to operate with minimal changes while benefiting from the
protocol v3 features (.ltws packages, per-API logos, request metadata,
 etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from ltws import (
    LTWSParser,
    WallpaperSource,
    WallpaperAPI as LTWSWallpaperAPI,
    Category as LTWSCategory,
    Parameter as LTWSParameter,
    ParameterType as LTWSParameterType,
    InvalidSourceError,
    ParseError,
    ValidationError,
    WallpaperSourceError,
)
from ltws.exceptions import FileNotFoundError as LTWSFileNotFoundError
from ltws.utils import is_valid_url


FormatType = Literal[
    "json",
    "toml",
    "image_url",
    "image_raw",
    "image_base64",
    "static_list",
    "static_dict",
]

MethodType = Literal["GET", "POST"]


@dataclass(slots=True)
class FieldMapping:
    image: str | None = None
    title: str | None = None
    description: str | None = None
    copyright: str | None = None
    thumbnail: str | None = None
    width: str | None = None
    height: str | None = None
    author: str | None = None
    source: str | None = None
    tags: str | None = None
    date: str | None = None
    item_mapping: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MultiConfig:
    enabled: bool
    items_path: str | None = None


@dataclass(slots=True)
class StaticList:
    urls: list[str]


@dataclass(slots=True)
class StaticDictItem:
    url: str
    title: str | None = None
    description: str | None = None


@dataclass(slots=True)
class StaticDict:
    items: list[StaticDictItem]


@dataclass(slots=True)
class ParameterOption:
    key: str
    type: Literal["choice", "boolean", "text"]
    label: str | None = None
    description: str | None = None
    default: Any = None
    choices: list[str] | None = None
    placeholder: str | None = None
    hidden: bool = False
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None


@dataclass(slots=True)
class ParameterPreset:
    id: str
    options: list[ParameterOption] = field(default_factory=list)


@dataclass(slots=True)
class Category:
    id: str
    name: str
    category: str
    subcategory: str | None = None
    subsubcategory: str | None = None
    description: str | None = None
    icon: str | None = None
    param_preset_id: str | None = None


@dataclass(slots=True)
class API:
    name: str
    format: FormatType
    url: str | None = None
    description: str | None = None
    footer_text: str | None = None
    logo: str | None = None
    method: MethodType = "GET"
    multi: MultiConfig | None = None
    field_mapping: FieldMapping | None = None
    static_list: StaticList | None = None
    static_dict: StaticDict | None = None
    category_ids: tuple[str, ...] = field(default_factory=tuple)
    category_icons: dict[str, str] = field(default_factory=dict)
    param_preset_id: str | None = None
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: Any = None
    timeout_seconds: int | None = None
    interval_seconds: int | None = None
    max_concurrent: int | None = None
    skip_ssl_verify: bool | None = None
    user_agent: str | None = None
    response_type: Literal["single", "multi"] = "single"
    raw: LTWSWallpaperAPI | None = None


@dataclass(slots=True)
class SourceSpec:
    scheme: str
    identifier: str
    name: str
    version: str
    description: str | None = None
    details: str | None = None
    logo: str | None = None
    skip_ssl_verify: bool = False
    refresh_interval_seconds: int = 0
    footer_text: str | None = None

    apis: list[API] = field(default_factory=list)
    parameters: dict[str, ParameterPreset] = field(default_factory=dict)
    categories: list[Category] = field(default_factory=list)
    api_categories: dict[str, list[Category]] = field(default_factory=dict)

    config: dict[str, Any] = field(default_factory=dict)
    request_headers: dict[str, str] = field(default_factory=dict)
    request_timeout: int | None = None
    request_interval: int | None = None
    request_user_agent: str | None = None
    raw: WallpaperSource | None = None

    def effective_footer_for_api(self, api: API) -> str | None:
        return api.footer_text or self.footer_text


class SourceValidationError(ValueError):
    """Raised when a wallpaper source fails validation."""


def parse_source_file(path: str | Path) -> SourceSpec:
    """Parse an LTWS v3 source file or directory and return SourceSpec."""
    parser = LTWSParser(strict=True)
    resolved = Path(path).resolve()
    try:
        source = parser.parse(str(resolved))
    except (InvalidSourceError, ValidationError, ParseError, WallpaperSourceError, LTWSFileNotFoundError) as exc:
        raise SourceValidationError(str(exc)) from exc
    return _convert_source(source)


def _convert_source(source: WallpaperSource) -> SourceSpec:
    metadata = source.metadata or {}

    scheme = _string(metadata.get("scheme")) or "littletree_wallpaper_source_v3"
    identifier = _string(metadata.get("identifier"))
    if not identifier:
        raise SourceValidationError("source.toml 缺少 identifier")

    name = _string(metadata.get("name")) or identifier
    version = _string(metadata.get("version")) or "0.0.0"
    description = _string(metadata.get("description"))
    details = _string(metadata.get("details"))
    logo = _string(metadata.get("logo"))
    footer_text = _string(metadata.get("footer_text"))

    config: dict[str, Any] = source.config if isinstance(source.config, dict) else {}
    request_cfg = config.get("request") if isinstance(config.get("request"), dict) else {}

    skip_ssl_verify = bool(request_cfg.get("skip_ssl_verify", False))
    request_timeout = _int(request_cfg.get("timeout_seconds"))
    request_interval = _int(request_cfg.get("global_interval_seconds"))
    request_headers = _sanitize_headers(request_cfg.get("headers"))
    request_user_agent = _string(request_cfg.get("user_agent"))

    categories = [_convert_category(cat) for cat in source.categories]
    category_index = {cat.id: cat for cat in categories}

    parameters: dict[str, ParameterPreset] = {}
    api_categories: dict[str, list[Category]] = {}
    apis: list[API] = []

    for api in source.apis:
        converted_api, bindings = _convert_api(
            api,
            category_index=category_index,
            parameter_registry=parameters,
        )
        apis.append(converted_api)
        api_categories[converted_api.name] = bindings

    if not apis:
        logger.warning("未定义任何 API，该壁纸源不会显示内容")

    if not any(bindings for bindings in api_categories.values()):
        logger.warning("没有任何 API 绑定到分类，源将不会在 UI 中展示")

    spec = SourceSpec(
        scheme=scheme,
        identifier=identifier,
        name=name,
        version=version,
        description=description,
        details=details,
        logo=logo,
        skip_ssl_verify=skip_ssl_verify,
        refresh_interval_seconds=request_interval or 0,
        footer_text=footer_text,
        apis=apis,
        parameters=parameters,
        categories=categories,
        api_categories=api_categories,
        config=config,
        request_headers=request_headers,
        request_timeout=request_timeout,
        request_interval=request_interval,
        request_user_agent=request_user_agent,
        raw=source,
    )
    return spec


def _convert_category(category: LTWSCategory) -> Category:
    return Category(
        id=category.id,
        name=category.name,
        category=category.category,
        subcategory=category.subcategory,
        subsubcategory=category.subsubcategory,
        description=_string(category.description),
        icon=_string(category.icon),
        param_preset_id=None,
    )


def _convert_parameter(option: LTWSParameter) -> ParameterOption:
    param_type = option.type.value
    default_value: Any = option.default
    if option.default in (None, ""):
        default_value = None
    elif option.type is LTWSParameterType.BOOLEAN:
        default_value = _to_bool(option.default)
    elif option.type is LTWSParameterType.CHOICE:
        default_value = str(option.default)
    else:
        default_value = str(option.default)

    choices = list(option.choices) if option.choices else None

    return ParameterOption(
        key=option.key,
        type=param_type,  # type: ignore[arg-type]
        label=_string(option.label),
        description=_string(option.description),
        default=default_value,
        choices=choices,
        placeholder=_string(option.placeholder),
        hidden=bool(option.hidden),
        min_length=_int(option.min_length),
        max_length=_int(option.max_length),
        pattern=_string(option.pattern),
    )


def _convert_api(
    api: LTWSWallpaperAPI,
    *,
    category_index: dict[str, Category],
    parameter_registry: dict[str, ParameterPreset],
) -> tuple[API, list[Category]]:
    response = api.response or {}
    fmt = _string(response.get("format")) or "json"
    fmt = fmt.lower()
    response_type = _string(response.get("type")) or "single"
    response_type = response_type.lower()

    request = api.request
    method = (request.method or "GET").upper()
    url = _string(request.url)

    multi: MultiConfig | None = None
    field_mapping: FieldMapping | None = None

    mapping = api.mapping
    if mapping:
        mapping_dict = {k: v for k, v in (mapping.item_mapping or {}).items() if isinstance(v, str)}
        field_mapping = FieldMapping(
            image=_string(mapping.image),
            title=_string(mapping.title),
            description=_string(mapping.description),
            copyright=_string(mapping.source) or _string(mapping.author),
            thumbnail=_string(mapping.thumbnail),
            width=_string(mapping.width),
            height=_string(mapping.height),
            author=_string(mapping.author),
            source=_string(mapping.source),
            tags=_string(mapping.tags),
            date=_string(mapping.date),
            item_mapping=mapping_dict,
        )
        if response_type == "multi" and mapping.items:
            multi = MultiConfig(enabled=True, items_path=_string(mapping.items))
            if mapping_dict:
                field_mapping.image = _string(mapping_dict.get("image")) or field_mapping.image
                field_mapping.title = _string(mapping_dict.get("title")) or field_mapping.title
                field_mapping.description = _string(mapping_dict.get("description")) or field_mapping.description
                if mapping_dict.get("source") or mapping_dict.get("copyright"):
                    field_mapping.copyright = _string(mapping_dict.get("copyright")) or _string(mapping_dict.get("source")) or field_mapping.copyright
                field_mapping.thumbnail = _string(mapping_dict.get("thumbnail")) or field_mapping.thumbnail
                field_mapping.width = _string(mapping_dict.get("width")) or field_mapping.width
                field_mapping.height = _string(mapping_dict.get("height")) or field_mapping.height
                field_mapping.author = _string(mapping_dict.get("author")) or field_mapping.author
                field_mapping.source = _string(mapping_dict.get("source")) or field_mapping.source
                field_mapping.tags = _string(mapping_dict.get("tags")) or field_mapping.tags
                field_mapping.date = _string(mapping_dict.get("date")) or field_mapping.date
        elif response_type == "multi":
            multi = MultiConfig(enabled=True, items_path=None)
    elif fmt in {"json", "toml"}:
        multi = MultiConfig(enabled=response_type == "multi", items_path=None)

    static_list = _convert_static_list(api) if fmt == "static_list" else None
    static_dict = _convert_static_dict(api) if fmt == "static_dict" else None

    preset_id: str | None = None
    if api.parameters:
        preset_id = api.name
        if preset_id not in parameter_registry:
            options = [_convert_parameter(option) for option in api.parameters]
            parameter_registry[preset_id] = ParameterPreset(id=preset_id, options=options)

    request_headers = _sanitize_headers(request.headers)
    if request.user_agent:
        request_headers.setdefault("User-Agent", request.user_agent)

    category_icons: dict[str, str] = {}
    raw_category_icons = getattr(api, "category_icons", None)
    if isinstance(raw_category_icons, dict):
        for key, value in raw_category_icons.items():
            key_str = _string(key)
            value_str = _string(value)
            if key_str and value_str:
                category_icons[key_str] = value_str

    bindings: list[Category] = []
    for cat_id in api.categories:
        base = category_index.get(cat_id)
        if base is None:
            logger.warning("API %s 引用了未定义的分类 %s", api.name, cat_id)
            continue
        clone = replace(base, param_preset_id=preset_id)
        icon_override = category_icons.get(cat_id)
        if icon_override:
            clone = replace(clone, icon=icon_override)
        bindings.append(clone)

    api_obj = API(
        name=api.name,
        format=fmt,  # type: ignore[arg-type]
        url=url if fmt not in {"static_list", "static_dict"} else None,
        description=_string(api.description),
        footer_text=_string(response.get("footer_text")),
        logo=_string(api.logo),
        method=method,  # type: ignore[arg-type]
        multi=multi,
        field_mapping=field_mapping,
        static_list=static_list,
        static_dict=static_dict,
        category_ids=tuple(api.categories),
        category_icons=category_icons,
        param_preset_id=preset_id,
        request_headers=request_headers,
        request_body=request.body,
        timeout_seconds=_int(request.timeout_seconds),
        interval_seconds=_int(request.interval_seconds),
        max_concurrent=_int(request.max_concurrent),
        skip_ssl_verify=request.skip_ssl_verify,
        user_agent=_string(request.user_agent),
        response_type=response_type if response_type in {"single", "multi"} else "single",
        raw=api,
    )

    return api_obj, bindings


def _convert_static_list(api: LTWSWallpaperAPI) -> StaticList | None:
    data = getattr(api, "static_list", None)
    if not isinstance(data, dict):
        return None
    urls_raw = data.get("urls")
    if not isinstance(urls_raw, list):
        return None
    urls: list[str] = []
    for entry in urls_raw:
        value = _string(entry)
        if not value:
            continue
        if not is_valid_url(value):
            logger.warning("static_list.urls 中存在无效链接: %s", value)
            continue
        urls.append(value)
    return StaticList(urls=urls)


def _convert_static_dict(api: LTWSWallpaperAPI) -> StaticDict | None:
    data = getattr(api, "static_dict", None)
    if not isinstance(data, dict):
        return None
    items_raw = data.get("items")
    if not isinstance(items_raw, list):
        return None
    items: list[StaticDictItem] = []
    for entry in items_raw:
        if not isinstance(entry, dict):
            continue
        url = _string(entry.get("url"))
        if not url or not is_valid_url(url):
            logger.warning("static_dict.items 中存在无效链接: %s", entry.get("url"))
            continue
        items.append(
            StaticDictItem(
                url=url,
                title=_string(entry.get("title")),
                description=_string(entry.get("description")),
            ),
        )
    return StaticDict(items=items)


def _sanitize_headers(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    headers: dict[str, str] = {}
    for key, value in raw.items():
        key_str = _string(key)
        value_str = _string(value)
        if not key_str or value_str is None:
            continue
        headers[key_str] = value_str
    return headers


def _string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, bool):  # bool is instance of int
            return int(value)
        return int(value)
    except Exception:
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


__all__ = [
    "API",
    "Category",
    "FieldMapping",
    "FormatType",
    "MethodType",
    "MultiConfig",
    "ParameterOption",
    "ParameterPreset",
    "SourceSpec",
    "SourceValidationError",
    "StaticDict",
    "StaticDictItem",
    "StaticList",
    "parse_source_file",
]
