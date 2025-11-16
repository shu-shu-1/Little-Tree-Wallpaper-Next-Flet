"""Application-wide constants used across the UI and plugins.

Keep numeric tab indices here so callers can avoid magic numbers. These
values reflect the order of tabs in the main settings view (0-based).
"""

# Index of the "Plugins" tab inside the Settings view (0-based).
SETTINGS_TAB_PLUGINS = 5
"""Global constants for Little Tree Wallpaper Next."""

APP_NAME = "小树壁纸 Next"
VER = "0.1.0"
BUILD = "2025.11.16-001"
MODE = "TEST"
BUILD_VERSION = f"v{VER} ({BUILD})"

# 调整该标记值以控制首次启动引导是否在新版本中重新显示。
FIRST_RUN_MARKER_VERSION = 1

HITOKOTO_API = [
    "https://v1.hitokoto.cn",
    "https://international.v1.hitokoto.cn/",
]

HITOKOTO_CATEGORY_LABELS = {
    "a": "动画",
    "b": "漫画",
    "c": "游戏",
    "d": "文学",
    "e": "原创",
    "f": "网络",
    "g": "其他",
    "h": "影视",
    "i": "诗词",
    "j": "网易云",
    "k": "哲学",
    "l": "抖机灵",
}

ZHAOYU_API_URL = "https://hub.saintic.com/openservice/sentence/"

# 是否显示右下角“测试版”水印（稳定版不显示）
SHOW_WATERMARK = MODE != "STABLE"
