"""Filesystem paths used across the application."""

from pathlib import Path
import platformdirs
import sys
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

WALLPAPER_SOURCES_BUILTIN_PATH = BASE_DIR / "wallpaper_sources"
WALLPAPER_SOURCES_USER_PATH = DATA_DIR / "wallpaper_sources"

if getattr(sys, 'frozen', False):
    # PyInstaller 打包后的路径
    SOFTWARE_DIR = Path(sys.executable)
else:
    # 开发环境下的脚本路径
    SOFTWARE_DIR = Path(__file__).parent.parent / "main.py"
    

logger.info(f"【启动】目录获取\n软件路径\n\t· 运行目录: {BASE_DIR}\n\t· 执行文件: {SOFTWARE_DIR}\n数据目录\n\t· 缓存目录: {CACHE_DIR}\n\t· 配置目录: {CONFIG_DIR}\n\t· 数据目录: {DATA_DIR}\n\t· 插件目录: {PLUGINS_DIR}\n\t· 壁纸源目录[内置]: {WALLPAPER_SOURCES_BUILTIN_PATH}\n\t· 壁纸源目录[用户]: {WALLPAPER_SOURCES_USER_PATH}")
