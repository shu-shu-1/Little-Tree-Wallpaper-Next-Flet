import os
import sys

if os.name == "nt":
    import winreg


def get_sys_wallpaper():
    if os.name == "nt":
        # Windows
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
        wallpaper_path, _ = winreg.QueryValueEx(reg_key, "WallPaper")
        winreg.CloseKey(reg_key)
        return wallpaper_path

    elif sys.platform == "darwin":
        # macOS
        try:
            import subprocess

            script = """/usr/bin/osascript -e 'tell application "System Events" to get picture of current desktop'"""
            result = subprocess.check_output(script, shell=True)
            return result.decode("utf-8").strip()
        except Exception:
            return None

    elif sys.platform.startswith("linux"):
        # Linux: 常见桌面环境
        try:
            import subprocess

            # GNOME
            try:
                result = subprocess.check_output(
                    ["gsettings", "get", "org.gnome.desktop.background", "picture-uri"]
                )
                return result.decode("utf-8").strip().strip("'").replace("file://", "")
            except Exception:
                pass
            # KDE Plasma
            try:
                # 读取配置文件
                kde_conf = os.path.expanduser(
                    "~/.config/plasma-org.kde.plasma.desktop-appletsrc"
                )
                if os.path.exists(kde_conf):
                    with open(kde_conf, encoding="utf-8") as f:
                        for line in f:
                            if "Image=" in line:
                                return (
                                    line.split("=", 1)[1].strip().replace("file://", "")
                                )
            except Exception:
                pass
            # XFCE
            try:
                result = subprocess.check_output(
                    [
                        "xfconf-query",
                        "--channel",
                        "xfce4-desktop",
                        "--property",
                        "/backdrop/screen0/monitor0/image-path",
                    ]
                )
                return result.decode("utf-8").strip()
            except Exception:
                pass
        except Exception:
            return None
    return None


if __name__ == "__main__":
    print(get_sys_wallpaper())
