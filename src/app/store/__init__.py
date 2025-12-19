# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Little Tree Studio <studio@zsxiaoshu.cn>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
商店模块：提供主题、壁纸源、插件的获取和管理功能
"""

from .models import (
    PluginMetadata,
    ResourceAsset,
    ResourceAuthor,
    ResourceMetadata,
    ThemeMetadata,
)
from .service import StoreService, StoreServiceError

__all__ = [
    "StoreService",
    "StoreServiceError",
    "ResourceMetadata",
    "ResourceAuthor",
    "ResourceAsset",
    "PluginMetadata",
    "ThemeMetadata",
]
