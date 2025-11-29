"""图片优化管理器 - 处理图片格式转换和优化功能。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from PIL import Image


@dataclass
class ImageOptimizationResult:
    """图片优化结果。"""

    success: bool
    total_files: int
    processed_files: int
    failed_files: int
    original_size: int  # 字节
    optimized_size: int  # 字节
    time_elapsed: float  # 秒
    errors: list[str]


@dataclass
class OptimizationProgress:
    """优化进度信息。"""

    current_file: str
    processed_count: int
    total_count: int
    percentage: float
    current_size: int
    optimized_size: int


class ImageOptimizer:
    """图片优化器。"""

    def __init__(self):
        self._supported_formats = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
        self._executor = ThreadPoolExecutor(max_workers=4)

    def is_image_file(self, file_path: Path) -> bool:
        """检查是否为支持的图片文件。"""
        return file_path.suffix.lower() in self._supported_formats

    def get_image_files(self, folder_path: Path) -> list[Path]:
        """获取文件夹中的所有图片文件。"""
        if not folder_path.exists():
            return []

        image_files = []
        try:
            for file_path in folder_path.rglob("*"):
                if file_path.is_file() and self.is_image_file(file_path):
                    image_files.append(file_path)
        except Exception as e:
            logger.error(f"扫描图片文件时出错: {e}")

        return sorted(image_files)

    def convert_to_avif(self, source_path: Path, target_path: Path, quality: int = 85) -> tuple[bool, str]:
        """将图片转换为AVIF格式。"""
        try:
            with Image.open(source_path) as img:
                # 转换为RGB模式（如果需要）
                if img.mode in ("RGBA", "LA", "P"):
                    # 保持透明度
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # 保存为AVIF格式
                img.save(
                    target_path,
                    "AVIF",
                    quality=quality,
                    optimize=True,
                )

            return True, f"转换成功: {source_path.name}"

        except Exception as e:
            error_msg = f"转换失败 {source_path.name}: {e}"
            logger.error(error_msg)
            return False, error_msg

    async def optimize_folder_to_avif(
        self,
        folder_path: Path,
        quality: int = 85,
        progress_callback: Callable[[OptimizationProgress], None] | None = None,
    ) -> ImageOptimizationResult:
        """异步优化文件夹中的所有图片为AVIF格式。"""
        start_time = time.time()

        # 获取所有图片文件
        image_files = self.get_image_files(folder_path)
        if not image_files:
            return ImageOptimizationResult(
                success=True,
                total_files=0,
                processed_files=0,
                failed_files=0,
                original_size=0,
                optimized_size=0,
                time_elapsed=0,
                errors=[],
            )

        processed_count = 0
        failed_count = 0
        original_size = 0
        optimized_size = 0
        errors = []

        # 创建输出文件夹
        avif_folder = folder_path / "avif_optimized"
        avif_folder.mkdir(exist_ok=True)

        # 记录成功处理的文件及其目标路径，便于后续替换原图
        processed_mapping: list[tuple[Path, Path]] = []

        # 逐个处理文件
        for i, source_file in enumerate(image_files):
            try:
                # 计算原始文件大小
                original_size += source_file.stat().st_size

                # 生成输出文件名（暂时输出到 avif_optimized 目录，后续再移动回原目录）
                relative_path = source_file.relative_to(folder_path)
                target_file = avif_folder / f"{relative_path.stem}.avif"
                target_file.parent.mkdir(parents=True, exist_ok=True)

                # 转换文件
                success, message = await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    self.convert_to_avif,
                    source_file,
                    target_file,
                    quality,
                )

                if success:
                    processed_count += 1
                    # 记录映射关系，稍后替换原图
                    processed_mapping.append((source_file, target_file))
                    # 计算优化后文件大小
                    if target_file.exists():
                        optimized_size += target_file.stat().st_size
                else:
                    failed_count += 1
                    errors.append(message)

                # 更新进度
                if progress_callback:
                    progress_info = OptimizationProgress(
                        current_file=source_file.name,
                        processed_count=processed_count,
                        total_count=len(image_files),
                        percentage=(i + 1) / len(image_files) * 100,
                        current_size=original_size,
                        optimized_size=optimized_size,
                    )
                    progress_callback(progress_info)

                # 稍微延迟以避免界面卡顿
                await asyncio.sleep(0.01)

            except Exception as e:
                error_msg = f"处理文件 {source_file.name} 时出错: {e}"
                logger.error(error_msg)
                failed_count += 1
                errors.append(error_msg)

        # 将生成的 AVIF 文件移动回原目录，并删除原文件
        for source_file, temp_avif in processed_mapping:
            try:
                # 目标路径：原目录下，扩展名改为 .avif
                final_avif = source_file.with_suffix(".avif")

                # 如果已存在同名 .avif 文件，先删除，避免 rename 失败
                if final_avif.exists():
                    final_avif.unlink()

                # 移动 AVIF 文件到目标位置
                if temp_avif.exists():
                    temp_avif.replace(final_avif)

                # 删除原始文件
                if source_file.exists():
                    try:
                        source_file.unlink()
                    except Exception as e:
                        err = f"删除原文件失败 {source_file}: {e}"
                        logger.warning(err)
                        errors.append(err)
                        failed_count += 1
            except Exception as e:
                err = f"替换原文件为 AVIF 时出错 {source_file}: {e}"
                logger.error(err)
                errors.append(err)
                failed_count += 1

        # 清理临时 avif_optimized 目录（若为空则删除）
        try:
            if avif_folder.exists():
                # 仅在目录为空时删除，避免误删其他文件
                if not any(avif_folder.iterdir()):
                    avif_folder.rmdir()
        except Exception as e:
            logger.warning(f"清理临时 AVIF 目录失败 {avif_folder}: {e}")

        time_elapsed = time.time() - start_time

        return ImageOptimizationResult(
            success=failed_count == 0,
            total_files=len(image_files),
            processed_files=processed_count,
            failed_files=failed_count,
            original_size=original_size,
            optimized_size=optimized_size,
            time_elapsed=time_elapsed,
            errors=errors,
        )

    def format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小。"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)

        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.1f} {size_names[i]}"

    def calculate_compression_ratio(self, original_size: int, optimized_size: int) -> float:
        """计算压缩比。"""
        if original_size == 0:
            return 0.0

        return (1 - optimized_size / original_size) * 100


# 创建全局实例
image_optimizer = ImageOptimizer()
