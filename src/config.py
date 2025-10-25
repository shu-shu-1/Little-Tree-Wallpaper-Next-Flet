import orjson
import os
import toml

DEFAULT_CONFIG = {
    "metadata": {"version": "1.0.0"},
    "ui": {
        "language": "zh-CN",
        "theme": "system",
        "theme_profile": "default",
        "window_background": "",
        "window_icon": "./assets/icons/icon.ico",
    },
    "updates": {
        "auto_check": True,
        "channel": "stable",
        "proxy": {
            "enabled": False,
            "selected_index": 0,
            "mirrors": [
                "https://www.ghproxy.cn/",
                "https://gh.llkk.cc/",
                "https://gh-proxy.com/",
                "https://github.moeyy.xyz/",
            ],
        },
    },
    "storage": {
        "cache_directory": "./cache",
        "log_directory": "./log",
        "download_directory": "",
        "favorites_directory": "",
        "clear_cache_after_360_source": True,
    },
    "wallpaper": {
        "auto_change": {"mode": "random", "interval_seconds": 600},
        "allow_NSFW": False,
    },
    "download": {
        "segment_size_kb": 200,
        "proxy": {"enabled": False, "type": "http", "server": ""},
    },
    "startup": {
        "auto_start": False,
        "script": {"enabled": False, "path": ""},
        "wallpaper_change": {
            "enabled": False,
            "source": "bing",
            "auto_rotation": False,
        },
    },
    "home_page": {
        "hitokoto": {
            "API": "default",
            "type": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "k", "l"],
        },
    },
    "im": {
        # IntelliMarkets 图片源镜像优先级："default_first" | "mirror_first"
        "mirror_preference": "mirror_first",
    },
}


def get_config_version(file_path: str) -> str:
    """
    获取配置文件的版本号

    :param file_path: 配置文件的路径
    :return str: 版本号
    """
    with open(file_path, "rb") as f:
        config = orjson.loads(f.read())
    return config["metadata"]["version"]


def check_config_file(file_path):
    """
    检查指定的配置文件是否正常。
    1. 检查文件是否存在
    2. 检查文件格式是否正确
    3. 检查文件版本号
    4. 检查键是否完整


    :param file_path: 配置文件的路径
    :return ltwtype.ConfigState:
    文件正常返回"normal" | 版本号较低返回"low_version" | 较高返回"high_version" | 键缺失返回"key_missing" | 格式错误返回"format_error" | 文件不存在返回"file_not_exists"
    """
    if not os.path.exists(file_path):
        return "file_not_exists"
    try:
        with open(file_path, "rb") as f:
            config = orjson.loads(f.read())
    except orjson.JSONDecodeError:
        return "format_error"
    # 检查版本号
    if config["metadata"]["version"] != DEFAULT_CONFIG["metadata"]["version"]:
        return "low_version"
    # 检查键是否完整
    for key in DEFAULT_CONFIG.keys():
        if key not in config:
            return "key_missing"
    return "normal"


