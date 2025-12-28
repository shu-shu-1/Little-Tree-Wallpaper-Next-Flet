"""Application theme management utilities."""

from __future__ import annotations

import copy
import json
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flet as ft
from loguru import logger

from .paths import CONFIG_DIR
from .settings import SettingsStore

DEFAULT_THEME_DATA: dict[str, Any] = {
    "schema_version": 1,
    "name": "Default",
    "description": "Little Tree Wallpaper Next 的默认配色方案，自动适配浅色和深色模式。",
    "details": "默认主题提供 Material 3 风格的基础配色与布局，适配系统外观并作为其他主题的参考实现。",
    "author": "Little Tree Studio",
    "website": "",
    "logo": "",
    "palette": {
        "mode": "seed",
        "seed_color": "#4f46e5",
        "preferred_mode": "system",
        "use_material3": True,
    },
    "background": {
        "image": "",
        "opacity": 0.0,
        "fit": "cover",
        "alignment": "center",
        "repeat": "no_repeat",
    },
    "components": {},
}

MONO_THEME_DATA: dict[str, Any] = {
    "schema_version": 1,
    "name": "Black & White",
    "description": "高对比度黑白主题，使用种子色自适应深浅模式。",
    "details": "仅使用黑白基调，保留 Material 3 适配。",
    "author": "Little Tree Studio",
    "website": "",
    "logo": "",
    "palette": {
        "mode": "custom",
        "preferred_mode": "system",
        "use_material3": True,
        "color_scheme": {
            "primary": "#1a1a1a",
            "on_primary": "#f8f8f8",
            "primary_container": "#e4e4e4",
            "on_primary_container": "#1a1a1a",
            "secondary": "#2a2a2a",
            "on_secondary": "#f6f6f6",
            "secondary_container": "#e8e8e8",
            "on_secondary_container": "#1c1c1c",
            "tertiary": "#3a3a3a",
            "on_tertiary": "#f4f4f4",
            "tertiary_container": "#ededed",
            "on_tertiary_container": "#202020",
            "error": "#5a5a5a",
            "on_error": "#f5f5f5",
            "error_container": "#d9d9d9",
            "on_error_container": "#1f1f1f",
            "background": "#f3f3f3",
            "on_background": "#1a1a1a",
            "surface": "#f5f5f5",
            "on_surface": "#1c1c1c",
            "surface_variant": "#e5e5e5",
            "on_surface_variant": "#2f2f2f",
            "outline": "#7a7a7a",
            "outline_variant": "#c7c7c7",
            "shadow": "#000000",
            "scrim": "#000000",
            "surface_tint": "#1a1a1a",
            "inverse_surface": "#2b2b2b",
            "inverse_on_surface": "#f2f2f2",
            "inverse_primary": "#d0d0d0",
        },
    },
    "background": {
        "image": "",
        "opacity": 0.0,
        "fit": "cover",
        "alignment": "center",
        "repeat": "no_repeat",
    },
    "components": {},
}

BUILTIN_THEMES: dict[str, dict[str, Any]] = {
    "default": DEFAULT_THEME_DATA,
    "bw": MONO_THEME_DATA,
}

ALLOWED_COLOR_SCHEME_KEYS = {
    "primary",
    "on_primary",
    "primary_container",
    "on_primary_container",
    "secondary",
    "on_secondary",
    "secondary_container",
    "on_secondary_container",
    "tertiary",
    "on_tertiary",
    "tertiary_container",
    "on_tertiary_container",
    "error",
    "on_error",
    "error_container",
    "on_error_container",
    "outline",
    "background",
    "on_background",
    "surface",
    "on_surface",
    "surface_variant",
    "on_surface_variant",
    "inverse_surface",
    "on_inverse_surface",
    "inverse_primary",
    "shadow",
    "surface_tint",
    "outline_variant",
    "scrim",
}

