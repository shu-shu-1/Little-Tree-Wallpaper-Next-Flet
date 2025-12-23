# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Little Tree Studio <studio@zsxiaoshu.cn>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
商店资源获取和管理服务
"""

from __future__ import annotations

import asyncio
from typing import Literal

import aiohttp
import rtoml
from loguru import logger

from .models import (
    PluginMetadata,
    ResourceAsset,
    ResourceAuthor,
    ResourceMetadata,
    ThemeMetadata,
)


class StoreServiceError(Exception):
    """商店服务异常基类"""
    pass


class StoreService:
    """商店服务：负责从远程源获取资源列表和元数据"""
    
    # 默认官方源
    DEFAULT_BASE_URL = "https://wallpaper.api.zsxiaoshu.cn"
    
    def __init__(self, base_url: str | None = None):
        """
        初始化商店服务
        
        Args:
            base_url: 资源服务器基础URL，默认使用官方源
        """
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self._session: aiohttp.ClientSession | None = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def _fetch_json(self, url: str) -> list[str]:
        """获取JSON数据"""
        session = await self._get_session()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.error(f"获取 {url} 失败: {e}")
            raise StoreServiceError(f"获取资源列表失败: {e}") from e
    
    async def _fetch_toml(self, url: str) -> dict:
        """获取TOML数据"""
        session = await self._get_session()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                content = await response.text()
                return rtoml.loads(content)
        except Exception as e:
            logger.error(f"获取 {url} 失败: {e}")
            raise StoreServiceError(f"获取资源元数据失败: {e}") from e
    
    async def list_resources(
        self, 
        resource_type: Literal["theme", "resources", "plugins"]
    ) -> list[str]:
        """
        获取资源列表
        
        Args:
            resource_type: 资源类型（theme/resources/plugins）
            
        Returns:
            文件名列表
        """
        url = f"{self.base_url}/{resource_type}/index.json"
        return await self._fetch_json(url)
    
    def _parse_author(self, data: dict) -> ResourceAuthor | None:
        """解析作者信息"""
        author_data = data.get("author")
        if not author_data or not isinstance(author_data, dict):
            return None
        
        return ResourceAuthor(
            name=author_data.get("name", ""),
            email=author_data.get("email"),
            url=author_data.get("url"),
            links=author_data.get("links", {}),
        )
    
    def _parse_assets(self, data: dict) -> list[ResourceAsset]:
        """解析资产列表"""
        assets_data = data.get("assets", [])
        if not isinstance(assets_data, list):
            return []
        
        assets = []
        for asset_data in assets_data:
            if not isinstance(asset_data, dict):
                continue
            assets.append(ResourceAsset(
                name=asset_data.get("name", ""),
                path=asset_data.get("path"),
                url=asset_data.get("url"),
                sha256=asset_data.get("sha256"),
                size_bytes=asset_data.get("size_bytes"),
            ))
        return assets
    
    def _parse_plugin_metadata(self, data: dict) -> PluginMetadata | None:
        """解析插件特定元数据"""
        plugin_data = data.get("plugin")
        if not plugin_data or not isinstance(plugin_data, dict):
            return None
        
        return PluginMetadata(
            min_client_version=plugin_data.get("min_client_version"),
            max_client_version=plugin_data.get("max_client_version"),
            api_version=plugin_data.get("api_version"),
            entry=plugin_data.get("entry"),
            dependencies=plugin_data.get("dependencies", []),
        )
    
    def _parse_theme_metadata(self, data: dict) -> ThemeMetadata | None:
        """解析主题特定元数据"""
        theme_data = data.get("theme")
        if not theme_data or not isinstance(theme_data, dict):
            return None
        
        return ThemeMetadata(
            preview_url=theme_data.get("preview_url"),
        )
    
    def _parse_resource_metadata(self, data: dict) -> ResourceMetadata:
        """解析资源元数据"""
        return ResourceMetadata(
            type=data.get("type", "plugin"),
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "0.0.0"),
            summary=data.get("summary", ""),
            description_md=data.get("description_md", ""),
            protocol_version=data.get("protocol_version"),
            icon_url=data.get("icon_url"),
            icon_path=data.get("icon_path"),
            icon_data_uri=data.get("icon_data_uri"),
            icon_base64=data.get("icon_base64"),
            icon_mime=data.get("icon_mime"),
            download_url=data.get("download_url"),
            download_path=data.get("download_path"),
            assets=self._parse_assets(data),
            homepage_url=data.get("homepage_url"),
            repository_url=data.get("repository_url"),
            license=data.get("license"),
            author=self._parse_author(data),
            tags=data.get("tags", []),
            changelog_url=data.get("changelog_url"),
            plugin=self._parse_plugin_metadata(data),
            theme=self._parse_theme_metadata(data),
        )
    
    async def get_resource_metadata(
        self, 
        resource_type: Literal["theme", "resources", "plugins"],
        filename: str
    ) -> ResourceMetadata:
        """
        获取资源元数据
        
        Args:
            resource_type: 资源类型
            filename: 文件名
            
        Returns:
            资源元数据对象
        """
        url = f"{self.base_url}/{resource_type}/{filename}"
        data = await self._fetch_toml(url)
        return self._parse_resource_metadata(data)
    
    async def get_all_resources(
        self,
        resource_type: Literal["theme", "resources", "plugins"]
    ) -> list[ResourceMetadata]:
        """
        获取所有资源的元数据
        
        Args:
            resource_type: 资源类型
            
        Returns:
            资源元数据列表
        """
        filenames = await self.list_resources(resource_type)
        
        # 并发获取所有元数据
        tasks = [
            self.get_resource_metadata(resource_type, filename)
            for filename in filenames
        ]
        
        results = []
        for task in asyncio.as_completed(tasks):
            try:
                metadata = await task
                results.append(metadata)
            except Exception as e:
                logger.error(f"获取资源元数据失败: {e}")
                # 继续处理其他资源
        
        return results
    
    def resolve_icon_url(self, metadata: ResourceMetadata) -> str | None:
        """
        解析图标URL（将相对路径转换为完整URL）
        
        Args:
            metadata: 资源元数据
            
        Returns:
            完整的图标URL或None
        """
        if metadata.icon_data_uri:
            return metadata.icon_data_uri
        
        if metadata.icon_path:
            # 将相对路径转换为完整URL
            # icon_path 格式如 "src/icons/xxx.png"
            return f"{self.base_url}/{metadata.icon_path}"
        
        if metadata.icon_url:
            return metadata.icon_url
        
        if metadata.icon_base64 and metadata.icon_mime:
            return f"data:{metadata.icon_mime};base64,{metadata.icon_base64}"
        
        return None
    
    def resolve_download_url(self, metadata: ResourceMetadata) -> str | None:
        """
        解析下载URL（将相对路径转换为完整URL）
        
        Args:
            metadata: 资源元数据
            
        Returns:
            完整的下载URL或None
        """
        source, source_type = metadata.get_download_source()
        
        if source_type == "path" and source:
            # 将相对路径转换为完整URL
            return f"{self.base_url}/{source}"
        
        if source_type == "url" and source:
            return source
        
        return None
