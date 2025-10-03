"""Global constants for Little Tree Wallpaper Next."""

VER = "0.2.0"
BUILD = "20251003-056"
MODE = "TEST"
BUILD_VERSION = f"v{VER} ({BUILD})"

HITOKOTO_API = [
    "https://v1.hitokoto.cn",
    "https://international.v1.hitokoto.cn/",
]

# 是否显示右下角“测试版”水印（稳定版不显示）
SHOW_WATERMARK = MODE != "STABLE"