IMAGE_FIT_MAP = {
    "contain": ft.BoxFit.CONTAIN,
    "cover": ft.BoxFit.COVER,
    "fill": ft.BoxFit.FILL,
    "fit_height": ft.BoxFit.FIT_HEIGHT,
    "fit_width": ft.BoxFit.FIT_WIDTH,
    "none": ft.BoxFit.NONE,
    "scale_down": ft.BoxFit.SCALE_DOWN,
}

IMAGE_REPEAT_MAP = {
    "no_repeat": ft.ImageRepeat.NO_REPEAT,
    "repeat": ft.ImageRepeat.REPEAT,
    "repeat_x": ft.ImageRepeat.REPEAT_X,
    "repeat_y": ft.ImageRepeat.REPEAT_Y,
}

ALIGNMENT_MAP = {
    "center": ft.Alignment.CENTER,
    "top_left": ft.Alignment.TOP_LEFT,
    "top": ft.Alignment.TOP_CENTER,
    "top_center": ft.Alignment.TOP_CENTER,
    "top_right": ft.Alignment.TOP_RIGHT,
    "left": ft.Alignment.CENTER_LEFT,
    "center_left": ft.Alignment.CENTER_LEFT,
    "right": ft.Alignment.CENTER_RIGHT,
    "center_right": ft.Alignment.CENTER_RIGHT,
    "bottom_left": ft.Alignment.BOTTOM_LEFT,
    "bottom": ft.Alignment.BOTTOM_CENTER,
    "bottom_center": ft.Alignment.BOTTOM_CENTER,
    "bottom_right": ft.Alignment.BOTTOM_RIGHT,
}


@dataclass(slots=True)
class BackgroundLayer:
    src: str
    opacity: float
    fit: ft.BoxFit
    alignment: ft.Alignment
    repeat: ft.ImageRepeat


@dataclass(slots=True)
class OverlayLayer:
    color: str
    opacity: float


@dataclass(slots=True)
class LoadedTheme:
    raw: dict[str, Any]
    theme: ft.Theme
    preferred_mode: ft.ThemeMode | None
    components: dict[str, dict[str, Any]]
    background: BackgroundLayer | None
    overlay: OverlayLayer | None
    source_path: Path | None


@dataclass(slots=True)
class ThemeProfileInfo:
    identifier: str
    name: str
    path: str | None
    builtin: bool
    source: str
    summary: str | None = None
    description: str | None = None
    author: str | None = None
    logo: str | None = None
    details: str | None = None
    website: str | None = None
    is_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "name": self.name,
            "path": self.path,
            "builtin": self.builtin,
            "source": self.source,
            "summary": self.summary,
            "description": self.description,
            "author": self.author,
            "logo": self.logo,
            "details": self.details,
            "website": self.website,
            "is_active": self.is_active,
        }


