from __future__ import annotations

import argparse
import datetime as _dt
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from shutil import which

# tools/build.py
# 构建脚本：自动更新版本号、调用 PyInstaller、复制资源并重命名输出目录
# 依赖：Python 3.8+，已安装 pyinstaller
# 用法：
#   直接运行：python tools/build.py
#   传参运行：python tools/build.py [--console] [--test] [--internal]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
CONSTANTS_PATH = SRC_DIR / "app" / "constants.py"
ICON_PATH = SRC_DIR / "assets" / "images" / "icon.ico"

DEFAULT_ENTRY = SRC_DIR / "main.py"
DEFAULT_APP_NAME = "LittleTreeWallpaper"  # PyInstaller 的 --name，exe 名称
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


def _ensure_tool(cmd: str) -> list[str]:
    # 返回可用的 pyinstaller 调用命令
    exe = which(cmd)
    if exe:
        return [exe]
    # 回退到 python -m PyInstaller
    return [sys.executable, "-m", "PyInstaller"]


def _run(cmd: list[str], cwd: Path) -> None:
    _runlog(" ".join(cmd))
    proc = subprocess.run(cmd, check=False, cwd=str(cwd))
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        _warn(f"skip copy, not found: {src}")
        return
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    _info(f"Copied {src} -> {dst}")


def build(entry: Path, app_name: str, windowed: bool) -> Path:
    # 清理构建缓存目录（由 PyInstaller 使用）
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    cmd = _ensure_tool("pyinstaller")
    args = [
        str(entry),
        "--noconfirm",
        "--clean",
        "--onedir",
        f"--name={app_name}",
    ]
    if windowed:
        args.append("--windowed")

    if ICON_PATH.exists():
        args.append(f"--icon={ICON_PATH}")
    else:
        _warn(f"icon not found at {ICON_PATH}, continue without --icon")

    _run(cmd + args, cwd=PROJECT_ROOT)

    out_dir = DIST_DIR / app_name
    if not out_dir.exists():
        # 某些情况下 PyInstaller 可能使用不同命名，兜底检查
        candidates = [p for p in DIST_DIR.iterdir() if p.is_dir()]
        if len(candidates) == 1:
            out_dir = candidates[0]
        else:
            raise FileNotFoundError(f"Build output folder not found: {out_dir}")
    _info(f"PyInstaller output: {out_dir}")
    return out_dir


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="LittleTreeWallpaper-next 构建脚本（PyInstaller）")
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

    # 2) 运行 PyInstaller
    out_dir = build(
        entry=DEFAULT_ENTRY,
        app_name=DEFAULT_APP_NAME,
        windowed=not args.console,
    )

    # 3) 复制 src 中的 plugins 和 assets 到构建输出目录
    _copy_tree(SRC_DIR / "plugins", out_dir / "_internal" / "plugins")
    _copy_tree(SRC_DIR / "assets", out_dir / "_internal" / "assets")
    _copy_tree(SRC_DIR / "licenses", out_dir / "_internal" / "licenses")
    _copy_tree(SRC_DIR / "wallpaper_sources", out_dir / "_internal" / "wallpaper_sources")

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
