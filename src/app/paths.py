"""Filesystem paths used across the application."""

from pathlib import Path
import platformdirs
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
ASSET_DIR = BASE_DIR / "assets"
UI_FONT_PATH = ASSET_DIR / "fonts" / "LXGWNeoXiHeiPlus.ttf"
HITO_FONT_PATH = ASSET_DIR / "fonts" / "LXGWWenKaiLite.ttf"
IMAGE_PATH = ASSET_DIR / "images"
ICO_PATH = IMAGE_PATH / "icon.ico"
LICENSE_PATH = BASE_DIR / "LICENSES"

CACHE_DIR = Path(
    platformdirs.user_cache_dir(
        "Little-Tree-Wallpaper", "Little Tree Studio", "Next", ensure_exists=True
    )
)
RUNTIME_DIR = Path(
    platformdirs.user_runtime_dir(
        "Little-Tree-Wallpaper", "Little Tree Studio", "Next", ensure_exists=True
    )
)
CONFIG_DIR = Path(
    platformdirs.user_config_dir(
        "Little-Tree-Wallpaper", "Little Tree Studio", "Next", ensure_exists=True
    )
)
DATA_DIR = Path(
    platformdirs.user_data_dir(
        "Little-Tree-Wallpaper", "Little Tree Studio", "Next", ensure_exists=True
    )
)

PLUGINS_DIR = BASE_DIR / "plugins"

logger.info(f"【启动】数据目录\n缓存目录: {CACHE_DIR}\n配置目录: {CONFIG_DIR}\n数据目录: {DATA_DIR}\n 插件目录: {PLUGINS_DIR}")
