"""Image sniffing service."""

from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import shutil
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from loguru import logger

import ltwapi
from app.paths import CACHE_DIR

_IMAGE_TAGS = {"img", "image", "input"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif", ".svg", ".tiff"}
_STYLE_URL_RE = re.compile(r"url\((['\"]?)([^'\"\)]+)\1\)")
_SRCSET_SPLIT_RE = re.compile(r"\s*,\s*")

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=40)


@dataclass(slots=True)
class SniffedImage:
    id: str
    url: str
    filename: str
    content_type: str | None = None
    referer: str | None = None


class SniffServiceError(RuntimeError):
    """Raised when sniffing fails."""


class _ImageExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._process_tag(tag, dict(attrs))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._process_tag(tag, dict(attrs))

    def _process_tag(self, tag: str, attrs: dict[str, str | None]) -> None:
        tag_lower = tag.lower()
        if tag_lower in _IMAGE_TAGS:
            src = attrs.get("src") or attrs.get("data-src")
            if src:
                self.urls.append(src)
            srcset = attrs.get("srcset")
            if srcset:
                for entry in _SRCSET_SPLIT_RE.split(srcset.strip()):
                    candidate = entry.strip().split()[0]
                    if candidate:
                        self.urls.append(candidate)
            style = attrs.get("style")
            if style:
                self.urls.extend(_STYLE_URL_RE.findall(style))
        elif tag_lower in {"source", "video", "picture"}:
            for key in ("src", "srcset", "data-src", "data-srcset"):
                value = attrs.get(key)
                if not value:
                    continue
                if key.endswith("srcset"):
                    for entry in _SRCSET_SPLIT_RE.split(value.strip()):
                        candidate = entry.strip().split()[0]
                        if candidate:
                            self.urls.append(candidate)
                else:
                    self.urls.append(value)
        elif tag_lower == "meta":
            property_val = (attrs.get("property") or attrs.get("name") or "").lower()
            if property_val in {"og:image", "twitter:image", "image"}:
                content = attrs.get("content")
                if content:
                    self.urls.append(content)
        style_attr = attrs.get("style")
        if style_attr:
            matches = _STYLE_URL_RE.findall(style_attr)
            for _, match in matches:
                self.urls.append(match)


