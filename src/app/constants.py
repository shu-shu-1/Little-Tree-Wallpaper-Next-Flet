"""Application-wide constants used across the UI and plugins.

Keep numeric tab indices here so callers can avoid magic numbers. These
values reflect the order of tabs in the main settings view (0-based).
"""

# Index of the "Plugins" tab inside the Settings view (0-based).
SETTINGS_TAB_PLUGINS = 5
"""Global constants for Little Tree Wallpaper Next."""

VER = "0.1.0"
BUILD = "20251025-early_testing"
MODE = "TEST"
BUILD_VERSION = f"v{VER} ({BUILD})"

HITOKOTO_API = [
    "https://v1.hitokoto.cn",
    "https://international.v1.hitokoto.cn/",
]

# 是否显示右下角“测试版”水印（稳定版不显示）
SHOW_WATERMARK = MODE != "STABLE"