class ThemeManager:
    """Loads and applies UI theme definitions from JSON files."""

    def __init__(
        self,
        settings: SettingsStore | None = None,
        *,
        themes_dir: Path | None = None,
    ) -> None:
        self._settings = settings
        self._themes_dir = themes_dir or (CONFIG_DIR / "themes")
        self._themes_dir.mkdir(parents=True, exist_ok=True)
        self._active: LoadedTheme | None = None
        self._override_profile: str | None = None
        self._override_reason: str | None = None
        self._override_locked: bool = False

        # Enforce memorial-day override as early as possible to avoid any
        # pre-load applying user themes before lock kicks in.
        if self._is_memorial_day():
            self._override_profile = "bw"
            self._override_reason = (
                "12月13日为南京大屠杀死难者国家公祭日，已启用黑白主题并暂停主题自定义，以示哀悼。"
            )
            self._override_locked = True

    @property
    def active(self) -> LoadedTheme:
        if self._active is None:
            self.reload()
        assert self._active is not None
        return self._active

    @property
    def preferred_theme_mode(self) -> ft.ThemeMode | None:
        return self.active.preferred_mode

    @property
    def themes_dir(self) -> Path:
        return self._themes_dir

    def current_profile(self) -> str:
        if self._override_profile:
            return self._override_profile
        if self._settings is None:
            return "default"
        value = self._settings.get("ui.theme_profile", "default")
        if not isinstance(value, str):
            return "default"
        token = value.strip() or "default"
        if token.lower() == "system":
            return "default"
        return token

    @property
    def override_profile(self) -> str | None:
        return self._override_profile

    @property
    def override_reason(self) -> str | None:
        return self._override_reason

    @property
    def override_locked(self) -> bool:
        return self._override_locked

    @staticmethod
    def _is_memorial_day() -> bool:
        today = datetime.date.today()
        return today.month == 12 and today.day == 13

    def apply_profile_override(
        self,
        profile: str | None,
        *,
        reason: str | None = None,
        lock_changes: bool = False,
        reload: bool = True,
    ) -> None:
        token = profile.strip() if isinstance(profile, str) else None
        reason_text = reason.strip() if isinstance(reason, str) else None
        changed = (
            token != self._override_profile
            or reason_text != self._override_reason
            or bool(lock_changes) != self._override_locked
        )

        self._override_profile = token
        self._override_reason = reason_text
        self._override_locked = bool(token) and bool(lock_changes)

        if changed and reload:
            self.reload()

    @staticmethod
    def _sanitize_metadata_text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    def _extract_profile_metadata(
        self, payload: dict[str, Any], source_path: Path | None,
    ) -> dict[str, str | None]:
        name = self._sanitize_metadata_text(payload.get("name"))
        description = self._sanitize_metadata_text(
            payload.get("description") or payload.get("summary"),
        )
        if not description:
            description = self._sanitize_metadata_text(payload.get("details"))
        details = self._sanitize_metadata_text(payload.get("details"))
        author = self._sanitize_metadata_text(payload.get("author"))
        website = self._sanitize_metadata_text(payload.get("website"))

        summary = description
        if summary and len(summary) > 120:
            summary = summary[:119] + "…"

        logo: str | None = None
        raw_logo = payload.get("logo")
        if isinstance(raw_logo, str) and raw_logo.strip():
            token = raw_logo.strip()
            try:
                logo = self._resolve_asset_path(token, source_path)
            except Exception:  # pragma: no cover - resolution fallback
                logo = token

        return {
            "name": name,
            "description": description,
            "summary": summary,
            "details": details,
            "author": author,
            "website": website,
            "logo": logo,
        }

    def reload(self) -> None:
        self._active = self._load_theme()

    def style_for(self, component: str) -> dict[str, Any]:
        return copy.deepcopy(self.active.components.get(component, {}))

    def apply_component_style(self, component: str, target: Any) -> None:
        style = self.style_for(component)
        if not style:
            return
        for key, raw_value in style.items():
            value = self._coerce_style_value(key, raw_value)
            try:
                setattr(target, key, value)
            except AttributeError:
                logger.debug(
                    "apply_component_style skipped unknown attribute",
                    key=key,
                    component=component,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "apply_component_style failed",
                    component=component,
                    key=key,
                    error=str(exc),
                )

    def apply_page_theme(self, page: ft.Page) -> None:
        page.theme = self.active.theme
        self.apply_component_style("page", page)

    def build_background_layer(self) -> ft.Container | None:
        background = self.active.background
        if background is None:
            return None
        image = ft.Image(
            src=background.src,
            expand=True,
            fit=background.fit,
            repeat=background.repeat,
        )
        return ft.Container(
            expand=True,
            content=image,
            alignment=background.alignment,
            opacity=background.opacity,
        )

    def build_overlay_layer(self) -> ft.Container | None:
        overlay = self.active.overlay
        if overlay is None:
            return None
        return ft.Container(
            expand=True,
            bgcolor=overlay.color,
            opacity=overlay.opacity,
        )

    def list_profiles(self) -> list[dict[str, Any]]:
        current = self.current_profile()
        profiles: list[ThemeProfileInfo] = []
        seen: set[str] = set()

        for builtin_key, builtin_data in BUILTIN_THEMES.items():
            meta = self._extract_profile_metadata(builtin_data, None)
            name = meta.get("name") or builtin_data.get("name") or builtin_key
            identifier = builtin_key
            is_active = current.lower() == identifier.lower()
            profiles.append(
                ThemeProfileInfo(
                    identifier=identifier,
                    name=str(name),
                    path=None,
                    builtin=True,
                    source="builtin",
                    summary=meta.get("summary"),
                    description=meta.get("description"),
                    author=meta.get("author"),
                    logo=meta.get("logo"),
                    details=meta.get("details"),
                    website=meta.get("website"),
                    is_active=is_active,
                ),
            )
            seen.add(identifier)
        try:
            theme_files = sorted(self._themes_dir.glob("**/*.json"))
        except Exception as exc:  # pragma: no cover - filesystem guard
            logger.warning("遍历主题目录失败: {error}", error=str(exc))
            theme_files = []

        for file_path in theme_files:
            try:
                relative = file_path.relative_to(self._themes_dir)
                identifier = relative.as_posix()
            except Exception:
                identifier = file_path.name

            metadata: dict[str, str | None] = {}
            try:
                with file_path.open("r", encoding="utf-8") as fp:
                    payload = json.load(fp)
                if isinstance(payload, dict):
                    metadata = self._extract_profile_metadata(payload, file_path)
                else:
                    metadata = {}
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.debug(
                    "读取主题文件元数据失败: {error}",
                    error=str(exc),
                )
                metadata = {}

            name = metadata.get("name") or file_path.stem
            info = ThemeProfileInfo(
                identifier=identifier,
                name=name,
                path=str(file_path),
                builtin=False,
                source="file",
                summary=metadata.get("summary"),
                description=metadata.get("description"),
                author=metadata.get("author"),
                logo=metadata.get("logo"),
                details=metadata.get("details"),
                website=metadata.get("website"),
                is_active=identifier == current,
            )
            profiles.append(info)
            seen.add(identifier)

        if current not in seen and current not in {"default"}:
            resolved = self._resolve_profile_path(current)
            metadata: dict[str, str | None] = {}
            if resolved and resolved.exists():
                try:
                    with resolved.open("r", encoding="utf-8") as fp:
                        payload = json.load(fp)
                    if isinstance(payload, dict):
                        metadata = self._extract_profile_metadata(payload, resolved)
                except Exception:  # pragma: no cover - defensive logging
                    metadata = {}
            name = metadata.get("name") or Path(current).stem or current
            profiles.append(
                ThemeProfileInfo(
                    identifier=current,
                    name=name,
                    path=str(resolved) if resolved else None,
                    builtin=False,
                    source="custom",
                    summary=metadata.get("summary"),
                    description=metadata.get("description"),
                    author=metadata.get("author"),
                    logo=metadata.get("logo"),
                    details=metadata.get("details"),
                    website=metadata.get("website"),
                    is_active=True,
                ),
            )

        return [profile.to_dict() for profile in profiles]

    def import_theme(self, source: Path) -> dict[str, Any]:
        if not source.exists():
            raise FileNotFoundError(f"未找到主题文件: {source}")
        if not source.is_file():
            raise ValueError("主题导入仅支持文件或压缩包。")

        suffix = source.suffix.lower()
        if suffix not in {".json", ".zip"}:
            raise ValueError("请选择 .json 或 .zip 主题包。")

        temp_dir: Path | None = None
        try:
            if suffix == ".zip":
                import tempfile
                import zipfile

                temp_dir_obj = tempfile.TemporaryDirectory()
                temp_dir = Path(temp_dir_obj.name)
                with zipfile.ZipFile(source, "r") as zf:
                    zf.extractall(temp_dir)
                candidates = sorted(temp_dir.rglob("*.json"))
                if not candidates:
                    raise ValueError("压缩包中未找到 JSON 主题文件。")
                theme_file = candidates[0]
            else:
                theme_file = source

            try:
                data_bytes = theme_file.read_bytes()
            except Exception as exc:  # pragma: no cover - defensive logging
                raise ValueError(f"读取主题文件失败: {exc}") from exc

            try:
                text = data_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("主题文件必须使用 UTF-8 编码。") from exc

            try:
                payload = json.loads(text)
            except Exception as exc:
                raise ValueError("主题文件不是有效的 JSON。") from exc

            if not isinstance(payload, dict):
                raise ValueError("主题文件必须是 JSON 对象。")

            # 目标目录按文件名归档
            base_name = theme_file.stem
            sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in base_name).strip("_")
            sanitized = sanitized or "theme"
            target_dir = self._themes_dir / sanitized
            counter = 1
            while target_dir.exists():
                target_dir = self._themes_dir / f"{sanitized}_{counter}"
                counter += 1

            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{theme_file.stem}.json"
            target.write_text(text, encoding="utf-8")

            metadata = self._extract_profile_metadata(payload, target)
            identifier = target.relative_to(self._themes_dir).as_posix()
            return {
                "id": identifier,
                "path": str(target),
                "metadata": metadata,
            }
        finally:
            if temp_dir and temp_dir.exists():
                try:
                    import shutil

                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

    def set_profile(self, profile: str) -> dict[str, Any]:
        if self._settings is None:
            raise RuntimeError("ThemeManager 未绑定设置存储，无法更新主题。")
        if self._override_locked:
            reason = self._override_reason or "当前已锁定主题切换。"
            raise RuntimeError(reason)
        token = (profile or "").strip()
        if not token:
            raise ValueError("主题标识不能为空。")

        lowered = token.lower()

        if lowered in {"default", "system"}:
            stored = "default"
        elif lowered in {key.lower() for key in BUILTIN_THEMES.keys()}:
            stored = token
        else:
            candidate = self._resolve_profile_path(token)
            if not candidate or not candidate.exists():
                raise FileNotFoundError(f"未找到主题文件: {token}")
            try:
                relative = candidate.relative_to(self._themes_dir)
                stored = relative.as_posix()
            except ValueError:
                stored = str(candidate)

        self._settings.set("ui.theme_profile", stored)
        self.reload()
        profiles = self.list_profiles()
        current = next((item for item in profiles if item.get("is_active")), None)
        return {"profile": current, "profiles": profiles}

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _load_theme(self) -> LoadedTheme:
        profile = self._override_profile or "default"
        if self._override_profile is None and self._settings is not None:
            raw_profile = self._settings.get("ui.theme_profile", "default")
            if isinstance(raw_profile, str) and raw_profile.strip():
                profile = raw_profile.strip()

        data = copy.deepcopy(DEFAULT_THEME_DATA)
        source_path: Path | None = None

        lowered = profile.lower()

        if lowered in {key.lower() for key in BUILTIN_THEMES.keys()}:
            data = copy.deepcopy(BUILTIN_THEMES[next(k for k in BUILTIN_THEMES if k.lower() == lowered)])
        elif lowered not in ("default", "system"):
            candidate = self._resolve_profile_path(profile)
            if candidate and candidate.exists():
                try:
                    with candidate.open("r", encoding="utf-8") as fp:
                        loaded = json.load(fp)
                    if isinstance(loaded, dict):
                        data = loaded
                        source_path = candidate
                    else:
                        logger.warning("主题文件 {path} 不是有效的 JSON 对象", path=str(candidate))
                except Exception as exc:  # pragma: no cover - I/O guard
                    logger.warning("加载主题文件失败: {error}", error=str(exc))
            else:
                logger.warning("未找到指定的主题文件 {profile}", profile=profile)

        return self._parse_theme(data, source_path)

    def _parse_theme(self, data: dict[str, Any], source_path: Path | None) -> LoadedTheme:
        palette = data.get("palette") or {}
        components = data.get("components") or {}
        background = data.get("background") or {}

        theme, preferred_mode = self._build_theme_from_palette(palette)
        sanitized_components: dict[str, dict[str, Any]] = {}
        for key, value in components.items():
            if isinstance(key, str) and isinstance(value, dict):
                sanitized_components[key] = value

        background_layer = self._build_background_layer(background, source_path)
        overlay_layer = self._extract_overlay_layer(
            sanitized_components.get("home_view"),
            background_layer,
        )

        return LoadedTheme(
            raw=data,
            theme=theme,
            preferred_mode=preferred_mode,
            components=sanitized_components,
            background=background_layer,
            overlay=overlay_layer,
            source_path=source_path,
        )

    def _build_theme_from_palette(
        self, palette: dict[str, Any],
    ) -> tuple[ft.Theme, ft.ThemeMode | None]:
        mode = str(palette.get("mode", "seed")).lower()
        preferred_mode = self._coerce_theme_mode(palette.get("preferred_mode"))
        theme = ft.Theme()

        use_material3 = palette.get("use_material3")
        if isinstance(use_material3, bool):
            theme.use_material3 = use_material3

        if mode == "custom":
            color_scheme_data = palette.get("color_scheme") or {}
            scheme = self._build_color_scheme(color_scheme_data)
            if scheme is not None:
                theme.color_scheme = scheme
            else:
                seed = palette.get("seed_color") or palette.get("primary")
                if isinstance(seed, str):
                    theme.color_scheme_seed = self._normalize_color(seed)
        elif mode == "none":
            pass
        else:  # default to seed mode
            seed = palette.get("seed_color") or palette.get("primary")
            if isinstance(seed, str):
                theme.color_scheme_seed = self._normalize_color(seed)

        return theme, preferred_mode

    def _build_color_scheme(self, data: dict[str, Any]) -> ft.ColorScheme | None:
        if not isinstance(data, dict):
            return None
        kwargs: dict[str, Any] = {}
        for key in ALLOWED_COLOR_SCHEME_KEYS:
            if key in data:
                value = data[key]
                kwargs[key] = self._normalize_color(value)
        if not kwargs:
            return None
        return ft.ColorScheme(**kwargs)

    def _build_background_layer(
        self, data: dict[str, Any], source_path: Path | None,
    ) -> BackgroundLayer | None:
        image = data.get("image")
        if not image:
            return None

        opacity = data.get("opacity", 1.0)
        try:
            opacity_value = float(opacity)
        except (TypeError, ValueError):
            opacity_value = 1.0
        opacity_value = max(0.0, min(1.0, opacity_value))

        fit = self._coerce_image_fit(data.get("fit"))
        repeat = self._coerce_image_repeat(data.get("repeat"))
        alignment = self._coerce_alignment(data.get("alignment"))
        src = self._resolve_asset_path(str(image), source_path)

        return BackgroundLayer(
            src=src,
            opacity=opacity_value,
            fit=fit,
            alignment=alignment,
            repeat=repeat,
        )

    def _extract_overlay_layer(
        self,
        home_view_style: dict[str, Any] | None,
        background: BackgroundLayer | None,
    ) -> OverlayLayer | None:
        if not isinstance(home_view_style, dict):
            return None

        force_bgcolor = bool(home_view_style.pop("force_bgcolor", False))
        overlay_color = home_view_style.pop("overlay_color", None)
        overlay_opacity = home_view_style.pop("overlay_opacity", None)

        if background is not None and not force_bgcolor:
            if overlay_color is None and "bgcolor" in home_view_style:
                overlay_color = home_view_style.pop("bgcolor")
            if overlay_opacity is None and "opacity" in home_view_style:
                overlay_opacity = home_view_style.pop("opacity")

        if overlay_color is None:
            return None

        color = self._normalize_color(overlay_color)
        if overlay_opacity is None:
            opacity_value = 1.0
        else:
            try:
                opacity_value = float(overlay_opacity)
            except (TypeError, ValueError):
                opacity_value = 1.0
        opacity_value = max(0.0, min(1.0, opacity_value))

        return OverlayLayer(color=color, opacity=opacity_value)

    def _coerce_image_fit(self, value: Any) -> ft.BoxFit:
        if isinstance(value, str):
            key = value.strip().lower()
            if key in IMAGE_FIT_MAP:
                return IMAGE_FIT_MAP[key]
        return ft.BoxFit.COVER

    def _coerce_image_repeat(self, value: Any) -> ft.ImageRepeat:
        if isinstance(value, str):
            key = value.strip().lower()
            if key in IMAGE_REPEAT_MAP:
                return IMAGE_REPEAT_MAP[key]
        return ft.ImageRepeat.NO_REPEAT

    def _coerce_alignment(self, value: Any) -> ft.Alignment:
        if isinstance(value, str):
            key = value.strip().lower()
            if key in ALIGNMENT_MAP:
                return ALIGNMENT_MAP[key]
        return ft.Alignment.CENTER

    def _coerce_theme_mode(self, value: Any) -> ft.ThemeMode | None:
        if not isinstance(value, str):
            return None
        key = value.strip().lower()
        if key == "light":
            return ft.ThemeMode.LIGHT
        if key == "dark":
            return ft.ThemeMode.DARK
        if key == "system":
            return ft.ThemeMode.SYSTEM
        return None

    def _coerce_brightness(self, value: Any) -> ft.Brightness | None:
        if isinstance(value, ft.Brightness):
            return value
        if isinstance(value, str):
            key = value.strip().lower()
            if key == "dark":
                return ft.Brightness.DARK
            if key == "light":
                return ft.Brightness.LIGHT
        return None

    def _normalize_color(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        token = value.strip()
        if not token:
            return token
        if token.startswith("#") or token.startswith("rgb"):
            return token
        normalized = token.replace(" ", "_").replace("-", "_")
        attr = normalized.upper()
        if hasattr(ft.Colors, attr):
            return getattr(ft.Colors, attr)
        return token

    def _coerce_style_value(self, key: str, value: Any) -> Any:
        if isinstance(key, str):
            lowered = key.lower()
            if "color" in lowered:
                return self._normalize_color(value)
            if lowered == "opacity":
                try:
                    return max(0.0, min(1.0, float(value)))
                except (TypeError, ValueError):
                    return value
        return value

    def _resolve_profile_path(self, profile: str) -> Path | None:
        if profile.startswith("http://") or profile.startswith("https://"):
            return None

        raw = Path(profile)
        candidates: list[Path] = []

        possible_names = [raw]
        if not raw.suffix:
            possible_names.insert(0, raw.with_suffix(".json"))

        for name in possible_names:
            if name.is_absolute():
                candidates.append(name)
            else:
                candidates.append(self._themes_dir / name)
                candidates.append(CONFIG_DIR / name)
                candidates.append(Path.cwd() / name)

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[0] if candidates else raw

    def _resolve_asset_path(self, value: str, source_path: Path | None) -> str:
        if value.startswith("http://") or value.startswith("https://") or value.startswith("data:"):
            return value
        candidate = Path(value)
        if candidate.is_absolute() and candidate.exists():
            return str(candidate)

        search_roots: list[Path] = []
        if source_path is not None:
            search_roots.append(source_path.parent)
        search_roots.append(self._themes_dir)
        search_roots.append(CONFIG_DIR)

        for root in search_roots:
            resolved = root / candidate
            if resolved.exists():
                return str(resolved)

        return str(candidate)


__all__ = ["DEFAULT_THEME_DATA", "ThemeManager", "ThemeProfileInfo"]