class SniffService:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = Path(cache_dir or (CACHE_DIR / "sniff"))
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def sniff(self, url: str) -> list[SniffedImage]:
        normalized = url.strip()
        if not normalized.startswith(("http://", "https://")):
            raise SniffServiceError("仅支持 HTTP/HTTPS 链接")

        logger.info("开始嗅探图片: {}", normalized)
        async with aiohttp.ClientSession(timeout=_DEFAULT_TIMEOUT) as session:
            try:
                async with session.get(normalized, headers={"User-Agent": self._user_agent()}) as resp:
                    resp.raise_for_status()
                    actual_url = str(resp.url)
                    content_type = resp.headers.get("Content-Type", "").lower()
                    if content_type.startswith("image/"):
                        filename = self._derive_filename(actual_url, content_type)
                        return [
                            SniffedImage(
                                id=uuid.uuid4().hex,
                                url=actual_url,
                                filename=filename,
                                content_type=content_type,
                                referer=normalized,
                            ),
                        ]
                    text = await resp.text(errors="ignore")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - network errors
                logger.error("嗅探失败: {}", exc)
                raise SniffServiceError("链接访问失败") from exc

        extractor = _ImageExtractor()
        try:
            extractor.feed(text)
        except Exception as exc:  # pragma: no cover - parser failures
            logger.warning("解析 HTML 失败: {}", exc)
        candidates = self._normalize_candidates(extractor.urls, actual_url)
        logger.info("嗅探完成，发现 {} 张图片", len(candidates))
        return [
            SniffedImage(
                id=uuid.uuid4().hex,
                url=link,
                filename=self._derive_filename(link, None),
                content_type=None,
                referer=normalized,
            )
            for link in candidates
        ]

    async def ensure_cached(self, image: SniffedImage) -> Path:
        cached = self._find_cached(image.id)
        if cached:
            return cached
        headers: dict[str, str] | None = None
        if image.referer:
            headers = {"Referer": image.referer}
        filename = image.filename or image.id
        filename = self._sanitize_filename(filename)
        result = await asyncio.to_thread(
            ltwapi.download_file,
            image.url,
            str(self._cache_dir),
            filename,
            300,
            3,
            headers,
            None,
            False,
        )
        if not result:
            raise SniffServiceError("下载失败")
        downloaded_path = Path(result)
        target = self._cache_dir / f"{image.id}{downloaded_path.suffix}"
        if downloaded_path != target:
            try:
                if target.exists():
                    downloaded_path = target
                else:
                    downloaded_path.replace(target)
                    downloaded_path = target
            except Exception:
                pass
        return downloaded_path

    async def download(self, image: SniffedImage, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        cached = await self.ensure_cached(image)
        filename = self._sanitize_filename(image.filename or cached.name)
        filename = self._ensure_extension(filename, cached.suffix)
        target = self._unique_path(dest_dir, filename)
        shutil.copy2(cached, target)
        return target

    async def download_many(self, images: Sequence[SniffedImage], dest_dir: Path) -> list[Path]:
        results: list[Path] = []
        for image in images:
            try:
                path = await self.download(image, dest_dir)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("下载图片失败 {}: {}", image.url, exc)
                continue
            results.append(path)
        return results

    def _find_cached(self, image_id: str) -> Path | None:
        for candidate in self._cache_dir.glob(f"{image_id}.*"):
            if candidate.is_file():
                return candidate
        return None

    def _normalize_candidates(self, urls: Iterable[str], base_url: str) -> list[str]:
        seen: set[str] = set()
        results: list[str] = []
        for raw in urls:
            candidate = raw[1] if isinstance(raw, tuple) else raw
            candidate = (candidate or "").strip()
            if not candidate:
                continue
            if candidate.startswith("data:"):
                continue
            absolute = urljoin(base_url, candidate)
            if absolute in seen:
                continue
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if not self._looks_like_image(parsed.path) and not self._has_image_hint(candidate):
                continue
            seen.add(absolute)
            results.append(absolute)
        return results

    def _looks_like_image(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in _IMAGE_EXTENSIONS

    def _has_image_hint(self, value: str) -> bool:
        lowered = value.lower()
        return any(hint in lowered for hint in ("image", "img", "photo", "picture"))

    def _derive_filename(self, url: str, content_type: str | None) -> str:
        parsed = urlparse(url)
        name = os.path.basename(parsed.path)
        ext = os.path.splitext(name)[1]
        if not ext and content_type:
            ext = self._guess_extension(url, content_type)
        if not name:
            name = f"image-{uuid.uuid4().hex[:8]}"
        sanitized = self._sanitize_filename(name)
        return self._ensure_extension(sanitized, ext or ".jpg")

    def _ensure_extension(self, name: str, ext: str) -> str:
        if not ext:
            return name
        if not ext.startswith("."):
            ext = f".{ext}"
        root, current_ext = os.path.splitext(name)
        if current_ext.lower() != ext.lower():
            return f"{root}{ext.lower()}"
        return name

    def _unique_path(self, directory: Path, name: str) -> Path:
        candidate = directory / name
        if not candidate.exists():
            return candidate
        stem, ext = os.path.splitext(name)
        index = 1
        while True:
            candidate = directory / f"{stem}_{index}{ext}"
            if not candidate.exists():
                return candidate
            index += 1

    def _sanitize_filename(self, value: str) -> str:
        sanitized = [ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value]
        name = "".join(sanitized).strip("._") or "image"
        return name[:120]

    def _guess_extension(self, url: str, content_type: str | None) -> str:
        if content_type:
            primary = content_type.split(";")[0].strip().lower()
            ext = mimetypes.guess_extension(primary) or ""
            if ext == ".jpe":
                ext = ".jpg"
            if ext:
                return ext
        parsed_ext = os.path.splitext(urlparse(url).path)[1]
        if parsed_ext.lower() in _IMAGE_EXTENSIONS:
            return parsed_ext.lower()
        return ".jpg"

    def _user_agent(self) -> str:
        return "LittleTreeWallpaperSniffer/1.0"


__all__ = ["SniffService", "SniffServiceError", "SniffedImage"]
