# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Little Tree Studio <studio@zsxiaoshu.cn>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
商店资源元数据模型定义
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ResourceAuthor:
    """资源作者信息"""
    name: str
    email: str | None = None
    url: str | None = None
    links: dict[str, str] = field(default_factory=dict)


@dataclass
class ResourceAsset:
    """可下载资产条目"""
    name: str
    path: str | None = None
    url: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None


@dataclass
class PluginMetadata:
    """插件特有字段"""
    min_client_version: str | None = None
    max_client_version: str | None = None
    api_version: str | None = None
    entry: str | None = None
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ThemeMetadata:
    """主题特有字段"""
    preview_url: str | None = None


@dataclass
class ResourceMetadata:
    """资源元数据"""
    type: Literal["plugin", "theme", "wallpaper_source"]
    id: str
    name: str
    version: str
    summary: str
    description_md: str
    
    # 协议版本（仅壁纸源使用）
    protocol_version: int | None = None
    
    # 图标字段（四选一）
    icon_url: str | None = None
    icon_path: str | None = None
    icon_data_uri: str | None = None
    icon_base64: str | None = None
    icon_mime: str | None = None
    
    # 下载相关
    download_url: str | None = None
    download_path: str | None = None
    assets: list[ResourceAsset] = field(default_factory=list)
    
    # 元信息
    homepage_url: str | None = None
    repository_url: str | None = None
    license: str | None = None
    author: ResourceAuthor | None = None
    tags: list[str] = field(default_factory=list)
    changelog_url: str | None = None
    
    # 类型特定字段
    plugin: PluginMetadata | None = None
    theme: ThemeMetadata | None = None
    
    def get_icon(self) -> str | None:
        """获取图标URL（优先级：icon_data_uri > icon_path > icon_url > icon_base64+icon_mime）"""
        if self.icon_data_uri:
            return self.icon_data_uri
        if self.icon_path:
            # icon_path 是相对路径，需要从服务器基础URL获取
            return None  # 将在服务层处理
        if self.icon_url:
            return self.icon_url
        if self.icon_base64 and self.icon_mime:
            return f"data:{self.icon_mime};base64,{self.icon_base64}"
        return None
    
    def get_download_source(self) -> tuple[str | None, str]:
        """获取下载源（返回: (url_or_path, type)）"""
        if self.download_path:
            return (self.download_path, "path")
        if self.download_url:
            return (self.download_url, "url")
        if self.assets:
            # 使用第一个资产
            asset = self.assets[0]
            if asset.path:
                return (asset.path, "path")
            if asset.url:
                return (asset.url, "url")
        return (None, "none")
