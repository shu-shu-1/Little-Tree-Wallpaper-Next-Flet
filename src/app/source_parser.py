"""Wallpaper Source TOML parser for Little Tree Wallpaper Next (Protocol v2.0).

- Parses and validates a source TOML using rtoml.
- Returns normalized, typed structures for main program consumption.
- Supports category association by explicit `[[categories]].api` (recommended).

Notes:
- The protocol example in docs omits the `api` field. Because TOML parsers don't
  preserve inter-table ordering needed to infer associations reliably, this parser
  requires `[[categories]]` to include an `api` field referencing `[[apis]].name`.
  If omitted, the category entry is ignored with a warning.

Usage:
    from app.wallpaper_source_parser import parse_source_file, SourceSpec
    spec = parse_source_file(path)
    for api in spec.apis: ...

"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import rtoml
from loguru import logger

# -----------------------------
# Data models
# -----------------------------

FormatType = Literal[
    "json",
    "toml",
    "image_url",
    "image_base64",
    "image_raw",
    "static_list",
    "static_dict",
]

MethodType = Literal["GET", "POST"]


@dataclass(slots=True)
class FieldMapping:
    image: str
    title: str | None = None
    description: str | None = None
    copyright: str | None = None


@dataclass(slots=True)
class MultiConfig:
    enabled: bool
    items_path: str


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
    param_preset_id: str | None = None


@dataclass(slots=True)
class API:
    name: str
    format: FormatType
    url: str | None = None
    description: str | None = None
    footer_text: str | None = None
    method: MethodType = "GET"
    multi: MultiConfig | None = None
    field_mapping: FieldMapping | None = None
    static_list: StaticList | None = None
    static_dict: StaticDict | None = None
    category_ids: tuple[str, ...] = field(default_factory=tuple)
    category_param_mapping: dict[str, str] = field(default_factory=dict)
    param_preset_id: str | None = None


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

    # Convenience: API name -> categories
    api_categories: dict[str, list[Category]] = field(default_factory=dict)

    def effective_footer_for_api(self, api: API) -> str | None:
        return api.footer_text or self.footer_text


# -----------------------------
# Validation helpers
# -----------------------------

_IDENTIFIER_RE = re.compile(r"^[a-z0-9_]{3,32}$")
# SemVer 2.0.0 without leading zeros for major/minor/patch
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$",
)


def _is_https(url: str) -> bool:
    return url.lower().startswith("https://")


def _is_data_or_base64_image(url: str) -> bool:
    u = url.lower()
    return u.startswith("data:image/") or u.startswith("image;base64,")


class SourceValidationError(ValueError):
    pass


# -----------------------------
# Public API
# -----------------------------

def parse_source_string(toml_text: str, *, path_hint: str | None = None) -> SourceSpec:
    """Parse and validate a Wallpaper Source TOML string into SourceSpec.

    Raises SourceValidationError on invalid input.
    """
    try:
        data = rtoml.loads(toml_text)
    except Exception as exc:
        raise SourceValidationError(f"TOML 解析失败: {exc}") from exc

    return _build_spec(data, path_hint=path_hint)


def parse_source_file(path: str | Path) -> SourceSpec:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return parse_source_string(text, path_hint=str(p))


# -----------------------------
# Internal builders
# -----------------------------

def _build_spec(data: dict[str, Any], *, path_hint: str | None) -> SourceSpec:
    # Global required fields
    scheme = _req_str(data, "scheme")
    if scheme != "littletree_wallpaper_source_v2":
        raise SourceValidationError(
            f"scheme 必须为 'littletree_wallpaper_source_v2'，实际为: {scheme}",
        )

    identifier = _req_str(data, "identifier")
    if not _IDENTIFIER_RE.match(identifier):
        raise SourceValidationError("identifier 需为 3-32 位的 [a-z0-9_] 组成")

    name = _req_str(data, "name")

    version = _req_str(data, "version")
    if not _SEMVER_RE.match(version):
        raise SourceValidationError("version 必须符合 SemVer 2.0.0 规范")

    description = _opt_str(data, "description")
    if description and len(description) > 100:
        raise SourceValidationError("description 长度不能超过 100 字符")

    details = _opt_str(data, "details")
    logo = _opt_str(data, "logo")
    if logo and (not _is_https(logo) and not _is_data_or_base64_image(logo)):
        raise SourceValidationError("logo 必须为 HTTPS URL 或 data:image/... base64 字符串")

    skip_ssl_verify = bool(data.get("skip_ssl_verify", False))

    refresh_raw = data.get("refresh_interval_seconds", 0)
    try:
        refresh_interval_seconds = int(refresh_raw)
    except Exception as exc:  # pragma: no cover - defensive
        raise SourceValidationError("refresh_interval_seconds 必须为整数") from exc
    if refresh_interval_seconds < 0:
        raise SourceValidationError("refresh_interval_seconds 必须大于等于 0")

    footer_text = _opt_str(data, "footer_text")

    # Parameters (presets)
    parameter_index: dict[str, ParameterPreset] = {}
    for preset in data.get("parameters", []) or []:
        if not isinstance(preset, dict):
            raise SourceValidationError("parameters 列表项必须为对象")
        pid = _req_str(preset, "id", ctx="parameters")
        if pid in parameter_index:
            raise SourceValidationError(f"parameters.id 重复: {pid}")
        options_raw = preset.get("options", []) or []
        if not isinstance(options_raw, list):
            raise SourceValidationError("parameters.options 必须为数组")
        options: list[ParameterOption] = []
        for opt in options_raw:
            if not isinstance(opt, dict):
                raise SourceValidationError("parameters.options 元素必须为对象")
            options.append(_build_parameter_option(opt))
        parameter_index[pid] = ParameterPreset(id=pid, options=options)

    # Categories definitions
    categories_raw = data.get("categories", []) or []
    if not isinstance(categories_raw, list):
        raise SourceValidationError("categories 必须为数组")
    categories: list[Category] = []
    category_index: dict[str, Category] = {}
    for entry in categories_raw:
        if not isinstance(entry, dict):
            raise SourceValidationError("categories 列表项必须为对象")
        cat_id = _req_str(entry, "id", ctx="categories")
        if not _IDENTIFIER_RE.match(cat_id):
            raise SourceValidationError("categories.id 需为 3-32 位的 [a-z0-9_] 组成")
        if cat_id in category_index:
            raise SourceValidationError(f"categories.id 重复: {cat_id}")
        display_name = _req_str(entry, "name", ctx="categories")
        primary = _req_str(entry, "category", ctx="categories")
        sub = _opt_str(entry, "subcategory")
        subsub = _opt_str(entry, "subsubcategory")
        category_obj = Category(
            id=cat_id,
            name=display_name,
            category=primary,
            subcategory=sub,
            subsubcategory=subsub,
            param_preset_id=None,
        )
        categories.append(category_obj)
        category_index[cat_id] = category_obj

    # APIs and bindings
    apis_raw = data.get("apis", []) or []
    if not isinstance(apis_raw, list):
        raise SourceValidationError("apis 必须为数组")
    apis: list[API] = []
    api_categories: dict[str, list[Category]] = {}
    for api_entry in apis_raw:
        if not isinstance(api_entry, dict):
            raise SourceValidationError("apis 列表项必须为对象")
        api, bindings = _build_api(
            api_entry,
            global_skip_ssl=skip_ssl_verify,
            parameters=parameter_index,
            categories=category_index,
        )
        if api.name in api_categories:
            raise SourceValidationError(f"重复的 API name: {api.name}")
        apis.append(api)
        api_categories[api.name] = bindings

    if not apis:
        logger.warning("未定义任何 API，该壁纸源不会显示内容")

    # Ensure at least one API binds to categories
    if not any(bindings for bindings in api_categories.values()):
        logger.warning("没有任何 API 绑定到分类，源将不会在 UI 中展示")

    return SourceSpec(
        scheme=scheme,
        identifier=identifier,
        name=name,
        version=version,
        description=description,
        details=details,
        logo=logo,
        skip_ssl_verify=skip_ssl_verify,
        refresh_interval_seconds=refresh_interval_seconds,
        footer_text=footer_text,
        apis=apis,
        parameters=parameter_index,
        categories=categories,
        api_categories=api_categories,
    )


def _build_parameter_option(opt: dict[str, Any]) -> ParameterOption:
    key = _req_str(opt, "key", ctx="parameters.options")
    typ = _req_str(opt, "type", ctx="parameters.options")
    if typ not in ("choice", "boolean", "text"):
        raise SourceValidationError(f"不支持的参数类型: {typ}")
    hidden = bool(opt.get("hidden", False))
    label = _opt_str(opt, "label")
    if not hidden and not label:
        raise SourceValidationError("可见参数必须提供 label")
    desc = _opt_str(opt, "description")
    default = opt.get("default")
    choices = opt.get("choices")
    placeholder = _opt_str(opt, "placeholder")

    if typ == "choice":
        if not isinstance(choices, list) or not all(isinstance(x, str) for x in choices):
            raise SourceValidationError("choice 类型必须提供字符串数组 choices")
        if default is not None and default not in choices:
            raise SourceValidationError("choice 类型的 default 必须在 choices 中")
    elif typ == "boolean":
        if default is not None and not isinstance(default, bool):
            raise SourceValidationError("boolean 类型的 default 必须为布尔值")
    elif typ == "text":
        if default is not None and not isinstance(default, str):
            raise SourceValidationError("text 类型的 default 必须为字符串")

    return ParameterOption(
        key=key,
        type=typ,  # type: ignore[arg-type]
        label=label,
        description=desc,
        default=default,
        choices=choices,
        placeholder=placeholder,
        hidden=hidden,
    )


def _build_api(
    api_data: dict[str, Any],
    *,
    global_skip_ssl: bool,
    parameters: dict[str, ParameterPreset],
    categories: dict[str, Category],
) -> tuple[API, list[Category]]:
    name = _req_str(api_data, "name", ctx="apis")
    fmt = _req_str(api_data, "format", ctx="apis").lower()
    valid_formats = {
        "json",
        "toml",
        "image_url",
        "image_base64",
        "image_raw",
        "static_list",
        "static_dict",
    }
    if fmt not in valid_formats:
        raise SourceValidationError(f"不支持的 format: {fmt}")

    method = (_opt_str(api_data, "method") or "GET").upper()
    if method not in ("GET", "POST"):
        raise SourceValidationError("method 只能为 GET 或 POST")

    description = _opt_str(api_data, "description")
    footer_text = _opt_str(api_data, "footer_text")

    url = _opt_str(api_data, "url")
    static_list: StaticList | None = None
    static_dict: StaticDict | None = None
    multi: MultiConfig | None = None
    field_mapping: FieldMapping | None = None

    supports_parameters = fmt in ("json", "toml")

    if fmt == "static_list":
        if url:
            raise SourceValidationError("static_list 不允许提供 url 字段")
        if "multi" in api_data:
            raise SourceValidationError("static_list 不支持 multi")
        if "field_mapping" in api_data:
            raise SourceValidationError("static_list 不支持 field_mapping")
        static_section = api_data.get("static_list") or {}
        if not isinstance(static_section, dict):
            raise SourceValidationError("apis.static_list 必须为对象")
        urls_raw = static_section.get("urls")
        if not isinstance(urls_raw, list) or not urls_raw:
            raise SourceValidationError("static_list.urls 必须为非空数组")
        urls: list[str] = []
        for entry in urls_raw:
            if not isinstance(entry, str) or not entry.strip():
                raise SourceValidationError("static_list.urls 必须为字符串")
            value = entry.strip()
            if not _is_https(value):
                raise SourceValidationError("static_list.urls 必须为 HTTPS URL")
            urls.append(value)
        static_list = StaticList(urls=urls)
        url = None
    elif fmt == "static_dict":
        if url:
            raise SourceValidationError("static_dict 不允许提供 url 字段")
        if "multi" in api_data:
            raise SourceValidationError("static_dict 不支持 multi")
        if "field_mapping" in api_data:
            raise SourceValidationError("static_dict 不支持 field_mapping")
        static_section = api_data.get("static_dict") or {}
        if not isinstance(static_section, dict):
            raise SourceValidationError("apis.static_dict 必须为对象")
        items_raw = static_section.get("items")
        if not isinstance(items_raw, list) or not items_raw:
            raise SourceValidationError("static_dict.items 必须为非空数组")
        items: list[StaticDictItem] = []
        for item in items_raw:
            if not isinstance(item, dict):
                raise SourceValidationError("static_dict.items 元素必须为对象")
            item_url = _req_str(item, "url", ctx="apis.static_dict.items")
            if not _is_https(item_url):
                raise SourceValidationError("static_dict.items.url 必须为 HTTPS URL")
            items.append(
                StaticDictItem(
                    url=item_url,
                    title=_opt_str(item, "title"),
                    description=_opt_str(item, "description"),
                ),
            )
        static_dict = StaticDict(items=items)
        url = None
    else:
        if not url:
            raise SourceValidationError("该 API 缺少 url")
        scheme = url.lower()
        if scheme.startswith("http://"):
            if not global_skip_ssl:
                raise SourceValidationError("HTTP url 仅在 skip_ssl_verify=true 时允许")
        elif not _is_https(url):
            raise SourceValidationError("url 必须为 HTTPS")

        if fmt in ("json", "toml"):
            if "multi" in api_data:
                multi_cfg = api_data.get("multi") or {}
                if not isinstance(multi_cfg, dict):
                    raise SourceValidationError("apis.multi 必须为对象")
                enabled = bool(multi_cfg.get("enabled", False))
                items_path = _opt_str(multi_cfg, "items_path")
                if enabled and not items_path:
                    raise SourceValidationError("multi.enabled=true 时必须提供 items_path")
                if enabled:
                    multi = MultiConfig(enabled=True, items_path=items_path or "")
            if "field_mapping" not in api_data:
                raise SourceValidationError("json/toml 格式必须提供 field_mapping")
            fm_data = api_data.get("field_mapping") or {}
            if not isinstance(fm_data, dict):
                raise SourceValidationError("apis.field_mapping 必须为对象")
            image_path = _req_str(fm_data, "image", ctx="apis.field_mapping")
            field_mapping = FieldMapping(
                image=image_path,
                title=_opt_str(fm_data, "title"),
                description=_opt_str(fm_data, "description"),
                copyright=_opt_str(fm_data, "copyright"),
            )
        else:
            if "multi" in api_data and (api_data.get("multi") or {}).get("enabled"):
                raise SourceValidationError(f"{fmt} 不支持 multi")
            if "field_mapping" in api_data:
                raise SourceValidationError(f"{fmt} 不支持 field_mapping")

        if fmt == "image_base64" and "field_mapping" in api_data:
            raise SourceValidationError("image_base64 不支持 field_mapping")

    # Category bindings
    category_ids_field = api_data.get("category_ids")
    category_param_mapping_raw = api_data.get("category_param_mapping")
    if category_ids_field is not None and category_param_mapping_raw is not None:
        raise SourceValidationError("category_ids 与 category_param_mapping 不能同时存在")

    param_preset_id = _opt_str(api_data, "param_preset_id")
    if param_preset_id:
        if not supports_parameters:
            raise SourceValidationError(f"{fmt} 格式不支持 param_preset_id")
        if param_preset_id not in parameters:
            raise SourceValidationError(f"param_preset_id 未定义: {param_preset_id}")

    bindings: list[Category] = []
    category_ids: tuple[str, ...] = ()
    category_param_mapping: dict[str, str] = {}

    if category_param_mapping_raw is not None:
        if not supports_parameters:
            raise SourceValidationError("category_param_mapping 仅支持 json/toml 格式")
        if not isinstance(category_param_mapping_raw, dict) or not category_param_mapping_raw:
            raise SourceValidationError("category_param_mapping 必须为非空对象")
        mapping: dict[str, str] = {}
        ordered_ids: list[str] = []
        for cat_id_raw, preset_raw in category_param_mapping_raw.items():
            if not isinstance(cat_id_raw, str) or not cat_id_raw:
                raise SourceValidationError("category_param_mapping 的键必须为字符串")
            if cat_id_raw not in categories:
                raise SourceValidationError(f"category_param_mapping 引用了未定义的分类: {cat_id_raw}")
            if not isinstance(preset_raw, str) or not preset_raw:
                raise SourceValidationError("category_param_mapping 的值必须为字符串")
            if preset_raw not in parameters:
                raise SourceValidationError(f"category_param_mapping 引用了未定义的参数: {preset_raw}")
            ordered_ids.append(cat_id_raw)
            mapping[cat_id_raw] = preset_raw
            bindings.append(replace(categories[cat_id_raw], param_preset_id=preset_raw))
        category_param_mapping = mapping
        category_ids = tuple(ordered_ids)
        param_preset_id = None
    else:
        if category_ids_field is None:
            raise SourceValidationError("API 必须至少绑定一个分类")
        if isinstance(category_ids_field, str):
            ids_list = [category_ids_field]
        elif isinstance(category_ids_field, list):
            ids_list = []
            for item in category_ids_field:
                if not isinstance(item, str) or not item:
                    raise SourceValidationError("category_ids 数组元素必须为字符串")
                ids_list.append(item)
        else:
            raise SourceValidationError("category_ids 必须为字符串或字符串数组")
        if not ids_list:
            raise SourceValidationError("category_ids 不能为空")
        validated_ids: list[str] = []
        for cat_id in ids_list:
            if cat_id not in categories:
                raise SourceValidationError(f"category_ids 引用了未定义的分类: {cat_id}")
            validated_ids.append(cat_id)
            bindings.append(replace(categories[cat_id], param_preset_id=param_preset_id))
        category_ids = tuple(validated_ids)

    if not bindings:
        raise SourceValidationError("API 缺少有效的分类绑定")

    if not supports_parameters and (param_preset_id or category_param_mapping):
        raise SourceValidationError(f"{fmt} 格式不支持参数预设")

    api_obj = API(
        name=name,
        format=fmt,  # type: ignore[arg-type]
        url=url,
        description=description,
        footer_text=footer_text,
        method=method,  # type: ignore[arg-type]
        multi=multi,
        field_mapping=field_mapping,
        static_list=static_list,
        static_dict=static_dict,
        category_ids=category_ids,
        category_param_mapping=category_param_mapping,
        param_preset_id=param_preset_id,
    )

    return api_obj, bindings


# -----------------------------
# Small helpers
# -----------------------------

def _req_str(d: dict[str, Any], key: str, *, ctx: str | None = None) -> str:
    val = d.get(key)
    if not isinstance(val, str) or not val:
        where = f" in {ctx}" if ctx else ""
        raise SourceValidationError(f"缺少必需字符串字段: {key}{where}")
    return val


def _opt_str(d: dict[str, Any], key: str) -> str | None:
    val = d.get(key)
    return val if isinstance(val, str) and val else None


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
    "parse_source_string",
]
