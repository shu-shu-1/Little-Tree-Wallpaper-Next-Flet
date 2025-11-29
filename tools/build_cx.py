"""Little Tree Wallpaper Next - cx_Freeze 构建脚本
依赖：Python 3.8+，已安装 cx_Freeze
用法：
  直接运行：python tools/build_cx.py
  传参运行：python tools/build_cx.py [--console] [--test] [--internal]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import platform
import re
import shutil
import sys
from pathlib import Path

# tools/build_cx.py
# 构建脚本：自动更新版本号、调用 cx_Freeze、复制资源并重命名输出目录

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
CONSTANTS_PATH = SRC_DIR / "app" / "constants.py"
ICON_PATH = SRC_DIR / "assets" / "images" / "icon.ico"

DEFAULT_ENTRY = SRC_DIR / "main.py"
DEFAULT_APP_NAME = "LittleTreeWallpaper"  # 应用名称
PRODUCT_PREFIX = "LittleTreeWallpaper-next"

# 彩色输出
try:
    from colorama import Fore as _F
    from colorama import Style as _S
    from colorama import init as _colorama_init
    _colorama_init()
    _RESET = _S.RESET_ALL
    _C_INFO = _F.CYAN
    _C_WARN = _F.YELLOW
    _C_RUN = _F.MAGENTA
    _C_DONE = _F.GREEN
    _C_ERR = _F.RED
except Exception:
    _RESET = ""
    _C_INFO = _C_WARN = _C_RUN = _C_DONE = _C_ERR = ""

def _info(msg: str) -> None:
    print(f"{_C_INFO}[info]{_RESET} {msg}")

def _warn(msg: str) -> None:
    print(f"{_C_WARN}[warn]{_RESET} {msg}")

def _done(msg: str) -> None:
    print(f"{_C_DONE}[done]{_RESET} {msg}")

def _err(msg: str) -> None:
    print(f"{_C_ERR}[error]{_RESET} {msg}")

def _runlog(msg: str) -> None:
    print(f"{_C_RUN}[run ]{_RESET} {msg}")


def _date_str() -> str:
    return _dt.datetime.now().strftime("%Y.%m.%d")


def _platform_suffix(prefix: str = "internal") -> str:
    system = platform.system().lower()
    arch = (platform.machine() or "x64").lower()
    if system.startswith("win"):
        return f"{prefix}-windows-x64"
    return f"{prefix}-{system}-{arch}"


def _today_build_index(dist_dir: Path, date_str: str) -> str:
    # 在 dist 目录中查找当天既有构建编号，返回下一次的 3 位编号
    if not dist_dir.exists():
        return "001"
    max_idx = 0
    pattern = re.compile(rf"^{re.escape(PRODUCT_PREFIX)}-{re.escape(date_str)}-(\d+)-")
    for p in dist_dir.iterdir():
        if not p.is_dir():
            continue
        m = pattern.search(p.name)
        if m:
            try:
                max_idx = max(max_idx, int(m.group(1)))
            except ValueError:
                pass
    return f"{max_idx + 1:03d}"


def _update_build_constant(constants_path: Path, build_tag: str) -> None:
    """将 src/app/constants.py 中的 BUILD 变量更新为新的 build_tag。
    若未找到 BUILD 定义，则在文件末尾追加。
    """
    if not constants_path.exists():
        _warn(f"constants.py not found: {constants_path}")
        return

    text = constants_path.read_text(encoding="utf-8")
    pattern = re.compile(r'^(\s*BUILD\s*=\s*)([\'"])(.*?)(\2)', re.MULTILINE)
    if pattern.search(text):
        new_text = pattern.sub(rf'\1"{build_tag}"', text)
    else:
        if not text.endswith("\n"):
            text += "\n"
        new_text = text + f'BUILD = "{build_tag}"\n'
    constants_path.write_text(new_text, encoding="utf-8")
    _info(f"Updated BUILD in {constants_path} -> {build_tag}")


def _update_mode_constant(constants_path: Path, mode_value: str) -> None:
    """将 src/app/constants.py 中的 MODE 变量更新为给定的 mode_value。
    若未找到 MODE 定义，则在文件末尾追加。
    """
    if not constants_path.exists():
        _warn(f"constants.py not found: {constants_path}")
        return

    text = constants_path.read_text(encoding="utf-8")
    pattern = re.compile(r'^(\s*MODE\s*=\s*)([\'"])(.*?)(\2)', re.MULTILINE)
    if pattern.search(text):
        new_text = pattern.sub(rf'\1"{mode_value}"', text)
    else:
        if not text.endswith("\n"):
            text += "\n"
        new_text = text + f'MODE = "{mode_value}"\n'
    constants_path.write_text(new_text, encoding="utf-8")
    _info(f"Updated MODE in {constants_path} -> {mode_value}")


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        _warn(f"skip copy, not found: {src}")
        return
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    _info(f"Copied {src} -> {dst}")


def build_with_cx_freeze(entry: Path, app_name: str, windowed: bool) -> Path:
    """使用 cx_Freeze 构建应用
    """
    try:
        from cx_Freeze import Executable, setup
    except ImportError:
        _err("cx_Freeze not found. Please install it with: pip install cx_Freeze")
        sys.exit(1)

    # 清理构建缓存目录
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 构建配置
    build_exe_options = {
        "build_exe": str(BUILD_DIR / "exe"),
        "include_files": [],
        "packages": ["flet", "aiohttp", "requests", "filetype", "magic", "loguru",
                     "platformdirs", "pyperclip", "orjson", "rtoml", "pystray", "psutil"],
        "excludes": [],
    }

    # 添加图标（如果存在）
    if ICON_PATH.exists():
        icon_path = str(ICON_PATH)
    else:
        icon_path = None
        _warn(f"icon not found at {ICON_PATH}, continue without icon")

    # 创建可执行文件配置
    if windowed:
        # Windows 下无控制台窗口
        base = "Win32GUI" if sys.platform == "win32" else None
    else:
        base = None

    executable = Executable(
        script=str(entry),
        target_name=app_name + (".exe" if sys.platform == "win32" else ""),
        base=base,
        icon=icon_path,
    )

    # 复制资源到构建目录
    _copy_tree(SRC_DIR / "plugins", BUILD_DIR / "exe" / "_internal" / "plugins")
    _copy_tree(SRC_DIR / "assets", BUILD_DIR / "exe" / "_internal" / "assets")
    _copy_tree(SRC_DIR / "licenses", BUILD_DIR / "exe" / "_internal" / "licenses")
    _copy_tree(SRC_DIR / "wallpaper_sources", BUILD_DIR / "exe" / "_internal" / "wallpaper_sources")

    # 运行构建
    _info("Running cx_Freeze build...")

    # 模拟命令行参数调用 cx_Freeze
    sys.argv = [sys.argv[0], "build_exe"]
    try:
        setup(
            name=app_name,
            version="1.0",
            description="Little Tree Wallpaper Next",
            options={"build_exe": build_exe_options},
            executables=[executable],
        )
    except SystemExit:
        pass  # cx_Freeze 会调用 sys.exit()，我们忽略它

    # 移动构建结果到 dist 目录
    build_output = BUILD_DIR / "exe"
    if not build_output.exists():
        raise FileNotFoundError(f"Build output folder not found: {build_output}")

    out_dir = DIST_DIR / app_name
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)

    shutil.move(str(build_output), str(out_dir))
    _info(f"cx_Freeze output: {out_dir}")
    return out_dir


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="LittleTreeWallpaper-next 构建脚本（cx_Freeze）")
    # 是否启用命令行、是否启用测试版本、是否为内部版本
    parser.add_argument("--console", action="store_true", default=False, help="启用控制台（默认关闭）")
    parser.add_argument("--test", action="store_true", default=False, help="启用测试版本：设置 MODE=TEST，输出目录后缀为 test-*")
    parser.add_argument("--internal", action="store_true", default=False, help="启用内部版本：设置 MODE=TEST，但保留 internal-* 后缀")
    args = parser.parse_args(argv)

    # 切换到项目根目录，保证相对路径一致
    os.chdir(PROJECT_ROOT)

    # 参数协调：若同时指定 --test 与 --internal，则优先 internal，并给出警告
    if args.test and args.internal:
        _warn("同时指定了 --test 与 --internal，按内部版本处理（保留 internal 后缀）")
        # internal 优先
        test_mode = True
        keep_internal_suffix = True
    else:
        test_mode = args.test or args.internal
        keep_internal_suffix = args.internal  # 仅 internal 时保留 internal

    date_str = _date_str()
    idx = _today_build_index(DIST_DIR, date_str)

    # 根据模式决定后缀前缀
    suffix_prefix = "internal" if keep_internal_suffix or not test_mode else "test"
    suffix = _platform_suffix(prefix=suffix_prefix)

    build_tag = f"{date_str}-{idx}"
    final_dir_name = f"{PRODUCT_PREFIX}-{date_str}-{idx}-{suffix}"

    _info(f"Build tag: {build_tag}")
    _info(f"Final output dir: {final_dir_name}")

    # 1) 更新 BUILD 变量
    _update_build_constant(CONSTANTS_PATH, build_tag)

    # 1.1) 测试/内部版本将 MODE 设为 TEST
    if test_mode:
        _update_mode_constant(CONSTANTS_PATH, "TEST")

    # 2) 运行 cx_Freeze
    out_dir = build_with_cx_freeze(
        entry=DEFAULT_ENTRY,
        app_name=DEFAULT_APP_NAME,
        windowed=not args.console,
    )

    # 3) 复制 src 中的 plugins 和 assets 到构建输出目录
    # 注意：这些资源在 build_with_cx_freeze 中已经复制过了，这里不再重复复制

    # 4) 重命名输出目录为期望格式
    final_out = DIST_DIR / final_dir_name
    if final_out.exists():
        shutil.rmtree(final_out, ignore_errors=True)
    out_dir.rename(final_out)
    _done(f"Output: {final_out}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print()
        _warn("cancelled")
        sys.exit(130)