def fix_config_file(file_path: str, error_type):
    """
    修复配置文件

    :param file_path: 配置文件的路径
    :param error_type: 错误类型
    :return bool: 修复成功返回True
    """
    if error_type == "file_not_exists" or error_type == "key_missing":
        reset_config_file(file_path)
    elif error_type == "low_version":
        if get_config_version() == "1.0.0":
            ...  # 当配置文件版本更新时，再进行编写
    elif error_type == "format_error":
        try:
            with open(file_path, "rb") as f:
                old_config = toml.loads(f.read())
                new_config = DEFAULT_CONFIG
                # 迁移配置数据
                if "info" in old_config:
                    new_config["metadata"]["version"] = old_config["info"]["version"]

                if "display" in old_config:
                    new_config["ui"]["language"] = old_config["display"]["language"]
                    new_config["ui"]["theme"] = old_config["display"]["color_mode"]
                    new_config["ui"]["window_background"] = old_config["display"][
                        "window_background_image_path"
                    ]
                    new_config["ui"]["window_icon"] = old_config["display"][
                        "window_icon_path"
                    ]

                if "update" in old_config:
                    new_config["updates"]["auto_check"] = bool(
                        old_config["update"]["enabled"]
                    )
                    new_config["updates"]["channel"] = old_config["update"][
                        "channel"
                    ].lower()
                    if "proxy" in old_config["update"]:
                        new_config["updates"]["proxy"]["enabled"] = bool(
                            old_config["update"]["proxy"]["enabled"]
                        )
                        new_config["updates"]["proxy"]["selected_index"] = old_config[
                            "update"
                        ]["proxy"]["proxy_index"]
                        new_config["updates"]["proxy"]["mirrors"] = old_config[
                            "update"
                        ]["proxy"]["proxy_list"]

                if "data" in old_config:
                    new_config["storage"]["cache_directory"] = old_config["data"][
                        "cache_path"
                    ]
                    new_config["storage"]["log_directory"] = old_config["data"][
                        "log_path"
                    ]
                    new_config["storage"]["download_directory"] = old_config["data"][
                        "download_path"
                    ]
                    new_config["storage"]["favorites_directory"] = old_config["data"][
                        "favorites_path"
                    ]
                    new_config["storage"]["clear_cache_after_360_source"] = bool(
                        old_config["data"]["clear_cache_when_360_back"]
                    )

                if "automatic_wallpaper_change" in old_config:
                    new_config["wallpaper"]["auto_change"]["mode"] = old_config[
                        "automatic_wallpaper_change"
                    ]["mode"]
                    new_config["wallpaper"]["auto_change"]["interval_seconds"] = (
                        old_config["automatic_wallpaper_change"]["interval_time"]
                    )

                if "download" in old_config:
                    new_config["download"]["segment_size_kb"] = old_config["download"][
                        "segmented_download_size"
                    ]
                    if "proxy" in old_config["download"]:
                        new_config["download"]["proxy"]["enabled"] = bool(
                            old_config["download"]["proxy"]["enabled"]
                        )
                        new_config["download"]["proxy"]["type"] = old_config[
                            "download"
                        ]["proxy"]["mode"]
                        new_config["download"]["proxy"]["server"] = old_config[
                            "download"
                        ]["proxy"]["server"]

                if "auto_start" in old_config:
                    new_config["startup"]["auto_start"] = bool(
                        old_config["auto_start"]["enabled"]
                    )
                    new_config["startup"]["script"]["enabled"] = bool(
                        old_config["auto_start"]["script_enabled"]
                    )
                    new_config["startup"]["script"]["path"] = old_config["auto_start"][
                        "script_path"
                    ]
                    new_config["startup"]["wallpaper_change"]["enabled"] = bool(
                        old_config["auto_start"]["change_wallpaper_enabled"]
                    )
                    new_config["startup"]["wallpaper_change"]["source"] = old_config[
                        "auto_start"
                    ]["change_wallpaper_mode"]
                    new_config["startup"]["wallpaper_change"]["auto_rotation"] = bool(
                        old_config["auto_start"]["automatic_wallpaper_change"]
                    )

                save_config_file(file_path, new_config)
        except toml.TomlDecodeError:
            reset_config_file(file_path)


def reset_config_file(file_path: str) -> None:
    save_config_file(file_path, DEFAULT_CONFIG)


def save_config_file(file_path: str, config: dict) -> None:
    # 分离文件路径和扩展名
    file_path_without_ext, _ = os.path.splitext(file_path)
    # 强制使用 .json 扩展名
    json_file_path = file_path_without_ext + ".json"

    try:
        # 删除原文件，如果存在的话
        if os.path.exists(file_path):
            os.remove(file_path)

        # 删除同名的 JSON 文件，如果存在的话
        if os.path.exists(json_file_path) and json_file_path != file_path:
            os.remove(json_file_path)
    except Exception:
        pass
    with open(json_file_path, "wb") as f:
        f.write(orjson.dumps(config, option=orjson.OPT_INDENT_2))

def get_config_file(file_path: str) -> dict:
    base, _ = os.path.splitext(file_path)
    json_path = base + ".json"

    # Ensure directory exists
    dirpath = os.path.dirname(json_path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    status = "file_not_exists"
    if os.path.exists(json_path):
        status = check_config_file(json_path)

    if status == "normal":
        try:
            with open(json_path, "rb") as f:
                return orjson.loads(f.read())
        except orjson.JSONDecodeError:
            status = "format_error"

    if status in ("file_not_exists", "key_missing"):
        reset_config_file(file_path)
    elif status == "low_version":
        # Migration not implemented; fallback to reset
        reset_config_file(file_path)
    elif status == "format_error":
        try:
            fix_config_file(json_path, "format_error")
        except Exception:
            reset_config_file(file_path)

    try:
        with open(os.path.splitext(file_path)[0] + ".json", "rb") as f:
            return orjson.loads(f.read())
    except Exception:
        return DEFAULT_CONFIG