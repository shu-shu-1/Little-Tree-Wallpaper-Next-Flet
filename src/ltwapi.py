import os
import sys
import requests
import aiohttp
import platform
import subprocess
from pathlib import Path
import re
import io
import uuid
import time
import json
import shutil
import hashlib
import mimetypes
from urllib.parse import urlparse, unquote
import pycurl
from typing import Callable, Optional, Dict
from loguru import logger

try:
    import magic
except ImportError:
    magic = None
try:
    import filetype
except ImportError:
    filetype = None



def _try_subprocess(cmd: list) -> Optional[str]:
    """运行命令并返回 stdout 的 str，失败返回 None。"""
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return None


def _from_file_uri(raw: str) -> str:
    """把 gsettings 返回的 'file:///xxx/yyy.jpg' 转成真实路径。"""
    from urllib.parse import urlparse, unquote

    if raw.startswith("file://"):
        return unquote(urlparse(raw).path)
    return unquote(raw)


def get_sys_wallpaper(windows_way = "reg") -> Optional[str]:
    """
    返回当前系统桌面壁纸的绝对路径；失败返回 None。
    支持 Windows / macOS / Linux(GNOME/KDE/XFCE)。
    """
    if os.name == "nt":
        # ---------- Windows ----------
        if windows_way == "reg":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop"
                ) as key:
                    path, _ = winreg.QueryValueEx(key, "WallPaper")
                return path if os.path.isfile(path) else None
            except Exception:
                return None
        else:
            try:
                import ctypes
                path = ctypes.windll.user32.SystemParametersInfoW(20, 0, None, 0)
                return path if os.path.isfile(path) else None
            except Exception:
                return None
    if sys.platform == "darwin":
        # ---------- macOS ----------
        # 兼容多显示器：获取所有桌面的壁纸，按顺序返回第一个存在的路径
        try:
            # 使用 POSIX 路径，避免别名/冒号风格路径
            script = 'tell application "System Events" to get POSIX path of picture of every desktop'
            out = _try_subprocess(["osascript", "-e", script])
            if not out:
                return None
            # osascript 返回可能是以", "分隔的一行，或按行分隔
            candidates = [p.strip() for p in re.split(r",\s+|\n+", out) if p.strip()]
            for p in candidates:
                if os.path.isfile(p):
                    return p
            return None
        except Exception:
            return None

    if sys.platform.startswith("linux"):
        # ---------- Linux ----------
        # 1) GNOME / Unity / Cinnamon / Budgie / MATE 等 gsettings 方案
        schemas = [
            ("org.gnome.desktop.background", "picture-uri-dark"),
            ("org.gnome.desktop.background", "picture-uri"),
            ("org.cinnamon.desktop.background", "picture-uri"),
            ("org.mate.background", "picture-filename"),
        ]
        for schema, key in schemas:
            try:
                uri_out = _try_subprocess(["gsettings", "get", schema, key])
                if not uri_out or uri_out in {"''", '""'}:
                    continue
                # 可能返回：'file:///path' 或 'file:///a', 'file:///b' 或普通路径字符串
                # 去除外层引号
                uri_out = uri_out.strip()
                if (uri_out.startswith("'") and uri_out.endswith("'")) or (
                    uri_out.startswith('"') and uri_out.endswith('"')
                ):
                    uri_out = uri_out[1:-1]
                # 若是逗号分隔的多值，逐个尝试
                candidates = [s.strip() for s in uri_out.split(",")]
                for cand in candidates:
                    path = _from_file_uri(cand)
                    if os.path.isfile(path):
                        return path
            except Exception:
                pass

        # 2) KDE Plasma 5/6
        # 读取 plasma 配置文件，可能有多个 Image=，优先后出现的（通常为当前活动桌面）
        kde_conf = os.path.expanduser(
            "~/.config/plasma-org.kde.plasma.desktop-appletsrc"
        )
        if os.path.isfile(kde_conf):
            try:
                images = []
                with open(kde_conf, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("Image="):
                            val = line.split("=", 1)[1].strip()
                            p = _from_file_uri(val)
                            images.append(p)
                # 从后往前找第一个存在的
                for p in reversed(images):
                    if os.path.isfile(p):
                        return p
            except Exception:
                pass

        # 3) XFCE
        # 列出所有 backdrop 键，检查包含 image-path/last-image 的键值
        try:
            props_out = _try_subprocess(
                ["xfconf-query", "--channel", "xfce4-desktop", "--property", "/backdrop", "--list"]
            )
            if props_out:
                props = [p.strip() for p in props_out.splitlines() if p.strip()]
                for prop in props:
                    if prop.endswith("image-path") or prop.endswith("last-image"):
                        val = _try_subprocess(
                            [
                                "xfconf-query",
                                "--channel",
                                "xfce4-desktop",
                                "--property",
                                prop,
                            ]
                        )
                        if val:
                            p = _from_file_uri(val.strip())
                            if os.path.isfile(p):
                                return p
        except Exception:
            pass

    return None


def get_bing_wallpaper(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
):
    try:
        url = "https://cn.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1"
        headers = {}
        if user_agent:
            headers["User-Agent"] = user_agent
        response = requests.get(url, headers=headers)
        data = response.json()
        if data and "images" in data and len(data["images"]) > 0:
            image_info = data["images"][0]
            return {
                "url": image_info["url"],
                "title": image_info.get("title", ""),
                "copyright": image_info.get("copyright", ""),
                "startdate": image_info.get("startdate", ""),
            }
        return None
    except Exception:
        return None


async def get_bing_wallpaper_async(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
):
    try:
        url = "https://cn.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1"
        headers = {}
        if user_agent:
            headers["User-Agent"] = user_agent
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                if data and "images" in data and len(data["images"]) > 0:
                    image_info = data["images"][0]
                    return {
                        "url": image_info["url"],
                        "title": image_info.get("title", ""),
                        "copyright": image_info.get("copyright", ""),
                        "startdate": image_info.get("startdate", ""),
                    }
                return None
    except Exception:
        return None
    
async def get_spotlight_wallpaper_async(user_agent: str = None):

    """
    异步获取 Windows Spotlight 壁纸信息。
    """
    try:
        url = "https://fd.api.iris.microsoft.com/v4/api/selection?&placement=88000820&bcnt=4&country=CN&locale=zh-CN&fmt=json"
        headers = {}
        spotlight_wallpaper = list()
        if user_agent:
            headers["User-Agent"] = user_agent
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:

                data = await response.json()
                data = data.get("batchrsp", {})
                if data and "items" in data and len(data["items"]) > 0:
                    for item in data["items"]:
                        item_tmp = json.loads(item["item"])["ad"]
                        spotlight_wallpaper.append({
                            "url" : item_tmp.get("landscapeImage", {}).get("asset", ""),
                            "title": item_tmp.get("title", ""),
                            "description": item_tmp.get("description", ""),
                            "copyright": item_tmp.get("copyright", ""),
                            "ctaUri": item_tmp.get("ctaUri", "").replace("microsoft-edge:", ""),
                        })
                    return spotlight_wallpaper
                logger.error("获取 Windows Spotlight 壁纸失败，返回数据格式不正确")
                return None
                

    except Exception as e:
        logger.error(f"获取 Windows Spotlight 壁纸失败: {e}")
        return None
                            

def set_wallpaper(path: str) -> None:
    """
    将指定图片设置为当前桌面壁纸。
    支持 Windows / macOS / Linux 常见桌面环境。
    """
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    system = platform.system()

    # ---------- Windows ----------
    if system == "Windows":
        import ctypes
        import winreg as reg

        ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)

        key = reg.OpenKey(
            reg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, reg.KEY_SET_VALUE
        )
        reg.SetValueEx(key, "Wallpaper", 0, reg.REG_SZ, path)
        reg.CloseKey(key)
        return

    # ---------- macOS ----------
    if system == "Darwin":
        script = f"""
        tell application "System Events"
            tell every desktop
                set picture to "{path}"
            end tell
        end tell
        """
        subprocess.run(["osascript", "-e", script], check=True)
        return

    # ---------- Linux ----------
    if system != "Linux":
        raise OSError("Unsupported operating system")

    # 常见桌面环境探测
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session = os.environ.get("DESKTOP_SESSION", "").lower()

    # GNOME / Unity / Budgie
    if {"gnome", "unity", "budgie"} & {de, session}:
        uri = Path(path).as_uri()
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
            check=True,
        )
        return

    # MATE
    if "mate" in de:
        uri = Path(path).as_uri()
        subprocess.run(
            ["gsettings", "set", "org.mate.background", "picture-filename", path],
            check=True,
        )
        return

    # Cinnamon
    if "cinnamon" in de:
        uri = Path(path).as_uri()
        subprocess.run(
            ["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri],
            check=True,
        )
        return

    # XFCE：对所有监视器设置
    if "xfce" in de or "xfce" in session:
        # 获取所有背景通道
        result = subprocess.run(
            ["xfconf-query", "-c", "xfce4-desktop", "-p", "/backdrop", "-l"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if "image-path" in line or "last-image" in line:
                subprocess.run(
                    ["xfconf-query", "-c", "xfce4-desktop", "-p", line, "-s", path],
                    check=False,
                )
        return

    # KDE Plasma 5/6
    if "kde" in de or "plasma" in de:
        script = f"""
        var allDesktops = desktops();
        for (i=0;i<allDesktops.length;i++) {{
            d = allDesktops[i];
            d.wallpaperPlugin = "org.kde.image";
            d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");
            d.writeConfig("Image", "file://{path}");
        }}
        """
        subprocess.run(
            [
                "qdbus",
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                script,
            ],
            check=True,
        )
        return

    # Deepin
    if "deepin" in de:
        subprocess.run(
            [
                "gsettings",
                "set",
                "com.deepin.wrap.gnome.desktop.background",
                "picture-uri",
                Path(path).as_uri(),
            ],
            check=True,
        )
        return

    # LXDE/LXQt
    if {"lxde", "lxqt"} & {de, session}:
        subprocess.run(["pcmanfm", "--set-wallpaper", path], check=False)
        return

    # 兜底：使用 feh / nitrogen
    if which("feh"):
        subprocess.run(["feh", "--bg-scale", path], check=True)
        return
    if which("nitrogen"):
        subprocess.run(["nitrogen", "--set-scaled", path], check=True)
        return

    raise OSError("无法识别当前 Linux 桌面环境或缺少设置工具")


def which(program: str) -> Optional[str]:
    """模拟 shutil.which 的简易实现，兼容旧版本 Python"""
    for d in os.environ["PATH"].split(os.pathsep):
        exe = os.path.join(d, program)
        if os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
    return None


# ---------- 魔数字典 ----------
SIGNATURE_MAP = {
    b"\x50\x4b\x03\x04": ".zip",
    b"\x1f\x8b\x08": ".gz",
    b"\x52\x61\x72\x21\x1a\x07\x00": ".rar",
    b"\x25\x50\x44\x46": ".pdf",
    b"\xff\xd8\xff": ".jpg",
    b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a": ".png",
    b"\x47\x49\x46\x38": ".gif",
    b"\x49\x49\x2a\x00": ".tif",
    b"\x4d\x4d\x00\x2a": ".tif",
    b"\x66\x74\x79\x70": ".mp4",
    b"\x00\x00\x00\x20\x66\x74\x79\x70": ".mp4",
    b"\x1a\x45\xdf\xa3": ".mkv",
    b"\x52\x49\x46\x46": ".avi",
}


def _guess_ext_by_signature(head: bytes) -> Optional[str]:
    for sig, ext in SIGNATURE_MAP.items():
        if head.startswith(sig):
            return ext
    return None


def _is_office_zip(head: bytes) -> Optional[str]:
    try:
        import zipfile

        z = zipfile.ZipFile(io.BytesIO(head + b"..."))
        if "[Content_Types].xml" in z.namelist():
            if "word/document.xml" in z.namelist():
                return ".docx"
            if "xl/workbook.xml" in z.namelist():
                return ".xlsx"
            if "ppt/presentation.xml" in z.namelist():
                return ".pptx"
    except Exception:
        pass
    return None


# ---------- 反向 MIME 表 ----------
def _build_reverse_mime_map() -> Dict[str, str]:
    try:
        import requests

        txt = requests.get(
            "https://raw.githubusercontent.com/nginx/nginx/master/conf/mime.types",
            timeout=5,
        ).text
    except Exception:
        return {}
    m = {}
    for line in txt.splitlines():
        line = line.strip()
        if line.endswith(";") and len(line.split()) >= 2:
            parts = line.rstrip(";").split()
            mime, *exts = parts
            m[mime] = "." + exts[0]
    return m


_REVERSE_MIME_MAP: Optional[Dict[str, str]] = None


def _reverse_mime(mime: str) -> Optional[str]:
    global _REVERSE_MIME_MAP
    if _REVERSE_MIME_MAP is None:
        _REVERSE_MIME_MAP = _build_reverse_mime_map()
    return _REVERSE_MIME_MAP.get(mime)


# ---------- 服务器侧推断 ----------
def _infer_ext_from_server(resp_headers: Dict[str, str], url: str) -> Optional[str]:
    # 1) Content-Disposition
    cd = resp_headers.get("content-disposition", "")
    match = re.findall(r'filename\*?=(?:[^\'"]*\'\'|["\']?)([^"\';]+)', cd, re.I)
    if match:
        filename = unquote(match[-1].strip())
        ext = Path(filename).suffix.lower()
        if ext:
            return ext

    # 2) Content-Type
    ct = resp_headers.get("content-type", "").split(";")[0].strip().lower()
    if ct and ct != "application/octet-stream":
        ext = mimetypes.guess_extension(ct)
        if ext:
            return ext
        ext = _reverse_mime(ct)
        if ext:
            return ext

    # 3) URL 路径
    url_path = unquote(urlparse(url).path).lower()
    maybe_ext = Path(url_path).suffix
    if maybe_ext and re.fullmatch(r"\.\w{2,6}", maybe_ext):
        return maybe_ext

    return None


# ---------- 下载主函数 ----------
def download_file(
    url: str,
    save_path: str = "./temp",
    custom_filename: Optional[str] = None,
    timeout: int = 300,
    max_retries: int = 3,
    headers: Optional[Dict[str, str]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    resume: bool = False,
) -> Optional[str]:
    logger.debug(f"开始下载：{url}")

    req_headers = [
        "User-Agent: Mozilla/5.0",
        "Accept: */*",
        "Connection: keep-alive",
    ]
    if headers:
        for k, v in headers.items():
            req_headers.append(f"{k}: {v}")

    save_path = Path(save_path).expanduser().resolve()
    save_dir = save_path if save_path.is_dir() else save_path.parent
    save_dir.mkdir(parents=True, exist_ok=True)

    def _xferinfo(d_total: float, d_loaded: float, u_total: float, u_loaded: float):
        if progress_callback and d_total > 0:
            progress_callback(int(d_loaded), int(d_total))

    c = pycurl.Curl()
    try:
        for attempt in range(1, max_retries + 1):
            start_offset = 0
            tmp_path = save_dir / f"{uuid.uuid4().hex}.tmp"
            mode = "wb"

            if resume and attempt > 1:
                tmp_files = list(save_dir.glob("*.tmp"))
                if tmp_files:
                    tmp_path = tmp_files[0]
                    start_offset = tmp_path.stat().st_size
                    logger.debug("断点续传：从 {} 字节继续", start_offset)
                    mode = "ab"

            try:
                header_io = io.BytesIO()
                with open(tmp_path, mode) as f:
                    c.setopt(pycurl.URL, url)
                    c.setopt(pycurl.WRITEDATA, f)
                    if start_offset:
                        c.setopt(pycurl.RANGE, f"{start_offset}-")
                    c.setopt(pycurl.HEADERFUNCTION, header_io.write)
                    c.setopt(pycurl.FOLLOWLOCATION, 1)
                    c.setopt(pycurl.MAXREDIRS, 5)
                    c.setopt(pycurl.CONNECTTIMEOUT, timeout)
                    c.setopt(pycurl.TIMEOUT, timeout)
                    c.setopt(pycurl.HTTPHEADER, req_headers)
                    c.setopt(pycurl.NOPROGRESS, 0)
                    c.setopt(pycurl.XFERINFOFUNCTION, _xferinfo)
                    c.perform()

                http_code = c.getinfo(pycurl.HTTP_CODE)
                if start_offset > 0 and http_code != 206:
                    logger.warning("服务器不支持断点续传 HTTP {}，重新下载", http_code)
                    tmp_path.unlink(missing_ok=True)
                    continue
                if http_code >= 400:
                    raise pycurl.error(f"HTTP {http_code}")

                resp_headers = {}
                for line in header_io.getvalue().decode(errors="ignore").splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        resp_headers[k.strip().lower()] = v.strip()

                # ---------- 文件名 ----------
                filename = custom_filename
                if not filename:
                    cd = resp_headers.get("content-disposition", "")
                    match = re.findall(
                        r'filename\*?=(?:[^\'"]*\'\'|["\']?)([^"\';]+)', cd, re.I
                    )
                    if match:
                        filename = unquote(match[-1].strip())
                if not filename:
                    filename = unquote(os.path.basename(urlparse(url).path)) or None
                if not filename:
                    filename = hashlib.md5(url.encode()).hexdigest()

                # ---------- 扩展名 ----------
                ext = _infer_ext_from_server(resp_headers, url)

                if not ext or ext in {".bin", ".tmp"}:
                    with open(tmp_path, "rb") as fb:
                        head = fb.read(2048)
                    ext = _guess_ext_by_signature(head)

                if ext == ".zip":
                    ext = _is_office_zip(head) or ext

                if (not ext or ext in {".bin", ".tmp"}) and magic:
                    ext = mimetypes.guess_extension(magic.from_buffer(head, mime=True))

                if (not ext or ext in {".bin", ".tmp"}) and filetype:
                    ft = filetype.guess(head)
                    if ft:
                        ext = "." + ft.extension

                if custom_filename and "." in custom_filename:
                    pass
                elif ext and not filename.lower().endswith(ext.lower()):
                    filename = f"{Path(filename).stem}{ext}"

                target = save_path if save_path.is_file() else save_dir / filename
                shutil.move(str(tmp_path), str(target))
                logger.success("下载完成：{}", target)
                return str(target)

            except Exception as e:
                if isinstance(e, pycurl.error) and "HTTP 404" in str(e):
                    logger.error("资源不存在，放弃重试：{}", url)
                    return None
                logger.warning("第 {}/{} 次尝试失败：{}", attempt, max_retries, e)
                if attempt == max_retries:
                    logger.error("下载失败：{}", url)
                    return None
                time.sleep(2**attempt)
            finally:
                if attempt == max_retries and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
    finally:
        c.close()


if __name__ == "__main__":
    print(get_sys_wallpaper())

    def show_progress(current, total):
        percent = 100 * current // total if total else 0
        print(f"\r{percent:3d}%  {current}/{total}", end="", flush=True)

    download_file(
        url="https://dldir1v6.qq.com/weixin/Universal/Windows/WeChatWin.exe",
        progress_callback=show_progress,
        timeout=120,
    )
