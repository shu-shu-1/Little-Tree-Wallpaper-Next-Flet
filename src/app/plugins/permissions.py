"""Definitions for plugin permission policies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class PermissionState(str, Enum):
    """Tri-state decision recorded for a plugin permission."""

    GRANTED = "granted"
    DENIED = "denied"
    PROMPT = "prompt"


@dataclass(slots=True, frozen=True)
class PluginPermission:
    """Declarative information about a plugin capability request."""

    identifier: str
    name: str
    description: str


KNOWN_PERMISSIONS: dict[str, PluginPermission] = {
    "filesystem": PluginPermission(
        identifier="filesystem",
        name="文件访问",
        description="允许插件读写应用的数据目录之外的文件。",
    ),
    "network": PluginPermission(
        identifier="network",
        name="网络访问",
        description="允许插件发起网络请求（除内置壁纸接口之外）。",
    ),
    "clipboard": PluginPermission(
        identifier="clipboard",
        name="剪贴板",
        description="允许插件读取或写入系统剪贴板。",
    ),
    "wallpaper": PluginPermission(
        identifier="wallpaper",
        name="壁纸控制",
        description="允许插件设置或删除系统壁纸。",
    ),
    "resource_data": PluginPermission(
        identifier="resource_data",
        name="资源数据访问",
        description="允许插件接收资源页提供的图片标题、描述以及下载链接等数据。",
    ),
    "python_import": PluginPermission(
        identifier="python_import",
        name="动态库导入",
        description="允许插件在运行时加载额外的 Python 模块或附带的依赖。",
    ),
    "app_route": PluginPermission(
        identifier="app_route",
        name="打开应用内部路由",
        description="允许插件请求跳转到小树壁纸的任意已注册页面。",
    ),
    "app_home": PluginPermission(
        identifier="app_home",
        name="切换首页导航",
        description="允许插件切换小树壁纸首页侧栏中的目标页面。",
    ),
    "app_settings": PluginPermission(
        identifier="app_settings",
        name="打开设置标签页",
        description="允许插件切换到设置页并定位到指定的标签。",
    ),
    "wallpaper_control": PluginPermission(
        identifier="wallpaper_control",
        name="壁纸操作调用",
        description="允许插件直接触发将壁纸设置为 Bing 或 Windows 聚焦资源。",
    ),
    "ipc_broadcast": PluginPermission(
        identifier="ipc_broadcast",
        name="跨进程广播",
        description="允许插件通过内置 IPC 服务订阅、发送跨进程广播消息。",
    ),
}


_STATE_ALIASES: Dict[str, PermissionState] = {
    PermissionState.GRANTED.value: PermissionState.GRANTED,
    PermissionState.DENIED.value: PermissionState.DENIED,
    PermissionState.PROMPT.value: PermissionState.PROMPT,
    "allow": PermissionState.GRANTED,
    "deny": PermissionState.DENIED,
    "unconfirmed": PermissionState.PROMPT,
    "pending": PermissionState.PROMPT,
}


def normalize_permission_state(value: Any) -> PermissionState:
    """Convert assorted persisted representations into a :class:`PermissionState`."""

    if isinstance(value, PermissionState):
        return value
    if isinstance(value, bool):
        return PermissionState.GRANTED if value else PermissionState.DENIED
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _STATE_ALIASES:
            return _STATE_ALIASES[lowered]
    return PermissionState.PROMPT


def ensure_permission_states(
    requested: tuple[str, ...], existing: dict[str, Any] | None = None
) -> dict[str, PermissionState]:
    """Ensure all declared permissions have an explicit stored state."""

    result: dict[str, PermissionState] = {}
    if existing:
        for key, value in existing.items():
            result[key] = normalize_permission_state(value)
    for permission in requested:
        result.setdefault(permission, PermissionState.PROMPT)
    return result


__all__ = [
    "PluginPermission",
    "PermissionState",
    "KNOWN_PERMISSIONS",
    "normalize_permission_state",
    "ensure_permission_states",
]
