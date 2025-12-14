# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Little Tree Studio <studio@zsxiaoshu.cn>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                -++-                                                
                                               +%%%%#.                                              
                                              *%#%%%%#:                                             
                                             *%#%%%%%%#:                                            
                                           .*%#%%%%%%%%%:                                           
                                          .#%#%%%%%%%%%%%-                                          
                                         .#%#%%%%%%%%%%%%%-                                         
                                        :#%#%%%%%%%%%%%%%%%=                                        
                                       :#%#%%%%%%%%%%%%%%##*=                                       
                                      :##############%%%#****=                                      
                                     -##############%##*******=                                     
                                    -################**********+                                    
                                   =###############*************+                                   
                                  =##############****************+.                                 
                                 =#############*******************+.                                
                                +############*******************+===.                               
                               +###########*******************+==-===.                              
                              *##########*******************+=--===--=.                             
                            .*#########******************+==--==-------.                            
                           .*#######*******************+==-==-----------.                           
                          .*######******************+==-====-------------:                          
                         :*#*#*******************++==-===-----------------:                         
                        :**********************+=======--------------------:                        
                       :********************++========----------------------:                       
                      :*******************+===========-----------------------:                      
                     -*****************++=============------------------------:                     
                    :***************++===============---------------------------                    
                    .+***********++===================-------------------------:                    
                      .::::::::::::::::::::::.:------:........................                      
                                               ::::::.                                              
                                               ------:                                              
                                               ------.                                              
                                               ------.                                              
                                               ------:                                              
                                               ------:                                              
                                              .------:                                              
                                               :....:                                               

🌳 Little Tree Wallpaper Next Flet
Little Tree Studio
https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet

================================================================================

Module Name: [module_name]

Copyright (C) 2024 Little Tree Studio <studio@zsxiaoshu.cn>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Project Information:
    - Official Website: https://wp.zsxiaoshu.cn/
    - Repository: https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet
    - Issue Tracker: https://github.com/shu-shu-1/Little-Tree-Wallpaper-Next-Flet/issues

Module Description:
    Core page implementations for Little Tree Wallpaper Next.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import io
import json
import mimetypes
import os
import random
import re
import shutil
import tarfile
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace as dc_replace
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, quote, quote_plus, urlencode

import aiohttp
import flet as ft
import pyperclip
from loguru import logger

import ltwapi
from app.auto_change import (
    ORDER_RANDOM,
    ORDER_RANDOM_NO_REPEAT,
    ORDER_SEQUENTIAL,
    AutoChangeList,
    AutoChangeListEntry,
    AutoChangeListStore,
    AutoChangeService,
)
from app.conflicts import StartupConflict
from app.constants import (
    BUILD_VERSION,
    FIRST_RUN_MARKER_VERSION,
    HITOKOTO_API,
    HITOKOTO_CATEGORY_LABELS,
    SHOW_WATERMARK,
    VER,
    ZHAOYU_API_URL,
)
from app.download_manager import DownloadLocationType, download_manager
from app.favorites import (
    FavoriteFolder,
    FavoriteItem,
    FavoriteManager,
    FavoriteSource,
)
from app.first_run import update_marker
from app.image_optimizer import image_optimizer
from app.paths import CACHE_DIR, LICENSE_PATH
from app.plugins import (
    KNOWN_PERMISSIONS,
    AppRouteView,
    GlobalDataAccess,
    GlobalDataError,
    PermissionState,
    PluginImportResult,
    PluginKind,
    PluginOperationResult,
    PluginPermission,
    PluginRuntimeInfo,
    PluginService,
    PluginStatus,
)
from app.plugins.events import EventDefinition, PluginEventBus
from app.settings import SettingsStore
from app.sniff import SniffedImage, SniffService, SniffServiceError
from app.startup import StartupManager
from app.ui_utils import (
    build_watermark,
    copy_files_to_clipboard,
    copy_image_to_clipboard,
)
from app.wallpaper_sources import (
    WallpaperCategoryRef,
    WallpaperItem,
    WallpaperSourceError,
    WallpaperSourceFetchError,
    WallpaperSourceImportError,
    WallpaperSourceManager,
    WallpaperSourceRecord,
)
from app.source_parser import SourceSpec

app_config = SettingsStore()

_WS_DEFAULT_KEY = "__default__"


@dataclass(slots=True)
class _IMParameterControl:
    config: dict[str, Any]
    control: ft.Control
    display: ft.Control
    getter: Callable[[], Any]
    setter: Callable[[Any], None]
    key: str


@dataclass(slots=True)
class _WSParameterControl:
    option: Any
    control: ft.Control
    display: ft.Control
    getter: Callable[[], Any]
    setter: Callable[[Any], None]


if TYPE_CHECKING:
    from app.plugins import PluginOperationResult
    from app.plugins.base import PluginSettingsPage
    from app.theme import ThemeManager


class Pages:
    def __init__(
        self,
        page: ft.Page,
        bing_action_factories: list[Callable[[], ft.Control]] | None = None,
        spotlight_action_factories: list[Callable[[], ft.Control]] | None = None,
        settings_pages: list[PluginSettingsPage] | None = None,
        event_bus: PluginEventBus | None = None,
        plugin_service: PluginService | None = None,
        plugin_runtime: list[PluginRuntimeInfo] | None = None,
        known_permissions: dict[str, PluginPermission] | None = None,
        event_definitions: list[EventDefinition] | None = None,
        global_data: GlobalDataAccess | None = None,
        theme_manager: ThemeManager | None = None,
        theme_list_handler: Callable[[], PluginOperationResult] | None = None,
        theme_apply_handler: Callable[[str], PluginOperationResult] | None = None,
        theme_profiles: list[dict[str, Any]] | None = None,
        theme_lock_active: bool = False,
        theme_lock_reason: str | None = None,
        theme_lock_profile: str | None = None,
        first_run_required_version: int | None = None,
        first_run_pending: bool = False,
        first_run_next_route: str = "/",
    ):
        self.page = page
        self.event_bus = event_bus
        self.plugin_service = plugin_service
        self._plugin_runtime_cache: list[PluginRuntimeInfo] = list(plugin_runtime or [])
        self._known_permissions: dict[str, PluginPermission] = dict(
            known_permissions or {},
        )
        self._sync_known_permissions()
        # Flet Colors compatibility: some versions may not expose SURFACE_CONTAINER_LOW
        self._bgcolor_surface_low = getattr(
            ft.Colors, "SURFACE_CONTAINER_LOW", ft.Colors.SURFACE_CONTAINER_HIGHEST,
        )
        self._event_definitions: list[EventDefinition] = list(event_definitions or [])
        self._plugin_list_column: ft.Column | None = None
        self._plugin_file_picker: ft.FilePicker | None = None
        self._favorite_file_picker: ft.FilePicker | None = None
        self._theme_file_picker: ft.FilePicker | None = None
        self._home_export_picker: ft.FilePicker | None = None
        self._home_pending_export_source: Path | None = None
        self._home_change_button: ft.TextButton | None = None
        self.home_quote_text: ft.Text | None = None
        self.home_quote_loading: ft.ProgressRing | None = None
        self._home_source_dropdown: ft.Dropdown | None = None
        self._home_show_author_switch: ft.Switch | None = None
        self._home_show_source_switch: ft.Switch | None = None
        self._home_hitokoto_region_dropdown: ft.Dropdown | None = None
        self._home_hitokoto_category_checks: dict[str, ft.Checkbox] = {}
        self._home_hitokoto_section: ft.Container | None = None
        self._home_zhaoyu_section: ft.Container | None = None
        self._home_custom_section: ft.Container | None = None
        self._home_custom_entries: list[dict[str, str]] = []
        self._home_custom_entries_column: ft.GridView | None = None
        self._home_custom_import_picker: ft.FilePicker | None = None
        self._home_custom_export_picker: ft.FilePicker | None = None
        self.wallpaper_path = ltwapi.get_sys_wallpaper()
        self.bing_wallpaper = None
        self.bing_wallpaper_url = None
        self.bing_loading = True
        self.bing_error: str | None = None
        self.spotlight_loading = True
        self.spotlight_wallpaper_url = None
        self.spotlight_wallpaper = list()
        self.spotlight_current_index = 0
        self.spotlight_error: str | None = None

        self.bing_action_factories = (
            bing_action_factories if bing_action_factories is not None else []
        )
        self.spotlight_action_factories = (
            spotlight_action_factories if spotlight_action_factories is not None else []
        )
        self._settings_pages = settings_pages if settings_pages is not None else []
        self._settings_page_map: dict[str, PluginSettingsPage] = {}
        self._refresh_settings_registry()
        self._global_data = global_data
        self._bing_data_id: str | None = None
        self._bing_save_picker: ft.FilePicker | None = None
        self._spotlight_save_picker: ft.FilePicker | None = None
        self._spotlight_data_id: str | None = None
        self._settings_tabs = None
        self._settings_tab_indices: dict[str, int] = {}
        self._pending_settings_tab: str | None = None
        # reload banner removed: use no-op methods instead
        self._route_register: Callable[[AppRouteView], None] | None = None

        self._ensure_global_namespaces()

        self._favorite_manager = FavoriteManager()
        self._favorite_tabs: ft.Tabs | None = None
        self._favorite_selected_folder: str = "__all__"
        self._favorite_folder_dropdown: ft.Dropdown | None = None
        self._favorite_form_fields: dict[str, ft.Control] = {}
        self._favorite_edit_folder_button: ft.IconButton | None = None
        self._favorite_delete_folder_button: ft.IconButton | None = None
        self._favorite_localize_button: ft.IconButton | None = None
        self._favorite_export_button: ft.IconButton | None = None
        self._favorite_import_button: ft.IconButton | None = None
        self._favorite_localization_status_text: ft.Text | None = None
        self._favorite_localization_progress_bar: ft.ProgressBar | None = None
        self._favorite_localization_status_row: ft.Row | None = None
        self._favorite_localization_spinner: ft.ProgressRing | None = None
        self._favorite_localizing_items: set[str] = set()
        self._favorite_item_localize_controls: dict[
            str, tuple[ft.IconButton, ft.Control],
        ] = {}
        self._favorite_item_wallpaper_buttons: dict[str, ft.IconButton] = {}
        self._favorite_item_export_buttons: dict[str, ft.IconButton] = {}
        self._favorite_batch_total: int = 0
        self._favorite_batch_done: int = 0
        self._favorite_preview_cache: dict[str, tuple[float, str]] = {}
        self._favorite_add_local_button: ft.IconButton | None = None
        self._favorite_view_cache: ft.Control | None = None
        self._favorite_view_holder: ft.Container | None = None
        self._favorite_view_loading: bool = False
        self._favorite_loading_overlay: ft.Container | None = None
        self._favorite_tabs_container: ft.Container | None = None

        self._theme_manager = theme_manager
        self._theme_list_handler = theme_list_handler
        self._theme_apply_handler = theme_apply_handler
        self._theme_profiles: list[dict[str, Any]] = list(theme_profiles or [])
        self._theme_cards_wrap: ft.Row | None = None
        self._theme_detail_dialog: ft.AlertDialog | None = None
        self._theme_locked = bool(theme_lock_active)
        self._theme_lock_reason = (theme_lock_reason or "").strip()
        self._theme_lock_profile = theme_lock_profile
        try:
            self._first_run_required_version = (
                int(first_run_required_version)
                if first_run_required_version is not None
                else FIRST_RUN_MARKER_VERSION
            )
        except (TypeError, ValueError):
            logger.warning("首次运行标记版本无效，使用默认值。")
            self._first_run_required_version = FIRST_RUN_MARKER_VERSION
        self._first_run_pending = bool(first_run_pending)
        self._first_run_next_route = first_run_next_route or "/"
        self._test_warning_next_route: str = "/"
        self._conflict_next_route: str = "/"
        self._startup_conflicts: list[StartupConflict] = []

        self._generate_provider_dropdown: ft.Dropdown | None = None
        self._generate_seed_field: ft.TextField | None = None
        self._generate_width_field: ft.TextField | None = None
        self._generate_height_field: ft.TextField | None = None
        self._generate_enhance_switch: ft.Switch | None = None
        self._generate_prompt_field: ft.TextField | None = None
        self._generate_output_container: ft.Container | None = None
        self._generate_status_text: ft.Text | None = None
        self._generate_loading_indicator: ft.ProgressRing | None = None
        self._generate_last_file: Path | None = None
        self._generate_action_buttons: dict[str, ft.Control] = {}
        self._generate_save_picker: ft.FilePicker | None = None
        self._generate_pending_save_source: Path | None = None
        self._generate_last_prompt: str | None = None
        self._generate_last_seed: str | None = None
        self._generate_last_width: int | None = None
        self._generate_last_height: int | None = None
        self._generate_last_request_url: str | None = None
        self._generate_last_provider: str | None = None
        self._generate_last_model: str | None = None
        self._generate_last_enhance: bool = False
        self._generate_last_allow_nsfw: bool = False

        # Sniff page state
        self._sniff_service = SniffService()
        self._sniff_url_field: ft.TextField | None = None
        self._sniff_fetch_button: ft.FilledButton | None = None
        self._sniff_status_text: ft.Text | None = None
        self._sniff_progress: ft.ProgressRing | None = None
        self._sniff_grid: ft.GridView | None = None
        self._sniff_images: list[SniffedImage] = []
        self._sniff_selected_ids: set[str] = set()
        self._sniff_action_buttons: dict[str, ft.Control] = {}
        self._sniff_source_url: str | None = None
        self._sniff_save_picker: ft.FilePicker | None = None
        self._sniff_pending_save_ids: set[str] | None = None
        self._sniff_selection_text: ft.Text | None = None
        self._sniff_empty_placeholder: ft.Container | None = None
        self._sniff_image_index: dict[str, SniffedImage] = {}
        self._sniff_task_text: ft.Text | None = None
        self._sniff_task_bar: ft.ProgressBar | None = None
        self._sniff_task_container: ft.Column | None = None
        self._sniff_actions_busy: bool = False

        # IntelliMarkets source marketplace state
        self._im_sources_by_category: dict[str, list[dict[str, Any]]] = {}
        self._im_all_category_key: str = "__all__"
        self._im_all_category_label: str = "全部"
        self._im_total_sources: int = 0
        self._im_loading: bool = False
        self._im_error: str | None = None
        self._im_selected_category: str | None = None
        self._im_last_updated: float | None = None
        self._im_status_text: ft.Text | None = None
        self._im_loading_indicator: ft.ProgressRing | None = None
        self._im_category_dropdown: ft.Dropdown | None = None
        self._im_sources_list: ft.GridView | None = None
        self._im_search_field: ft.TextField | None = None
        self._im_search_text: str = ""
        self._im_refresh_button: ft.TextButton | None = None
        self._im_repo_owner = "IntelliMarkets"
        self._im_repo_name = "Wallpaper_API_Index"
        self._im_repo_branch = "main"
        self._im_mirror_pref_dropdown: ft.Dropdown | None = None
        self._im_source_dialog: ft.AlertDialog | None = None
        self._im_active_source: dict[str, Any] | None = None
        self._im_param_controls: list[_IMParameterControl] = []
        self._im_cached_inputs: dict[str, dict[str, Any]] = {}
        self._im_run_button: ft.Control | None = None
        self._im_result_container: ft.Column | None = None
        self._im_result_status_text: ft.Text | None = None
        self._im_result_spinner: ft.ProgressRing | None = None
        self._im_running: bool = False
        self._im_fetch_task: asyncio.Task | None = None
        self._im_notice_dismissed_key = "im.notice_dismissed"
        self._im_info_visible: bool = not bool(
            app_config.get(self._im_notice_dismissed_key, False),
        )
        self._im_info_card: ft.Control | None = None
        self._im_last_results: list[dict[str, Any]] = []

        self._wallpaper_source_manager = WallpaperSourceManager()
        self._ws_fetch_button: ft.FilledButton | None = None
        self._ws_reload_button: ft.OutlinedButton | None = None
        self._ws_search_field: ft.TextField | None = None
        self._ws_source_tabs: ft.Tabs | None = None
        self._ws_primary_tabs: ft.Tabs | None = None
        self._ws_secondary_tabs: ft.Tabs | None = None
        self._ws_tertiary_tabs: ft.Tabs | None = None
        self._ws_leaf_tabs: ft.Tabs | None = None
        self._ws_source_tabs_container: ft.Container | None = None
        self._ws_primary_container: ft.Container | None = None
        self._ws_secondary_container: ft.Container | None = None
        self._ws_tertiary_container: ft.Container | None = None
        self._ws_leaf_container: ft.Container | None = None
        self._ws_source_info_container: ft.Container | None = None
        self._ws_param_container: ft.Container | None = None
        self._ws_status_text: ft.Text | None = None
        self._ws_loading_indicator: ft.ProgressRing | None = None
        self._ws_result_list: ft.ListView | None = None
        self._ws_file_picker: ft.FilePicker | None = None
        self._ws_settings_list: ft.Column | None = None
        self._ws_settings_summary_text: ft.Text | None = None
        self._ws_active_source_id: str | None = (
            self._wallpaper_source_manager.active_source_identifier()
        )
        self._ws_active_primary_key: str | None = None
        self._ws_active_secondary_key: str | None = None
        self._ws_active_tertiary_key: str | None = None
        self._ws_active_leaf_index: int = 0
        self._ws_active_category_id: str | None = None
        self._ws_cached_results: dict[str, list[WallpaperItem]] = {}
        self._ws_item_index: dict[str, WallpaperItem] = {}
        self._ws_search_text: str = ""
        self._ws_hierarchy: dict[str, Any] = {}
        self._ws_logo_cache: dict[str, tuple[str, bool]] = {}
        self._ws_category_icon_cache: dict[str, tuple[str, bool]] = {}
        self._ws_merge_display: bool = bool(
            app_config.get("wallpaper.sources.merge_display", False),
        )
        self._ws_merge_mode_dropdown: ft.Dropdown | None = None
        self._ws_updating_ui: bool = False
        self._ws_param_controls: list[_WSParameterControl] = []
        self._ws_param_cache: dict[str, dict[str, Any]] = {}
        self._ws_fetch_in_progress: bool = False
        self._ws_preview_item: WallpaperItem | None = None
        self._ws_preview_item_id: str | None = None

        self._auto_list_store = AutoChangeListStore()
        self._auto_change_service = AutoChangeService(
            settings_store=app_config,
            list_store=self._auto_list_store,
            wallpaper_source_manager=self._wallpaper_source_manager,
            favorite_manager=self._favorite_manager,
        )
        self._auto_lists_column: ft.Column | None = None
        self._auto_lists_summary_text: ft.Text | None = None
        self._auto_list_picker: ft.FilePicker | None = None
        self._auto_list_picker_mode: str | None = None
        self._auto_list_pending_export_id: str | None = None
        self._auto_fixed_image_picker: ft.FilePicker | None = None
        self._auto_slideshow_file_picker: ft.FilePicker | None = None
        self._auto_slideshow_dir_picker: ft.FilePicker | None = None
        self._auto_change_config_cache: dict[str, Any] = {}
        self._auto_enable_switch: ft.Switch | None = None
        self._auto_mode_dropdown: ft.Dropdown | None = None
        self._auto_interval_section: ft.Container | None = None
        self._auto_schedule_section: ft.Container | None = None
        self._auto_slideshow_section: ft.Container | None = None
        self._auto_interval_value_field: ft.TextField | None = None
        self._auto_interval_unit_dropdown: ft.Dropdown | None = None
        self._auto_interval_order_dropdown: ft.Dropdown | None = None
        self._auto_interval_lists_wrap: ft.Column | None = None
        self._auto_interval_list_checks: dict[str, ft.Checkbox] = {}
        self._auto_interval_fixed_image_display: ft.Text | None = None
        self._auto_interval_select_button: ft.TextButton | None = None
        self._auto_interval_clear_button: ft.TextButton | None = None
        self._auto_schedule_entries_column: ft.Column | None = None
        self._auto_schedule_add_button: ft.TextButton | None = None
        self._auto_schedule_column: ft.Column | None = None
        self._auto_schedule_dialog: ft.AlertDialog | None = None
        self._auto_schedule_dialog_state: dict[str, Any] = {}
        self._auto_schedule_order_dropdown: ft.Dropdown | None = None
        self._auto_slideshow_interval_field: ft.TextField | None = None
        self._auto_slideshow_unit_dropdown: ft.Dropdown | None = None
        self._auto_slideshow_mode_dropdown: ft.Dropdown | None = None
        self._auto_slideshow_items_column: ft.Column | None = None
        self._auto_slideshow_items: list[dict[str, Any]] = []
        self._auto_slideshow_add_file_button: ft.TextButton | None = None
        self._auto_slideshow_add_folder_button: ft.TextButton | None = None
        self._auto_editor_dialog: ft.AlertDialog | None = None
        self._auto_editor_state: dict[str, Any] = {}
        self._auto_entry_dialog: ft.AlertDialog | None = None
        self._auto_entry_dialog_state: dict[str, Any] = {}
        self._auto_fixed_image_target: tuple[str, Any] | None = None
        self._auto_updating_auto_ui: bool = False
        self._startup_auto_switch: ft.Switch | None = None
        self._startup_auto_status_text: ft.Text | None = None
        self._startup_wallpaper_switch: ft.Switch | None = None
        self._startup_wallpaper_lists_column: ft.Column | None = None
        self._startup_wallpaper_list_checks: dict[str, ft.Checkbox] = {}
        self._startup_wallpaper_order_dropdown: ft.Dropdown | None = None
        self._startup_wallpaper_delay_field: ft.TextField | None = None
        self._startup_wallpaper_fixed_image_display: ft.Text | None = None
        self._startup_wallpaper_clear_button: ft.TextButton | None = None

        self.page.run_task(self._auto_change_service.ensure_running)
        self._load_auto_change_config()

        self.home = self._build_home()
        self.resource = self._build_resource()
        self.generate = self._build_generate()
        self.sniff = self._build_sniff()
        self.favorite = self._build_favorite()
        self.test = self._build_test()

        self._refresh_theme_profiles(initial=True)

        self.page.run_task(self._load_bing_wallpaper)
        self.page.run_task(self._load_spotlight_wallpaper)
        self.page.run_task(self._load_im_sources)

    # 模型列表加载已移除

    def _sync_known_permissions(self) -> None:
        self._known_permissions.update(KNOWN_PERMISSIONS)

    @property
    def favorite_manager(self) -> FavoriteManager:
        return self._favorite_manager

    @property
    def auto_change_service(self) -> AutoChangeService:
        return self._auto_change_service

    def _ensure_global_namespaces(self) -> None:
        if not self._global_data:
            return
        try:
            self._global_data.register_namespace(
                "resource.bing",
                description="Bing 每日壁纸元数据",
                permission="resource_data",
            )
            self._global_data.register_namespace(
                "resource.spotlight",
                description="Windows 聚焦壁纸列表",
                permission="resource_data",
            )
        except GlobalDataError as exc:
            logger.error(f"初始化全局数据命名空间失败: {exc}")

    # ------------------------------------------------------------------
    # auto-change helpers
    # ------------------------------------------------------------------
    def _load_auto_change_config(self) -> dict[str, Any]:
        data = app_config.get("wallpaper.auto_change", {}) or {}
        if not isinstance(data, dict):
            data = {}
        self._auto_change_config_cache = copy.deepcopy(data)
        return self._auto_change_config_cache

    def _auto_current_config(self) -> dict[str, Any]:
        if not self._auto_change_config_cache:
            self._load_auto_change_config()
        return self._auto_change_config_cache

    def _auto_commit_config(self, config: dict[str, Any]) -> None:
        app_config.set("wallpaper.auto_change", config)
        self._auto_change_config_cache = copy.deepcopy(config)
        self._auto_change_service.refresh()
        self._refresh_auto_change_controls()

    def _update_home_change_button_state(
        self,
        *,
        interval_enabled: bool,
        slideshow_enabled: bool,
    ) -> None:
        if self._home_change_button is None:
            return
        available = interval_enabled or slideshow_enabled
        tooltip = (
            "立即触发自动更换（仅限间隔与轮播模式）"
            if available
            else "仅在启用间隔或轮播模式时可用"
        )
        self._home_change_button.disabled = not available
        self._home_change_button.tooltip = tooltip
        if self._home_change_button.page is not None:
            self._home_change_button.update()

    def _refresh_auto_change_controls(self) -> None:
        config = self._auto_current_config()
        enabled = bool(config.get("enabled", False))
        mode = str(config.get("mode") or "off")
        interval_config = config.get("interval") or {}
        interval_unit = str(interval_config.get("unit") or "minutes")
        if interval_unit not in {"seconds", "minutes", "hours"}:
            interval_unit = "minutes"
        interval_value = interval_config.get("value", 30) or 30
        if not isinstance(interval_value, int):
            try:
                interval_value = int(interval_value)
            except Exception:
                interval_value = 30
        interval_order = str(interval_config.get("order") or "random")
        if interval_order == "shuffle":
            interval_order = "random"
        if interval_order not in {"random", "random_no_repeat", "sequential"}:
            interval_order = "random"
        fixed_path = interval_config.get("fixed_image") or ""
        schedule_config = config.get("schedule") or {}
        schedule_order = str(schedule_config.get("order") or "random")
        if schedule_order == "shuffle":
            schedule_order = "random"
        if schedule_order not in {"random", "random_no_repeat", "sequential"}:
            schedule_order = "random"
        slideshow_config = config.get("slideshow") or {}
        slideshow_unit = str(slideshow_config.get("unit") or "minutes")
        if slideshow_unit not in {"seconds", "minutes", "hours"}:
            slideshow_unit = "minutes"
        slideshow_value = slideshow_config.get("value", 5) or 5
        if not isinstance(slideshow_value, int):
            try:
                slideshow_value = int(slideshow_value)
            except Exception:
                slideshow_value = 5
        slideshow_mode = str(slideshow_config.get("order") or "sequential")
        if slideshow_mode == "shuffle":
            slideshow_mode = "random"
        if slideshow_mode not in {"sequential", "random", "random_no_repeat"}:
            slideshow_mode = "sequential"
        schedule_enabled = enabled and mode == "schedule"
        interval_enabled = enabled and mode == "interval"
        slideshow_enabled = enabled and mode == "slideshow"
        self._update_home_change_button_state(
            interval_enabled=interval_enabled,
            slideshow_enabled=slideshow_enabled,
        )
        self._auto_updating_auto_ui = True
        try:
            if self._auto_enable_switch is not None:
                self._auto_enable_switch.value = enabled
                if self._auto_enable_switch.page is not None:
                    self._auto_enable_switch.update()
            if self._auto_mode_dropdown is not None:
                target_mode = (
                    mode
                    if mode in {"off", "interval", "schedule", "slideshow"}
                    else "off"
                )
                self._auto_mode_dropdown.value = target_mode
                self._auto_mode_dropdown.disabled = not enabled
                if self._auto_mode_dropdown.page is not None:
                    self._auto_mode_dropdown.update()
            if self._auto_interval_value_field is not None:
                self._auto_interval_value_field.value = str(interval_value)
                self._auto_interval_value_field.error_text = None
                self._auto_interval_value_field.disabled = not interval_enabled
                if self._auto_interval_value_field.page is not None:
                    self._auto_interval_value_field.update()
            if self._auto_interval_unit_dropdown is not None:
                self._auto_interval_unit_dropdown.value = interval_unit
                self._auto_interval_unit_dropdown.disabled = not interval_enabled
                if self._auto_interval_unit_dropdown.page is not None:
                    self._auto_interval_unit_dropdown.update()
            if self._auto_interval_order_dropdown is not None:
                self._auto_interval_order_dropdown.value = interval_order
                self._auto_interval_order_dropdown.disabled = not interval_enabled
                if self._auto_interval_order_dropdown.page is not None:
                    self._auto_interval_order_dropdown.update()
            self._auto_refresh_interval_lists(enabled=interval_enabled)
            if self._auto_interval_fixed_image_display is not None:
                display_text = str(fixed_path) if fixed_path else "未选择"
                display_color = ft.Colors.ON_SURFACE if fixed_path else ft.Colors.GREY
                self._auto_interval_fixed_image_display.value = display_text
                self._auto_interval_fixed_image_display.color = display_color
                if self._auto_interval_fixed_image_display.page is not None:
                    self._auto_interval_fixed_image_display.update()
            if self._auto_interval_select_button is not None:
                self._auto_interval_select_button.disabled = not interval_enabled
                if self._auto_interval_select_button.page is not None:
                    self._auto_interval_select_button.update()
            if self._auto_interval_clear_button is not None:
                self._auto_interval_clear_button.disabled = not (
                    interval_enabled and bool(fixed_path)
                )
                if self._auto_interval_clear_button.page is not None:
                    self._auto_interval_clear_button.update()
            if self._auto_slideshow_interval_field is not None:
                self._auto_slideshow_interval_field.value = str(slideshow_value)
                self._auto_slideshow_interval_field.error_text = None
                self._auto_slideshow_interval_field.disabled = not slideshow_enabled
                if self._auto_slideshow_interval_field.page is not None:
                    self._auto_slideshow_interval_field.update()
            if self._auto_slideshow_unit_dropdown is not None:
                self._auto_slideshow_unit_dropdown.value = slideshow_unit
                self._auto_slideshow_unit_dropdown.disabled = not slideshow_enabled
                if self._auto_slideshow_unit_dropdown.page is not None:
                    self._auto_slideshow_unit_dropdown.update()
            if self._auto_slideshow_mode_dropdown is not None:
                self._auto_slideshow_mode_dropdown.value = slideshow_mode
                self._auto_slideshow_mode_dropdown.disabled = not slideshow_enabled
                if self._auto_slideshow_mode_dropdown.page is not None:
                    self._auto_slideshow_mode_dropdown.update()
            if self._auto_schedule_order_dropdown is not None:
                self._auto_schedule_order_dropdown.value = schedule_order
                self._auto_schedule_order_dropdown.disabled = not schedule_enabled
                if self._auto_schedule_order_dropdown.page is not None:
                    self._auto_schedule_order_dropdown.update()
            if self._auto_slideshow_add_file_button is not None:
                self._auto_slideshow_add_file_button.disabled = not slideshow_enabled
                if self._auto_slideshow_add_file_button.page is not None:
                    self._auto_slideshow_add_file_button.update()
            if self._auto_slideshow_add_folder_button is not None:
                self._auto_slideshow_add_folder_button.disabled = not slideshow_enabled
                if self._auto_slideshow_add_folder_button.page is not None:
                    self._auto_slideshow_add_folder_button.update()
        finally:
            self._auto_updating_auto_ui = False

        if self._auto_interval_section is not None:
            self._auto_interval_section.visible = mode == "interval"
            if self._auto_interval_section.page is not None:
                self._auto_interval_section.update()
        if self._auto_schedule_section is not None:
            self._auto_schedule_section.visible = mode == "schedule"
            if self._auto_schedule_section.page is not None:
                self._auto_schedule_section.update()
        if self._auto_slideshow_section is not None:
            self._auto_slideshow_section.visible = mode == "slideshow"
            if self._auto_slideshow_section.page is not None:
                self._auto_slideshow_section.update()

        self._auto_refresh_schedule_entries(enabled=schedule_enabled)
        self._auto_refresh_slideshow_items(enabled=slideshow_enabled)

    def _ensure_auto_list_picker(self) -> None:
        if self.page is None:
            return
        if self._auto_list_picker is None:
            self._auto_list_picker = ft.FilePicker(
                on_result=self._handle_auto_list_picker_result,
            )
        if self._auto_list_picker not in self.page.overlay:
            self.page.overlay.append(self._auto_list_picker)
            self.page.update()

    def _handle_auto_list_picker_result(self, event: ft.FilePickerResultEvent) -> None:
        mode = self._auto_list_picker_mode
        self._auto_list_picker_mode = None
        if not mode:
            return
        if mode == "import":
            if not event.files:
                return
            existing_ids = {auto_list.id for auto_list in self._auto_list_store.all()}
            imported_any = False
            for file in event.files:
                path = getattr(file, "path", None)
                if not path:
                    continue
                try:
                    lists = self._auto_list_store.import_file(Path(path))
                except Exception as exc:
                    logger.error("导入自动更换列表失败: {error}", error=str(exc))
                    self._show_snackbar(f"导入失败：{exc}", error=True)
                    continue
                for auto_list in lists:
                    while auto_list.id in existing_ids:
                        auto_list.id = uuid.uuid4().hex
                    existing_ids.add(auto_list.id)
                    self._auto_list_store.upsert(auto_list)
                    imported_any = True
            if imported_any:
                self._refresh_auto_lists_view()
                self._auto_change_service.refresh()
                self._show_snackbar("已导入自动更换列表。")
            return
        if mode == "export_all":
            if not event.path:
                return
            try:
                self._auto_list_store.export_all(Path(event.path))
                self._show_snackbar("已导出所有自动更换列表。")
            except Exception as exc:
                logger.error("导出自动更换列表失败: {error}", error=str(exc))
                self._show_snackbar(f"导出失败：{exc}", error=True)

    def _build_auto_change_settings_section(self) -> ft.Control:
        config = self._auto_current_config()
        enabled = bool(config.get("enabled", False))
        mode = str(config.get("mode") or "off")

        self._auto_enable_switch = ft.Switch(
            label="启用自动更换",
            value=enabled,
            on_change=self._auto_on_toggle_enabled,
        )
        mode_options = [
            ft.DropdownOption(key="off", text="关闭"),
            ft.DropdownOption(key="interval", text="间隔模式"),
            ft.DropdownOption(key="schedule", text="定时模式"),
            ft.DropdownOption(key="slideshow", text="轮播模式"),
        ]
        self._auto_mode_dropdown = ft.Dropdown(
            label="模式",
            value=mode if mode in {option.key for option in mode_options} else "off",
            options=mode_options,
            dense=True,
            on_change=self._auto_on_mode_change,
        )

        header_row = ft.Row(
            [self._auto_enable_switch, self._auto_mode_dropdown],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        interval_section = self._build_auto_interval_section()
        schedule_section = self._build_auto_schedule_section()
        slideshow_section = self._build_auto_slideshow_section()

        # settings_container = ft.Container(
        #     content=ft.Column(
        #         [
        #             ft.Text("自动更换", size=18, weight=ft.FontWeight.BOLD),
        #             header_row,
        #             interval_section,
        #             schedule_section,
        #             slideshow_section,
        #         ],
        #         spacing=16,
        #         tight=True,
        #     ),
        #     bgcolor=self._bgcolor_surface_low,
        #     border_radius=8,
        #     padding=16,
        # )
        settings_column = ft.Column(
            [
                ft.Text("自动更换", size=18, weight=ft.FontWeight.BOLD),
                header_row,
                interval_section,
                schedule_section,
                slideshow_section,
            ],
            spacing=16,
            tight=True,
        )

        lists_section = self._build_auto_change_lists_section()
        wrapper = ft.Column(
            [settings_column, lists_section],
            spacing=16,
            tight=True,
        )
        self._refresh_auto_change_controls()
        return wrapper

    def _build_auto_change_lists_section(self) -> ft.Control:
        self._ensure_auto_list_picker()
        header = ft.Row(
            [
                ft.Text("自动更换列表", size=18, weight=ft.FontWeight.BOLD),
                ft.Row(
                    [
                        ft.TextButton(
                            "新建列表",
                            icon=ft.Icons.ADD,
                            on_click=lambda _: self._auto_create_list(),
                        ),
                        ft.TextButton(
                            "导入",
                            icon=ft.Icons.UPLOAD_FILE,
                            on_click=lambda _: self._auto_open_list_import(),
                        ),
                        ft.TextButton(
                            "导出全部",
                            icon=ft.Icons.DOWNLOAD,
                            on_click=lambda _: self._auto_open_list_export_all(),
                        ),
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._auto_lists_summary_text = ft.Text("", size=12, color=ft.Colors.GREY)
        self._auto_lists_column = ft.Column(spacing=8, tight=True)
        container = ft.Container(
            content=self._auto_lists_column,
            bgcolor=self._bgcolor_surface_low,
            border_radius=8,
            padding=12,
        )
        description_text = ft.Text(
            "自动更换列表用于管理要轮换的壁纸条目，可混合本地文件、收藏夹和壁纸源，并在各模式下复用。",
            size=12,
            color=ft.Colors.GREY,
        )
        self._refresh_auto_lists_view()
        return ft.Column(
            [header, description_text, self._auto_lists_summary_text, container],
            spacing=12,
        )

    def _build_auto_interval_section(self) -> ft.Container:
        config = self._auto_current_config()
        interval_config = config.get("interval") or {}
        interval_title = ft.Text("间隔模式", size=16, weight=ft.FontWeight.BOLD)
        self._auto_interval_value_field = ft.TextField(
            label="间隔时长",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=self._auto_on_interval_value_change,
            on_submit=self._auto_on_interval_value_change,
            width=140,
        )
        unit_options = [
            ft.DropdownOption(key="minutes", text="分钟"),
            ft.DropdownOption(key="hours", text="小时"),
            ft.DropdownOption(key="seconds", text="秒"),
        ]
        self._auto_interval_unit_dropdown = ft.Dropdown(
            label="单位",
            options=unit_options,
            dense=True,
            width=140,
            on_change=self._auto_on_interval_unit_change,
        )
        interval_value_row = ft.Row(
            [self._auto_interval_value_field, self._auto_interval_unit_dropdown],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        order_options = [
            ft.DropdownOption(key="random", text="随机"),
            ft.DropdownOption(key="random_no_repeat", text="不重复随机"),
            ft.DropdownOption(key="sequential", text="顺序"),
        ]
        interval_order = str(interval_config.get("order") or "random")
        if interval_order == "shuffle":
            interval_order = "random"
        if interval_order not in {option.key for option in order_options}:
            interval_order = "random"
        self._auto_interval_order_dropdown = ft.Dropdown(
            label="列表顺序",
            value=interval_order,
            options=order_options,
            dense=True,
            width=200,
            on_change=self._auto_on_interval_order_change,
        )
        order_hint = ft.Text(
            "随机从列表中选择条目或按照顺序轮换。", size=12, color=ft.Colors.GREY,
        )
        order_section = ft.Column(
            [self._auto_interval_order_dropdown, order_hint],
            spacing=4,
            tight=True,
        )

        self._auto_interval_lists_wrap = ft.Column(spacing=4, tight=True)
        list_header = ft.Text("使用的自动更换列表", size=14, weight=ft.FontWeight.BOLD)
        list_wrapper = ft.Column(
            [list_header, self._auto_interval_lists_wrap],
            spacing=8,
            tight=True,
        )

        self._auto_interval_fixed_image_display = ft.Text(
            "未选择", size=12, color=ft.Colors.GREY,
        )
        self._auto_interval_select_button = ft.TextButton(
            "选择图片",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=lambda _: self._auto_open_fixed_image_picker("interval"),
        )
        self._auto_interval_clear_button = ft.TextButton(
            "清除",
            icon=ft.Icons.CLEAR,
            on_click=lambda _: self._auto_clear_interval_fixed_image(),
        )
        fixed_row = ft.Column(
            [
                ft.Text("固定图片（可选）", size=14, weight=ft.FontWeight.BOLD),
                ft.Row(
                    [
                        self._auto_interval_fixed_image_display,
                        self._auto_interval_select_button,
                        self._auto_interval_clear_button,
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=8,
            tight=True,
        )

        body = ft.Column(
            [
                interval_title,
                interval_value_row,
                order_section,
                list_wrapper,
                fixed_row,
            ],
            spacing=12,
            tight=True,
        )
        self._auto_interval_section = ft.Container(
            content=body,
            bgcolor=ft.Colors.SURFACE,
            border_radius=8,
            padding=12,
        )
        self._auto_refresh_interval_lists()
        return self._auto_interval_section

    def _build_auto_schedule_section(self) -> ft.Container:
        config = self._auto_current_config()
        schedule_config = config.get("schedule") or {}
        self._auto_schedule_entries_column = ft.Column(spacing=8, tight=True)
        self._auto_schedule_column = self._auto_schedule_entries_column
        self._auto_schedule_add_button = ft.TextButton(
            "添加时间段",
            icon=ft.Icons.ADD,
            on_click=lambda _: self._auto_open_schedule_entry_dialog(),
        )
        header_row = ft.Row(
            [
                ft.Text("定时模式", size=16, weight=ft.FontWeight.BOLD),
                self._auto_schedule_add_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        hint_text = ft.Text(
            "可按时间点执行自动更换，未选择列表则使用固定图片。",
            size=12,
            color=ft.Colors.GREY,
        )
        schedule_order_options = [
            ft.DropdownOption(key="random", text="随机"),
            ft.DropdownOption(key="random_no_repeat", text="不重复随机"),
            ft.DropdownOption(key="sequential", text="顺序"),
        ]
        schedule_order_value = str(schedule_config.get("order") or "random")
        if schedule_order_value == "shuffle":
            schedule_order_value = "random"
        if schedule_order_value not in {
            option.key for option in schedule_order_options
        }:
            schedule_order_value = "random"
        self._auto_schedule_order_dropdown = ft.Dropdown(
            label="列表顺序",
            value=schedule_order_value,
            options=schedule_order_options,
            dense=True,
            width=220,
            on_change=self._auto_on_schedule_order_change,
        )
        schedule_order_hint = ft.Text(
            "控制定时执行时从自动更换列表取图的方式。",
            size=12,
            color=ft.Colors.GREY,
        )
        order_section = ft.Column(
            [self._auto_schedule_order_dropdown, schedule_order_hint],
            spacing=4,
            tight=True,
        )
        body = ft.Column(
            [header_row, hint_text, order_section, self._auto_schedule_entries_column],
            spacing=12,
            tight=True,
        )
        self._auto_schedule_section = ft.Container(
            content=body,
            bgcolor=ft.Colors.SURFACE,
            border_radius=8,
            padding=12,
            visible=str(config.get("mode") or "off") == "schedule",
        )
        self._auto_refresh_schedule_entries()
        return self._auto_schedule_section

    def _build_auto_slideshow_section(self) -> ft.Container:
        config = self._auto_current_config()
        slideshow_config = config.get("slideshow") or {}
        self._auto_slideshow_interval_field = ft.TextField(
            label="间隔时长",
            value=str(slideshow_config.get("value", 5) or 5),
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=self._auto_on_slideshow_value_change,
            on_submit=self._auto_on_slideshow_value_change,
            width=140,
        )
        unit_options = [
            ft.DropdownOption(key="minutes", text="分钟"),
            ft.DropdownOption(key="hours", text="小时"),
            ft.DropdownOption(key="seconds", text="秒"),
        ]
        self._auto_slideshow_unit_dropdown = ft.Dropdown(
            label="单位",
            value=str(slideshow_config.get("unit") or "minutes"),
            options=unit_options,
            dense=True,
            width=140,
            on_change=self._auto_on_slideshow_unit_change,
        )
        interval_row = ft.Row(
            [self._auto_slideshow_interval_field, self._auto_slideshow_unit_dropdown],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        slideshow_order_options = [
            ft.DropdownOption(key="sequential", text="顺序"),
            ft.DropdownOption(key="random", text="随机"),
            ft.DropdownOption(key="random_no_repeat", text="不重复随机"),
        ]
        slideshow_order_value = str(slideshow_config.get("order") or "sequential")
        if slideshow_order_value == "shuffle":
            slideshow_order_value = "random"
        if slideshow_order_value not in {
            option.key for option in slideshow_order_options
        }:
            slideshow_order_value = "sequential"
        self._auto_slideshow_mode_dropdown = ft.Dropdown(
            label="播放顺序",
            value=slideshow_order_value,
            options=slideshow_order_options,
            dense=True,
            width=200,
            on_change=self._auto_on_slideshow_order_change,
        )
        slideshow_order_hint = ft.Text(
            "顺序播放或随机播放轮播素材。不重复随机会遍历全部素材后再重新洗牌。",
            size=12,
            color=ft.Colors.GREY,
        )
        order_section = ft.Column(
            [self._auto_slideshow_mode_dropdown, slideshow_order_hint],
            spacing=4,
            tight=True,
        )

        self._auto_slideshow_add_file_button = ft.TextButton(
            "添加图片",
            icon=ft.Icons.IMAGE,
            on_click=lambda _: self._auto_open_slideshow_file_picker(),
        )
        self._auto_slideshow_add_folder_button = ft.TextButton(
            "添加文件夹",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=lambda _: self._auto_open_slideshow_dir_picker(),
        )
        action_row = ft.Row(
            [
                self._auto_slideshow_add_file_button,
                self._auto_slideshow_add_folder_button,
            ],
            spacing=12,
        )

        self._auto_slideshow_items_column = ft.Column(spacing=8, tight=True)
        items_wrapper = ft.Column(
            [
                ft.Text("轮播素材", size=14, weight=ft.FontWeight.BOLD),
                self._auto_slideshow_items_column,
            ],
            spacing=8,
            tight=True,
        )

        hint_text = ft.Text(
            "支持手动选择图片或整个文件夹，按顺序轮播。",
            size=12,
            color=ft.Colors.GREY,
        )

        body = ft.Column(
            [
                ft.Text("轮播模式", size=16, weight=ft.FontWeight.BOLD),
                hint_text,
                interval_row,
                order_section,
                action_row,
                items_wrapper,
            ],
            spacing=12,
            tight=True,
        )
        self._auto_slideshow_section = ft.Container(
            content=body,
            bgcolor=ft.Colors.SURFACE,
            border_radius=8,
            padding=12,
            visible=str(config.get("mode") or "off") == "slideshow",
        )
        self._auto_refresh_slideshow_items()
        return self._auto_slideshow_section

    def _auto_refresh_schedule_entries(self, *, enabled: bool | None = None) -> None:
        if self._auto_schedule_entries_column is None:
            return
        config = self._auto_current_config()
        schedule = config.get("schedule") or {}
        raw_entries = schedule.get("entries") or []
        indexed_entries: list[tuple[int, dict[str, Any]]] = []
        for idx, item in enumerate(raw_entries):
            if isinstance(item, dict):
                indexed_entries.append((idx, dict(item)))
        indexed_entries.sort(key=lambda pair: str(pair[1].get("time") or "00:00"))
        list_map = {
            auto_list.id: auto_list.name for auto_list in self._auto_list_store.all()
        }
        enabled_state = (
            bool(enabled)
            if enabled is not None
            else bool(
                config.get("enabled", False)
                and str(config.get("mode") or "off") == "schedule",
            )
        )
        column = self._auto_schedule_entries_column
        column.controls.clear()
        if not indexed_entries:
            column.controls.append(
                ft.Text("尚未添加任何定时任务。", size=12, color=ft.Colors.GREY),
            )
        else:
            for config_index, entry in indexed_entries:
                column.controls.append(
                    self._auto_build_schedule_entry_card(
                        config_index, entry, list_map, enabled=enabled_state,
                    ),
                )
        if column.page is not None:
            column.update()
        if self._auto_schedule_add_button is not None:
            self._auto_schedule_add_button.disabled = not enabled_state
            if self._auto_schedule_add_button.page is not None:
                self._auto_schedule_add_button.update()

    def _auto_build_schedule_entry_card(
        self,
        config_index: int,
        entry: dict[str, Any],
        list_map: dict[str, str],
        *,
        enabled: bool,
    ) -> ft.Control:
        time_str = str(entry.get("time") or "00:00")
        list_ids = [str(item) for item in entry.get("list_ids", []) if item]
        if list_ids:
            list_names = [list_map.get(list_id, list_id) for list_id in list_ids]
            lists_summary = "，".join(list_names)
        else:
            lists_summary = "未选择列表，将使用固定图片"
        fixed_image = entry.get("fixed_image") or ""
        if fixed_image:
            fixed_label = (
                Path(fixed_image).name if Path(fixed_image).name else fixed_image
            )
            fixed_summary = f"固定图片：{fixed_label}"
        else:
            fixed_summary = "固定图片：未设置"
        info = ft.Column(
            [
                ft.Text(f"时间：{time_str}", size=14, weight=ft.FontWeight.BOLD),
                ft.Text(lists_summary, size=12, color=ft.Colors.GREY),
                ft.Text(fixed_summary, size=12, color=ft.Colors.GREY),
            ],
            spacing=4,
            tight=True,
        )
        actions = ft.Row(
            [
                ft.TextButton(
                    "编辑",
                    icon=ft.Icons.EDIT,
                    on_click=lambda _: self._auto_open_schedule_entry_dialog(
                        config_index,
                    ),
                    disabled=not enabled,
                ),
                ft.TextButton(
                    "删除",
                    icon=ft.Icons.DELETE,
                    on_click=lambda _: self._auto_delete_schedule_entry(config_index),
                    disabled=not enabled,
                ),
            ],
            spacing=8,
        )
        return ft.Card(
            content=ft.Container(
                ft.Row(
                    [info, actions],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.padding.symmetric(vertical=8, horizontal=12),
            ),
        )

    def _auto_open_schedule_entry_dialog(self, index: int | None = None) -> None:
        config = self._auto_current_config()
        schedule = config.get("schedule") or {}
        raw_entries = schedule.get("entries") or []
        existing = {}
        if index is not None and 0 <= index < len(raw_entries):
            raw_entry = raw_entries[index]
            if isinstance(raw_entry, dict):
                existing = dict(raw_entry)
        now_struct = time.localtime()
        default_time = f"{now_struct.tm_hour:02d}:{now_struct.tm_min:02d}"
        time_value = str(existing.get("time") or default_time)
        time_field = ft.TextField(label="时间 (HH:MM)", value=time_value, width=140)
        selected_ids = {str(item) for item in existing.get("list_ids", []) if item}
        list_checks: dict[str, ft.Checkbox] = {}
        list_controls: list[ft.Control] = []
        available_lists = self._auto_list_store.all()
        if not available_lists:
            list_controls.append(
                ft.Text(
                    "暂无自动更换列表，可在下方新建。", size=12, color=ft.Colors.GREY,
                ),
            )
        else:
            for auto_list in available_lists:
                checkbox = ft.Checkbox(
                    label=f"{auto_list.name}（{len(auto_list.entries)} 条目）",
                    value=auto_list.id in selected_ids,
                )
                list_checks[auto_list.id] = checkbox
                list_controls.append(checkbox)
        lists_column = ft.Column(list_controls, spacing=4, tight=True)

        fixed_image = existing.get("fixed_image") or None
        fixed_display = ft.Text(
            fixed_image if fixed_image else "未选择",
            size=12,
            color=ft.Colors.ON_SURFACE if fixed_image else ft.Colors.GREY,
        )
        clear_button = ft.TextButton(
            "清除",
            icon=ft.Icons.CLEAR,
            on_click=lambda _: self._auto_schedule_dialog_clear_fixed_image(),
            disabled=not fixed_image,
        )
        select_button = ft.TextButton(
            "选择图片",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=lambda _: self._auto_schedule_dialog_open_fixed_image_picker(),
        )
        fixed_row = ft.Row(
            [fixed_display, select_button, clear_button],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        dialog_content = ft.Column(
            [
                ft.Text(
                    "设定每天的执行时间（24 小时制）", size=12, color=ft.Colors.GREY,
                ),
                time_field,
                ft.Text("选择自动更换列表 (可多选)", size=12, color=ft.Colors.GREY),
                lists_column,
                ft.Text("固定图片 (可选)", size=12, color=ft.Colors.GREY),
                fixed_row,
            ],
            spacing=10,
            tight=True,
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑定时任务" if existing else "新增定时任务"),
            content=ft.Container(dialog_content, width=420),
            actions=[
                ft.TextButton(
                    "取消", on_click=lambda _: self._auto_schedule_dialog_cancel(),
                ),
                ft.FilledButton(
                    "保存", on_click=lambda _: self._auto_schedule_dialog_save(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._auto_schedule_dialog = dialog
        self._auto_schedule_dialog_state = {
            "index": index,
            "time_field": time_field,
            "list_checks": list_checks,
            "fixed_image": fixed_image,
            "fixed_display": fixed_display,
            "clear_button": clear_button,
        }
        self._open_dialog(dialog)

    def _auto_schedule_dialog_open_fixed_image_picker(self) -> None:
        if not self._auto_schedule_dialog_state:
            return
        self._ensure_auto_fixed_image_picker()
        if self._auto_fixed_image_picker is None:
            self._show_snackbar("无法打开文件选择器。", error=True)
            return
        self._auto_fixed_image_target = ("schedule_dialog", None)
        try:
            self._auto_fixed_image_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.IMAGE,
            )
        except Exception as exc:
            logger.error("打开文件选择器失败: {error}", error=str(exc))
            self._show_snackbar("无法打开文件选择器。", error=True)

    def _auto_schedule_dialog_set_fixed_image(self, path: str | None) -> None:
        if not self._auto_schedule_dialog_state:
            return
        fixed_image = path or None
        self._auto_schedule_dialog_state["fixed_image"] = fixed_image
        display: ft.Text = self._auto_schedule_dialog_state.get("fixed_display")  # type: ignore[assignment]
        clear_button: ft.TextButton = self._auto_schedule_dialog_state.get(
            "clear_button",
        )  # type: ignore[assignment]
        if display is not None:
            display.value = fixed_image if fixed_image else "未选择"
            display.color = ft.Colors.ON_SURFACE if fixed_image else ft.Colors.GREY
            if display.page is not None:
                display.update()
        if clear_button is not None:
            clear_button.disabled = not fixed_image
            if clear_button.page is not None:
                clear_button.update()

    def _auto_schedule_dialog_clear_fixed_image(self) -> None:
        self._auto_schedule_dialog_set_fixed_image(None)

    def _auto_schedule_dialog_save(self) -> None:
        state = self._auto_schedule_dialog_state
        if not state:
            self._auto_schedule_dialog_cancel()
            return
        time_field: ft.TextField = state.get("time_field")  # type: ignore[assignment]
        if time_field is None:
            self._auto_schedule_dialog_cancel()
            return
        raw_time = str(time_field.value or "").strip()
        normalized_time = self._auto_normalize_schedule_time(raw_time)
        if normalized_time is None:
            time_field.error_text = "请输入合法的 24 小时时间，如 08:30"
            if time_field.page is not None:
                time_field.update()
            return
        time_field.error_text = None
        if time_field.page is not None:
            time_field.update()
        list_checks: dict[str, ft.Checkbox] = state.get("list_checks", {})  # type: ignore[assignment]
        selected_ids = [
            list_id for list_id, checkbox in list_checks.items() if bool(checkbox.value)
        ]
        fixed_image = state.get("fixed_image") or None
        entry_data = {
            "time": normalized_time,
            "list_ids": selected_ids,
            "fixed_image": fixed_image,
        }
        config = copy.deepcopy(self._auto_current_config())
        schedule = dict(config.get("schedule") or {})
        entries = [
            dict(item) for item in schedule.get("entries", []) if isinstance(item, dict)
        ]
        index = state.get("index")
        if isinstance(index, int) and 0 <= index < len(entries):
            entries[index] = entry_data
        else:
            entries.append(entry_data)
        entries.sort(key=lambda item: str(item.get("time") or "00:00"))
        schedule["entries"] = entries
        config["schedule"] = schedule
        self._auto_schedule_dialog_state = {}
        self._close_dialog()
        self._auto_schedule_dialog = None
        self._auto_commit_config(config)
        self._show_snackbar("定时任务已保存。")

    def _auto_schedule_dialog_cancel(self) -> None:
        self._auto_schedule_dialog_state = {}
        if self._auto_schedule_dialog is not None:
            self._close_dialog()
            self._auto_schedule_dialog = None

    def _auto_normalize_schedule_time(self, value: str) -> str | None:
        if not value:
            return None
        parts = value.split(":", 1)
        if len(parts) != 2:
            return None
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError:
            return None
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"

    def _auto_delete_schedule_entry(self, index: int) -> None:
        config = copy.deepcopy(self._auto_current_config())
        schedule = dict(config.get("schedule") or {})
        entries = [
            dict(item) for item in schedule.get("entries", []) if isinstance(item, dict)
        ]
        if not (0 <= index < len(entries)):
            self._show_snackbar("未找到该定时任务。", error=True)
            return
        entries.pop(index)
        schedule["entries"] = entries
        config["schedule"] = schedule
        self._auto_commit_config(config)
        self._show_snackbar("已删除定时任务。")

    def _auto_on_schedule_order_change(self, event: ft.ControlEvent) -> None:
        if self._auto_updating_auto_ui:
            return
        value = str(getattr(event.control, "value", "") or "random")
        if value not in {"random", "random_no_repeat", "sequential"}:
            value = "random"
        config = copy.deepcopy(self._auto_current_config())
        schedule = dict(config.get("schedule") or {})
        current = str(schedule.get("order") or "random")
        if current == "shuffle":
            current = "random"
        if current == value:
            return
        schedule["order"] = value
        config["schedule"] = schedule
        self._auto_commit_config(config)

    def _auto_refresh_slideshow_items(self, *, enabled: bool | None = None) -> None:
        if self._auto_slideshow_items_column is None:
            return
        config = self._auto_current_config()
        slideshow = config.get("slideshow") or {}
        items = [
            dict(item) for item in slideshow.get("items", []) if isinstance(item, dict)
        ]
        self._auto_slideshow_items = items
        enabled_state = (
            bool(enabled)
            if enabled is not None
            else bool(
                config.get("enabled", False)
                and str(config.get("mode") or "off") == "slideshow",
            )
        )
        column = self._auto_slideshow_items_column
        column.controls.clear()
        if not items:
            column.controls.append(
                ft.Text("尚未添加任何轮播素材。", size=12, color=ft.Colors.GREY),
            )
        else:
            for item in items:
                column.controls.append(
                    self._auto_build_slideshow_item_row(item, enabled=enabled_state),
                )
        if column.page is not None:
            column.update()
        for button in (
            self._auto_slideshow_add_file_button,
            self._auto_slideshow_add_folder_button,
        ):
            if button is not None:
                button.disabled = not enabled_state
                if button.page is not None:
                    button.update()

    def _auto_build_slideshow_item_row(
        self, item: dict[str, Any], *, enabled: bool,
    ) -> ft.Control:
        item_id = str(item.get("id") or uuid.uuid4().hex)
        kind = str(item.get("kind") or "file")
        path = str(item.get("path") or "")
        icon = ft.Icons.IMAGE if kind == "file" else ft.Icons.FOLDER
        name = Path(path).name or path or "(空路径)"
        info_column = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(icon, size=16),
                        ft.Text(name, size=13, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(path, size=12, color=ft.Colors.GREY),
            ],
            spacing=2,
            tight=True,
        )
        remove_button = ft.IconButton(
            icon=ft.Icons.DELETE,
            tooltip="移除",
            on_click=lambda _: self._auto_remove_slideshow_item(item_id),
            disabled=not enabled,
        )
        return ft.Container(
            ft.Row(
                [info_column, remove_button],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=self._bgcolor_surface_low,
            border_radius=8,
            padding=ft.padding.symmetric(vertical=6, horizontal=10),
        )

    def _auto_open_slideshow_file_picker(self) -> None:
        self._ensure_auto_slideshow_file_picker()
        if self._auto_slideshow_file_picker is None:
            self._show_snackbar("无法打开文件选择器。", error=True)
            return
        try:
            self._auto_slideshow_file_picker.pick_files(
                allow_multiple=True,
                file_type=ft.FilePickerFileType.IMAGE,
            )
        except Exception as exc:
            logger.error("选择图片失败: {error}", error=str(exc))
            self._show_snackbar("无法选择图片。", error=True)

    def _auto_open_slideshow_dir_picker(self) -> None:
        self._ensure_auto_slideshow_dir_picker()
        if self._auto_slideshow_dir_picker is None:
            self._show_snackbar("无法打开文件选择器。", error=True)
            return
        try:
            self._auto_slideshow_dir_picker.get_directory_path()
        except Exception as exc:
            logger.error("选择文件夹失败: {error}", error=str(exc))
            self._show_snackbar("无法选择文件夹。", error=True)

    def _ensure_auto_slideshow_file_picker(self) -> None:
        if self.page is None:
            return
        if self._auto_slideshow_file_picker is None:
            self._auto_slideshow_file_picker = ft.FilePicker(
                on_result=self._handle_auto_slideshow_file_result,
            )
        if self._auto_slideshow_file_picker not in self.page.overlay:
            self.page.overlay.append(self._auto_slideshow_file_picker)
            self.page.update()

    def _ensure_auto_slideshow_dir_picker(self) -> None:
        if self.page is None:
            return
        if self._auto_slideshow_dir_picker is None:
            self._auto_slideshow_dir_picker = ft.FilePicker(
                on_result=self._handle_auto_slideshow_dir_result,
            )
        if self._auto_slideshow_dir_picker not in self.page.overlay:
            self.page.overlay.append(self._auto_slideshow_dir_picker)
            self.page.update()

    def _handle_auto_slideshow_file_result(
        self, event: ft.FilePickerResultEvent,
    ) -> None:
        if not event.files:
            return
        paths = [getattr(item, "path", None) for item in event.files]
        valid_paths = [path for path in paths if path]
        if not valid_paths:
            return
        self._auto_add_slideshow_items("file", valid_paths)

    def _handle_auto_slideshow_dir_result(
        self, event: ft.FilePickerResultEvent,
    ) -> None:
        path = getattr(event, "path", None) or getattr(event, "full_path", None)
        if not path:
            return
        self._auto_add_slideshow_items("folder", [path])

    def _auto_add_slideshow_items(self, kind: str, paths: Sequence[str]) -> None:
        if not paths:
            return
        config = copy.deepcopy(self._auto_current_config())
        slideshow = dict(config.get("slideshow") or {})
        items = [
            dict(item) for item in slideshow.get("items", []) if isinstance(item, dict)
        ]
        existing_paths = {item.get("path") for item in items}
        added = False
        for path in paths:
            if not path or path in existing_paths:
                continue
            items.append({"id": uuid.uuid4().hex, "kind": kind, "path": path})
            existing_paths.add(path)
            added = True
        if not added:
            self._show_snackbar("未添加新项目。")
            return
        slideshow["items"] = items
        config["slideshow"] = slideshow
        self._auto_commit_config(config)
        self._show_snackbar("已添加轮播素材。")

    def _auto_remove_slideshow_item(self, item_id: str) -> None:
        config = copy.deepcopy(self._auto_current_config())
        slideshow = dict(config.get("slideshow") or {})
        items = [
            dict(item) for item in slideshow.get("items", []) if isinstance(item, dict)
        ]
        new_items = [item for item in items if str(item.get("id")) != item_id]
        if len(new_items) == len(items):
            self._show_snackbar("未找到该项目。", error=True)
            return
        slideshow["items"] = new_items
        config["slideshow"] = slideshow
        self._auto_commit_config(config)
        self._show_snackbar("已移除轮播素材。")

    def _auto_on_slideshow_value_change(self, event: ft.ControlEvent) -> None:
        control: ft.TextField = event.control  # type: ignore[assignment]
        if control is None or self._auto_updating_auto_ui:
            return
        raw = str(control.value or "").strip()
        if not raw:
            control.error_text = "请输入数字"
            if control.page is not None:
                control.update()
            return
        try:
            value = int(raw)
        except ValueError:
            control.error_text = "请输入数字"
            if control.page is not None:
                control.update()
            return
        if value <= 0:
            control.error_text = "必须大于 0"
            if control.page is not None:
                control.update()
            return
        control.error_text = None
        if control.page is not None:
            control.update()
        config = copy.deepcopy(self._auto_current_config())
        slideshow = dict(config.get("slideshow") or {})
        slideshow["value"] = value
        config["slideshow"] = slideshow
        self._auto_commit_config(config)

    def _auto_on_slideshow_unit_change(self, event: ft.ControlEvent) -> None:
        if self._auto_updating_auto_ui:
            return
        value = str(getattr(event.control, "value", "") or "minutes")
        if value not in {"seconds", "minutes", "hours"}:
            value = "minutes"
        config = copy.deepcopy(self._auto_current_config())
        slideshow = dict(config.get("slideshow") or {})
        slideshow["unit"] = value
        config["slideshow"] = slideshow
        self._auto_commit_config(config)

    def _auto_on_slideshow_order_change(self, event: ft.ControlEvent) -> None:
        if self._auto_updating_auto_ui:
            return
        value = str(getattr(event.control, "value", "") or "sequential")
        if value not in {"sequential", "random", "random_no_repeat"}:
            value = "sequential"
        config = copy.deepcopy(self._auto_current_config())
        slideshow = dict(config.get("slideshow") or {})
        current = str(slideshow.get("order") or "sequential")
        if current == "shuffle":
            current = "random"
        if current == value:
            return
        slideshow["order"] = value
        config["slideshow"] = slideshow
        self._auto_commit_config(config)

    def _auto_on_toggle_enabled(self, event: ft.ControlEvent) -> None:
        if self._auto_updating_auto_ui:
            return
        new_value = bool(getattr(event.control, "value", False))
        config = copy.deepcopy(self._auto_current_config())
        config["enabled"] = new_value
        self._auto_commit_config(config)

    def _auto_on_mode_change(self, event: ft.ControlEvent) -> None:
        if self._auto_updating_auto_ui:
            return
        value = str(getattr(event.control, "value", "") or "off")
        if value not in {"off", "interval", "schedule", "slideshow"}:
            value = "off"
        config = copy.deepcopy(self._auto_current_config())
        config["mode"] = value
        self._auto_commit_config(config)

    def _auto_on_interval_value_change(self, event: ft.ControlEvent) -> None:
        control: ft.TextField = event.control  # type: ignore[assignment]
        if control is None:
            return
        if self._auto_updating_auto_ui:
            return
        raw = str(control.value or "").strip()
        if not raw:
            control.error_text = "请输入数字"
            if control.page is not None:
                control.update()
            return
        try:
            value = int(raw)
        except ValueError:
            control.error_text = "请输入数字"
            if control.page is not None:
                control.update()
            return
        if value <= 0:
            control.error_text = "必须大于 0"
            if control.page is not None:
                control.update()
            return
        control.error_text = None
        if control.page is not None:
            control.update()
        config = copy.deepcopy(self._auto_current_config())
        interval = dict(config.get("interval") or {})
        interval["value"] = value
        config["interval"] = interval
        self._auto_commit_config(config)

    def _auto_on_interval_unit_change(self, event: ft.ControlEvent) -> None:
        if self._auto_updating_auto_ui:
            return
        value = str(getattr(event.control, "value", "") or "minutes")
        if value not in {"seconds", "minutes", "hours"}:
            value = "minutes"
        config = copy.deepcopy(self._auto_current_config())
        interval = dict(config.get("interval") or {})
        interval["unit"] = value
        config["interval"] = interval
        self._auto_commit_config(config)

    def _auto_on_interval_order_change(self, event: ft.ControlEvent) -> None:
        if self._auto_updating_auto_ui:
            return
        value = str(getattr(event.control, "value", "") or "random")
        if value not in {"random", "random_no_repeat", "sequential"}:
            value = "random"
        config = copy.deepcopy(self._auto_current_config())
        interval = dict(config.get("interval") or {})
        current = str(interval.get("order") or "random")
        if current == "shuffle":
            current = "random"
        if current == value:
            return
        interval["order"] = value
        config["interval"] = interval
        self._auto_commit_config(config)

    def _auto_refresh_interval_lists(self, *, enabled: bool | None = None) -> None:
        if self._auto_interval_lists_wrap is None:
            return
        config = self._auto_current_config()
        selected_ids = set((config.get("interval") or {}).get("list_ids") or [])
        enabled_state = (
            bool(config.get("enabled", False)) if enabled is None else bool(enabled)
        )
        lists = self._auto_list_store.all()
        self._auto_interval_list_checks = {}
        self._auto_interval_lists_wrap.controls.clear()
        if not lists:
            self._auto_interval_lists_wrap.controls.append(
                ft.Text(
                    "暂无自动更换列表，可在下方新建。", size=12, color=ft.Colors.GREY,
                ),
            )
        else:
            for auto_list in lists:
                label = f"{auto_list.name}（{len(auto_list.entries)} 条目）"
                checkbox = ft.Checkbox(
                    label=label,
                    value=auto_list.id in selected_ids,
                    on_change=lambda e,
                    list_id=auto_list.id: self._auto_on_interval_list_toggle(
                        list_id, bool(getattr(e.control, "value", False)),
                    ),
                    disabled=not enabled_state,
                )
                self._auto_interval_list_checks[auto_list.id] = checkbox
                self._auto_interval_lists_wrap.controls.append(checkbox)
        if self._auto_interval_lists_wrap.page is not None:
            self._auto_interval_lists_wrap.update()

    def _auto_on_interval_list_toggle(self, list_id: str, checked: bool) -> None:
        if self._auto_updating_auto_ui:
            return
        config = copy.deepcopy(self._auto_current_config())
        interval = dict(config.get("interval") or {})
        list_ids = [str(item) for item in interval.get("list_ids", []) if item]
        if checked and list_id not in list_ids:
            list_ids.append(list_id)
        if not checked and list_id in list_ids:
            list_ids = [item for item in list_ids if item != list_id]
        interval["list_ids"] = list_ids
        config["interval"] = interval
        self._auto_commit_config(config)

    def _auto_set_interval_fixed_image(self, path: str | None) -> None:
        config = copy.deepcopy(self._auto_current_config())
        interval = dict(config.get("interval") or {})
        interval["fixed_image"] = path or None
        config["interval"] = interval
        self._auto_commit_config(config)

    def _auto_clear_interval_fixed_image(self) -> None:
        self._auto_set_interval_fixed_image(None)

    def _auto_open_fixed_image_picker(
        self, target: str, index: int | None = None,
    ) -> None:
        self._ensure_auto_fixed_image_picker()
        if self._auto_fixed_image_picker is None:
            self._show_snackbar("无法打开文件选择器。", error=True)
            return
        self._auto_fixed_image_target = (target, index)
        try:
            self._auto_fixed_image_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.IMAGE,
            )
        except Exception as exc:
            logger.error("打开文件选择器失败: {error}", error=str(exc))
            self._show_snackbar("无法打开文件选择器。", error=True)

    def _ensure_auto_fixed_image_picker(self) -> None:
        if self.page is None:
            return
        if self._auto_fixed_image_picker is None:
            self._auto_fixed_image_picker = ft.FilePicker(
                on_result=self._handle_auto_fixed_image_picker_result,
            )
        if self._auto_fixed_image_picker not in self.page.overlay:
            self.page.overlay.append(self._auto_fixed_image_picker)
            self.page.update()

    def _handle_auto_fixed_image_picker_result(
        self, event: ft.FilePickerResultEvent,
    ) -> None:
        target = self._auto_fixed_image_target
        self._auto_fixed_image_target = None
        if not target:
            return
        path: str | None = None
        if event.files:
            file = event.files[0]
            path = getattr(file, "path", None)
        if not path:
            return
        target_name, target_index = target
        if target_name == "interval":
            self._auto_set_interval_fixed_image(path)
        elif target_name == "schedule":
            self._auto_update_schedule_entry_fixed_image(target_index, path)
        elif target_name == "startup":
            self._startup_set_fixed_image(path)
        elif target_name == "schedule_dialog" or target_name == "schedule_dialog":
            self._auto_schedule_dialog_set_fixed_image(path)

    def _auto_update_schedule_entry_fixed_image(
        self, index: int | None, path: str | None,
    ) -> None:
        # 占位：定时模式界面尚未实现
        if index is None:
            return
        config = copy.deepcopy(self._auto_current_config())
        schedule = dict(config.get("schedule") or {})
        entries = [dict(item) for item in schedule.get("entries", [])]
        if not (0 <= index < len(entries)):
            return
        entries[index]["fixed_image"] = path or None
        schedule["entries"] = entries
        config["schedule"] = schedule
        self._auto_commit_config(config)

    def _auto_open_list_import(self) -> None:
        self._ensure_auto_list_picker()
        if self._auto_list_picker is None:
            self._show_snackbar("无法打开文件选择器。", error=True)
            return
        self._auto_list_picker_mode = "import"
        try:
            self._auto_list_picker.pick_files(
                allow_multiple=True,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
            )
        except Exception as exc:
            logger.error("打开导入对话框失败: {error}", error=str(exc))
            self._show_snackbar("无法打开导入对话框。", error=True)

    def _auto_open_list_export_all(self) -> None:
        self._ensure_auto_list_picker()
        if self._auto_list_picker is None:
            self._show_snackbar("无法打开文件选择器。", error=True)
            return
        self._auto_list_picker_mode = "export_all"
        try:
            self._auto_list_picker.save_file(file_name="auto_lists.json")
        except Exception as exc:
            logger.error("打开导出对话框失败: {error}", error=str(exc))
            self._show_snackbar("无法打开导出对话框。", error=True)

    def _auto_refresh_auto_lists_summary(self, lists: list[AutoChangeList]) -> None:
        if self._auto_lists_summary_text is None:
            return
        self._auto_lists_summary_text.value = (
            f"当前共 {len(lists)} 个列表，可在自动更换设置中随时选择使用。"
        )
        if self._auto_lists_summary_text.page is not None:
            self._auto_lists_summary_text.update()

    def _refresh_auto_lists_view(self) -> None:
        if self._auto_lists_column is None:
            return
        lists = self._auto_list_store.all()
        self._auto_refresh_auto_lists_summary(lists)
        self._auto_lists_column.controls.clear()
        if not lists:
            self._auto_lists_column.controls.append(
                ft.Text("尚未创建任何自动更换列表。", size=12, color=ft.Colors.GREY),
            )
        else:
            for auto_list in lists:
                self._auto_lists_column.controls.append(
                    self._auto_build_list_card(auto_list),
                )
        if self._auto_lists_column.page is not None:
            self._auto_lists_column.update()
        self._rebuild_startup_wallpaper_list_checks()

    def _auto_build_list_card(self, auto_list: AutoChangeList) -> ft.Control:
        entry_count = len(auto_list.entries)
        subtitle = f"{entry_count} 个条目"
        description = auto_list.description.strip()
        info_column = ft.Column(
            [
                ft.Text(auto_list.name, size=16, weight=ft.FontWeight.BOLD),
                ft.Text(subtitle, size=12, color=ft.Colors.GREY),
            ]
            + ([ft.Text(description, size=12)] if description else []),
            spacing=4,
            tight=True,
        )
        actions = ft.Row(
            [
                ft.TextButton(
                    "编辑",
                    icon=ft.Icons.EDIT,
                    on_click=lambda _: self._auto_open_list_editor(auto_list.id),
                ),
                ft.TextButton(
                    "导出",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda _: self._auto_export_single_list(auto_list.id),
                ),
                ft.TextButton(
                    "删除",
                    icon=ft.Icons.DELETE,
                    on_click=lambda _: self._auto_confirm_delete_list(auto_list.id),
                ),
            ],
            spacing=8,
        )
        summary = ft.Column(
            [info_column, actions],
            spacing=8,
        )
        return ft.Card(
            content=ft.Container(
                summary,
                padding=12,
            ),
        )

    def _auto_create_list(self) -> None:
        new_list = AutoChangeList(id=uuid.uuid4().hex, name="新建列表")
        self._auto_start_list_editor(new_list)

    def _auto_open_list_editor(self, list_id: str) -> None:
        auto_list = self._auto_list_store.get(list_id)
        if auto_list is None:
            self._show_snackbar("未找到该列表。", error=True)
            return
        self._auto_start_list_editor(auto_list)

    def _auto_export_single_list(self, list_id: str) -> None:
        self._ensure_auto_list_picker()
        if self._auto_list_picker is None:
            self._show_snackbar("无法打开另存为对话框。", error=True)
            return
        self._auto_list_picker_mode = "export_single"
        self._auto_list_pending_export_id = list_id
        try:
            self._auto_list_picker.save_file(file_name=f"auto_list_{list_id}.json")
        except Exception as exc:
            logger.error("打开导出对话框失败: {error}", error=str(exc))
            self._show_snackbar("无法打开导出对话框。", error=True)

    def _auto_confirm_delete_list(self, list_id: str) -> None:
        auto_list = self._auto_list_store.get(list_id)
        if auto_list is None:
            self._show_snackbar("未找到该列表。", error=True)
            return

        def _on_confirm(_: ft.ControlEvent | None = None) -> None:
            self._close_dialog()
            self._auto_delete_list(list_id)

        def _on_cancel(_: ft.ControlEvent | None = None) -> None:
            self._close_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("删除自动更换列表"),
            content=ft.Text(f"确定要删除列表“{auto_list.name}”吗？该操作不可撤销。"),
            actions=[
                ft.TextButton("取消", on_click=_on_cancel),
                ft.TextButton("删除", on_click=_on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._open_dialog(dialog)

    def _auto_delete_list(self, list_id: str) -> None:
        removed = self._auto_list_store.delete(list_id)
        if not removed:
            self._show_snackbar("删除失败，列表不存在。", error=True)
            return
        config = self._auto_current_config()
        changed = False
        interval = config.get("interval") or {}
        list_ids = interval.get("list_ids") or []
        if list_id in list_ids:
            interval["list_ids"] = [item for item in list_ids if item != list_id]
            config["interval"] = interval
            changed = True
        schedule = config.get("schedule") or {}
        entries = schedule.get("entries") or []
        new_entries = []
        for entry in entries:
            ids = [item for item in entry.get("list_ids", []) if item != list_id]
            if ids != entry.get("list_ids", []):
                changed = True
            entry["list_ids"] = ids
            new_entries.append(entry)
        if schedule.get("entries") != new_entries:
            schedule["entries"] = new_entries
            config["schedule"] = schedule
        if changed:
            self._auto_commit_config(config)
        self._refresh_auto_lists_view()
        self._show_snackbar("已删除自动更换列表。")

    def _auto_start_list_editor(self, auto_list: AutoChangeList) -> None:
        name_field = ft.TextField(
            label="列表名称", value=auto_list.name, autofocus=True,
        )
        desc_field = ft.TextField(
            label="描述",
            value=auto_list.description,
            multiline=True,
            min_lines=1,
            max_lines=3,
        )
        entries = [entry.to_dict() for entry in auto_list.entries]
        entries_column = ft.Column(spacing=8, tight=True)
        entry_editor = ft.Container()
        self._auto_editor_state = {
            "list": auto_list,
            "name_field": name_field,
            "desc_field": desc_field,
            "entries": entries,
            "entries_column": entries_column,
            "entry_editor": entry_editor,
        }

        add_button = ft.PopupMenuButton(
            icon=ft.Icons.ADD,
            items=[
                ft.PopupMenuItem(
                    text="Bing 每日",
                    on_click=lambda _: self._auto_editor_add_entry_type("bing"),
                ),
                ft.PopupMenuItem(
                    text="Windows 聚焦",
                    on_click=lambda _: self._auto_editor_add_entry_type("spotlight"),
                ),
                ft.PopupMenuItem(
                    text="收藏夹",
                    on_click=lambda _: self._auto_editor_add_entry_type(
                        "favorite_folder",
                    ),
                ),
                ft.PopupMenuItem(
                    text="壁纸源",
                    on_click=lambda _: self._auto_editor_add_entry_type(
                        "wallpaper_source",
                    ),
                ),
                ft.PopupMenuItem(
                    text="IM 图片源",
                    on_click=lambda _: self._auto_editor_add_entry_type("im_source"),
                ),
                ft.PopupMenuItem(
                    text="AI 生成",
                    on_click=lambda _: self._auto_editor_add_entry_type("ai"),
                ),
                ft.PopupMenuItem(
                    text="本地图片",
                    on_click=lambda _: self._auto_editor_add_entry_type("local_image"),
                ),
                ft.PopupMenuItem(
                    text="本地文件夹",
                    on_click=lambda _: self._auto_editor_add_entry_type("local_folder"),
                ),
            ],
        )

        controls = ft.Column(
            [
                name_field,
                desc_field,
                ft.Row(
                    [ft.Text("条目", size=14, weight=ft.FontWeight.BOLD), add_button],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                entries_column,
                entry_editor,
            ],
            spacing=12,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑自动更换列表"),
            content=ft.Container(controls, width=520),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._auto_editor_cancel()),
                ft.FilledButton("保存", on_click=lambda _: self._auto_editor_save()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._auto_editor_dialog = dialog
        self._open_dialog(dialog)
        self._auto_editor_refresh_entries()

    def _auto_editor_cancel(self) -> None:
        self._auto_editor_state = {}
        if self._auto_editor_dialog is not None:
            self._close_dialog()
            self._auto_editor_dialog = None

    def _auto_editor_save(self) -> None:
        state = self._auto_editor_state
        if not state:
            self._auto_editor_cancel()
            return
        name_field: ft.TextField = state["name_field"]
        desc_field: ft.TextField = state["desc_field"]
        raw_name = (name_field.value or "").strip() or "未命名列表"
        raw_desc = (desc_field.value or "").strip()
        entries_data: list[dict[str, Any]] = state.get("entries", [])
        auto_list: AutoChangeList = state["list"]
        auto_list.name = raw_name
        auto_list.description = raw_desc
        auto_list.entries = [
            AutoChangeListEntry.from_dict(entry) for entry in entries_data
        ]
        self._auto_list_store.upsert(auto_list)
        self._auto_editor_cancel()
        self._refresh_auto_lists_view()
        self._auto_change_service.refresh()
        self._show_snackbar("已保存自动更换列表。")

    def _auto_editor_refresh_entries(self) -> None:
        state = self._auto_editor_state
        if not state:
            return
        entries_column: ft.Column = state.get("entries_column")
        if entries_column is None:
            return
        entries = state.get("entries", [])
        entries_column.controls.clear()
        if not entries:
            entries_column.controls.append(
                ft.Text("当前列表暂无条目。", size=12, color=ft.Colors.GREY),
            )
        else:
            for index, entry in enumerate(entries):
                entries_column.controls.append(
                    self._auto_build_editor_entry_row(index, entry),
                )
        if entries_column.page is not None:
            entries_column.update()

    def _auto_build_editor_entry_row(
        self, index: int, entry: dict[str, Any],
    ) -> ft.Control:
        summary = self._auto_entry_summary(entry)
        return ft.Container(
            ft.Row(
                [
                    ft.Text(summary, size=13),
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                tooltip="编辑",
                                on_click=lambda _: self._auto_editor_add_entry_type(
                                    entry.get("type", ""), index,
                                ),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE,
                                tooltip="删除",
                                on_click=lambda _: self._auto_editor_remove_entry(
                                    index,
                                ),
                            ),
                        ],
                        spacing=4,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(vertical=4, horizontal=8),
            bgcolor=self._bgcolor_surface_low,
            border_radius=8,
        )

    def _auto_editor_remove_entry(self, index: int) -> None:
        entries = self._auto_editor_state.get("entries")
        if not isinstance(entries, list):
            return
        if 0 <= index < len(entries):
            entries.pop(index)
            self._auto_editor_refresh_entries()

    def _auto_entry_summary(self, entry: dict[str, Any]) -> str:
        entry_type = entry.get("type", "")
        config = entry.get("config") or {}
        if entry_type == "bing":
            return "Bing 每日"
        if entry_type == "spotlight":
            return "Windows 聚焦"
        if entry_type == "favorite_folder":
            folder_id = config.get("folder_id")
            folder = self._favorite_manager.get_folder(folder_id) if folder_id else None
            name = folder.name if folder else "未知收藏夹"
            return f"收藏夹：{name}"
        if entry_type == "wallpaper_source":
            category_id = config.get("category_id")
            ref = (
                self._wallpaper_source_manager.find_category(category_id)
                if category_id
                else None
            )
            if ref is None:
                return "壁纸源：未找到分类"
            return f"壁纸源：{ref.source_name} · {ref.label}"
        if entry_type == "im_source":
            source = config.get("source") or {}
            friendly = (
                source.get("friendly_name") or source.get("file_name") or "未命名源"
            )
            category = source.get("category")
            if category:
                return f"IM：{category} / {friendly}"
            return f"IM：{friendly}"
        if entry_type == "ai":
            provider = config.get("provider") or "AI"
            prompt = (config.get("prompt") or "").strip()
            if len(prompt) > 20:
                prompt = prompt[:20] + "…"
            return f"AI：{provider} · {prompt or '无提示'}"
        if entry_type == "local_image":
            path = config.get("path") or ""
            return f"图片：{path or '未选择'}"
        if entry_type == "local_folder":
            path = config.get("path") or ""
            return f"文件夹：{path or '未选择'}"
        return entry_type or "未知条目"

    def _auto_editor_add_entry_type(
        self, entry_type: str, index: int | None = None,
    ) -> None:
        state = self._auto_editor_state
        if not state:
            return
        entries = state.get("entries")
        if not isinstance(entries, list):
            return
        existing = (
            entries[index] if index is not None and 0 <= index < len(entries) else None
        )
        self._auto_open_entry_dialog(entry_type, existing, index)

    def _auto_open_entry_dialog(
        self,
        entry_type: str,
        existing: dict[str, Any] | None,
        index: int | None,
    ) -> None:
        normalized_type = entry_type or (existing.get("type") if existing else "")
        normalized_type = str(normalized_type or "").strip()
        if not normalized_type:
            self._show_snackbar("暂不支持该条目类型。", error=True)
            return
        config = dict(existing.get("config") or {}) if existing else {}
        controls: list[ft.Control] = []
        confirm_enabled = True
        error_message: str | None = None
        collected_controls: dict[str, Any] = {}

        def _collect_wallpaper_source() -> dict[str, Any]:
            dropdown: ft.Dropdown = collected_controls["dropdown"]
            category_id = dropdown.value
            if not category_id:
                raise ValueError("请选择一个壁纸源分类。")
            ref = self._wallpaper_source_manager.find_category(category_id)
            if ref is None:
                raise ValueError("未找到所选壁纸源分类。")
            params_controls: list[_WSParameterControl] = collected_controls.get(
                "params", [],
            )
            params: dict[str, Any] = {}
            for control in params_controls:
                value = control.getter()
                if getattr(control.option, "required", False) and value in (None, ""):
                    label = getattr(control.option, "label", None) or getattr(
                        control.option, "key", "参数",
                    )
                    raise ValueError(f"请填写 {label}。")
                if value not in (None, ""):
                    params[control.option.key] = value
            return {"category_id": category_id, "params": params}

        def _collect_favorite_folder() -> dict[str, Any]:
            dropdown: ft.Dropdown = collected_controls["dropdown"]
            folder_id = dropdown.value
            if not folder_id:
                raise ValueError("请选择一个收藏夹。")
            return {"folder_id": folder_id}

        def _collect_im_source() -> dict[str, Any]:
            dropdown: ft.Dropdown = collected_controls["dropdown"]
            source_key = dropdown.value
            if not source_key:
                raise ValueError("请选择一个 IM 图片源。")
            source = collected_controls.get("source_map", {}).get(source_key)
            if not source:
                raise ValueError("未找到该 IM 图片源。")
            param_controls: list[_IMParameterControl] = collected_controls.get(
                "params", [],
            )
            parameters: list[dict[str, Any]] = []
            for control in param_controls:
                value = control.getter()
                config_meta = control.config or {}
                required = bool(config_meta.get("required"))
                friendly_label = (
                    config_meta.get("friendly_name")
                    or config_meta.get("name")
                    or control.key
                )
                if required and value in (None, ""):
                    raise ValueError(f"请填写 {friendly_label}。")
                if value in (None, ""):
                    continue
                parameters.append(
                    {
                        "config": copy.deepcopy(config_meta),
                        "value": value,
                        "key": control.key,
                    },
                )
            payload = {"source": source}
            if parameters:
                payload["parameters"] = parameters
            return payload

        def _collect_ai() -> dict[str, Any]:
            provider_field: ft.Dropdown = collected_controls["provider"]
            prompt_field: ft.TextField = collected_controls["prompt"]
            width_field: ft.TextField = collected_controls["width"]
            height_field: ft.TextField = collected_controls["height"]
            provider = provider_field.value or ""
            prompt = (prompt_field.value or "").strip()
            if not provider:
                raise ValueError("请选择提供商。")
            if not prompt:
                raise ValueError("请输入提示词。")
            try:
                width = int(width_field.value or 0)
                height = int(height_field.value or 0)
            except ValueError:
                raise ValueError("请输入合法的尺寸。")
            if width <= 0 or height <= 0:
                raise ValueError("尺寸必须大于 0。")
            return {
                "provider": provider,
                "prompt": prompt,
                "width": width,
                "height": height,
            }

        def _collect_local_path(field_key: str, required_text: str) -> dict[str, Any]:
            text_field: ft.TextField = collected_controls[field_key]
            value = (text_field.value or "").strip()
            if not value:
                raise ValueError(required_text)
            return {"path": value}

        collect_fn: Callable[[], dict[str, Any]]

        if normalized_type == "bing":
            controls.append(
                ft.Text(
                    "Bing 每日壁纸将自动获取最新图片。", size=12, color=ft.Colors.GREY,
                ),
            )

            def _collect_bing() -> dict[str, Any]:
                return {}

            collect_fn = _collect_bing
        elif normalized_type == "spotlight":
            controls.append(
                ft.Text(
                    "Windows 聚焦将使用系统 Spotlight 壁纸。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
            )

            def _collect_spotlight() -> dict[str, Any]:
                return {}

            collect_fn = _collect_spotlight
        elif normalized_type == "favorite_folder":
            folders = self._favorite_manager.list_folders()
            options = [
                ft.dropdown.Option(text=folder.name, key=folder.id)
                for folder in folders
            ]
            dropdown = ft.Dropdown(label="收藏夹", options=options, dense=True)
            if not options:
                confirm_enabled = False
                error_message = "当前没有收藏夹可用。"
            default_folder = config.get("folder_id")
            if default_folder and options:
                dropdown.value = default_folder
            elif options:
                dropdown.value = options[0].key
            collected_controls["dropdown"] = dropdown
            controls.append(dropdown)
            collect_fn = _collect_favorite_folder
        elif normalized_type == "wallpaper_source":
            refs = self._auto_collect_wallpaper_categories()
            if not refs:
                confirm_enabled = False
                error_message = "暂无可用壁纸源分类。"
            dropdown_options: list[ft.dropdown.Option] = []
            ref_map: dict[str, WallpaperCategoryRef] = {}
            for ref in refs:
                dropdown_options.append(
                    ft.dropdown.Option(
                        text=f"{ref.source_name} · {ref.label}", key=ref.category_id,
                    ),
                )
                ref_map[ref.category_id] = ref
            dropdown = ft.Dropdown(
                label="壁纸源分类", options=dropdown_options, dense=True,
            )
            params_column = ft.Column(spacing=8, tight=True)
            collected_controls["dropdown"] = dropdown
            collected_controls["params_column"] = params_column

            def rebuild_params(category_id: str | None) -> None:
                params_controls: list[_WSParameterControl] = []
                params_column.controls.clear()
                if not category_id:
                    params_column.controls.append(
                        ft.Text("请选择分类。", size=12, color=ft.Colors.GREY),
                    )
                else:
                    ref = ref_map.get(category_id)
                    if ref is None:
                        params_column.controls.append(
                            ft.Text("该分类不可用。", size=12, color=ft.Colors.RED),
                        )
                    else:
                        record = self._wallpaper_source_manager.get_record(
                            ref.source_id,
                        )
                        cached_params = (
                            dict(config.get("params") or {})
                            if ref.category_id == config.get("category_id")
                            else {}
                        )
                        if record is None:
                            params_column.controls.append(
                                ft.Text(
                                    "无法加载壁纸源。", size=12, color=ft.Colors.RED,
                                ),
                            )
                        else:
                            preset_id = ref.category.param_preset_id
                            preset = (
                                record.spec.parameters.get(preset_id)
                                if preset_id
                                else None
                            )
                            if preset and preset.options:
                                for option in preset.options:
                                    if getattr(option, "hidden", False):
                                        continue
                                    control = self._ws_make_parameter_control(
                                        option,
                                        cached_params.get(option.key),
                                    )
                                    params_controls.append(control)
                                    params_column.controls.append(control.display)
                            else:
                                params_column.controls.append(
                                    ft.Text(
                                        "该分类无需额外参数。",
                                        size=12,
                                        color=ft.Colors.GREY,
                                    ),
                                )
                collected_controls["params"] = params_controls
                if params_column.page is not None:
                    params_column.update()

            def on_change(event: ft.ControlEvent) -> None:
                rebuild_params(event.control.value)

            dropdown.on_change = on_change
            default_category = config.get("category_id") if config else None
            if default_category and default_category in ref_map:
                dropdown.value = default_category
            elif dropdown_options:
                dropdown.value = dropdown_options[0].key
            rebuild_params(dropdown.value)
            controls.extend([dropdown, params_column])
            collect_fn = _collect_wallpaper_source
        elif normalized_type == "im_source":
            categories = self._im_sources_by_category or {}
            if not categories:
                confirm_enabled = False
                error_message = "暂无 IM 图片源，请先在“在线图片”页加载。"
            dropdown_options: list[ft.dropdown.Option] = []
            source_map: dict[str, dict[str, Any]] = {}
            for category, items in categories.items():
                for item in items:
                    key = self._im_source_id(item)
                    friendly_name = (
                        item.get("friendly_name") or item.get("file_name") or key
                    )
                    dropdown_options.append(
                        ft.dropdown.Option(
                            text=f"{category} · {friendly_name}", key=key,
                        ),
                    )
                    source_map[key] = item
            dropdown = ft.Dropdown(
                label="IM 图片源", options=dropdown_options, dense=True,
            )
            collected_controls["dropdown"] = dropdown
            collected_controls["source_map"] = source_map
            params_column = ft.Column(spacing=8, tight=True)
            collected_controls["params_column"] = params_column

            def rebuild_im_params(source_key: str | None) -> None:
                params_controls: list[_IMParameterControl] = []
                params_column.controls.clear()
                if not source_key:
                    params_column.controls.append(
                        ft.Text("请选择图片源。", size=12, color=ft.Colors.GREY),
                    )
                else:
                    source = source_map.get(source_key)
                    if source is None:
                        params_column.controls.append(
                            ft.Text("未找到该图片源。", size=12, color=ft.Colors.RED),
                        )
                    else:
                        params = source.get("parameters") or []
                        cached_params: dict[str, Any] = {}
                        if existing and source_key == self._im_source_id(
                            config.get("source") or {},
                        ):
                            raw_cached = config.get("parameters") or []
                            if isinstance(raw_cached, Sequence):
                                for item in raw_cached:
                                    if not isinstance(item, dict):
                                        continue
                                    cache_key = item.get("key")
                                    if not cache_key:
                                        meta = (
                                            item.get("config")
                                            or item.get("parameter")
                                            or {}
                                        )
                                        cache_key = meta.get("name")
                                    if cache_key:
                                        cached_params[str(cache_key)] = item.get(
                                            "value",
                                        )
                        for idx, param in enumerate(params):
                            try:
                                control = self._make_im_parameter_control(
                                    param or {},
                                    cached_params,
                                    idx,
                                )
                            except Exception as exc:
                                logger.error(f"构建 IM 参数控件失败: {exc}")
                                continue
                            params_controls.append(control)
                            params_column.controls.append(control.display)
                        if not params_controls:
                            params_column.controls.append(
                                ft.Text(
                                    "该图片源无需参数。", size=12, color=ft.Colors.GREY,
                                ),
                            )
                collected_controls["params"] = params_controls
                if params_column.page is not None:
                    params_column.update()

            def im_on_change(event: ft.ControlEvent) -> None:
                rebuild_im_params(event.control.value)

            dropdown.on_change = im_on_change
            default_source = None
            if existing:
                default_source = self._im_source_id(config.get("source") or {})
            if default_source and default_source in source_map:
                dropdown.value = default_source
            elif dropdown_options:
                dropdown.value = dropdown_options[0].key
            rebuild_im_params(dropdown.value)
            controls.extend([dropdown, params_column])
            collect_fn = _collect_im_source
        elif normalized_type == "ai":
            provider_dropdown = ft.Dropdown(
                label="提供商",
                options=[ft.dropdown.Option(key="pollinations", text="Pollinations")],
                value=config.get("provider") or "pollinations",
                dense=True,
            )
            prompt_field = ft.TextField(
                label="提示词(英文)",
                value=config.get("prompt") or "",
                multiline=True,
                min_lines=2,
                max_lines=4,
            )
            width_field = ft.TextField(
                label="宽度",
                value=str(config.get("width") or "512"),
                keyboard_type=ft.KeyboardType.NUMBER,
                width=140,
                dense=True,
            )
            height_field = ft.TextField(
                label="高度",
                value=str(config.get("height") or "512"),
                keyboard_type=ft.KeyboardType.NUMBER,
                width=140,
                dense=True,
            )
            collected_controls["provider"] = provider_dropdown
            collected_controls["prompt"] = prompt_field
            collected_controls["width"] = width_field
            collected_controls["height"] = height_field
            controls.extend(
                [
                    provider_dropdown,
                    prompt_field,
                    ft.Row([width_field, height_field], spacing=8),
                ],
            )
            collect_fn = _collect_ai
        elif normalized_type == "local_image":
            path_field = ft.TextField(label="图片路径", value=config.get("path") or "")
            collected_controls["path"] = path_field
            controls.append(path_field)

            def _collect_local_image() -> dict[str, Any]:
                return _collect_local_path("path", "请选择图片文件。")

            collect_fn = _collect_local_image
        elif normalized_type == "local_folder":
            path_field = ft.TextField(
                label="文件夹路径", value=config.get("path") or "",
            )
            collected_controls["path"] = path_field
            controls.append(path_field)

            def _collect_local_folder() -> dict[str, Any]:
                return _collect_local_path("path", "请选择图片文件夹。")

            collect_fn = _collect_local_folder
        else:
            self._show_snackbar("暂不支持该条目类型。", error=True)
            return

        body = ft.Column(controls, spacing=12, tight=True)
        if error_message:
            body.controls.append(ft.Text(error_message, size=12, color=ft.Colors.RED))

        # If the list editor dialog is open, render the entry editor inline inside it
        if self._auto_editor_dialog is not None and self._auto_editor_state:
            # store inline state so confirm handler can access controls/collector
            self._auto_entry_dialog_state = {
                "type": normalized_type,
                "collect": collect_fn,
                "existing": existing,
                "index": index,
                "controls": collected_controls,
            }

            cancel_btn = ft.TextButton(
                "取消", on_click=lambda _: self._auto_close_entry_inline(),
            )
            confirm_btn = ft.FilledButton(
                "确定",
                on_click=lambda _: self._auto_confirm_entry_inline(),
                disabled=not confirm_enabled,
            )

            inline_column = ft.Column(
                [
                    body,
                    ft.Row(
                        [cancel_btn, confirm_btn], alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=8,
            )
            placeholder: ft.Container = self._auto_editor_state.get("entry_editor")  # type: ignore[assignment]
            if placeholder is None:
                # fallback to dialog if placeholder missing
                dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("编辑条目"),
                    content=ft.Container(body, width=420),
                    actions=[cancel_btn, confirm_btn],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                self._auto_entry_dialog = dialog
                self._open_dialog(dialog)
                return
            placeholder.content = inline_column
            # update UI
            if placeholder.page is not None:
                placeholder.update()
            return

        # Otherwise fall back to modal dialog
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑条目"),
            content=ft.Container(body, width=420),
            actions=[
                ft.TextButton(
                    "取消", on_click=lambda _: self._auto_close_entry_dialog(),
                ),
                ft.FilledButton(
                    "确定",
                    on_click=lambda _: self._auto_confirm_entry(
                        normalized_type, collect_fn, existing, index,
                    ),
                    disabled=not confirm_enabled,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._auto_entry_dialog_state = {
            "type": normalized_type,
            "collect": collect_fn,
            "existing": existing,
            "index": index,
            "controls": collected_controls,
        }
        self._auto_entry_dialog = dialog
        self._open_dialog(dialog)

    def _auto_confirm_entry(
        self,
        entry_type: str,
        collect_fn: Callable[[], dict[str, Any]],
        existing: dict[str, Any] | None,
        index: int | None,
    ) -> None:
        state = self._auto_editor_state
        if not state:
            self._auto_close_entry_dialog()
            return
        try:
            config = collect_fn()
        except ValueError as exc:
            self._show_snackbar(str(exc), error=True)
            return
        entries = state.get("entries")
        if not isinstance(entries, list):
            self._auto_close_entry_dialog()
            return
        entry_id = existing.get("id") if existing else None
        if not entry_id:
            entry_id = uuid.uuid4().hex
        payload = {"id": entry_id, "type": entry_type, "config": config}
        if index is None or index >= len(entries):
            entries.append(payload)
        else:
            entries[index] = payload
        self._auto_close_entry_dialog()
        self._auto_editor_refresh_entries()

    def _auto_close_entry_dialog(self) -> None:
        self._auto_entry_dialog_state = {}
        if self._auto_entry_dialog is not None:
            self._close_dialog()
            self._auto_entry_dialog = None

    def _auto_close_entry_inline(self) -> None:
        # Clear inline editor area in list editor dialog
        try:
            placeholder: ft.Container | None = self._auto_editor_state.get(
                "entry_editor",
            )  # type: ignore[assignment]
        except Exception:
            placeholder = None
        if placeholder is not None:
            placeholder.content = None
            if placeholder.page is not None:
                placeholder.update()
        self._auto_entry_dialog_state = {}

    def _auto_confirm_entry_inline(self) -> None:
        state = self._auto_entry_dialog_state
        if not state:
            self._auto_close_entry_inline()
            return
        collect_fn: Callable[[], dict[str, Any]] | None = state.get("collect")
        existing: dict[str, Any] | None = state.get("existing")
        index: int | None = state.get("index")
        if collect_fn is None:
            self._show_snackbar("内部错误：缺少收集函数。", error=True)
            return
        try:
            config = collect_fn()
        except ValueError as exc:
            self._show_snackbar(str(exc), error=True)
            return
        editor_state = self._auto_editor_state
        if not editor_state:
            self._auto_close_entry_inline()
            return
        entries = editor_state.get("entries")
        if not isinstance(entries, list):
            self._auto_close_entry_inline()
            return
        entry_id = existing.get("id") if existing else None
        if not entry_id:
            entry_id = uuid.uuid4().hex
        payload = {"id": entry_id, "type": state.get("type"), "config": config}
        if index is None or index >= len(entries):
            entries.append(payload)
        else:
            entries[index] = payload
        # clear inline editor and refresh entries
        self._auto_close_entry_inline()
        self._auto_editor_refresh_entries()

    def _auto_collect_wallpaper_categories(self) -> list[WallpaperCategoryRef]:
        refs: list[WallpaperCategoryRef] = []
        for record in self._wallpaper_source_manager.enabled_records():
            refs.extend(self._wallpaper_source_manager.category_refs(record.identifier))
        refs.sort(key=lambda ref: (ref.source_name.lower(), ref.label.lower()))
        return refs

    def _build_plugin_actions(
        self, factories: list[Callable[[], ft.Control]],
    ) -> list[ft.Control]:
        controls: list[ft.Control] = []
        for factory in factories:
            try:
                control = factory()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"插件动作生成失败: {exc}")
                continue
            if control is not None:
                controls.append(control)
        return controls

    def _build_plugin_settings_content(self) -> ft.Control:
        management_section = self._build_plugin_management_panel()
        # 插件特定的设置页面可从插件卡片按钮获取
        # 此处仅显示管理面板；插件特定页面可通过每个插件的“插件设置”按钮获取，该按钮会导航至专用视图。
        return ft.Container(
            content=ft.Column(
                [
                    management_section,
                ],
                spacing=24,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=20,
            expand=True,
        )

    def _refresh_settings_registry(self) -> None:
        if not self._settings_pages:
            self._settings_page_map = {}
            return
        self._settings_page_map = {
            entry.plugin_identifier: entry
            for entry in self._settings_pages
            if getattr(entry, "plugin_identifier", None)
        }

    def set_route_registrar(self, registrar: Callable[[AppRouteView], None]) -> None:
        """Provide a callback used to register plugin settings routes."""
        self._route_register = registrar
        self._register_all_plugin_settings_routes()

    def _make_plugin_settings_route(self, entry: PluginSettingsPage) -> AppRouteView:
        route_path = self._settings_route(entry.plugin_identifier)

        def _builder(pid: str = entry.plugin_identifier) -> ft.View:
            return self.build_plugin_settings_view(pid)

        return AppRouteView(route=route_path, builder=_builder)

    def _register_settings_page_route(self, entry: PluginSettingsPage) -> None:
        if not self._route_register:
            return
        try:
            view = self._make_plugin_settings_route(entry)
            self._route_register(view)
        except Exception as exc:
            logger.warning(
                "注册插件设置路由失败: {error}",
                error=str(exc),
            )

    def _register_all_plugin_settings_routes(self) -> None:
        if not self._route_register:
            return
        for entry in self.iter_plugin_settings_pages():
            self._register_settings_page_route(entry)

    def notify_settings_page_registered(self, entry: PluginSettingsPage) -> None:
        self._refresh_settings_registry()
        self._register_settings_page_route(entry)

    def set_first_run_next_route(self, route: str) -> None:
        self._first_run_next_route = route or "/"

    def set_test_warning_next_route(self, route: str) -> None:
        self._test_warning_next_route = route or "/"

    def set_conflict_next_route(self, route: str) -> None:
        self._conflict_next_route = route or "/"

    def set_startup_conflicts(self, conflicts: Sequence[StartupConflict]) -> None:
        self._startup_conflicts = list(conflicts or [])

    @property
    def first_run_pending(self) -> bool:
        return self._first_run_pending

    def finish_first_run(self, *, show_feedback: bool = True) -> None:
        if not self._first_run_pending and show_feedback:
            self._show_snackbar("已完成首次运行引导。")
            if self.page is not None:
                self.page.go(self._first_run_next_route or "/")
            return
        try:
            update_marker(self._first_run_required_version)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("更新首次运行标记失败: {error}", error=str(exc))
            self._show_snackbar("保存首次运行状态失败，请稍后再试。", error=True)
            return
        self._first_run_pending = False
        if show_feedback:
            self._show_snackbar("首次运行引导已完成，欢迎使用。")
        target_route = self._first_run_next_route or "/"
        if self.page is None:
            return
        try:
            self.page.go(target_route)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("首次运行完成后跳转失败: {error}", error=str(exc))

    def iter_plugin_settings_pages(self) -> list[PluginSettingsPage]:
        self._refresh_settings_registry()
        return list(self._settings_pages)

    def select_settings_tab(self, tab_id: str) -> bool:
        normalized = tab_id.strip().lower()
        if not normalized:
            return False
        if normalized not in self._settings_tab_indices:
            return False
        if self._settings_tabs is None:
            logger.info(f"延迟切换设置页面标签到 {normalized}")
            self._pending_settings_tab = normalized
            return True

        self._settings_tabs.selected_index = self._settings_tab_indices[normalized]
        logger.info(
            f"切换设置页面标签到 {normalized}({self._settings_tabs.selected_index})",
        )
        self.page.update()
        return True

    def select_settings_tab_index(self, index: int) -> bool:
        # 允许按数字索引进行选择。如果标签尚未创建，则保存待处理索引。
        try:
            if index < 0:
                return False
        except Exception:
            return False
        if self._settings_tabs is None:
            logger.info(f"延迟切换设置页面索引到 {index}")
            # 存储为标准化字符串，以便现有的待处理逻辑能够处理它
            self._pending_settings_tab = str(index)
            return True
        # 防止超出范围
        if not getattr(self._settings_tabs, "tabs", None):
            return False
        if index >= len(self._settings_tabs.tabs):
            return False
        logger.info(f"切换设置页面索引到 {index}")
        self._settings_tabs.selected_index = index
        self.page.update()
        return True

    def _resolve_plugin_runtime(self, plugin_id: str) -> PluginRuntimeInfo | None:
        for runtime in self._plugin_runtime_cache:
            if runtime.identifier == plugin_id:
                return runtime
        return None

    def _open_plugin_settings_page(self, runtime: PluginRuntimeInfo) -> None:
        self._refresh_settings_registry()
        registration = self._settings_page_map.get(runtime.identifier)
        if not registration:
            self._show_snackbar("该插件未提供设置页面。", error=True)
            return
        self.page.go(self._settings_route(runtime.identifier))

    def _settings_route(self, plugin_id: str) -> str:
        return f"/settings/plugin/{plugin_id}"

    def _handle_reload_request(self, _: ft.ControlEvent | None = None) -> None:
        logger.debug("已点击重载按钮")
        self._reload_plugins()

    # Banner-related functionality removed. Methods and UI have been deleted.

    def build_plugin_settings_view(self, plugin_id: str) -> ft.View:
        self._refresh_settings_registry()
        registration = self._settings_page_map.get(plugin_id)
        runtime = self._resolve_plugin_runtime(plugin_id)

        display_name = runtime.name if runtime else plugin_id
        description_text = (runtime.description if runtime else "") or ""
        if registration:
            try:
                plugin_control = registration.builder()
            except Exception as exc:
                message = f"插件设置内容构建失败：{exc}"
                logger.error(message)
                plugin_control = ft.Text(message, color=ft.Colors.ERROR)
        else:
            plugin_control = ft.Text("该插件未注册专属设置页面。", color=ft.Colors.GREY)

        content_controls: list[ft.Control] = []

        if registration:
            content_controls.append(
                ft.Text(registration.title, size=20, weight=ft.FontWeight.BOLD),
            )

        if description_text:
            content_controls.append(
                ft.Text(description_text, size=12, color=ft.Colors.GREY),
            )

        if registration and registration.description:
            content_controls.append(
                ft.Text(
                    registration.description,
                    size=12,
                    color=ft.Colors.GREY,
                ),
            )

        content_controls.append(plugin_control)

        body = ft.Container(
            content=ft.Column(
                controls=content_controls,
                spacing=16,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=20,
            expand=True,
        )

        return ft.View(
            self._settings_route(plugin_id),
            [
                ft.AppBar(
                    title=ft.Text(f"{display_name} 设置"),
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        tooltip="返回",
                        on_click=lambda _: self.page.go("/settings"),
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                body,
            ],
        )

    # ------------------------------------------------------------------
    # plugin management helpers
    # ------------------------------------------------------------------
    def _build_plugin_management_panel(self) -> ft.Control:
        if not self.plugin_service:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text("插件管理", size=24),
                        ft.Text("插件管理服务暂不可用。"),
                    ],
                    spacing=12,
                ),
                padding=20,
                bgcolor=self._bgcolor_surface_low,
                border_radius=12,
            )

        self._ensure_plugin_file_picker()
        if self._plugin_list_column is None:
            self._plugin_list_column = ft.Column(spacing=12, expand=True)

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("插件管理", size=24),
                        ft.Text(
                            "在此启用/禁用、导入、删除插件，并管理权限。",
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                ft.Row(
                    [
                        ft.TextButton(
                            text="刷新列表",
                            icon=ft.Icons.REFRESH,
                            tooltip="刷新插件状态",
                            on_click=lambda _: self._refresh_plugin_list(),
                        ),
                        ft.FilledTonalButton(
                            text="重载插件",
                            icon=ft.Icons.RESTART_ALT,
                            tooltip="重新加载所有插件",
                            on_click=lambda _: self._reload_plugins(),
                        ),
                        ft.FilledButton(
                            "导入插件 (.py)",
                            icon=ft.Icons.UPLOAD_FILE,
                            on_click=lambda _: self._open_import_picker(),
                        ),
                    ],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._refresh_plugin_list()

        body_controls: list[ft.Control] = [header, self._plugin_list_column]

        permission_catalog = self._build_permission_catalog_section()
        if permission_catalog:
            body_controls.extend([ft.Divider(), permission_catalog])

        event_section = self._build_event_definitions_section()
        if event_section:
            body_controls.extend([ft.Divider(), event_section])

        return ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(body_controls, spacing=16, expand=True),
            ),
        )

    def _refresh_plugin_list(self) -> None:
        if not self.plugin_service or not self._plugin_list_column:
            return

        self._plugin_list_column.controls = [
            ft.Row(
                [ft.ProgressRing(), ft.Text("正在加载插件信息…")],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ]
        self.page.update()

        try:
            runtimes = self.plugin_service.list_plugins()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"获取插件状态失败: {exc}")
            self._plugin_list_column.controls = [
                ft.Text(f"加载插件状态失败：{exc}", color=ft.Colors.ERROR),
            ]
            self.page.update()
            return

        self._plugin_runtime_cache = list(runtimes)

        if not runtimes:
            self._plugin_list_column.controls = [ft.Text("当前没有检测到插件。")]
        else:
            sorted_runtime = sorted(
                runtimes,
                key=lambda info: (not getattr(info, "builtin", False), info.identifier),
            )
            self._plugin_list_column.controls = [
                self._build_plugin_card(info) for info in sorted_runtime
            ]

        self.page.update()

    def _build_plugin_card(self, runtime: PluginRuntimeInfo) -> ft.Control:
        self._sync_known_permissions()
        status_label, status_color = self._status_display(runtime.status)
        permissions_summary = self._format_permissions(runtime)

        switch_disabled = runtime.builtin

        def _on_toggle(
            e: ft.ControlEvent,
            *,
            plugin_id: str = runtime.identifier,
            runtime_info: PluginRuntimeInfo = runtime,
        ) -> None:
            new_value = bool(e.control.value)
            if runtime_info.enabled == new_value:
                return
            if not self._toggle_plugin_enabled(plugin_id, new_value):
                e.control.value = runtime_info.enabled
                self.page.update()
                return
            runtime_info.enabled = new_value

        toggle = ft.Switch(
            label="启用",
            value=runtime.enabled,
            disabled=switch_disabled,
            on_change=_on_toggle,
        )

        action_buttons: list[ft.Control] = [
            ft.TextButton(
                "查看详情",
                icon=ft.Icons.INFO,
                on_click=lambda _: self._show_plugin_details(runtime),
            ),
        ]

        self._refresh_settings_registry()
        settings_page = self._settings_page_map.get(runtime.identifier)
        if settings_page:
            action_buttons.append(
                ft.TextButton(
                    settings_page.button_label,
                    icon=settings_page.icon or ft.Icons.TUNE,
                    on_click=lambda _: self._open_plugin_settings_page(runtime),
                ),
            )

        all_permissions = set(runtime.permissions_required) | set(
            runtime.permissions_granted.keys(),
        )
        if all_permissions:
            action_buttons.append(
                ft.TextButton(
                    "管理权限",
                    icon=ft.Icons.ADMIN_PANEL_SETTINGS,
                    on_click=lambda _: self._show_permission_dialog(runtime),
                ),
            )

        if not runtime.builtin:
            action_buttons.append(
                ft.TextButton(
                    "删除插件",
                    icon=ft.Icons.DELETE,
                    on_click=lambda _: self._confirm_delete_plugin(runtime),
                ),
            )

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            f"{runtime.name} v{runtime.version}",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            runtime.description or "暂无描述",
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                toggle,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        status_row = ft.Row(
            [
                ft.Text(f"状态：{status_label}", color=status_color),
                ft.Text(
                    f"标识符：{runtime.identifier}",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Text(
                    f"来源：{runtime.source_path if runtime.source_path else runtime.module_name or '未知'}",
                    size=12,
                    color=ft.Colors.GREY,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        controls: list[ft.Control] = [header, status_row]

        denied_permissions = [
            self._format_permission_label(perm)
            for perm, state in runtime.permission_states.items()
            if state is PermissionState.DENIED
        ]
        prompt_permissions = [
            self._format_permission_label(perm)
            for perm, state in runtime.permission_states.items()
            if state is PermissionState.PROMPT
        ]

        badges: list[ft.Control] = []
        if denied_permissions:
            badges.append(
                ft.Container(
                    padding=ft.Padding(8, 4, 8, 4),
                    bgcolor=ft.Colors.RED_50,
                    border_radius=6,
                    content=ft.Text(
                        f"已拒绝：{', '.join(denied_permissions)}",
                        size=11,
                        color=ft.Colors.RED_700,
                    ),
                ),
            )
        if prompt_permissions:
            badges.append(
                ft.Container(
                    padding=ft.Padding(8, 4, 8, 4),
                    bgcolor=ft.Colors.AMBER_50,
                    border_radius=6,
                    content=ft.Text(
                        f"下次询问：{', '.join(prompt_permissions)}",
                        size=11,
                        color=ft.Colors.AMBER_800,
                    ),
                ),
            )

        if badges:
            controls.append(
                ft.Row(
                    controls=badges,
                    spacing=6,
                    run_spacing=6,
                    wrap=True,
                ),
            )

        controls.append(
            ft.Text(
                f"类型：{self._format_plugin_kind(runtime.plugin_type)}",
                size=12,
                color=ft.Colors.GREY,
            ),
        )

        dependency_summary = self._dependency_summary(runtime)
        controls.append(
            ft.Text(
                f"依赖：{dependency_summary}",
                size=12,
                color=ft.Colors.ERROR if runtime.dependency_issues else ft.Colors.GREY,
            ),
        )

        if runtime.error:
            controls.append(ft.Text(f"错误：{runtime.error}", color=ft.Colors.ERROR))

        controls.append(
            ft.Text(f"权限：{permissions_summary}", size=12, color=ft.Colors.GREY),
        )
        controls.append(
            ft.Row(
                controls=action_buttons,
                spacing=10,
                run_spacing=6,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )

        return ft.Card(
            content=ft.Container(
                padding=16,
                content=ft.Column(controls, spacing=10),
            ),
        )

    def _status_display(self, status: PluginStatus | str) -> tuple[str, str]:
        try:
            key = status if isinstance(status, PluginStatus) else PluginStatus(status)
        except ValueError:  # pragma: no cover - defensive
            key = PluginStatus.ERROR

        mapping: dict[PluginStatus, tuple[str, str]] = {
            PluginStatus.ACTIVE: ("运行中", ft.Colors.GREEN),
            PluginStatus.LOADED: ("已加载", ft.Colors.BLUE),
            PluginStatus.DISABLED: ("已禁用", ft.Colors.GREY),
            PluginStatus.PERMISSION_BLOCKED: ("权限待授权", ft.Colors.AMBER),
            PluginStatus.ERROR: ("激活失败", ft.Colors.RED),
            PluginStatus.FAILED: ("加载失败", ft.Colors.RED),
            PluginStatus.NOT_LOADED: ("未加载", ft.Colors.GREY),
            PluginStatus.MISSING_DEPENDENCY: ("依赖缺失", ft.Colors.RED),
        }

        return mapping.get(key, ("未知", ft.Colors.GREY))

    def _format_plugin_kind(self, kind: PluginKind) -> str:
        mapping = {
            PluginKind.FEATURE: "功能插件",
            PluginKind.LIBRARY: "依赖插件",
        }
        return mapping.get(kind, str(kind))

    def _dependency_summary(self, runtime: PluginRuntimeInfo) -> str:
        if not runtime.dependencies:
            return "无"
        parts: list[str] = []
        for spec in runtime.dependencies:
            issue = runtime.dependency_issues.get(spec.identifier)
            if issue:
                parts.append(f"{spec.describe()}（未满足）")
            else:
                parts.append(f"{spec.describe()}（已满足）")
        return "、".join(parts)

    def _dependency_detail_controls(
        self, runtime: PluginRuntimeInfo,
    ) -> list[ft.Control]:
        if not runtime.dependencies:
            return [ft.Text("无依赖", size=12, color=ft.Colors.GREY)]
        controls: list[ft.Control] = []
        for spec in runtime.dependencies:
            issue = runtime.dependency_issues.get(spec.identifier)
            if issue:
                controls.append(
                    ft.Text(
                        f"{spec.describe()} - {issue}",
                        size=12,
                        color=ft.Colors.ERROR,
                    ),
                )
            else:
                controls.append(
                    ft.Text(
                        f"{spec.describe()} - 已满足",
                        size=12,
                        color=ft.Colors.GREY,
                    ),
                )
        return controls

    def _format_permissions(self, runtime: PluginRuntimeInfo) -> str:
        keys = sorted(
            set(runtime.permission_states.keys()) | set(runtime.permissions_required),
        )
        if not keys:
            return "无需权限"

        parts: list[str] = []
        for key in keys:
            permission = self._known_permissions.get(key)
            name = permission.name if permission else key
            state = runtime.permission_states.get(key)
            if state is None:
                state = (
                    PermissionState.GRANTED
                    if runtime.permissions_granted.get(key, False)
                    else PermissionState.PROMPT
                )
            if state is PermissionState.GRANTED:
                suffix = "已授权"
            elif state is PermissionState.DENIED:
                suffix = "已拒绝"
            else:
                suffix = "待确认"
            parts.append(f"{name}（{suffix}）")
        return "、".join(parts)

    def _show_plugin_details(self, runtime: PluginRuntimeInfo) -> None:
        manifest = runtime.manifest
        info_rows = [
            ft.ListTile(title=ft.Text("标识符"), subtitle=ft.Text(runtime.identifier)),
            ft.ListTile(title=ft.Text("版本"), subtitle=ft.Text(runtime.version)),
            ft.ListTile(
                title=ft.Text("描述"),
                subtitle=ft.Text(
                    manifest.description if manifest else runtime.description or "无",
                ),
            ),
            ft.ListTile(
                title=ft.Text("作者"),
                subtitle=ft.Text(manifest.author if manifest else "未知"),
            ),
            ft.ListTile(
                title=ft.Text("类型"),
                subtitle=ft.Text(self._format_plugin_kind(runtime.plugin_type)),
            ),
        ]

        if manifest and manifest.homepage:
            info_rows.append(
                ft.ListTile(
                    title=ft.Text("主页"),
                    subtitle=ft.Text(manifest.homepage, selectable=True),
                    on_click=lambda _: self.page.launch_url(manifest.homepage),
                ),
            )

        info_rows.extend(
            [
                ft.ListTile(
                    title=ft.Text("来源"),
                    subtitle=ft.Text(
                        str(runtime.source_path)
                        if runtime.source_path
                        else runtime.module_name or "未知",
                    ),
                ),
                ft.ListTile(
                    title=ft.Text("状态"),
                    subtitle=ft.Text(self._status_display(runtime.status)[0]),
                ),
            ],
        )

        if runtime.error:
            info_rows.append(
                ft.ListTile(
                    title=ft.Text("错误"),
                    subtitle=ft.Text(runtime.error, color=ft.Colors.ERROR),
                ),
            )

        permissions_text = self._format_permissions(runtime)
        info_rows.append(
            ft.ListTile(title=ft.Text("权限"), subtitle=ft.Text(permissions_text)),
        )

        info_rows.append(
            ft.ListTile(
                title=ft.Text("依赖"),
                subtitle=ft.Column(
                    self._dependency_detail_controls(runtime), spacing=4,
                ),
            ),
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"插件详情 - {runtime.name}"),
            content=ft.Container(
                width=400,
                content=ft.Column(
                    info_rows, tight=True, spacing=4, scroll=ft.ScrollMode.AUTO,
                ),
            ),
            actions=[
                ft.TextButton("关闭", on_click=lambda _: self._close_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _show_permission_dialog(self, runtime: PluginRuntimeInfo) -> None:
        self._sync_known_permissions()
        requested = sorted(
            set(runtime.permission_states.keys()) | set(runtime.permissions_required),
        )

        if not requested:
            self._show_snackbar("该插件未请求任何权限。")
            return

        pending_choices: dict[str, str] = {}
        initial_choices: dict[str, str] = {}
        action_holder: dict[str, ft.FilledButton | None] = {"button": None}

        def _update_apply_state() -> None:
            button = action_holder["button"]
            if not button:
                return
            button.disabled = not pending_choices
            button.update()

        def _submit(_: ft.ControlEvent | None = None) -> None:
            if not pending_choices:
                self._close_dialog()
                return
            for permission_id, choice in list(pending_choices.items()):
                new_state = self._state_from_choice(choice)
                if not self._update_permission_state(
                    runtime.identifier, permission_id, new_state,
                ):
                    _update_apply_state()
                    return
            pending_choices.clear()
            _update_apply_state()
            self._close_dialog()

        rows: list[ft.Control] = []

        for permission_id in requested:
            permission = self._known_permissions.get(permission_id)
            title = permission.name if permission else permission_id
            description = permission.description if permission else ""
            current_state = runtime.permission_states.get(permission_id)
            if current_state is None:
                current_state = (
                    PermissionState.GRANTED
                    if runtime.permissions_granted.get(permission_id, False)
                    else PermissionState.PROMPT
                )

            initial_choice = self._choice_from_state(current_state)
            initial_choices[permission_id] = initial_choice

            def _on_choice(
                e: ft.ControlEvent,
                *,
                perm: str = permission_id,
            ) -> None:
                choice = e.control.value
                if choice == initial_choices.get(perm):
                    pending_choices.pop(perm, None)
                else:
                    pending_choices[perm] = choice
                _update_apply_state()

            rows.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.SECURITY),
                    title=ft.Text(title),
                    subtitle=ft.Text(description or f"权限标识：{permission_id}"),
                    trailing=ft.Dropdown(
                        width=180,
                        value=initial_choice,
                        options=[
                            ft.DropdownOption(key="deny", text="禁用"),
                            ft.DropdownOption(key="prompt", text="下次询问"),
                            ft.DropdownOption(key="allow", text="允许"),
                        ],
                        on_change=_on_choice,
                    ),
                ),
            )

        apply_button = ft.FilledButton(
            "确定", icon=ft.Icons.CHECK, disabled=True, on_click=_submit,
        )
        action_holder["button"] = apply_button

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"权限管理 - {runtime.name}"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    rows, tight=True, spacing=4, scroll=ft.ScrollMode.AUTO,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                apply_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _toggle_plugin_enabled(self, identifier: str, enabled: bool) -> bool:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            return False
        try:
            self.plugin_service.set_enabled(identifier, enabled)
            self._show_snackbar("插件状态已更新，将在重新加载后生效。")

            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"更新插件启用状态失败: {exc}")
            self._show_snackbar(f"更新失败：{exc}", error=True)
            return False

    def _update_permission_state(
        self, identifier: str, permission: str, state: PermissionState,
    ) -> bool:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            return False
        try:
            self.plugin_service.update_permission(identifier, permission, state)
            pending_reload = False
            try:
                pending_reload = bool(self.plugin_service.is_reload_required())
            except Exception:
                pending_reload = False
            if pending_reload:
                self._show_snackbar("权限已更新，将在重新加载后生效。")
            else:
                self._show_snackbar("权限已更新，启用插件后生效。")

            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"更新插件权限失败: {exc}")
            self._show_snackbar(f"权限更新失败：{exc}", error=True)
            return False

    def _confirm_delete_plugin(self, runtime: PluginRuntimeInfo) -> None:
        if runtime.builtin:
            self._show_snackbar("内置插件无法删除。", error=True)
            return

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("删除插件"),
            content=ft.Text(f"确定要删除插件 {runtime.name} 吗？此操作不可撤销。"),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledTonalButton(
                    "删除",
                    icon=ft.Icons.DELETE_FOREVER,
                    on_click=lambda _: self._execute_delete_plugin(runtime.identifier),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _execute_delete_plugin(self, identifier: str) -> None:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            self._close_dialog()
            return
        try:
            self.plugin_service.delete_plugin(identifier)
            # 更新列表，提示用户稍后手动重新加载
            self._refresh_plugin_list()
            self._show_snackbar("插件已删除，需要重新加载后生效。")

        except Exception as exc:
            logger.error(f"删除插件失败: {exc}")
            self._show_snackbar(f"删除失败：{exc}", error=True)
        finally:
            self._close_dialog()

    def _reload_plugins(self) -> None:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            logger.warning("尝试重新加载插件，但插件服务不可用。")
            return
        try:
            logger.info("重新加载插件…")
            self.plugin_service.reload()

            self._show_snackbar("插件正在重新加载…")
            logger.info("重载插件命令已发送。")

        except Exception as exc:
            logger.error(f"重新加载插件失败: {exc}")
            self._show_snackbar(f"重新加载失败：{exc}", error=True)

    def _open_dialog(self, dialog: ft.AlertDialog) -> None:
        self.page.dialog = dialog
        self.page.open(self.page.dialog)

    def _close_dialog(self) -> None:
        if self.page.dialog is not None:
            self.page.close(self.page.dialog)

    # -----------------------------
    # 收藏：添加本地图片入口
    # -----------------------------
    def _ensure_favorite_file_picker(self) -> None:
        if self._favorite_file_picker is None:
            self._favorite_file_picker = ft.FilePicker(
                on_result=self._handle_add_local_favorite_result,
            )
        if self._favorite_file_picker not in self.page.overlay:
            self.page.overlay.append(self._favorite_file_picker)
            self.page.update()

    def _open_add_local_favorite_picker(self) -> None:
        self._ensure_favorite_file_picker()
        if self._favorite_file_picker:
            self._favorite_file_picker.pick_files(
                allow_multiple=True,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[
                    "jpg",
                    "jpeg",
                    "png",
                    "webp",
                    "bmp",
                    "gif",
                    "avif",
                ],
            )

    def _handle_add_local_favorite_result(
        self, event: ft.FilePickerResultEvent,
    ) -> None:
        if not event.files:
            return
        count = 0
        errors = 0
        folder_id = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else None
        )
        for f in event.files:
            try:
                if not f.path:
                    continue
                item, created = self._favorite_manager.add_local_item(
                    path=f.path,
                    folder_id=folder_id,
                )
                if created:
                    count += 1
            except Exception as exc:
                logger.error(f"添加本地收藏失败: {exc}")
                errors += 1
        # 刷新列表
        self._refresh_favorite_tabs()
        if count and not errors:
            self._show_snackbar(f"已添加 {count} 项本地收藏。")
        elif count and errors:
            self._show_snackbar(
                f"已添加 {count} 项本地收藏，{errors} 项失败。", error=True,
            )
        elif errors:
            self._show_snackbar("添加本地收藏失败。", error=True)

    def _ensure_plugin_file_picker(self) -> None:
        if self._plugin_file_picker is None:
            self._plugin_file_picker = ft.FilePicker(
                on_result=self._handle_import_result,
            )
        if self._plugin_file_picker not in self.page.overlay:
            self.page.overlay.append(self._plugin_file_picker)
            self.page.update()

    def _open_import_picker(self) -> None:
        if not self.plugin_service:
            self._show_snackbar("插件服务不可用。", error=True)
            return
        self._ensure_plugin_file_picker()
        if self._plugin_file_picker:
            self._plugin_file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.ANY,
                allowed_extensions=["py"],
            )

    def _handle_import_result(self, event: ft.FilePickerResultEvent) -> None:
        if not self.plugin_service or not event.files:
            return
        file = event.files[0]
        if not file.path:
            self._show_snackbar("未选择有效的文件。", error=True)
            return
        try:
            result = self.plugin_service.import_plugin(Path(file.path))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"导入插件失败: {exc}")
            self._show_snackbar(f"导入失败：{exc}", error=True)
            return

        if result.error:
            logger.warning(f"导入插件时解析 manifest 失败: {result.error}")

        if not result.identifier:
            self._show_snackbar(
                "插件已导入，但无法识别 manifest，将使用默认设置重新加载。",
            )
            try:
                self.plugin_service.reload()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"重新加载插件失败: {exc}")
                self._show_snackbar(f"重新加载失败：{exc}", error=True)
            return

        self._show_import_permission_dialog(result)

    def _show_import_permission_dialog(self, result: PluginImportResult) -> None:
        if not self.plugin_service:
            return

        self._sync_known_permissions()

        identifier = result.identifier or result.module_name or result.destination.stem
        manifest = result.manifest
        permission_controls: list[ft.Control] = []
        toggles: dict[str, ft.Dropdown] = {}

        description = manifest.description if manifest else ""
        plugin_title = manifest.name if manifest else identifier

        if result.requested_permissions:
            for perm in result.requested_permissions:
                info = self._known_permissions.get(perm)
                label = info.name if info else perm
                detail = info.description if info else "未在权限目录中登记。"
                selector = ft.Dropdown(
                    width=220,
                    label=f"授予 {label}",
                    value="prompt",
                    options=[
                        ft.DropdownOption(key="deny", text="禁用"),
                        ft.DropdownOption(key="prompt", text="下次询问"),
                        ft.DropdownOption(key="allow", text="允许"),
                    ],
                )
                toggles[perm] = selector
                permission_controls.append(
                    ft.Column(
                        [
                            selector,
                            ft.Text(
                                f"权限 ID：{perm}\n{detail}",
                                size=12,
                                color=ft.Colors.GREY,
                            ),
                        ],
                        spacing=4,
                    ),
                )
        else:
            permission_controls.append(
                ft.Text(
                    "该插件未请求额外权限，可直接加载。", size=12, color=ft.Colors.GREY,
                ),
            )

        warning_text: list[ft.Control] = []
        if result.error:
            warning_text.append(
                ft.Text(
                    f"警告：解析 manifest 时出现问题（{result.error}）。将尝试继续加载。",
                    color=ft.Colors.ERROR,
                    size=12,
                ),
            )

        def _on_accept(_: ft.ControlEvent) -> None:
            self._close_dialog()
            self._apply_import_permissions(identifier, toggles)

        def _on_skip(_: ft.ControlEvent) -> None:
            self._close_dialog()
            self._show_snackbar("插件已导入并保持禁用，可稍后在列表中启用。")
            self._refresh_plugin_list()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"新插件：{plugin_title}"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    [
                        ft.Text(
                            identifier,
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                        *(warning_text or []),
                        ft.Text(description, size=12)
                        if description
                        else ft.Container(),
                        ft.Divider(),
                        ft.Column(permission_controls, spacing=8),
                    ],
                    spacing=12,
                ),
            ),
            actions=[
                ft.TextButton("稍后再说", on_click=_on_skip),
                ft.FilledButton("保存设置", on_click=_on_accept),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _apply_import_permissions(
        self, identifier: str, toggles: dict[str, ft.Dropdown],
    ) -> None:
        if not self.plugin_service:
            return

        try:
            for perm, control in toggles.items():
                state = self._state_from_choice(control.value)
                self.plugin_service.update_permission(identifier, perm, state)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"设置导入权限失败: {exc}")
            self._show_snackbar(f"保存权限失败：{exc}", error=True)
            return

        self._show_snackbar("权限已保存，将在启用插件时生效。")
        self._refresh_plugin_list()

    def _build_permission_catalog_section(self) -> ft.Control | None:
        self._sync_known_permissions()
        if not self._known_permissions:
            return None

        items = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.VERIFIED_USER),
                title=ft.Text(f"{permission.name} ({permission.identifier})"),
                subtitle=ft.Text(permission.description),
            )
            for permission in sorted(
                self._known_permissions.values(), key=lambda p: p.identifier,
            )
        ]

        return ft.Column(
            [
                ft.Text("权限说明", size=16, weight=ft.FontWeight.BOLD),
                ft.Column(items, spacing=4),
            ],
            spacing=8,
        )

    def _build_event_definitions_section(self) -> ft.Control | None:
        definitions = self._event_definitions or []
        if not definitions:
            return None

        items: list[ft.Control] = []
        for definition in sorted(definitions, key=lambda d: d.event_type):
            permission_text = (
                "无需权限"
                if not definition.permission
                else f"需要权限：{self._format_permission_label(definition.permission)}"
            )
            items.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.EVENT),
                    title=ft.Text(definition.event_type, selectable=True),
                    subtitle=ft.Text(f"{definition.description}\n{permission_text}"),
                ),
            )

        return ft.Column(
            [
                ft.Text("可用事件", size=16, weight=ft.FontWeight.BOLD),
                ft.Column(items, spacing=4),
            ],
            spacing=8,
        )

    def _format_permission_label(self, permission_id: str) -> str:
        permission = self._known_permissions.get(permission_id)
        if permission:
            return f"{permission.name} ({permission.identifier})"
        return permission_id

    @staticmethod
    def _choice_from_state(state: PermissionState | None) -> str:
        if state is PermissionState.GRANTED:
            return "allow"
        if state is PermissionState.DENIED:
            return "deny"
        return "prompt"

    @staticmethod
    def _state_from_choice(value: str | None) -> PermissionState:
        if value == "allow":
            return PermissionState.GRANTED
        if value == "deny":
            return PermissionState.DENIED
        return PermissionState.PROMPT

    def _show_snackbar(self, message: str, *, error: bool = False) -> None:
        snackbar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.Colors.ERROR if error else None,
        )
        self.page.open(snackbar)

    @staticmethod
    def _abbreviate_text(text: str, max_len: int = 80) -> str:
        if len(text) <= max_len:
            return text
        if max_len <= 3:
            return text[:max_len]
        return text[: max_len - 3] + "..."

    # ------------------------------------------------------------------
    # plugin event helpers
    # ------------------------------------------------------------------
    def _bing_payload_data(self) -> dict[str, Any]:
        data = self.bing_wallpaper or {}
        payload: dict[str, Any] = {
            "available": bool(self.bing_wallpaper_url),
            "title": data.get("title"),
            "description": data.get("copyright") or data.get("desc"),
            "image_url": self.bing_wallpaper_url,
            "download_url": self.bing_wallpaper_url,
            "raw": dict(data) if isinstance(data, dict) else data,
        }
        return payload

    def _spotlight_payload_data(self) -> dict[str, Any]:
        items = self.spotlight_wallpaper or []
        idx = self.spotlight_current_index if items else None
        current = items[idx] if idx is not None and idx < len(items) else None
        if isinstance(current, dict):
            current = dict(current)
        return {
            "available": bool(items),
            "current_index": idx,
            "current": current,
            "items": items,
        }

    def _resolve_bing_entry_id(self, payload: dict[str, Any]) -> str:
        raw = payload.get("raw") or {}
        if isinstance(raw, dict):
            for key in ("startdate", "enddate", "date"):
                value = raw.get(key)
                if value:
                    return str(value)
            if raw.get("url"):
                return str(raw.get("url"))
        if payload.get("image_url"):
            return str(payload["image_url"])
        return f"bing-{int(time.time())}"

    def _resolve_spotlight_entry_id(self, payload: dict[str, Any]) -> str:
        current = payload.get("current")
        if isinstance(current, dict):
            for key in ("id", "identifier", "sha256", "url"):
                value = current.get(key)
                if value:
                    return str(value)
        return f"spotlight-{int(time.time())}"

    def _publish_bing_data(self) -> None:
        if not self._global_data:
            return
        payload = self._bing_payload_data()
        entry_id = (
            self._resolve_bing_entry_id(payload)
            if payload.get("available")
            else (self._bing_data_id or "bing-latest")
        )
        payload_with_meta = dict(payload)
        payload_with_meta["namespace"] = "resource.bing"
        try:
            snapshot = self._global_data.publish(
                "resource.bing", entry_id, payload_with_meta,
            )
            self._bing_data_id = snapshot.get("identifier")
        except GlobalDataError as exc:
            logger.error(f"写入 Bing 全局数据失败: {exc}")

    def _publish_spotlight_data(self) -> None:
        if not self._global_data:
            return
        payload = self._spotlight_payload_data()
        entry_id = (
            self._resolve_spotlight_entry_id(payload)
            if payload.get("available")
            else (self._spotlight_data_id or "spotlight-latest")
        )
        payload_with_meta = dict(payload)
        payload_with_meta["namespace"] = "resource.spotlight"
        try:
            snapshot = self._global_data.publish(
                "resource.spotlight",
                entry_id,
                payload_with_meta,
            )
            self._spotlight_data_id = snapshot.get("identifier")
        except GlobalDataError as exc:
            logger.error(f"写入 Spotlight 全局数据失败: {exc}")

    def _emit_resource_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        try:
            self.event_bus.emit(event_type, payload, source="core")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"派发插件事件失败 {event_type}: {exc}")

    def _emit_download_completed(
        self,
        source: str,
        action: str,
        file_path: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "source": source,
            "action": action,
            "file_path": str(file_path),
        }
        if source == "bing":
            payload.update(self._bing_event_payload())
        elif source == "spotlight":
            payload.update(self._spotlight_event_payload())
        if extra:
            payload.update(extra)
        self._emit_resource_event("resource.download.completed", payload)

    def _bing_event_payload(self) -> dict[str, Any]:
        payload = self._bing_payload_data()
        payload["data_id"] = self._bing_data_id
        payload["namespace"] = "resource.bing"
        payload["error"] = self.bing_error
        return payload

    def _spotlight_event_payload(self) -> dict[str, Any]:
        payload = self._spotlight_payload_data()
        payload["data_id"] = self._spotlight_data_id
        payload["namespace"] = "resource.spotlight"
        payload["error"] = self.spotlight_error
        return payload

    def _emit_bing_action(
        self, action: str, success: bool, extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "action": action,
            "success": success,
        }
        payload.update(self._bing_event_payload())
        if extra:
            payload.update(extra)
        self._emit_resource_event("resource.bing.action", payload)

    def _emit_spotlight_action(
        self,
        action: str,
        success: bool,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "action": action,
            "success": success,
        }
        payload.update(self._spotlight_event_payload())
        if extra:
            payload.update(extra)
        self._emit_resource_event("resource.spotlight.action", payload)

    def _get_license_text(self):
        parts: list[str] = []
        try:
            files = sorted(
                [p for p in LICENSE_PATH.iterdir() if p.is_file()],
                key=lambda p: p.name.lower(),
            )
        except Exception as exc:
            logger.error(f"读取许可证目录失败: {exc}")
            return "暂无许可证信息"

        for fp in files:
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                logger.error(f"读取许可证文件失败: {fp}: {exc}")
                continue
            title = fp.stem
            parts.append(f"# {title}\n\n{content}\n\n---")

        return "\n\n".join(parts) if parts else "暂无许可证信息"

    def _home_settings_dict(self) -> dict[str, Any]:
        data = app_config.get("home_page", {})
        return data if isinstance(data, dict) else {}

    def _home_subdict(self, key: str) -> dict[str, Any]:
        settings = self._home_settings_dict()
        value = settings.get(key)
        return value if isinstance(value, dict) else {}

    def _home_custom_items(self) -> list[dict[str, str]]:
        custom = self._home_subdict("custom")
        items = custom.get("items")
        if not isinstance(items, list):
            return []
        result: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("sentence") or "").strip()
            author = str(item.get("author") or "").strip()
            source = str(item.get("source") or item.get("from") or "").strip()
            if text:
                result.append({"text": text, "author": author, "source": source})
        return result

    async def _fetch_hitokoto_quote(self, settings: dict[str, Any]) -> dict[str, str]:
        hitokoto_settings = settings.get("hitokoto")
        if not isinstance(hitokoto_settings, dict):
            hitokoto_settings = {}
        region = str(hitokoto_settings.get("region") or "domestic").lower()
        base_url = HITOKOTO_API[1] if region == "international" else HITOKOTO_API[0]
        categories = hitokoto_settings.get("categories")
        params: list[tuple[str, str]] = [("encode", "json")]
        if isinstance(categories, list):
            for code in categories:
                code_str = str(code).strip()
                if code_str:
                    params.append(("c", code_str))
        query = urlencode(params, doseq=True) if params else ""
        url = f"{base_url}?{query}" if query else base_url
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
        text = str(data.get("hitokoto") or "").strip()
        author = str(
            data.get("from_who") or data.get("creator") or data.get("author") or "",
        ).strip()
        source = str(data.get("from") or data.get("origin") or "").strip()
        if not text:
            raise ValueError("Empty response from Hitokoto API")
        return {"text": text, "author": author, "source": source}

    async def _fetch_zhaoyu_quote(self, settings: dict[str, Any]) -> dict[str, str]:
        zhaoyu_settings = settings.get("zhaoyu")
        if not isinstance(zhaoyu_settings, dict):
            zhaoyu_settings = {}
        params: list[tuple[str, str]] = []
        for key in ("catalog", "theme", "author"):
            value = str(zhaoyu_settings.get(key) or "all").strip()
            if value:
                params.append((key, value))
        params.append(("suffix", "json"))
        base_url = ZHAOYU_API_URL.rstrip("/")
        query = urlencode(params, doseq=True)
        url = f"{base_url}?{query}" if query else base_url
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
        payload = data.get("data") if isinstance(data, dict) else None
        if not isinstance(payload, dict):
            raise ValueError("Invalid response structure from Zaoyu API")
        text = str(payload.get("sentence") or payload.get("content") or "").strip()
        if not text:
            raise ValueError("Empty response from Zaoyu API")
        author = str(payload.get("author") or "").strip()
        source = str(
            payload.get("name")
            or payload.get("catalog")
            or payload.get("src_url")
            or "",
        ).strip()
        return {"text": text, "author": author, "source": source}

    def _pick_custom_quote(self, settings: dict[str, Any]) -> dict[str, str]:
        items = self._home_custom_items()
        if not items:
            raise ValueError("No custom quotes configured")
        return random.choice(items)

    async def _load_home_quote_data(self) -> dict[str, str]:
        settings = self._home_settings_dict()
        source = str(settings.get("source") or "hitokoto").lower()
        try:
            if source == "zhaoyu":
                return await self._fetch_zhaoyu_quote(settings)
            if source == "custom":
                return self._pick_custom_quote(settings)
            return await self._fetch_hitokoto_quote(settings)
        except Exception as exc:
            logger.error("获取主页语句失败: {error}", error=str(exc))
            return {"text": "一言获取失败", "author": "", "source": ""}

    def _format_home_quote(self, data: dict[str, Any]) -> str:
        text = str(data.get("text") or "").strip()
        if not text:
            return "一言获取失败"
        display = f"「{text}」"
        show_author = bool(app_config.get("home_page.show_author", True))
        show_source = bool(app_config.get("home_page.show_source", True))
        meta_parts: list[str] = []
        author = str(data.get("author") or "").strip()
        source = str(data.get("source") or "").strip()
        if show_author and author:
            meta_parts.append(author)
        if show_source and source:
            meta_parts.append(source)
        if meta_parts:
            display = f"{display}\n—— {' · '.join(meta_parts)}"
        return display

    async def _show_home_quote(self):
        if self.home_quote_text is None or self.home_quote_loading is None:
            return
        self.home_quote_text.value = ""
        self.home_quote_loading.visible = True
        self.page.update()
        data = await self._load_home_quote_data()
        self.home_quote_text.value = self._format_home_quote(data)
        self.home_quote_loading.visible = False
        self.page.update()

    def refresh_home_quote(self, _=None):
        self.page.run_task(self._show_home_quote)

    def _update_wallpaper(self):
        self.wallpaper_path = ltwapi.get_sys_wallpaper()

    def _build_wallpaper_label_span(self) -> ft.TextSpan:
        path = self.wallpaper_path
        label = "当前壁纸：未检测到桌面壁纸"
        style = ft.TextStyle()
        on_click = None
        if path:
            try:
                name = Path(path).name or str(path)
            except (OSError, TypeError, ValueError):
                name = str(path)
            label = f"当前壁纸：{name}"
            style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)

            def on_click(_):
                return self._copy_sys_wallpaper_path()

        return ft.TextSpan(label, style, on_click=on_click)

    def _copy_sys_wallpaper_path(self):
        if not self.wallpaper_path:
            self.page.open(
                ft.SnackBar(
                    ft.Row(
                        controls=[
                            ft.Icon(
                                name=ft.Icons.WARNING_AMBER,
                                color=ft.Colors.ON_SECONDARY,
                            ),
                            ft.Text("未检测到壁纸路径，请先刷新~"),
                        ],
                    ),
                ),
            )
            return
        pyperclip.copy(self.wallpaper_path)
        self.page.open(
            ft.SnackBar(
                ft.Row(
                    controls=[
                        ft.Icon(name=ft.Icons.DONE, color=ft.Colors.ON_SECONDARY),
                        ft.Text("壁纸路径已复制~ (。・∀・)"),
                    ],
                ),
            ),
        )

    def _refresh_home(self, _):
        self._update_wallpaper()
        self.img.src = self.wallpaper_path or ""
        self.file_name.spans = [self._build_wallpaper_label_span()]
        self.refresh_home_quote()

        self.page.update()

    async def _load_bing_wallpaper(self):
        max_attempts = 3
        last_error: Exception | None = None
        self.bing_wallpaper = None
        self.bing_wallpaper_url = None
        for attempt in range(1, max_attempts + 1):
            try:
                self.bing_wallpaper = await ltwapi.get_bing_wallpaper_async()
                base = self.bing_wallpaper.get("url")
                if not base:
                    raise RuntimeError("Bing 响应缺少壁纸地址")
                self.bing_wallpaper_url = f"https://www.bing.com{base}".replace(
                    "1920x1080", "UHD",
                )
                self.bing_error = None
                break
            except Exception as exc:
                self.bing_wallpaper = None
                self.bing_wallpaper_url = None
                last_error = exc
                self.bing_error = str(exc)
                if attempt < max_attempts:
                    await asyncio.sleep(1.5)
        else:
            logger.error(
                "Bing 壁纸加载失败，已重试 {count} 次: {error}",
                count=max_attempts,
                error=last_error,
            )
        self.bing_loading = False
        self._publish_bing_data()
        self._emit_resource_event(
            "resource.bing.updated", self._bing_event_payload(),
        )
        self._refresh_bing_tab()

    async def _load_spotlight_wallpaper(self):
        max_attempts = 3
        last_error: Exception | None = None
        self.spotlight_wallpaper = []
        self.spotlight_wallpaper_url = None
        for attempt in range(1, max_attempts + 1):
            try:
                self.spotlight_wallpaper = await ltwapi.get_spotlight_wallpaper_async()
                if not self.spotlight_wallpaper:
                    raise RuntimeError("Windows 聚焦接口未返回任何壁纸")
                self.spotlight_current_index = 0
                self.spotlight_wallpaper_url = [
                    item.get("url")
                    for item in self.spotlight_wallpaper
                    if isinstance(item, dict) and item.get("url")
                ]
                if not self.spotlight_wallpaper_url:
                    raise RuntimeError("Windows 聚焦接口缺少壁纸地址")
                self.spotlight_error = None
                break
            except Exception as exc:
                self.spotlight_wallpaper = []
                self.spotlight_wallpaper_url = None
                last_error = exc
                self.spotlight_error = str(exc)
                if attempt < max_attempts:
                    await asyncio.sleep(1.5)
        else:
            logger.error(
                "加载 Windows 聚焦壁纸失败，已重试 {count} 次: {error}",
                count=max_attempts,
                error=last_error,
            )
        self.spotlight_loading = False
        self._publish_spotlight_data()
        self._emit_resource_event(
            "resource.spotlight.updated", self._spotlight_event_payload(),
        )
        self._refresh_spotlight_tab()

    def _refresh_bing_tab(self):
        for tab in self.resource_tabs.tabs:
            if tab.text == "Bing 每日":
                tab.content = self._build_bing_daily_content()
                break
        self.page.update()

    def _refresh_spotlight_tab(self):
        for tab in self.resource_tabs.tabs:
            if tab.text == "Windows 聚焦":
                tab.content = self._build_spotlight_daily_content()
                break
        self.page.update()

    def _ensure_home_export_picker(self) -> None:
        if self._home_export_picker is None:
            self._home_export_picker = ft.FilePicker(
                on_result=self._handle_home_export_result,
            )
        if self.page and self._home_export_picker not in self.page.overlay:
            self.page.overlay.append(self._home_export_picker)
            self.page.update()

    def _handle_home_export_clicked(self, _: ft.ControlEvent | None) -> None:
        path = self.wallpaper_path
        if not path:
            self._show_snackbar("当前没有壁纸可导出。", error=True)
            return
        try:
            source = Path(path)
        except Exception as exc:
            logger.error("无法解析壁纸路径: {error}", error=str(exc))
            self._show_snackbar("当前壁纸路径无效。", error=True)
            return
        if not source.exists():
            self._show_snackbar("壁纸文件不存在或已被删除。", error=True)
            return
        self._ensure_home_export_picker()
        picker = self._home_export_picker
        if picker is None:
            self._show_snackbar("无法打开文件对话框。", error=True)
            return
        self._home_pending_export_source = source
        file_name = source.name or "wallpaper.jpg"
        initial_dir = source.parent if source.parent.exists() else Path.home()
        try:
            picker.save_file(
                file_name=file_name,
                initial_directory=str(initial_dir),
            )
        except Exception as exc:
            logger.error("另存为对话框打开失败: {error}", error=str(exc))
            self._show_snackbar("无法打开另存为对话框。", error=True)
            self._home_pending_export_source = None

    def _handle_home_export_result(self, event: ft.FilePickerResultEvent) -> None:
        source = self._home_pending_export_source
        self._home_pending_export_source = None
        if source is None or not source.exists():
            return
        if not event.path:
            return
        target = Path(event.path)
        self.page.run_task(self._home_export_save_to_path, source, target)

    async def _home_export_save_to_path(self, source: Path, target: Path) -> None:
        def _copy() -> Path:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return target

        try:
            final_path = await asyncio.to_thread(_copy)
        except Exception as exc:
            logger.error("导出壁纸失败: {error}", error=str(exc))
            self._show_snackbar("导出失败，请查看日志。", error=True)
            return
        self._show_snackbar(f"已保存到 {final_path}")

    def _handle_home_add_wallpaper_to_favorite(self, _: ft.ControlEvent | None) -> None:
        path = self.wallpaper_path
        if not path:
            self._show_snackbar("当前没有壁纸可收藏。", error=True)
            return
        try:
            source = Path(path)
        except Exception as exc:
            logger.error("无法解析当前壁纸路径: {error}", error=str(exc))
            self._show_snackbar("当前壁纸路径无效。", error=True)
            return
        if not source.exists():
            self._show_snackbar("壁纸文件不存在或已被删除。", error=True)
            return
        folder_id = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else None
        )
        try:
            item, created = self._favorite_manager.add_local_item(
                path=str(source),
                folder_id=folder_id,
            )
        except Exception as exc:
            logger.error("添加当前壁纸到收藏失败: {error}", error=str(exc))
            self._show_snackbar("收藏失败，请查看日志。", error=True)
            return
        if item:
            self._schedule_favorite_classification(item.id)
        self._refresh_favorite_tabs()
        if created:
            self._show_snackbar("已将当前壁纸加入收藏。")
        else:
            self._show_snackbar("收藏已更新。")

    def _handle_home_change_wallpaper(self, _: ft.ControlEvent | None) -> None:
        success = self._auto_change_service.trigger_immediate_change()
        if success:
            self._show_snackbar("已触发自动更换，将立即刷新壁纸。")
        else:
            self._show_snackbar("请先启用间隔或轮播模式后再使用该功能。", error=True)

    def _build_home(self):
        from app.paths import ASSET_DIR  # local import to avoid circular dependencies

        self.file_name = ft.Text(spans=[self._build_wallpaper_label_span()])

        self.img = ft.Image(
            src=self.wallpaper_path or "",
            height=200,
            border_radius=10,
            fit=ft.ImageFit.COVER,
            tooltip="当前计算机的壁纸",
            error_content=ft.Container(ft.Text("图片已失效，请刷新数据~"), padding=20),
        )
        self.home_quote_loading = ft.ProgressRing(visible=False, width=24, height=24)
        self.home_quote_text = ft.Text("", size=16, font_family="HITOKOTOFont")
        refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="刷新语句",
            on_click=self.refresh_home_quote,
        )
        self._home_change_button = ft.TextButton(
            "更换",
            icon=ft.Icons.PHOTO_LIBRARY,
            tooltip="立即触发自动更换（仅限间隔与轮播模式）",
            on_click=self._handle_home_change_wallpaper,
        )
        config = self._auto_current_config()
        enabled = bool(config.get("enabled", False))
        mode = str(config.get("mode") or "off")
        self._update_home_change_button_state(
            interval_enabled=enabled and mode == "interval",
            slideshow_enabled=enabled and mode == "slideshow",
        )
        return ft.Container(
            ft.Column(
                [
                    ft.Text("当前壁纸", size=30),
                    ft.Row(
                        [
                            self.img,
                            ft.Column(
                                [
                                    ft.TextButton(
                                        "导出",
                                        icon=ft.Icons.SAVE_ALT,
                                        tooltip="另存为当前壁纸",
                                        on_click=self._handle_home_export_clicked,
                                    ),
                                    self._home_change_button,
                                    ft.TextButton(
                                        "收藏",
                                        icon=ft.Icons.STAR,
                                        tooltip="将当前壁纸加入收藏",
                                        on_click=self._handle_home_add_wallpaper_to_favorite,
                                    ),
                                    ft.TextButton(
                                        "刷新",
                                        tooltip="刷新当前壁纸信息",
                                        icon=ft.Icons.REFRESH,
                                        on_click=self._refresh_home,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.END,
                            ),
                        ],
                    ),
                    self.file_name,
                    ft.Container(
                        content=ft.Divider(height=1, thickness=1),
                        margin=ft.margin.only(top=30),
                    ),
                    ft.Row(
                        [self.home_quote_loading, self.home_quote_text, refresh_btn],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Image(src=ASSET_DIR / "images" / "1.gif"),
                ],
            ),
            expand=True,
            padding=16,
        )

    def _update_home_settings_visibility(self, source: str) -> None:
        target = source.lower().strip()
        if self._home_hitokoto_section is not None:
            self._home_hitokoto_section.visible = target == "hitokoto"
            self._home_hitokoto_section.update()
        if self._home_zhaoyu_section is not None:
            self._home_zhaoyu_section.visible = target == "zhaoyu"
            self._home_zhaoyu_section.update()
        if self._home_custom_section is not None:
            self._home_custom_section.visible = target == "custom"
            self._home_custom_section.update()

    def _handle_home_source_change(self, e: ft.ControlEvent) -> None:
        value = str(getattr(e.control, "value", "") or "hitokoto").lower()
        if value not in {"hitokoto", "zhaoyu", "custom"}:
            value = "hitokoto"
        app_config.set("home_page.source", value)
        if value == "zhaoyu":
            app_config.set("home_page.zhaoyu.catalog", "all")
            app_config.set("home_page.zhaoyu.theme", "all")
            app_config.set("home_page.zhaoyu.author", "all")
        self._update_home_settings_visibility(value)
        self.refresh_home_quote()

    def _handle_home_show_author_toggle(self, e: ft.ControlEvent) -> None:
        value = bool(getattr(e.control, "value", False))
        app_config.set("home_page.show_author", value)
        self.refresh_home_quote()

    def _handle_home_show_source_toggle(self, e: ft.ControlEvent) -> None:
        value = bool(getattr(e.control, "value", False))
        app_config.set("home_page.show_source", value)
        self.refresh_home_quote()

    def _handle_home_hitokoto_region_change(self, e: ft.ControlEvent) -> None:
        value = str(getattr(e.control, "value", "") or "domestic").lower()
        if value not in {"domestic", "international"}:
            value = "domestic"
        app_config.set("home_page.hitokoto.region", value)
        if str(app_config.get("home_page.source", "hitokoto")).lower() == "hitokoto":
            self.refresh_home_quote()

    def _handle_home_hitokoto_category_change(
        self, category: str, selected: bool,
    ) -> None:
        existing = app_config.get("home_page.hitokoto.categories", [])
        values = [
            str(item).strip() for item in existing if isinstance(item, str) and item
        ]
        if selected and category not in values:
            values.append(category)
        elif not selected and category in values:
            values.remove(category)
        app_config.set("home_page.hitokoto.categories", values)
        if str(app_config.get("home_page.source", "hitokoto")).lower() == "hitokoto":
            self.refresh_home_quote()

    def _build_home_custom_entry_row(
        self, index: int, item: dict[str, str],
    ) -> ft.Control:
        sentence_field = ft.TextField(
            label=f"语句 {index + 1}",
            value=item.get("text", ""),
            multiline=True,
            min_lines=1,
            max_lines=3,
            data={"index": index, "field": "text"},
            on_change=self._handle_home_custom_entry_field_change,
            expand=True,
        )
        author_field = ft.TextField(
            label="作者（可选）",
            value=item.get("author", ""),
            data={"index": index, "field": "author"},
            on_change=self._handle_home_custom_entry_field_change,
            width=220,
        )
        source_field = ft.TextField(
            label="来源（可选）",
            value=item.get("source", ""),
            data={"index": index, "field": "source"},
            on_change=self._handle_home_custom_entry_field_change,
            width=220,
        )
        remove_button = ft.IconButton(
            icon=ft.Icons.DELETE_FOREVER,
            tooltip="删除此语句",
            on_click=lambda _=None, idx=index: self._handle_home_custom_remove_entry(
                idx,
            ),
        )
        return ft.Card(
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    [
                        sentence_field,
                        ft.Row(
                            [author_field, source_field],
                            spacing=12,
                            run_spacing=12,
                            wrap=True,
                        ),
                        ft.Row(
                            [remove_button],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                    spacing=12,
                ),
            ),
        )

    def _refresh_home_custom_entries_ui(self) -> None:
        if self._home_custom_entries_column is None:
            return
        controls: list[ft.Control] = []
        if not self._home_custom_entries:
            controls.append(
                ft.Text(
                    "暂无自定义语句。点击下方“新增语句”按钮进行添加。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
            )
        else:
            for idx, item in enumerate(self._home_custom_entries):
                controls.append(self._build_home_custom_entry_row(idx, item))
        self._home_custom_entries_column.controls = controls
        if getattr(self._home_custom_entries_column, "page", None):
            self._home_custom_entries_column.update()

    def _handle_home_custom_add_entry(self, _: ft.ControlEvent | None = None) -> None:
        self._home_custom_entries.append({"text": "", "author": "", "source": ""})
        app_config.set(
            "home_page.custom.items", copy.deepcopy(self._home_custom_entries),
        )
        self._refresh_home_custom_entries_ui()

    def _handle_home_custom_remove_entry(self, index: int) -> None:
        if 0 <= index < len(self._home_custom_entries):
            self._home_custom_entries.pop(index)
            app_config.set(
                "home_page.custom.items", copy.deepcopy(self._home_custom_entries),
            )
            self._refresh_home_custom_entries_ui()
            if str(app_config.get("home_page.source", "hitokoto")).lower() == "custom":
                self.refresh_home_quote()

    def _handle_home_custom_entry_field_change(self, e: ft.ControlEvent) -> None:
        meta = getattr(e.control, "data", None)
        if not isinstance(meta, dict):
            return
        index = meta.get("index")
        field = meta.get("field")
        if not isinstance(index, int) or field not in {"text", "author", "source"}:
            return
        if not (0 <= index < len(self._home_custom_entries)):
            return
        value = str(getattr(e.control, "value", "") or "")
        self._home_custom_entries[index][field] = value
        app_config.set(
            "home_page.custom.items", copy.deepcopy(self._home_custom_entries),
        )

    def _ensure_home_custom_file_pickers(self) -> None:
        changed = False
        if self._home_custom_import_picker is None:
            self._home_custom_import_picker = ft.FilePicker(
                on_result=self._handle_home_custom_import_result,
            )
            changed = True
        if self._home_custom_export_picker is None:
            self._home_custom_export_picker = ft.FilePicker(
                on_result=self._handle_home_custom_export_result,
            )
            changed = True
        for picker in (
            self._home_custom_import_picker,
            self._home_custom_export_picker,
        ):
            if picker and self.page and picker not in self.page.overlay:
                self.page.overlay.append(picker)
                changed = True
        if changed and self.page is not None:
            self.page.update()

    def _open_home_custom_import_picker(self, _: ft.ControlEvent | None = None) -> None:
        self._ensure_home_custom_file_pickers()
        if self._home_custom_import_picker is None:
            self._show_snackbar("无法打开文件选择器。", error=True)
            return
        self._home_custom_import_picker.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
        )

    def _handle_home_custom_import_result(
        self, event: ft.FilePickerResultEvent,
    ) -> None:
        if not event.files:
            return
        file = event.files[0]
        if not getattr(file, "path", None):
            self._show_snackbar("未选择有效的文件。", error=True)
            return
        path = Path(file.path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("导入自定义语句失败: {error}", error=str(exc))
            self._show_snackbar("导入失败，请确认文件格式。", error=True)
            return

        raw_items = None
        if isinstance(data, dict):
            raw_items = data.get("items")
        elif isinstance(data, list):
            raw_items = data
        if not isinstance(raw_items, list):
            self._show_snackbar("文件中未找到有效的语句列表。", error=True)
            return

        imported: list[dict[str, str]] = []
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or entry.get("sentence") or "").strip()
            author = str(entry.get("author") or "").strip()
            source = str(entry.get("source") or entry.get("from") or "").strip()
            if text:
                imported.append({"text": text, "author": author, "source": source})

        if not imported:
            self._show_snackbar("文件中没有有效的语句。", error=True)
            return

        self._home_custom_entries = imported
        app_config.set(
            "home_page.custom.items", copy.deepcopy(self._home_custom_entries),
        )
        self._refresh_home_custom_entries_ui()
        if str(app_config.get("home_page.source", "hitokoto")).lower() == "custom":
            self.refresh_home_quote()
        self._show_snackbar("已导入自定义语句。")

    def _open_home_custom_export_picker(self, _: ft.ControlEvent | None = None) -> None:
        if not self._home_custom_entries:
            self._show_snackbar("暂无自定义语句可导出。", error=True)
            return
        self._ensure_home_custom_file_pickers()
        if self._home_custom_export_picker is None:
            self._show_snackbar("无法打开文件对话框。", error=True)
            return
        self._home_custom_export_picker.save_file(
            file_name="home_quotes.json",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
        )

    def _handle_home_custom_export_result(
        self, event: ft.FilePickerResultEvent,
    ) -> None:
        if not event.path:
            return
        if not self._home_custom_entries:
            self._show_snackbar("暂无自定义语句可导出。", error=True)
            return
        payload = {
            "scheme": "littletree_home_quotes_v1",
            "items": copy.deepcopy(self._home_custom_entries),
        }
        try:
            Path(event.path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("导出自定义语句失败: {error}", error=str(exc))
            self._show_snackbar("导出失败，请重试。", error=True)
            return
        self._show_snackbar("已导出自定义语句。")

    def _build_home_settings_section(self) -> ft.Control:
        source_value = str(
            app_config.get("home_page.source", "hitokoto") or "hitokoto",
        ).lower()

        self._home_source_dropdown = ft.Dropdown(
            label="主页语句源",
            value=source_value,
            options=[
                ft.DropdownOption(key="hitokoto", text="一言"),
                ft.DropdownOption(key="zhaoyu", text="诏预"),
                ft.DropdownOption(key="custom", text="自定义语句"),
            ],
            on_change=self._handle_home_source_change,
            width=260,
        )

        self._home_show_author_switch = ft.Switch(
            label="显示作者",
            value=bool(app_config.get("home_page.show_author", True)),
            on_change=self._handle_home_show_author_toggle,
        )
        self._home_show_source_switch = ft.Switch(
            label="显示来源",
            value=bool(app_config.get("home_page.show_source", True)),
            on_change=self._handle_home_show_source_toggle,
        )

        hitokoto_region = str(
            app_config.get("home_page.hitokoto.region", "domestic") or "domestic",
        ).lower()
        if hitokoto_region not in {"domestic", "international"}:
            hitokoto_region = "domestic"
        self._home_hitokoto_region_dropdown = ft.Dropdown(
            label="一言服务地区",
            value=hitokoto_region,
            options=[
                ft.DropdownOption(key="domestic", text="国内节点"),
                ft.DropdownOption(key="international", text="国际节点"),
            ],
            on_change=self._handle_home_hitokoto_region_change,
            width=220,
        )

        categories_value = app_config.get("home_page.hitokoto.categories", [])
        selected_categories = {
            str(item).strip()
            for item in categories_value
            if isinstance(item, str) and item
        }
        self._home_hitokoto_category_checks = {}
        category_controls: list[ft.Control] = []
        for code, label in HITOKOTO_CATEGORY_LABELS.items():
            checkbox = ft.Checkbox(
                label=f"{label} ({code})",
                value=code in selected_categories,
                on_change=lambda e,
                cat=code: self._handle_home_hitokoto_category_change(
                    cat, bool(getattr(e.control, "value", False)),
                ),
            )
            self._home_hitokoto_category_checks[code] = checkbox
            category_controls.append(checkbox)

        self._home_hitokoto_section = ft.Column(
            controls=[
                ft.Text("一言设置", size=16, weight=ft.FontWeight.BOLD),
                self._home_hitokoto_region_dropdown,
                ft.Text("分类筛选（留空表示全部随机）", size=12, color=ft.Colors.GREY),
                ft.Row(
                    controls=category_controls,
                    spacing=12,
                    run_spacing=12,
                    wrap=True,
                ),
            ],
            spacing=12,
            visible=source_value == "hitokoto",
        )

        # zhaoyu_settings = self._home_subdict("zhaoyu")
        # catalog_value = str(zhaoyu_settings.get("catalog", "all") or "all")
        # theme_value = str(zhaoyu_settings.get("theme", "all") or "all")
        # author_value = str(zhaoyu_settings.get("author", "all") or "all")

        def _pill(text: str) -> ft.Container:
            return ft.Container(
                content=ft.Text(text, size=12, color=ft.Colors.ON_SECONDARY_CONTAINER),
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=16,
            )

        self._home_zhaoyu_section = ft.Column(
            controls=[
                ft.Text("诏预 API 设置", size=16, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "诏预接口当前固定使用默认参数，暂不支持自定义分类、主题或古籍。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                # ft.Row(
                #     controls=[
                #         _pill(f"catalog：{catalog_value}"),
                #         _pill(f"theme：{theme_value}"),
                #         _pill(f"author：{author_value}"),
                #     ],
                #     spacing=12,
                #     run_spacing=12,
                #     wrap=True,
                # ),
            ],
            spacing=12,
            visible=source_value == "zhaoyu",
        )

        self._home_custom_entries = self._home_custom_items()
        self._home_custom_entries_column = ft.GridView(
            expand=True,
            runs_count=0,
            max_extent=420,
            spacing=12,
            run_spacing=12,
            child_aspect_ratio=0.75,
            controls=[],
        )
        self._refresh_home_custom_entries_ui()
        custom_grid_container = ft.Container(
            content=self._home_custom_entries_column,
            height=360,
            padding=ft.padding.only(right=4),
        )
        custom_actions = ft.Row(
            controls=[
                ft.TextButton(
                    "新增语句",
                    icon=ft.Icons.ADD,
                    on_click=self._handle_home_custom_add_entry,
                ),
                ft.TextButton(
                    "导入",
                    icon=ft.Icons.UPLOAD_FILE,
                    on_click=self._open_home_custom_import_picker,
                ),
                ft.TextButton(
                    "导出",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=self._open_home_custom_export_picker,
                ),
            ],
            spacing=12,
            run_spacing=12,
            wrap=True,
        )
        self._home_custom_section = ft.Column(
            controls=[
                ft.Text("自定义语句", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("将随机展示列表中的语句。", size=12, color=ft.Colors.GREY),
                custom_grid_container,
                custom_actions,
            ],
            spacing=12,
            visible=source_value == "custom",
        )

        return ft.Column(
            controls=[
                ft.Text("主页内容", size=20, weight=ft.FontWeight.BOLD),
                self._home_source_dropdown,
                ft.Text(
                    "选择主页语句来源，并配置附加信息显示。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Row(
                    [self._home_show_author_switch, self._home_show_source_switch],
                    spacing=16,
                    wrap=True,
                ),
                self._home_hitokoto_section,
                self._home_zhaoyu_section,
                self._home_custom_section,
            ],
            spacing=16,
            tight=True,
        )

    # ------------------------------------------------------------------
    # startup helpers
    # ------------------------------------------------------------------

    def _normalize_startup_order(self, value: str | None) -> str:
        raw = str(value or "").lower()
        if raw == "shuffle":
            return ORDER_RANDOM
        if raw in {ORDER_RANDOM, ORDER_RANDOM_NO_REPEAT, ORDER_SEQUENTIAL}:
            return raw
        return ORDER_RANDOM

    def _startup_wallpaper_config(self) -> dict[str, Any]:
        data = app_config.get("startup.wallpaper_change", {}) or {}
        if not isinstance(data, dict):
            data = {}
        list_ids = [str(entry) for entry in data.get("list_ids", []) if entry]
        order = self._normalize_startup_order(data.get("order"))
        delay_raw = data.get("delay_seconds", 0)
        try:
            delay_seconds = max(0, int(delay_raw))
        except (TypeError, ValueError):
            delay_seconds = 0
        fixed_image = data.get("fixed_image") or None
        return {
            "enabled": bool(data.get("enabled", False)),
            "list_ids": list_ids,
            "fixed_image": fixed_image,
            "order": order,
            "delay_seconds": delay_seconds,
        }

    def _save_startup_wallpaper_config(self, config: dict[str, Any]) -> None:
        base = app_config.get("startup.wallpaper_change", {}) or {}
        if not isinstance(base, dict):
            base = {}
        base.update(
            {
                "enabled": bool(config.get("enabled", False)),
                "list_ids": [str(item) for item in config.get("list_ids", []) if item],
                "fixed_image": config.get("fixed_image") or None,
                "order": self._normalize_startup_order(config.get("order")),
                "delay_seconds": max(0, int(config.get("delay_seconds", 0) or 0)),
            },
        )
        app_config.set("startup.wallpaper_change", base)
        self._refresh_startup_wallpaper_controls()

    def _refresh_startup_wallpaper_controls(self) -> None:
        config = self._startup_wallpaper_config()
        if self._startup_wallpaper_switch is not None:
            self._startup_wallpaper_switch.value = config["enabled"]
            if self._startup_wallpaper_switch.page is not None:
                self._startup_wallpaper_switch.update()
        if self._startup_wallpaper_order_dropdown is not None:
            self._startup_wallpaper_order_dropdown.value = config["order"]
            if self._startup_wallpaper_order_dropdown.page is not None:
                self._startup_wallpaper_order_dropdown.update()
        if self._startup_wallpaper_delay_field is not None:
            self._startup_wallpaper_delay_field.value = str(config["delay_seconds"])
            self._startup_wallpaper_delay_field.error_text = None
            if self._startup_wallpaper_delay_field.page is not None:
                self._startup_wallpaper_delay_field.update()
        self._update_startup_fixed_image_display(config.get("fixed_image"))
        self._rebuild_startup_wallpaper_list_checks()

    def _rebuild_startup_wallpaper_list_checks(self) -> None:
        column = self._startup_wallpaper_lists_column
        if column is None:
            return
        config = self._startup_wallpaper_config()
        selected = set(config.get("list_ids", []))
        column.controls.clear()
        self._startup_wallpaper_list_checks = {}
        lists = self._auto_list_store.all()
        if not lists:
            column.controls.append(
                ft.Text(
                    "暂无可用自动更换列表，请先在“壁纸”页创建。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
            )
        else:
            for auto_list in lists:
                checkbox = ft.Checkbox(
                    label=f"{auto_list.name} ({len(auto_list.entries)} 条)",
                    value=auto_list.id in selected,
                    on_change=lambda e, list_id=auto_list.id: self._handle_startup_wallpaper_list_toggle(
                        list_id,
                        bool(getattr(e.control, "value", False)),
                    ),
                )
                checkbox.disabled = False
                self._startup_wallpaper_list_checks[auto_list.id] = checkbox
                column.controls.append(checkbox)
        if column.page is not None:
            column.update()

    def _handle_startup_auto_switch(self, event: ft.ControlEvent) -> None:
        desired = bool(getattr(event.control, "value", False))
        app_config.set("startup.auto_start", desired)
        try:
            manager = StartupManager()
            if desired:
                manager.enable_startup()
                self._show_snackbar("已尝试添加至开机自启。")
            else:
                manager.disable_startup()
                self._show_snackbar("已尝试移除开机自启。")
        except Exception as exc:  # pragma: no cover - platform specific
            logger.error(f"更新开机启动状态失败: {exc}")
            event.control.value = not desired
            if event.control.page is not None:
                event.control.update()
            self._show_snackbar("无法修改开机启动状态，请查看日志。", error=True)
        finally:
            self._refresh_startup_auto_status()

    def _refresh_startup_auto_status(self) -> None:
        if self._startup_auto_status_text is None:
            return
        try:
            enabled = StartupManager().is_startup_enabled()
            text = "当前状态：已添加到开机启动" if enabled else "当前状态：未添加到开机启动"
            color = ft.Colors.GREEN if enabled else ft.Colors.GREY
        except Exception as exc:  # pragma: no cover - Windows-only
            logger.error(f"检查开机启动状态失败: {exc}")
            text = "当前状态：无法读取（仅支持 Windows）"
            color = ft.Colors.ERROR
        self._startup_auto_status_text.value = text
        self._startup_auto_status_text.color = color
        if self._startup_auto_status_text.page is not None:
            self._startup_auto_status_text.update()

    def _handle_startup_wallpaper_toggle(self, event: ft.ControlEvent) -> None:
        config = self._startup_wallpaper_config()
        config["enabled"] = bool(getattr(event.control, "value", False))
        self._save_startup_wallpaper_config(config)

    def _handle_startup_wallpaper_list_toggle(self, list_id: str, enabled: bool) -> None:
        config = self._startup_wallpaper_config()
        ids = [item for item in config.get("list_ids", []) if item]
        if enabled and list_id not in ids:
            ids.append(list_id)
        if not enabled:
            ids = [item for item in ids if item != list_id]
        config["list_ids"] = ids
        self._save_startup_wallpaper_config(config)

    def _handle_startup_wallpaper_order_change(self, event: ft.ControlEvent) -> None:
        config = self._startup_wallpaper_config()
        config["order"] = self._normalize_startup_order(getattr(event.control, "value", None))
        self._save_startup_wallpaper_config(config)

    def _handle_startup_wallpaper_delay_change(self, event: ft.ControlEvent) -> None:
        raw_value = str(getattr(event.control, "value", "") or "").strip()
        try:
            delay = max(0, int(raw_value))
        except ValueError:
            event.control.error_text = "请输入非负整数"
            if event.control.page is not None:
                event.control.update()
            return
        event.control.error_text = None
        if event.control.page is not None:
            event.control.update()
        config = self._startup_wallpaper_config()
        config["delay_seconds"] = delay
        self._save_startup_wallpaper_config(config)

    def _startup_open_fixed_image_picker(self) -> None:
        self._auto_open_fixed_image_picker("startup")

    def _startup_set_fixed_image(self, path: str | None) -> None:
        config = self._startup_wallpaper_config()
        config["fixed_image"] = path or None
        self._save_startup_wallpaper_config(config)

    def _startup_clear_fixed_image(self) -> None:
        self._startup_set_fixed_image(None)

    def _update_startup_fixed_image_display(self, path: str | None) -> None:
        if self._startup_wallpaper_fixed_image_display is not None:
            self._startup_wallpaper_fixed_image_display.value = path or "未选择"
            self._startup_wallpaper_fixed_image_display.color = (
                ft.Colors.ON_SURFACE if path else ft.Colors.GREY
            )
            if self._startup_wallpaper_fixed_image_display.page is not None:
                self._startup_wallpaper_fixed_image_display.update()
        if self._startup_wallpaper_clear_button is not None:
            self._startup_wallpaper_clear_button.disabled = not bool(path)
            if self._startup_wallpaper_clear_button.page is not None:
                self._startup_wallpaper_clear_button.update()

    def _handle_startup_wallpaper_run_now(self, _: ft.ControlEvent | None = None) -> None:
        config = self._startup_wallpaper_config()
        if not config.get("list_ids") and not config.get("fixed_image"):
            self._show_snackbar("请先选择自动更换列表或固定图片。", error=True)
            return
        self._schedule_startup_wallpaper_task(config, initiated_by_user=True)

    def _schedule_startup_wallpaper_task(
        self,
        config: dict[str, Any],
        *,
        initiated_by_user: bool,
    ) -> None:
        page = self.page
        if page is None:
            return
        list_ids = config.get("list_ids") or []
        fixed_image = config.get("fixed_image")
        if not list_ids and not fixed_image:
            if initiated_by_user:
                self._show_snackbar("缺少可用的列表或固定图片。", error=True)
            logger.info("开机壁纸任务跳过：未配置列表或固定图片。")
            return

        async def _runner() -> None:
            delay = 0 if initiated_by_user else int(config.get("delay_seconds", 0))
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                await self._auto_change_service.ensure_running()
                success = await self._auto_change_service.perform_custom_change(
                    list_ids,
                    fixed_image,
                    order=config.get("order"),
                )
                if initiated_by_user:
                    if success:
                        self._show_snackbar("已完成一次壁纸更换。")
                    else:
                        self._show_snackbar("未找到可用壁纸，请检查列表内容。", error=True)
            except Exception as exc:  # pragma: no cover - runtime safety
                logger.error(f"执行开机壁纸任务失败: {exc}")
                if initiated_by_user:
                    self._show_snackbar("执行失败，请查看日志。", error=True)

        page.run_task(_runner())

    def run_startup_wallpaper_change(self) -> None:
        config = self._startup_wallpaper_config()
        if not config.get("enabled"):
            return
        self._schedule_startup_wallpaper_task(config, initiated_by_user=False)

    def _build_startup_settings_section(self) -> ft.Control:
        auto_start_enabled = bool(app_config.get("startup.auto_start", False))
        self._startup_auto_switch = ft.Switch(
            label="开机自启动（Windows）",
            value=auto_start_enabled,
            on_change=self._handle_startup_auto_switch,
        )
        self._startup_auto_status_text = ft.Text("状态读取中…", size=12, color=ft.Colors.GREY)
        self._refresh_startup_auto_status()

        startup_wallpaper_config = self._startup_wallpaper_config()
        self._startup_wallpaper_switch = ft.Switch(
            label="开机后自动执行一次壁纸更换",
            value=startup_wallpaper_config["enabled"],
            on_change=self._handle_startup_wallpaper_toggle,
        )

        self._startup_wallpaper_lists_column = ft.Column(spacing=4, tight=True)
        self._rebuild_startup_wallpaper_list_checks()

        self._startup_wallpaper_order_dropdown = ft.Dropdown(
            label="列表顺序",
            value=startup_wallpaper_config["order"],
            options=[
                ft.DropdownOption(key=ORDER_RANDOM, text="随机"),
                ft.DropdownOption(key=ORDER_RANDOM_NO_REPEAT, text="随机（不重复）"),
                ft.DropdownOption(key=ORDER_SEQUENTIAL, text="顺序"),
            ],
            on_change=self._handle_startup_wallpaper_order_change,
            width=220,
        )
        self._startup_wallpaper_delay_field = ft.TextField(
            label="启动后延迟（秒）",
            value=str(startup_wallpaper_config["delay_seconds"]),
            width=180,
            on_change=self._handle_startup_wallpaper_delay_change,
        )

        self._startup_wallpaper_fixed_image_display = ft.Text(
            startup_wallpaper_config.get("fixed_image") or "未选择",
            size=12,
            color=(
                ft.Colors.ON_SURFACE
                if startup_wallpaper_config.get("fixed_image")
                else ft.Colors.GREY
            ),
        )
        self._startup_wallpaper_clear_button = ft.TextButton(
            "清除",
            icon=ft.Icons.CLEAR,
            on_click=lambda _: self._startup_clear_fixed_image(),
            disabled=not bool(startup_wallpaper_config.get("fixed_image")),
        )

        fixed_image_row = ft.Row(
            [
                ft.TextButton(
                    "选择固定图片",
                    icon=ft.Icons.IMAGE,
                    on_click=lambda _: self._startup_open_fixed_image_picker(),
                ),
                self._startup_wallpaper_clear_button,
                self._startup_wallpaper_fixed_image_display,
            ],
            spacing=8,
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        order_delay_row = ft.Row(
            [
                self._startup_wallpaper_order_dropdown,
                self._startup_wallpaper_delay_field,
            ],
            spacing=16,
            wrap=True,
        )

        actions_row = ft.Row(
            [
                ft.FilledTonalButton(
                    "立即执行一次",
                    icon=ft.Icons.PLAY_ARROW,
                    on_click=self._handle_startup_wallpaper_run_now,
                ),
            ],
            spacing=12,
        )

        return ft.Column(
            controls=[
                ft.Text("开机与后台", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "配置应用在 Windows 中的开机启动行为，并在启动后立刻执行一次壁纸更换。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Row([
                    self._startup_auto_switch,
                    self._startup_auto_status_text,
                ], spacing=16, wrap=True),
                ft.Divider(),
                self._startup_wallpaper_switch,
                ft.Text(
                    "使用自动更换列表决定开机后的第一张壁纸，可选固定图片或延迟执行。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Text("参与的自动更换列表", size=14, weight=ft.FontWeight.BOLD),
                self._startup_wallpaper_lists_column,
                order_delay_row,
                ft.Text("固定图片（可选）", size=14, weight=ft.FontWeight.BOLD),
                fixed_image_row,
                actions_row,
            ],
            spacing=16,
            tight=True,
        )

    def _build_download_settings_section(self) -> ft.Control:
        """构建下载设置页面"""
        # 获取当前下载位置配置
        current_location = download_manager.get_current_location(app_config)

        # 下载位置选择
        location_options = []
        available_locations = download_manager.get_available_locations(app_config)
        for loc in available_locations:
            location_options.append(
                ft.DropdownOption(key=loc.type, text=f"{loc.display_name} ({loc.path})"),
            )

        self._download_location_dropdown = ft.Dropdown(
            label="下载位置",
            value=current_location.type,
            options=location_options,
            on_change=self._handle_download_location_change,
            width=400,
        )

        # 自定义路径输入（仅在选择自定义位置时显示）
        custom_path_value = app_config.get("download.custom_path", "")
        self._download_custom_path_field = ft.TextField(
            label="自定义路径",
            value=custom_path_value,
            hint_text="请输入绝对路径，如 C:\\Users\\YourName\\Downloads\\Wallpapers",
            on_change=self._handle_download_custom_path_change,
            visible=current_location.type == "custom",
            width=400,
        )

        # 路径验证状态
        self._download_path_status = ft.Text(
            "",
            size=12,
            color=ft.Colors.GREY,
            visible=False,
        )

        # 下载统计信息
        stats = download_manager.get_download_stats(app_config)
        used_space_text = download_manager.format_file_size(stats.total_size)
        file_count_text = f"{stats.total_files} 个文件"
        last_download_text = "从未下载" if not stats.last_download_time else \
            f"最后下载: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats.last_download_time))}"

        self._download_stats_text = ft.Text(
            f"已用空间: {used_space_text} | {file_count_text} | {last_download_text}",
            size=12,
            color=ft.Colors.GREY,
        )

        # 按钮组
        open_folder_button = ft.FilledTonalButton(
            "打开文件夹",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self._handle_open_download_folder,
        )

        refresh_stats_button = ft.FilledTonalButton(
            "刷新统计",
            icon=ft.Icons.REFRESH,
            on_click=self._handle_refresh_download_stats,
        )

        clear_folder_button = ft.FilledTonalButton(
            "清空文件夹",
            icon=ft.Icons.DELETE_SWEEP,
            on_click=self._handle_clear_download_folder,
        )

        optimize_button = ft.FilledTonalButton(
            "优化图片",
            icon=ft.Icons.IMAGE,
            on_click=self._handle_optimize_images,
        )

        # 当前路径显示
        current_path_text = f"当前路径: {current_location.path}"
        self._current_path_display = ft.Text(
            current_path_text,
            size=12,
            color=ft.Colors.GREY_600,
        )

        return ft.Column(
            controls=[
                ft.Text("下载设置", size=18, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "配置壁纸下载位置，查看下载统计，管理下载文件夹。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Divider(),

                # 下载位置配置
                ft.Text("下载位置", size=16, weight=ft.FontWeight.BOLD),
                self._download_location_dropdown,
                self._download_custom_path_field,
                self._download_path_status,
                ft.Divider(),

                # 统计信息
                ft.Text("下载统计", size=16, weight=ft.FontWeight.BOLD),
                self._current_path_display,
                self._download_stats_text,
                ft.Row(
                    [open_folder_button, refresh_stats_button, clear_folder_button, optimize_button],
                    spacing=12,
                    run_spacing=12,
                    wrap=True,
                ),

                # 优化进度显示区域
                ft.Column(
                    controls=[
                        ft.Divider(),
                        ft.Text("图片优化进度", size=16, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=ft.Column([
                                ft.ProgressBar(
                                    width=400,
                                    height=20,
                                    bgcolor=ft.Colors.GREY_300,
                                    color=ft.Colors.PRIMARY,
                                    visible=False,
                                    key="optimize_progress_bar",
                                ),
                                ft.Text(
                                    "",
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                    key="optimize_status_text",
                                ),
                                ft.Text(
                                    "",
                                    size=11,
                                    color=ft.Colors.GREY_500,
                                    key="optimize_stats_text",
                                ),
                            ]),
                            key="optimize_progress_container",
                            visible=False,
                        ),
                    ],
                    spacing=8,
                    key="optimize_progress_section",
                    visible=False,
                ),
            ],
            spacing=16,
            tight=True,
        )

    # 下载设置事件处理方法
    def _handle_download_location_change(self, e: ft.ControlEvent):
        """处理下载位置改变"""
        new_location_type = e.control.value
        custom_path = (app_config.get("download.custom_path", "") or "").strip()

        # 切换自定义路径输入框可见性
        if hasattr(self, "_download_custom_path_field"):
            self._download_custom_path_field.visible = (
                new_location_type == DownloadLocationType.CUSTOM
            )
            self._download_custom_path_field.update()

        # 切换时重置状态提示
        if hasattr(self, "_download_path_status"):
            self._download_path_status.visible = False
            self._download_path_status.value = ""
            self._download_path_status.update()

        # 自定义路径需要额外校验
        if new_location_type == DownloadLocationType.CUSTOM:
            if not custom_path:
                if hasattr(self, "_download_path_status"):
                    self._download_path_status.value = "请输入有效的自定义路径"
                    self._download_path_status.color = ft.Colors.RED_400
                    self._download_path_status.visible = True
                    self._download_path_status.update()
                self._show_snackbar("请选择或输入自定义路径", error=True)
                return

            is_valid, message = download_manager.validate_custom_path(custom_path)
            if hasattr(self, "_download_path_status"):
                self._download_path_status.value = message
                self._download_path_status.color = (
                    ft.Colors.GREEN if is_valid else ft.Colors.RED_400
                )
                self._download_path_status.visible = True
                self._download_path_status.update()

            if not is_valid:
                self._show_snackbar(message or "自定义路径无效", error=True)
                return

        # 设置下载位置
        success = download_manager.set_download_location(
            app_config, new_location_type, custom_path,
        )

        if success:
            self._refresh_download_path_display()
            self._show_snackbar("下载位置已更新")
        else:
            self._show_snackbar("设置下载位置失败", error=True)

    def _handle_download_custom_path_change(self, e: ft.ControlEvent):
        """处理自定义路径改变"""
        new_path = e.control.value or ""
        if new_path:
            is_valid, message = download_manager.validate_custom_path(new_path)
            if hasattr(self, "_download_path_status"):
                self._download_path_status.value = message
                self._download_path_status.color = ft.Colors.GREEN if is_valid else ft.Colors.RED_400
                self._download_path_status.visible = True
                self._download_path_status.update()

            if is_valid:
                app_config.set("download.custom_path", new_path)
                # 如果当前选择的是自定义位置，则更新下载位置
                selected_type = (
                    getattr(self, "_download_location_dropdown", None).value
                    if getattr(self, "_download_location_dropdown", None)
                    else app_config.get(
                        "download.location_type", DownloadLocationType.SYSTEM_DOWNLOAD,
                    )
                )
                if selected_type == DownloadLocationType.CUSTOM:
                    success = download_manager.set_download_location(
                        app_config, DownloadLocationType.CUSTOM, new_path,
                    )
                    if success:
                        self._refresh_download_path_display()
                        self._show_snackbar("下载位置已更新")
                    else:
                        self._show_snackbar("保存自定义路径失败", error=True)

    def _refresh_download_path_display(self):
        """刷新当前路径显示"""
        current_location = download_manager.get_current_location(app_config)
        current_path_text = f"当前路径: {current_location.path}"
        if hasattr(self, "_current_path_display"):
            self._current_path_display.value = current_path_text
            self._current_path_display.update()

    def _handle_open_download_folder(self, e: ft.ControlEvent):
        """处理打开下载文件夹"""
        success = download_manager.open_download_folder(app_config)
        if success:
            self._show_snackbar("已打开下载文件夹")
        else:
            self._show_snackbar("打开下载文件夹失败", error=True)

    def _handle_refresh_download_stats(self, e: ft.ControlEvent):
        """处理刷新下载统计"""
        stats = download_manager.get_download_stats(app_config)
        used_space_text = download_manager.format_file_size(stats.total_size)
        file_count_text = f"{stats.total_files} 个文件"
        last_download_text = "从未下载" if not stats.last_download_time else \
            f"最后下载: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats.last_download_time))}"

        if hasattr(self, "_download_stats_text"):
            self._download_stats_text.value = f"已用空间: {used_space_text} | {file_count_text} | {last_download_text}"
            self._download_stats_text.update()

        self._show_snackbar("统计信息已刷新")

    def _handle_clear_download_folder(self, e: ft.ControlEvent):
        """处理清空下载文件夹"""
        # 显示确认对话框
        confirm_dialog = ft.AlertDialog(
            title=ft.Text("确认清空"),
            content=ft.Text("确定要清空下载文件夹吗？此操作不可撤销。"),
            actions=[
                ft.TextButton(
                    "取消",
                    on_click=lambda _: self._close_clear_download_dialog(),
                ),
                ft.ElevatedButton(
                    "确认清空",
                    bgcolor=ft.Colors.RED_400,
                    color=ft.Colors.WHITE,
                    on_click=lambda _: self._confirm_clear_download_folder(),
                ),
            ],
        )

        self._download_clear_dialog = confirm_dialog
        self.page.dialog = confirm_dialog
        confirm_dialog.open = True
        self.page.open(confirm_dialog)
        self.page.update()

    def _confirm_clear_download_folder(self):
        """确认清空下载文件夹"""
        success, message = download_manager.clear_download_folder(app_config)

        # 关闭下载清空确认对话框
        self._close_clear_download_dialog()

        # 显示结果
        if success:
            self._show_snackbar(message)
            # 刷新统计信息
            self._handle_refresh_download_stats(None)
        else:
            self._show_snackbar(f"清空失败: {message}", error=True)

    def _close_clear_download_dialog(self) -> None:
        """关闭下载清空确认对话框，不影响全局对话框关闭逻辑"""
        if hasattr(self, "_download_clear_dialog") and self._download_clear_dialog:
            self._download_clear_dialog.open = False
            try:
                # 如果当前页面的对话框正好是这个，也一起关闭
                if self.page.dialog is self._download_clear_dialog:
                    self.page.close(self.page.dialog)
                else:
                    self.page.close(self._download_clear_dialog)
            except Exception:
                # 兼容性处理：如果 close 过程中出错，不影响后续 UI 更新
                pass
            self.page.update()

    def _show_snackbar(self, message: str, error: bool = False):
        """显示提示消息"""
        if hasattr(self, "page") and self.page:
            snack = ft.SnackBar(
                content=ft.Text(message),
                bgcolor=ft.Colors.RED_400 if error else ft.Colors.ON_SURFACE,
            )
            self.page.snack_bar = snack
            snack.open = True
            self.page.open(snack)
            self.page.update()

    # 图片优化相关方法
    def _handle_optimize_images(self, e: ft.ControlEvent):
        """处理优化图片按钮点击"""
        # 检查是否已在优化中
        if hasattr(self, "_is_optimizing") and self._is_optimizing:
            self._show_snackbar("图片优化正在进行中，请等待完成", error=True)
            return

        folder_path = download_manager.get_download_folder_path(app_config)
        if not folder_path or not folder_path.exists():
            self._show_snackbar("下载文件夹不存在，无法优化", error=True)
            return

        # 检查是否有图片文件
        image_files = image_optimizer.get_image_files(folder_path)
        if not image_files:
            self._show_snackbar("没有找到可优化的图片文件", error=True)
            return

        # 显示优化对话框
        self._show_optimize_dialog(len(image_files))

    def _show_optimize_dialog(self, image_count: int):
        """显示图片优化对话框"""
        # 质量选择滑块
        quality_slider = ft.Slider(
            min=50,
            max=100,
            divisions=10,
            value=85,
            label="{value}%",
        )

        # 进度条
        progress_bar = ft.ProgressBar(
            width=300,
            height=20,
            bgcolor=ft.Colors.GREY_300,
            color=ft.Colors.PRIMARY,
            visible=False,
        )

        # 状态文本
        status_text = ft.Text(
            f"准备优化 {image_count} 张图片...",
            size=14,
            visible=True,
        )

        # 统计信息文本
        stats_text = ft.Text(
            "",
            size=12,
            color=ft.Colors.GREY_600,
            visible=True,
        )

        def on_start_optimize(e):
            """开始优化"""
            quality = int(quality_slider.value)

            # 设置优化状态
            self._is_optimizing = True

            # 禁用下载设置页面的按钮和控件
            self._disable_download_controls()

            # 显示进度显示区域
            self._show_optimize_progress_ui()

            # 禁用对话框控件
            start_button.disabled = True
            cancel_button.disabled = False
            quality_slider.disabled = True

            # 显示进度条
            progress_bar.visible = True
            progress_bar.value = 0
            status_text.value = "正在优化..."
            stats_text.visible = True
            stats_text.value = "准备开始..."

            self.page.update()

            # 开始异步优化
            self.page.run_task(self._start_image_optimization, quality, progress_bar, status_text, stats_text)

        def on_cancel_optimize(e):
            """取消优化"""
            self._close_optimize_dialog()

        start_button = ft.ElevatedButton(
            "开始优化",
            icon=ft.Icons.PLAY_ARROW,
            on_click=on_start_optimize,
        )

        cancel_button = ft.TextButton(
            "取消",
            icon=ft.Icons.CANCEL,
            on_click=on_cancel_optimize,
            disabled=True,
        )

        optimize_dialog = ft.AlertDialog(
            title=ft.Text("图片优化", size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"将把 {image_count} 张图片转换为AVIF格式"),
                    ft.Text("AVIF格式提供更好的压缩比和质量"),
                    ft.Divider(),
                    ft.Text("选择压缩质量:"),
                    quality_slider,
                    ft.Divider(),
                    status_text,
                    progress_bar,
                    stats_text,
                ],scroll=ft.ScrollMode.AUTO),
                width=350,
                height=250,
            ),
            actions=[
                cancel_button,
                start_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._optimize_dialog = optimize_dialog
        self.page.dialog = optimize_dialog
        optimize_dialog.open = True
        self.page.open(optimize_dialog)
        self.page.update()

    async def _start_image_optimization(self, quality: int, progress_bar: ft.ProgressBar, status_text: ft.Text, stats_text: ft.Text):
        """开始图片优化过程"""
        try:
            folder_path = download_manager.get_download_folder_path(app_config)
            if not folder_path:
                return

            # 进度回调函数
            def progress_callback(progress):
                if hasattr(self, "_optimize_dialog") and self._optimize_dialog.open:
                    # 更新进度条
                    progress_bar.value = progress.percentage / 100

                    # 更新状态文本
                    status_text.value = f"正在处理: {progress.current_file}"

                    # 更新统计信息
                    original_size_text = image_optimizer.format_file_size(progress.current_size)
                    optimized_size_text = image_optimizer.format_file_size(progress.optimized_size)

                    if progress.optimized_size > 0:
                        compression_ratio = image_optimizer.calculate_compression_ratio(progress.current_size, progress.optimized_size)
                        stats_text.value = f"已处理 {progress.processed_count}/{progress.total_count} | 原始: {original_size_text} → 优化: {optimized_size_text} | 压缩比: {compression_ratio:.1f}%"
                    else:
                        stats_text.value = f"已处理 {progress.processed_count}/{progress.total_count} | 原始: {original_size_text}"

                    # 更新UI
                    self.page.update()

            # 执行优化
            result = await image_optimizer.optimize_folder_to_avif(
                folder_path,
                quality=quality,
                progress_callback=progress_callback,
            )

            # 更新最终状态
            if hasattr(self, "_optimize_dialog") and self._optimize_dialog.open:
                if result.success:
                    status_text.value = "优化完成！"
                    compression_ratio = image_optimizer.calculate_compression_ratio(result.original_size, result.optimized_size)
                    stats_text.value = f"成功处理 {result.processed_files} 张图片 | 压缩比: {compression_ratio:.1f}% | 耗时: {result.time_elapsed:.1f}秒"
                    self._show_snackbar(f"图片优化完成！节省空间 {compression_ratio:.1f}%")
                else:
                    status_text.value = "优化完成（有错误）"
                    stats_text.value = f"成功: {result.processed_files}, 失败: {result.failed_files}"
                    self._show_snackbar(f"优化完成，但有 {result.failed_files} 个文件处理失败", error=True)

                # 更新按钮状态
                cancel_button = next((action for action in self._optimize_dialog.actions if isinstance(action, ft.TextButton)), None)
                if cancel_button:
                    cancel_button.text = "关闭"
                    cancel_button.on_click = lambda e: self._close_optimize_dialog()

                self.page.update()

                # 刷新下载统计
                self._handle_refresh_download_stats(None)

        except Exception as e:
            logger.error(f"图片优化过程出错: {e}")
            if hasattr(self, "_optimize_dialog") and self._optimize_dialog.open:
                status_text.value = "优化失败"
                stats_text.value = f"错误: {e!s}"
                self.page.update()

            # 重置优化状态
            self._is_optimizing = False
            self._enable_download_controls()
            self._hide_optimize_progress_ui()

            self._show_snackbar(f"优化失败: {e!s}", error=True)

    def _disable_download_controls(self):
        """禁用下载设置页面的控件"""
        try:
            # 禁用按钮
            if hasattr(self, "open_folder_button") and self.open_folder_button:
                self.open_folder_button.disabled = True
            if hasattr(self, "refresh_stats_button") and self.refresh_stats_button:
                self.refresh_stats_button.disabled = True
            if hasattr(self, "clear_folder_button") and self.clear_folder_button:
                self.clear_folder_button.disabled = True
            if hasattr(self, "optimize_button") and self.optimize_button:
                self.optimize_button.disabled = True

            # 禁用下拉框和输入框
            if hasattr(self, "_download_location_dropdown") and self._download_location_dropdown:
                self._download_location_dropdown.disabled = True
            if hasattr(self, "_download_custom_path_field") and self._download_custom_path_field:
                self._download_custom_path_field.disabled = True

            # 刷新UI
            if hasattr(self, "page") and self.page:
                self.page.update()
        except Exception as e:
            logger.error(f"禁用控件时出错: {e}")

    def _enable_download_controls(self):
        """启用下载设置页面的控件"""
        try:
            # 启用按钮
            if hasattr(self, "open_folder_button") and self.open_folder_button:
                self.open_folder_button.disabled = False
            if hasattr(self, "refresh_stats_button") and self.refresh_stats_button:
                self.refresh_stats_button.disabled = False
            if hasattr(self, "clear_folder_button") and self.clear_folder_button:
                self.clear_folder_button.disabled = False
            if hasattr(self, "optimize_button") and self.optimize_button:
                self.optimize_button.disabled = False

            # 启用下拉框和输入框
            if hasattr(self, "_download_location_dropdown") and self._download_location_dropdown:
                self._download_location_dropdown.disabled = False
            if hasattr(self, "_download_custom_path_field") and self._download_custom_path_field:
                self._download_custom_path_field.disabled = False

            # 刷新UI
            if hasattr(self, "page") and self.page:
                self.page.update()
        except Exception as e:
            logger.error(f"启用控件时出错: {e}")

    def _show_optimize_progress_ui(self):
        """显示优化进度UI"""
        try:
            if hasattr(self, "page") and self.page:
                # 使用 Flet 的 query API 获取控件
                query = self.page.query("#optimize_progress_section")
                progress_container = query.first if query else None
                if progress_container is not None:
                    progress_container.visible = True
                    progress_container.update()
        except Exception as e:
            logger.error(f"显示进度UI时出错: {e}")

    def _hide_optimize_progress_ui(self):
        """隐藏优化进度UI"""
        try:
            if hasattr(self, "page") and self.page:
                # 使用 Flet 的 query API 获取控件
                query = self.page.query("#optimize_progress_section")
                progress_container = query.first if query else None
                if progress_container is not None:
                    progress_container.visible = False
                    progress_container.update()
        except Exception as e:
            logger.error(f"隐藏进度UI时出错: {e}")

    def _close_optimize_dialog(self):
        """关闭优化对话框并恢复UI状态"""
        # 重置优化状态
        self._is_optimizing = False

        # 恢复下载设置页面的控件
        self._enable_download_controls()
        self._hide_optimize_progress_ui()

        # 关闭对话框
        if hasattr(self, "_optimize_dialog") and self._optimize_dialog:
            self._optimize_dialog.open = False
            self.page.close(self._optimize_dialog)
            self.page.update()

    def _build_resource(self):
        self.resource_tabs = ft.Tabs(
            tabs=[
                ft.Tab(
                    text="Bing 每日",
                    icon=ft.Icons.TODAY,
                    content=self._build_bing_loading_indicator(),
                ),
                ft.Tab(
                    text="Windows 聚焦",
                    icon=ft.Icons.WINDOW,
                    content=self._build_spotlight_loading_indicator(),
                ),
                ft.Tab(text="搜索", icon=ft.Icons.SEARCH),
                ft.Tab(
                    text="IntelliMarkets 图片源",
                    icon=ft.Icons.SUBJECT,
                    content=self._build_im_page(),
                ),
                ft.Tab(
                    text="壁纸源",
                    icon=ft.Icons.SUBJECT,
                    content=self._build_wallpaper_source_tab(),
                ),
            ],
            animation_duration=300,
        )
        return ft.Container(
            ft.Column(
                [
                    ft.Text("资源", size=30),
                    ft.Container(
                        content=self.resource_tabs,
                        expand=True,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    ),
                ],
            ),
            expand=True,
            padding=16,
        )

    def _build_generate(self):
        self._generate_provider_dropdown = ft.Dropdown(
            label="服务提供商",
            value="pollinations",
            options=[
                ft.DropdownOption(key="pollinations", text="Pollinations.ai"),
            ],
        )
        self._generate_seed_field = ft.TextField(
            label="种子（相同种子将生成相同图片）",
            value="42",
            input_filter=ft.NumbersOnlyInputFilter(),
            expand=True,
        )
        seed_random_button = ft.IconButton(
            icon=ft.Icons.SHUFFLE,
            tooltip="随机生成种子",
            on_click=self._handle_generate_random_seed,
        )
        seed_row = ft.Row(
            [self._generate_seed_field, seed_random_button],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )
        self._generate_width_field = ft.TextField(
            label="图片宽度",
            value="1920",
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self._generate_height_field = ft.TextField(
            label="图片高度",
            value="1080",
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self._generate_enhance_switch = ft.Switch(
            label="使用大模型优化提示词",
            value=False,
        )
        self._generate_prompt_field = ft.TextField(
            label="提示词",
            min_lines=3,
            max_lines=5,
            multiline=True,
        )

        self._generate_loading_indicator = ft.ProgressRing(
            width=20,
            height=20,
            stroke_width=2,
            visible=False,
        )
        self._generate_status_text = ft.Text(
            "填写提示词后点击生成，即可在右侧查看图片",
            size=12,
            color=ft.Colors.OUTLINE,
        )

        download_button = ft.FilledTonalButton(
            "下载",
            icon=ft.Icons.DOWNLOAD,
            disabled=True,
            on_click=lambda _: self.page.run_task(self._generate_download),
        )
        save_as_button = ft.FilledTonalButton(
            "另存为",
            icon=ft.Icons.SAVE_ALT,
            disabled=True,
            on_click=self._handle_generate_save_as_request,
        )
        copy_image_button = ft.FilledTonalButton(
            "复制图片",
            icon=ft.Icons.CONTENT_COPY,
            disabled=True,
            on_click=lambda _: self.page.run_task(self._generate_copy_image),
        )
        copy_file_button = ft.FilledTonalButton(
            "复制文件",
            icon=ft.Icons.FOLDER_COPY,
            disabled=True,
            on_click=lambda _: self.page.run_task(self._generate_copy_file),
        )
        favorite_button = ft.FilledTonalButton(
            "收藏",
            icon=ft.Icons.BOOKMARK_ADD,
            disabled=True,
            on_click=self._handle_generate_favorite,
        )
        set_wallpaper_button = ft.FilledTonalButton(
            "设为壁纸",
            icon=ft.Icons.WALLPAPER,
            disabled=True,
            on_click=lambda _: self.page.run_task(self._generate_set_wallpaper),
        )

        self._generate_action_buttons = {
            "download": download_button,
            "save_as": save_as_button,
            "copy_image": copy_image_button,
            "copy_file": copy_file_button,
            "favorite": favorite_button,
            "set_wallpaper": set_wallpaper_button,
        }

        self._generate_update_actions()

        actions_row = ft.Row(
            [
                download_button,
                save_as_button,
                copy_image_button,
                copy_file_button,
                favorite_button,
                set_wallpaper_button,
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
        )

        placeholder = ft.Column(
            [
                ft.Icon(ft.Icons.IMAGE, size=72, color=ft.Colors.OUTLINE),
                ft.Text("生成的图片会展示在这里", color=ft.Colors.OUTLINE),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        )

        self._generate_output_container = ft.Container(
            expand=True,
            border_radius=12,
            bgcolor=self._bgcolor_surface_low,
            alignment=ft.alignment.center,
            padding=16,
            content=placeholder,
        )

        left_panel = ft.Container(
            width=360,
            padding=16,
            bgcolor=self._bgcolor_surface_low,
            border_radius=12,
            content=ft.Column(
                [
                    self._generate_provider_dropdown,
                    seed_row,
                    self._generate_width_field,
                    self._generate_height_field,
                    self._generate_enhance_switch,
                    self._generate_prompt_field,
                    ft.FilledButton("生成", on_click=self._handle_generate_clicked),
                ],
                spacing=12,
                tight=True,
            ),
        )

        right_panel = ft.Container(
            expand=True,
            padding=16,
            bgcolor=ft.Colors.SURFACE,
            border_radius=12,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self._generate_loading_indicator,
                            self._generate_status_text,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    actions_row,
                    self._generate_output_container,
                ],
                spacing=16,
                expand=True,
            ),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("生成", size=30),
                    ft.Row(
                        [
                            left_panel,
                            right_panel,
                        ],
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=24,
                expand=True,
            ),
            expand=True,
            padding=16,
        )

    def _handle_generate_error(self, message: str) -> None:
        logger.error("Image generation failed: {message}", message=message)
        self._set_generate_loading(False)
        self._update_generate_status(message, error=True)
        self._show_snackbar(message, error=True)

    def _set_generate_loading(self, active: bool) -> None:
        if self._generate_loading_indicator is None:
            return
        self._generate_loading_indicator.visible = active
        if self._generate_loading_indicator.page is not None:
            self._generate_loading_indicator.update()

    def _update_generate_status(self, message: str, *, error: bool = False) -> None:
        if self._generate_status_text is None:
            return
        self._generate_status_text.value = message
        self._generate_status_text.color = (
            ft.Colors.ERROR if error else ft.Colors.OUTLINE
        )
        if self._generate_status_text.page is not None:
            self._generate_status_text.update()

    def _set_generate_output_image(
        self,
        source: str,
        *,
        is_local_file: bool = False,
    ) -> None:
        if self._generate_output_container is None:
            return
        logger.debug(
            "Updating preview image",
            source=source,
            local=is_local_file,
        )
        image_kwargs = dict(
            fit=ft.ImageFit.CONTAIN,
            expand=True,
            border_radius=12,
        )
        if is_local_file:
            try:
                data = Path(source).read_bytes()
            except Exception as exc:
                logger.error(
                    "Failed to read generated image file: {error}",
                    error=str(exc),
                )
                raise
            encoded = base64.b64encode(data).decode("ascii")
            image_control = ft.Image(src_base64=encoded, **image_kwargs)
        else:
            image_control = ft.Image(src=source, **image_kwargs)

        self._generate_output_container.content = image_control
        if self._generate_output_container.page is not None:
            self._generate_output_container.update()

    def _handle_generate_random_seed(self, _: ft.ControlEvent | None) -> None:
        if self._generate_seed_field is None:
            return
        seed_value = str(random.randint(0, 999_999_999))
        self._generate_seed_field.value = seed_value
        if self._generate_seed_field.page is not None:
            self._generate_seed_field.update()

    def _generate_update_actions(self) -> None:
        path = self._generate_last_file
        has_file = bool(path and path.exists())
        if path and not path.exists():
            self._generate_last_file = None
        for control in self._generate_action_buttons.values():
            control.disabled = not has_file
            if control.page is not None:
                control.update()

    def _generate_resolve_target_path(self, directory: Path, file_name: str) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / file_name
        if not target.exists():
            return target
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while True:
            candidate = directory / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _ensure_generate_save_picker(self) -> None:
        if self._generate_save_picker is None:
            self._generate_save_picker = ft.FilePicker(
                on_result=self._handle_generate_save_result,
            )
        if self._generate_save_picker not in self.page.overlay:
            self.page.overlay.append(self._generate_save_picker)
            self.page.update()

    def _handle_generate_save_result(self, event: ft.FilePickerResultEvent) -> None:
        source = self._generate_pending_save_source
        self._generate_pending_save_source = None
        if source is None or not source.exists():
            return
        if not event.path:
            return
        target = Path(event.path)
        self.page.run_task(self._generate_save_to_path, source, target)

    def _handle_generate_save_as_request(self, _: ft.ControlEvent | None) -> None:
        path = self._generate_last_file
        if not path or not path.exists():
            self._show_snackbar("当前没有可用的生成图片。", error=True)
            self._generate_update_actions()
            return
        self._ensure_generate_save_picker()
        self._generate_pending_save_source = path
        if self._generate_save_picker is None:
            return
        suggested = path.name or "generated-image.png"
        initial_dir = path.parent if path.parent.exists() else Path.cwd()
        try:
            self._generate_save_picker.save_file(
                file_name=suggested,
                initial_directory=str(initial_dir),
            )
        except Exception as exc:
            logger.error("另存为对话框打开失败: {error}", error=str(exc))
            self._show_snackbar("无法打开另存为对话框。", error=True)

    async def _generate_save_to_path(self, source: Path, target: Path) -> None:
        def _copy() -> Path:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return target

        try:
            final_path = await asyncio.to_thread(_copy)
        except Exception as exc:
            logger.error("另存为失败: {error}", error=str(exc))
            self._show_snackbar("另存为失败，请查看日志。", error=True)
            return
        self._show_snackbar(f"已保存到 {final_path}")

    async def _generate_download(self) -> None:
        path = self._generate_last_file
        if not path or not path.exists():
            self._show_snackbar("当前没有可用的生成图片。", error=True)
            self._generate_update_actions()
            return
        # 使用下载管理器获取配置的位置
        download_folder_path = download_manager.get_download_folder_path(app_config)
        if not download_folder_path:
            self._show_snackbar("尚未配置下载目录。", error=True)
            return

        # 确保下载文件夹存在
        try:
            download_folder_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.error(f"创建下载目录失败: {exc}")
            self._show_snackbar("创建下载目录失败。", error=True)
            return

        def _copy() -> Path:
            target = self._generate_resolve_target_path(download_folder_path, path.name)
            shutil.copy2(path, target)
            return target

        try:
            final_path = await asyncio.to_thread(_copy)
        except Exception as exc:
            logger.error("下载失败: {error}", error=str(exc))
            self._show_snackbar("下载失败，请查看日志。", error=True)
            return
        self._show_snackbar(f"已下载到 {final_path}")

    async def _generate_copy_image(self) -> None:
        path = self._generate_last_file
        if not path or not path.exists():
            self._show_snackbar("当前没有可用的生成图片。", error=True)
            self._generate_update_actions()
            return
        success = await asyncio.to_thread(copy_image_to_clipboard, path)
        if success:
            self._show_snackbar("图片已复制到剪贴板。")
        else:
            self._show_snackbar("复制图片失败。", error=True)

    async def _generate_copy_file(self) -> None:
        path = self._generate_last_file
        if not path or not path.exists():
            self._show_snackbar("当前没有可用的生成图片。", error=True)
            self._generate_update_actions()
            return
        success = await asyncio.to_thread(copy_files_to_clipboard, [str(path)])
        if success:
            self._show_snackbar("文件已复制到剪贴板。")
        else:
            self._show_snackbar("复制文件失败。", error=True)

    async def _generate_set_wallpaper(self) -> None:
        path = self._generate_last_file
        if not path or not path.exists():
            self._show_snackbar("当前没有可用的生成图片。", error=True)
            self._generate_update_actions()
            return
        try:
            await asyncio.to_thread(ltwapi.set_wallpaper, str(path))
        except Exception as exc:
            logger.error("设为壁纸失败: {error}", error=str(exc))
            self._show_snackbar("设为壁纸失败，请查看日志。", error=True)
            return
        self._show_snackbar("已设置为壁纸。")

    def _generate_make_favorite_payload(self) -> dict[str, Any] | None:
        path = self._generate_last_file
        if not path or not path.exists():
            return None
        prompt = (self._generate_last_prompt or "").strip()
        title = self._abbreviate_text(prompt, 40) if prompt else path.stem
        if not title:
            title = path.stem or "AI 生成壁纸"
        try:
            timestamp = path.stat().st_mtime
        except Exception:
            timestamp = time.time()
        identifier = hashlib.sha1(
            f"{path}-{timestamp}".encode("utf-8", "ignore"),
        ).hexdigest()
        tags: list[str] = ["generation"]
        if self._generate_last_provider:
            tags.append(self._generate_last_provider)
        tags = [tag for tag in dict.fromkeys(tag for tag in tags if tag)]
        extra = {
            "prompt": prompt or None,
            "seed": self._generate_last_seed or None,
            "width": self._generate_last_width,
            "height": self._generate_last_height,
            "provider": self._generate_last_provider or None,
            "request_url": self._generate_last_request_url or None,
            "enhance": self._generate_last_enhance,
            "allow_nsfw": self._generate_last_allow_nsfw,
        }
        extra = {key: value for key, value in extra.items() if value not in (None, "")}
        extra["file_path"] = str(path)
        favorite_source = FavoriteSource(
            type="generation",
            identifier=identifier,
            title=title,
            url=self._generate_last_request_url,
            preview_url=str(path),
            local_path=str(path),
            extra=extra,
        )
        default_folder = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else "default"
        )
        payload: dict[str, Any] = {
            "folder_id": default_folder,
            "title": title,
            "description": "",
            "tags": tags,
            "source": favorite_source,
            "preview_url": str(path),
            "local_path": str(path),
            "extra": extra,
        }
        return payload

    def _handle_generate_favorite(self, _: ft.ControlEvent | None) -> None:
        payload = self._generate_make_favorite_payload()
        if not payload:
            self._show_snackbar("当前没有可收藏的内容。", error=True)
            self._generate_update_actions()
            return
        self._open_favorite_editor(payload)

    def _handle_generate_clicked(self, _: ft.ControlEvent) -> None:
        prompt = (
            (self._generate_prompt_field.value or "").strip()
            if self._generate_prompt_field
            else ""
        )
        if not prompt:
            self._handle_generate_error("请输入提示词。")
            return

        logger.info(
            "Generate button clicked with prompt: {prompt}",
            prompt=self._abbreviate_text(prompt, 120),
        )

        provider = (
            (self._generate_provider_dropdown.value or "").strip().lower()
            if self._generate_provider_dropdown
            else "pollinations"
        )
        if provider not in ("pollinations", ""):
            logger.error("Unsupported provider selected: {provider}", provider=provider)
            self._handle_generate_error("当前仅支持 Pollinations.ai。")
            return

        width: int | None = None
        if self._generate_width_field:
            raw_width = (self._generate_width_field.value or "").strip()
            if raw_width:
                try:
                    width = int(raw_width)
                    if width <= 0:
                        raise ValueError
                except ValueError:
                    logger.warning("Invalid width value: {value}", value=raw_width)
                    self._handle_generate_error("图片宽度必须是正整数。")
                    return

        height: int | None = None
        if self._generate_height_field:
            raw_height = (self._generate_height_field.value or "").strip()
            if raw_height:
                try:
                    height = int(raw_height)
                    if height <= 0:
                        raise ValueError
                except ValueError:
                    logger.warning("Invalid height value: {value}", value=raw_height)
                    self._handle_generate_error("图片高度必须是正整数。")
                    return

        params: dict[str, str] = {}
        seed = (
            (self._generate_seed_field.value or "").strip()
            if self._generate_seed_field
            else ""
        )
        enhance = (
            self._generate_enhance_switch.value
            if self._generate_enhance_switch is not None
            else False
        )
        allow_nsfw = bool(app_config.get("wallpaper.allow_nsfw", False))

        if seed:
            params["seed"] = seed
        if width is not None:
            params["width"] = str(width)
        if height is not None:
            params["height"] = str(height)
        if enhance:
            params["enhance"] = "true"
        params["safe"] = "false" if allow_nsfw else "true"

        base_url = "https://image.pollinations.ai/prompt/"
        encoded_prompt = quote_plus(prompt)
        request_url = f"{base_url}{encoded_prompt}"
        if params:
            request_url = f"{request_url}?{urlencode(params)}&nologo=true"
        cache_token = str(int(time.time() * 1000))
        cache_suffix = f"cb={cache_token}"
        request_url = (
            f"{request_url}&{cache_suffix}"
            if params
            else f"{request_url}?{cache_suffix}"
        )

        logger.info(
            "Dispatching Pollinations request",
            prompt=self._abbreviate_text(prompt, 120),
            url=request_url,
            width=width,
            height=height,
            seed=seed,
            provider=provider or "pollinations",
            enhance=enhance,
            safe=params.get("safe"),
        )

        self._set_generate_loading(True)
        self._update_generate_status("已发送生成请求，正在等待图像生成…")
        self.page.run_task(
            self._process_generate_request,
            request_url,
            prompt,
            width,
            height,
            seed,
            enhance,
            allow_nsfw,
            provider,
        )

    async def _process_generate_request(
        self,
        request_url: str,
        prompt: str,
        width: int | None,
        height: int | None,
        seed: str,
        enhance: bool,
        allow_nsfw: bool,
        provider: str,
    ) -> None:
        cache_dir = CACHE_DIR / "generations"
        cache_dir.mkdir(parents=True, exist_ok=True)

        slug = self._favorite_filename_slug(prompt, "generation")
        timestamp = int(time.time())
        custom_name = f"{slug}-{timestamp}"

        async def _download() -> str | None:
            return await asyncio.to_thread(
                ltwapi.download_file,
                request_url,
                cache_dir,
                custom_name,
                120,
                3,
                {"Accept": "image/*"},
                None,
                False,
            )

        try:
            path_str = await _download()
        except Exception as exc:  # pragma: no cover - network
            logger.error(
                "Error downloading generated image: {error}",
                error=str(exc),
            )
            self._handle_generate_error("生成图片下载失败，请稍后重试。")
            return

        if not path_str:
            self._handle_generate_error("生成图片失败，请稍后重试。")
            return

        path = Path(path_str)
        self._generate_last_file = path
        try:
            self._set_generate_output_image(str(path), is_local_file=True)
        except Exception:
            self._handle_generate_error("加载生成的图片失败。")
            return

        self._generate_last_file = path
        self._generate_last_prompt = prompt
        self._generate_last_width = width
        self._generate_last_height = height
        self._generate_last_seed = seed
        self._generate_last_request_url = request_url
        self._generate_last_provider = provider or "pollinations"
        self._generate_last_model = None
        self._generate_last_enhance = enhance
        self._generate_last_allow_nsfw = allow_nsfw
        self._generate_update_actions()

        self._update_generate_status(f"生成完成，已保存到 {path.name}")
        logger.info(
            "Generated image cached locally",
            path=str(path),
            prompt=self._abbreviate_text(prompt, 120),
            width=width,
            height=height,
            seed=seed,
            provider=provider or "pollinations",
            enhance=enhance,
            safe="false" if allow_nsfw else "true",
        )
        self._set_generate_loading(False)
        self.page.update()

    def _build_bing_loading_indicator(self):
        return ft.Container(
            ft.Column(
                [
                    ft.ProgressRing(width=32, height=32),
                    ft.Text("正在加载 Bing 每日壁纸…"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=32,
        )

    def _build_spotlight_loading_indicator(self):
        return ft.Container(
            ft.Column(
                [
                    ft.ProgressRing(width=32, height=32),
                    ft.Text("正在加载 Windows 聚焦壁纸…"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=32,
        )

    def _build_wallpaper_source_tab(self):
        self._ws_fetch_button = ft.FilledButton(
            "获取壁纸",
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda _: self._ws_fetch_active_category(force=True),
        )
        self._ws_reload_button = ft.OutlinedButton(
            "刷新源列表",
            icon=ft.Icons.SYNC,
            on_click=lambda _: self._ws_reload_sources(),
        )
        manage_button = ft.TextButton(
            "在设置中管理",
            icon=ft.Icons.SETTINGS,
            on_click=lambda _: self._ws_open_wallpaper_source_settings(),
        )

        header_actions = ft.Row(
            controls=[
                self._ws_fetch_button,
                self._ws_reload_button,
                manage_button,
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._ws_source_info_container = ft.Container(visible=False)
        self._ws_source_tabs = ft.Tabs(
            tabs=[],
            scrollable=True,
            animation_duration=150,
            on_change=self._ws_on_source_tab_change,
        )
        self._ws_source_tabs_container = ft.Container(content=self._ws_source_tabs)

        self._ws_primary_container = ft.Container(visible=False)
        self._ws_secondary_container = ft.Container(visible=False)
        self._ws_tertiary_container = ft.Container(visible=False)
        self._ws_leaf_container = ft.Container(visible=False)
        self._ws_param_container = ft.Container(visible=False)

        self._ws_search_field = ft.TextField(
            label="搜索分类或壁纸",
            hint_text="输入关键字以筛选分类或壁纸",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            expand=True,
            on_change=self._ws_on_search_change,
        )

        self._ws_loading_indicator = ft.ProgressRing(
            width=18,
            height=18,
            stroke_width=2,
            visible=False,
        )
        self._ws_status_text = ft.Text("请选择分类", size=12, color=ft.Colors.GREY)

        status_row = ft.Row(
            [
                ft.Row(
                    [self._ws_loading_indicator, self._ws_status_text],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self._ws_result_list = ft.ListView(
            expand=True,
            spacing=12,
            auto_scroll=False,
        )

        content_column = ft.Column(
            controls=[
                header_actions,
                self._ws_search_field,
                self._ws_source_tabs_container,
                self._ws_primary_container,
                self._ws_secondary_container,
                self._ws_tertiary_container,
                self._ws_leaf_container,
                self._ws_param_container,
                status_row,
                ft.Container(content=self._ws_result_list, expand=True),
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        container = ft.Container(
            content=content_column,
            padding=12,
            expand=True,
        )

        self._ws_recompute_ui(preserve_selection=True)
        self._ws_update_fetch_button_state()
        return container

    def _ws_reload_sources(self) -> None:
        self._wallpaper_source_manager.reload()
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        self._ws_recompute_ui(preserve_selection=False)

    def _ws_recompute_ui(self, preserve_selection: bool = True) -> None:
        if self._ws_source_tabs is None or self._ws_source_tabs_container is None:
            return

        records = self._wallpaper_source_manager.enabled_records()
        has_records = bool(records)

        if self._ws_search_field is not None:
            self._ws_search_field.disabled = not has_records
            if self._ws_search_field.page is not None:
                self._ws_search_field.update()

        self._ws_hierarchy = self._ws_build_hierarchy(records)
        available_ids = list(self._ws_hierarchy.keys())
        display_records: list[WallpaperSourceRecord] = [
            self._ws_hierarchy[identifier]["record"]
            for identifier in available_ids
            if isinstance(self._ws_hierarchy[identifier].get("record"), WallpaperSourceRecord)
        ]
        if not available_ids:
            self._ws_active_source_id = None
            self._ws_active_primary_key = None
            self._ws_active_secondary_key = None
            self._ws_active_tertiary_key = None
            self._ws_active_leaf_index = 0
            self._ws_active_category_id = None
            if self._ws_source_info_container is not None:
                self._ws_source_info_container.content = ft.Container()
                self._ws_source_info_container.visible = False
                if self._ws_source_info_container.page is not None:
                    self._ws_source_info_container.update()
            self._ws_param_controls = []
            if self._ws_param_container is not None:
                self._ws_param_container.content = ft.Container()
                if self._ws_param_container.page is not None:
                    self._ws_param_container.update()
            empty_title = (
                "未找到匹配的壁纸源或分类" if has_records else "尚未启用壁纸源"
            )
            empty_hint = (
                "请尝试调整搜索条件或启用更多分类。"
                if has_records
                else "请刷新或前往设置 → 内容 导入/启用壁纸源。"
            )
            actions = [
                ft.TextButton(
                    "在设置中管理" if has_records else "前往设置管理壁纸源",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _: self._ws_open_wallpaper_source_settings(),
                ),
            ]
            placeholder = ft.Column(
                [
                    ft.Icon(
                        ft.Icons.FILTER_ALT_OFF
                        if has_records
                        else ft.Icons.LIBRARY_ADD,
                        size=48,
                        color=ft.Colors.OUTLINE,
                    ),
                    ft.Text(empty_title, size=15, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        empty_hint,
                        size=12,
                        color=ft.Colors.GREY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    *actions,
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            )
            self._ws_source_tabs.tabs = []
            self._ws_source_tabs.selected_index = 0
            self._ws_source_tabs_container.content = ft.Container(
                content=placeholder,
                alignment=ft.alignment.center,
                padding=16,
                bgcolor=self._bgcolor_surface_low,
                border_radius=8,
            )
            self._ws_source_tabs_container.visible = True
            if self._ws_source_tabs.page is not None:
                self._ws_source_tabs.update()
            if self._ws_source_tabs_container.page is not None:
                self._ws_source_tabs_container.update()
            for container in (
                self._ws_primary_container,
                self._ws_secondary_container,
                self._ws_tertiary_container,
                self._ws_leaf_container,
            ):
                container.content = None
                container.visible = False
                if container.page is not None:
                    container.update()
            status_message = (
                "未找到匹配的分类，请调整筛选条件。"
                if has_records
                else "尚未启用壁纸源，请先导入。"
            )
            self._ws_clear_results(status_message)
            self._ws_param_container.content = None
            self._ws_param_container.visible = False
            if self._ws_param_container.page is not None:
                self._ws_param_container.update()
            self._ws_update_fetch_button_state()
            return

        if not preserve_selection or self._ws_active_source_id not in available_ids:
            self._ws_active_source_id = available_ids[0]

        self._ws_update_source_tabs(display_records, preserve_selection=preserve_selection)
        active_record = self._ws_hierarchy.get(self._ws_active_source_id, {}).get(
            "record",
        )
        self._ws_update_source_info(active_record)
        self._ws_update_primary_tabs(
            self._ws_active_source_id,
            preserve_selection=preserve_selection,
        )
        self._ws_update_fetch_button_state()

    def _ws_build_hierarchy(
        self, records: list[WallpaperSourceRecord],
    ) -> dict[str, Any]:
        if self._ws_merge_display:
            return self._ws_build_merged_hierarchy(records)
        return self._ws_build_split_hierarchy(records)

    def _ws_build_split_hierarchy(
        self, records: list[WallpaperSourceRecord],
    ) -> dict[str, Any]:
        hierarchy: dict[str, Any] = {}
        term = (self._ws_search_text or "").strip().lower()
        for record in records:
            refs = self._wallpaper_source_manager.category_refs(record.identifier)
            filtered_refs = self._ws_filter_refs(refs, term)
            if not filtered_refs:
                continue
            primary_list = self._ws_build_primary_entries(
                filtered_refs,
                key_prefix=record.identifier,
                fallback_source_name=record.spec.name,
            )
            if primary_list:
                hierarchy[record.identifier] = {
                    "record": record,
                    "primary_list": primary_list,
                }
        return hierarchy

    def _ws_build_merged_hierarchy(
        self, records: list[WallpaperSourceRecord],
    ) -> dict[str, Any]:
        term = (self._ws_search_text or "").strip().lower()
        grouped: dict[str, dict[str, Any]] = {}
        order_index = {record.identifier: index for index, record in enumerate(records)}
        merge_priority = self._ws_merge_priority_map(records)
        for record in records:
            refs = self._wallpaper_source_manager.category_refs(record.identifier)
            for ref in refs:
                if term and not any(term in token for token in ref.search_tokens):
                    continue
                primary_label = ref.category.category or ref.source_name or record.spec.name
                label = primary_label or record.spec.name or "未分类"
                group = grouped.setdefault(
                    label,
                    {"label": label, "refs": []},
                )
                group["refs"].append(ref)

        for bucket in grouped.values():
            refs = bucket.get("refs", []) or []
            icon_counts = self._ws_count_icons_by_source(refs)
            bucket["refs"] = self._ws_apply_merged_icon_preference(
                refs,
                icon_counts,
                order_index,
                merge_priority,
            )

        hierarchy: dict[str, Any] = {}
        for label, bucket in sorted(grouped.items(), key=lambda item: item[0].lower()):
            refs = bucket["refs"]
            if not refs:
                continue
            primary_list = self._ws_build_primary_entries(
                refs,
                key_prefix="",
                fallback_source_name=label,
            )
            if not primary_list:
                continue
            merged_record = self._ws_create_merged_record(label, refs)
            hierarchy[merged_record.identifier] = {
                "record": merged_record,
                "primary_list": primary_list,
            }
        return hierarchy

    def _ws_category_key(self, ref: WallpaperCategoryRef) -> tuple[str, str, str, str, str]:
        cat = ref.category
        return (
            cat.id or "",
            cat.name or "",
            cat.category or "",
            cat.subcategory or "",
            cat.subsubcategory or "",
        )

    def _ws_count_icons_by_source(self, refs: list[WallpaperCategoryRef]) -> dict[str, int]:
        counts: dict[str, int] = {}
        seen: dict[str, set[tuple[str, str, str, str, str]]] = {}
        for ref in refs:
            if not ref.category.icon:
                continue
            source_seen = seen.setdefault(ref.source_id, set())
            key = self._ws_category_key(ref)
            if key in source_seen:
                continue
            source_seen.add(key)
            counts[ref.source_id] = counts.get(ref.source_id, 0) + 1
        return counts

    def _ws_merge_priority_map(self, records: list[WallpaperSourceRecord]) -> dict[str, int]:
        priorities: dict[str, int] = {}
        for record in records:
            priority_value = 0
            config = record.spec.config if isinstance(record.spec.config, dict) else {}
            merge_cfg = config.get("merge") if isinstance(config, dict) else {}
            raw_priority = merge_cfg.get("priority") if isinstance(merge_cfg, dict) else None
            try:
                if raw_priority is not None:
                    priority_value = int(raw_priority)
            except (TypeError, ValueError):
                priority_value = 0
            priorities[record.identifier] = priority_value
        return priorities

    def _ws_apply_merged_icon_preference(
        self,
        refs: list[WallpaperCategoryRef],
        icon_counts: dict[str, int],
        order_index: dict[str, int],
        merge_priority: dict[str, int],
    ) -> list[WallpaperCategoryRef]:
        grouped: dict[tuple[str, str, str, str, str], list[WallpaperCategoryRef]] = {}
        for ref in refs:
            grouped.setdefault(self._ws_category_key(ref), []).append(ref)

        resolved: list[WallpaperCategoryRef] = []
        for key, group in grouped.items():
            candidates = [ref for ref in group if ref.category.icon]
            if not candidates:
                resolved.extend(group)
                continue

            def _score(ref: WallpaperCategoryRef) -> tuple[int, int]:
                return (
                    merge_priority.get(ref.source_id, 0),
                    icon_counts.get(ref.source_id, 0),
                    order_index.get(ref.source_id, 0),
                )

            winner = max(candidates, key=_score)
            icon_value = winner.category.icon
            for ref in group:
                if ref.category.icon == icon_value:
                    resolved.append(ref)
                    continue
                resolved.append(
                    dc_replace(
                        ref,
                        category=dc_replace(ref.category, icon=icon_value),
                    ),
                )
        return resolved

    def _ws_filter_refs(
        self, refs: list[WallpaperCategoryRef], term: str,
    ) -> list[WallpaperCategoryRef]:
        if not term:
            return list(refs)
        return [ref for ref in refs if any(term in token for token in ref.search_tokens)]

    def _ws_build_primary_entries(
        self,
        refs: list[WallpaperCategoryRef],
        *,
        key_prefix: str,
        fallback_source_name: str | None,
    ) -> list[dict[str, Any]]:
        primary_map: dict[str, dict[str, Any]] = {}
        primary_list: list[dict[str, Any]] = []
        for ref in refs:
            category = ref.category
            primary_label = category.category or ref.source_name or fallback_source_name or ref.label
            key_parts: list[str] = []
            if key_prefix:
                key_parts.append(key_prefix)
            key_parts.append(primary_label or ref.source_id)
            primary_key = ":".join(key_parts)
            primary_entry = primary_map.get(primary_key)
            if primary_entry is None:
                primary_entry = {
                    "key": primary_key,
                    "label": primary_label or fallback_source_name or "其他",
                    "secondary_list": [],
                    "secondary_map": {},
                }
                primary_map[primary_key] = primary_entry
                primary_list.append(primary_entry)

            secondary_key = category.subcategory or _WS_DEFAULT_KEY
            secondary_label = category.subcategory or "全部"
            secondary_map = primary_entry["secondary_map"]
            secondary_entry = secondary_map.get(secondary_key)
            if secondary_entry is None:
                secondary_entry = {
                    "key": secondary_key,
                    "label": secondary_label if secondary_key != _WS_DEFAULT_KEY else "全部",
                    "tertiary_list": [],
                    "tertiary_map": {},
                }
                secondary_map[secondary_key] = secondary_entry
                primary_entry["secondary_list"].append(secondary_entry)

            tertiary_key = category.subsubcategory or _WS_DEFAULT_KEY
            tertiary_label = category.subsubcategory or (category.subcategory or ref.label)
            tertiary_map = secondary_entry["tertiary_map"]
            tertiary_entry = tertiary_map.get(tertiary_key)
            if tertiary_entry is None:
                tertiary_entry = {
                    "key": tertiary_key,
                    "label": tertiary_label if tertiary_key != _WS_DEFAULT_KEY else (category.subcategory or ref.label),
                    "refs": [],
                }
                tertiary_map[tertiary_key] = tertiary_entry
                secondary_entry["tertiary_list"].append(tertiary_entry)
            tertiary_entry["refs"].append(ref)

        result: list[dict[str, Any]] = []
        for entry in primary_list:
            entry.pop("secondary_map", None)
            entry["secondary_list"] = [
                secondary_entry
                for secondary_entry in entry["secondary_list"]
                if secondary_entry.get("tertiary_list")
            ]
            for secondary_entry in entry["secondary_list"]:
                secondary_entry.pop("tertiary_map", None)
                secondary_entry["tertiary_list"] = [
                    tertiary_entry
                    for tertiary_entry in secondary_entry["tertiary_list"]
                    if tertiary_entry.get("refs")
                ]
            if entry["secondary_list"]:
                result.append(entry)
        return result

    def _ws_create_merged_record(
        self,
        label: str,
        refs: list[WallpaperCategoryRef],
    ) -> WallpaperSourceRecord:
        unique_sources = sorted({ref.source_id for ref in refs})
        category_keys = sorted({
            f"{ref.category.category}|{ref.category.subcategory}|{ref.category.subsubcategory}|{ref.category.id}"
            for ref in refs
        })
        identifier_seed = "|".join([label or "", *unique_sources, *category_keys])
        slug = hashlib.sha1(identifier_seed.encode("utf-8", "ignore")).hexdigest()[:10]
        identifier = f"merged::{slug}"
        description = f"合并视图，包含 {len(unique_sources)} 个壁纸源"
        spec = SourceSpec(
            scheme="littletree_wallpaper_source_v3",
            identifier=identifier,
            name=label or "未分类",
            version="合并视图",
            description=description,
        )
        unique_categories: dict[str, Any] = {}
        for ref in refs:
            cat = ref.category
            cat_key = f"{cat.id}|{cat.name}|{cat.category}|{cat.subcategory}|{cat.subsubcategory}"
            unique_categories[cat_key] = cat
        spec.categories = list(unique_categories.values())
        spec.config["merged_sources"] = unique_sources
        pseudo_path = Path(f"merged_{slug}")
        merged_record = WallpaperSourceRecord(
            identifier=identifier,
            spec=spec,
            path=pseudo_path,
            origin="builtin",
            enabled=True,
        )
        return merged_record

    def _ws_update_source_tabs(
        self,
        records: list[WallpaperSourceRecord],
        *,
        preserve_selection: bool,
    ) -> None:
        if self._ws_source_tabs is None or self._ws_source_tabs_container is None:
            return
        available_records = [
            record for record in records if record.identifier in self._ws_hierarchy
        ]
        keys = [record.identifier for record in available_records]
        if not available_records:
            return
        self._ws_updating_ui = True
        tabs: list[ft.Tab] = []
        for record in available_records:
            category_count = len(record.spec.categories)
            logo_control = ft.Container(
                content=self._ws_build_logo_control(record, size=26),
                width=28,
                height=28,
                alignment=ft.alignment.center,
            )
            label_column = ft.Column(
                [
                    ft.Text(
                        record.spec.name,
                        size=13,
                        weight=ft.FontWeight.W_600,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        f"{category_count} 个分类",
                        size=11,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=0,
                tight=True,
                expand=True,
            )
            tab_row = ft.Row(
                [logo_control, label_column],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            tabs.append(
                ft.Tab(
                    text=record.spec.name,
                    tab_content=ft.Container(
                        content=tab_row,
                        padding=ft.padding.symmetric(horizontal=4, vertical=6),
                    ),
                ),
            )
        self._ws_source_tabs.tabs = tabs
        if not preserve_selection or self._ws_active_source_id not in keys:
            self._ws_active_source_id = keys[0]
        selected_index = keys.index(self._ws_active_source_id)
        self._ws_source_tabs.selected_index = selected_index
        self._ws_source_tabs.data = {"keys": keys}
        self._ws_source_tabs_container.content = self._ws_source_tabs
        self._ws_source_tabs_container.visible = True
        self._ws_updating_ui = False
        if self._ws_source_tabs.page is not None:
            self._ws_source_tabs.update()
        if self._ws_source_tabs_container.page is not None:
            self._ws_source_tabs_container.update()

    def _ws_update_source_info(self, record: WallpaperSourceRecord | None) -> None:
        if self._ws_source_info_container is None:
            return
        if record is None:
            self._ws_source_info_container.content = ft.Container()
            self._ws_source_info_container.visible = False
            if self._ws_source_info_container.page is not None:
                self._ws_source_info_container.update()
            return
        spec = record.spec
        if record.identifier.startswith("merged::"):
            origin_label = "合并视图"
            merged_sources = spec.config.get("merged_sources", []) if isinstance(spec.config, dict) else []
            merged_count = len(merged_sources)
            summary_text = (
                f"{origin_label} · 汇总 {merged_count} 个壁纸源 · {len(spec.categories)} 个分类"
            )
        else:
            origin_label = "内置" if record.origin == "builtin" else "用户导入"
            summary_text = (
                f"{origin_label} · 版本 {spec.version} · {len(spec.apis)} 个接口 · {len(spec.categories)} 个分类"
            )
        detail_preview = spec.details or spec.description or spec.name
        summary = ft.Text(summary_text, size=12, color=ft.Colors.GREY)
        info_column = ft.Column(
            [
                ft.Text(spec.name, size=18, weight=ft.FontWeight.BOLD),
                summary,
                ft.Text(
                    detail_preview,
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    selectable=True,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.TextButton(
                    "显示详情",
                    icon=ft.Icons.INFO,
                    on_click=lambda _: self._ws_open_source_details(record),
                ),
            ],
            spacing=4,
        )
        self._ws_source_info_container.content = ft.Row(
            [
                ft.Container(
                    content=self._ws_build_logo_control(record, size=56),
                    width=64,
                    height=64,
                    alignment=ft.alignment.center,
                ),
                info_column,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._ws_source_info_container.visible = True
        if self._ws_source_info_container.page is not None:
            self._ws_source_info_container.update()

    def _ws_update_primary_tabs(
        self, source_id: str | None, *, preserve_selection: bool,
    ) -> None:
        if not source_id or source_id not in self._ws_hierarchy:
            for container in (
                self._ws_primary_container,
                self._ws_secondary_container,
                self._ws_tertiary_container,
                self._ws_leaf_container,
            ):
                container.content = None
                container.visible = False
                if container.page is not None:
                    container.update()
            self._ws_active_primary_key = None
            self._ws_active_secondary_key = None
            self._ws_active_tertiary_key = None
            self._ws_active_leaf_index = 0
            self._ws_active_category_id = None
            self._ws_clear_results("该壁纸源没有可用的分类。")
            return
        primary_list = self._ws_hierarchy[source_id].get("primary_list", [])
        if not primary_list:
            for container in (
                self._ws_primary_container,
                self._ws_secondary_container,
                self._ws_tertiary_container,
                self._ws_leaf_container,
            ):
                container.content = None
                container.visible = False
                if container.page is not None:
                    container.update()
            self._ws_active_primary_key = None
            self._ws_active_secondary_key = None
            self._ws_active_tertiary_key = None
            self._ws_active_leaf_index = 0
            self._ws_active_category_id = None
            self._ws_clear_results("该壁纸源没有可用的分类。")
            return
        show_tabs = len(primary_list) > 1
        if show_tabs:
            if self._ws_primary_tabs is None:
                self._ws_primary_tabs = ft.Tabs(
                    tabs=[],
                    scrollable=True,
                    animation_duration=150,
                    on_change=self._ws_on_primary_tab_change,
                )
            keys = [entry["key"] for entry in primary_list]
            self._ws_updating_ui = True
            self._ws_primary_tabs.tabs = [
                ft.Tab(text=entry["label"]) for entry in primary_list
            ]
            if not preserve_selection or self._ws_active_primary_key not in keys:
                self._ws_active_primary_key = keys[0]
            self._ws_primary_tabs.selected_index = keys.index(
                self._ws_active_primary_key,
            )
            self._ws_primary_tabs.data = {
                "source_id": source_id,
                "keys": keys,
            }
            self._ws_primary_container.content = self._ws_primary_tabs
            self._ws_primary_container.visible = True
            self._ws_updating_ui = False
            if self._ws_primary_tabs.page is not None:
                self._ws_primary_tabs.update()
            if self._ws_primary_container.page is not None:
                self._ws_primary_container.update()
        else:
            self._ws_primary_container.content = None
            self._ws_primary_container.visible = False
            if self._ws_primary_container.page is not None:
                self._ws_primary_container.update()
            self._ws_active_primary_key = primary_list[0]["key"]

        current_primary = next(
            (
                entry
                for entry in primary_list
                if entry["key"] == self._ws_active_primary_key
            ),
            primary_list[0],
        )
        self._ws_update_secondary_tabs(
            source_id,
            current_primary,
            preserve_selection=preserve_selection,
        )

    def _ws_update_secondary_tabs(
        self,
        source_id: str | None,
        primary_entry: dict[str, Any] | None,
        *,
        preserve_selection: bool,
    ) -> None:
        if primary_entry is None:
            self._ws_secondary_container.content = None
            self._ws_secondary_container.visible = False
            if self._ws_secondary_container.page is not None:
                self._ws_secondary_container.update()
            self._ws_active_secondary_key = None
            self._ws_update_tertiary_tabs(None, preserve_selection=preserve_selection)
            return
        secondary_list = [
            entry
            for entry in primary_entry.get("secondary_list", [])
            if any(t["refs"] for t in entry.get("tertiary_list", []))
        ]
        if not secondary_list:
            self._ws_secondary_container.content = None
            self._ws_secondary_container.visible = False
            if self._ws_secondary_container.page is not None:
                self._ws_secondary_container.update()
            self._ws_active_secondary_key = None
            self._ws_update_tertiary_tabs(None, preserve_selection=preserve_selection)
            return
        show_tabs = (
            len(secondary_list) > 1 or secondary_list[0]["key"] != _WS_DEFAULT_KEY
        )
        if show_tabs:
            if self._ws_secondary_tabs is None:
                self._ws_secondary_tabs = ft.Tabs(
                    tabs=[],
                    scrollable=True,
                    animation_duration=150,
                    on_change=self._ws_on_secondary_tab_change,
                )
            keys = [entry["key"] for entry in secondary_list]
            self._ws_updating_ui = True
            self._ws_secondary_tabs.tabs = [
                ft.Tab(text=entry["label"]) for entry in secondary_list
            ]
            if not preserve_selection or self._ws_active_secondary_key not in keys:
                self._ws_active_secondary_key = keys[0]
            self._ws_secondary_tabs.selected_index = keys.index(
                self._ws_active_secondary_key,
            )
            self._ws_secondary_tabs.data = {
                "source_id": source_id,
                "primary_key": primary_entry["key"],
                "keys": keys,
            }
            self._ws_secondary_container.content = self._ws_secondary_tabs
            self._ws_secondary_container.visible = True
            self._ws_updating_ui = False
            if self._ws_secondary_tabs.page is not None:
                self._ws_secondary_tabs.update()
            if self._ws_secondary_container.page is not None:
                self._ws_secondary_container.update()
        else:
            self._ws_secondary_container.content = None
            self._ws_secondary_container.visible = False
            if self._ws_secondary_container.page is not None:
                self._ws_secondary_container.update()
            self._ws_active_secondary_key = secondary_list[0]["key"]

        current_secondary = next(
            (
                entry
                for entry in secondary_list
                if entry["key"] == self._ws_active_secondary_key
            ),
            secondary_list[0],
        )
        self._ws_update_tertiary_tabs(
            current_secondary,
            preserve_selection=preserve_selection,
        )

    def _ws_update_tertiary_tabs(
        self,
        secondary_entry: dict[str, Any] | None,
        *,
        preserve_selection: bool,
    ) -> None:
        if secondary_entry is None:
            self._ws_tertiary_container.content = None
            self._ws_tertiary_container.visible = False
            if self._ws_tertiary_container.page is not None:
                self._ws_tertiary_container.update()
            self._ws_active_tertiary_key = None
            self._ws_update_leaf_tabs([], preserve_selection=preserve_selection)
            return
        tertiary_list = [
            entry
            for entry in secondary_entry.get("tertiary_list", [])
            if entry.get("refs")
        ]
        if not tertiary_list:
            self._ws_tertiary_container.content = None
            self._ws_tertiary_container.visible = False
            if self._ws_tertiary_container.page is not None:
                self._ws_tertiary_container.update()
            self._ws_active_tertiary_key = None
            self._ws_update_leaf_tabs([], preserve_selection=preserve_selection)
            return
        show_tabs = len(tertiary_list) > 1 or tertiary_list[0]["key"] != _WS_DEFAULT_KEY
        if show_tabs:
            if self._ws_tertiary_tabs is None:
                self._ws_tertiary_tabs = ft.Tabs(
                    tabs=[],
                    scrollable=True,
                    animation_duration=150,
                    on_change=self._ws_on_tertiary_tab_change,
                )
            keys = [entry["key"] for entry in tertiary_list]
            self._ws_updating_ui = True
            self._ws_tertiary_tabs.tabs = [
                ft.Tab(text=entry["label"]) for entry in tertiary_list
            ]
            if not preserve_selection or self._ws_active_tertiary_key not in keys:
                self._ws_active_tertiary_key = keys[0]
            self._ws_tertiary_tabs.selected_index = keys.index(
                self._ws_active_tertiary_key,
            )
            self._ws_tertiary_tabs.data = {
                "source_id": self._ws_active_source_id,
                "primary_key": self._ws_active_primary_key,
                "secondary_key": secondary_entry["key"],
                "keys": keys,
            }
            self._ws_tertiary_container.content = self._ws_tertiary_tabs
            self._ws_tertiary_container.visible = True
            self._ws_updating_ui = False
            if self._ws_tertiary_tabs.page is not None:
                self._ws_tertiary_tabs.update()
            if self._ws_tertiary_container.page is not None:
                self._ws_tertiary_container.update()
        else:
            self._ws_tertiary_container.content = None
            self._ws_tertiary_container.visible = False
            if self._ws_tertiary_container.page is not None:
                self._ws_tertiary_container.update()
            self._ws_active_tertiary_key = tertiary_list[0]["key"]

        current_tertiary = next(
            (
                entry
                for entry in tertiary_list
                if entry["key"] == self._ws_active_tertiary_key
            ),
            tertiary_list[0],
        )
        self._ws_update_leaf_tabs(
            current_tertiary["refs"],
            preserve_selection=preserve_selection,
        )

    def _ws_update_leaf_tabs(
        self,
        refs: list[WallpaperCategoryRef],
        *,
        preserve_selection: bool,
    ) -> None:
        if not refs:
            self._ws_leaf_container.content = None
            self._ws_leaf_container.visible = False
            if self._ws_leaf_container.page is not None:
                self._ws_leaf_container.update()
            self._ws_active_leaf_index = 0
            self._ws_active_category_id = None
            self._ws_clear_results("该分类暂无可用壁纸。")
            self._ws_update_param_controls(None)
            self._ws_update_fetch_button_state()
            return
        if self._ws_leaf_tabs is None:
            self._ws_leaf_tabs = ft.Tabs(
                tabs=[],
                scrollable=True,
                animation_duration=150,
                on_change=self._ws_on_leaf_tab_change,
            )
        self._ws_updating_ui = True
        self._ws_leaf_tabs.tabs = [self._ws_build_leaf_tab(ref) for ref in refs]
        max_index = len(refs) - 1
        if not preserve_selection or self._ws_active_leaf_index > max_index:
            self._ws_active_leaf_index = 0
        self._ws_leaf_tabs.selected_index = self._ws_active_leaf_index
        self._ws_leaf_tabs.data = {"refs": refs}
        self._ws_leaf_container.content = self._ws_leaf_tabs
        self._ws_leaf_container.visible = True
        self._ws_updating_ui = False
        if self._ws_leaf_tabs.page is not None:
            self._ws_leaf_tabs.update()
        if self._ws_leaf_container.page is not None:
            self._ws_leaf_container.update()
        self._ws_select_leaf(refs[self._ws_active_leaf_index], force_refresh=False)
        self._ws_update_fetch_button_state()

    def _ws_build_leaf_tab(self, ref: WallpaperCategoryRef) -> ft.Tab:
        icon_control = self._ws_build_category_icon_control(ref.category.icon, size=20)
        if icon_control is None:
            return ft.Tab(text=ref.label)
        tab_row = ft.Row(
            [
                ft.Container(
                    content=icon_control,
                    width=24,
                    height=24,
                    alignment=ft.alignment.center,
                ),
                ft.Text(ref.label, overflow=ft.TextOverflow.ELLIPSIS),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.Tab(
            text=ref.label,
            tab_content=ft.Container(
                content=tab_row,
                padding=ft.padding.symmetric(horizontal=4, vertical=6),
            ),
        )

    def _ws_update_fetch_button_state(self) -> None:
        has_category = bool(self._ws_active_category_id)
        disabled = not has_category or self._ws_fetch_in_progress
        if self._ws_fetch_button is not None:
            self._ws_fetch_button.disabled = disabled
            if self._ws_fetch_button.page is not None:
                self._ws_fetch_button.update()
        if self._ws_reload_button is not None:
            self._ws_reload_button.disabled = self._ws_fetch_in_progress
            if self._ws_reload_button.page is not None:
                self._ws_reload_button.update()

    def _ws_clear_results(self, message: str, *, error: bool = False) -> None:
        self._ws_item_index.clear()
        if self._ws_result_list is not None:
            self._ws_result_list.controls.clear()
            if self._ws_result_list.page is not None:
                self._ws_result_list.update()
        self._ws_set_status(message, error=error)

    def _ws_select_leaf(
        self, ref: WallpaperCategoryRef, *, force_refresh: bool,
    ) -> None:
        self._ws_active_category_id = ref.category_id
        if not self._ws_merge_display:
            self._ws_active_source_id = ref.source_id
        self._ws_active_leaf_index = (
            getattr(self._ws_leaf_tabs, "selected_index", 0)
            if self._ws_leaf_tabs is not None
            else 0
        )
        try:
            self._wallpaper_source_manager.set_active_source(ref.source_id)
        except WallpaperSourceError:
            pass
        if force_refresh:
            self._ws_cached_results.pop(ref.category_id, None)

        self._ws_update_param_controls(ref)

        cached = None if force_refresh else self._ws_cached_results.get(ref.category_id)
        if cached:
            self._ws_display_results(
                ref.category_id,
                cached,
                status_override=f"共 {len(cached)} 项（来自上次获取）。",
            )
        else:
            self._ws_item_index.clear()
            self._ws_set_status("参数已就绪，点击“获取壁纸”开始下载。", error=False)
            if self._ws_result_list is not None:
                self._ws_result_list.controls.clear()
                if self._ws_result_list.page is not None:
                    self._ws_result_list.update()

        self._ws_update_fetch_button_state()

    def _ws_get_active_category_ref(self) -> WallpaperCategoryRef | None:
        category_id = self._ws_active_category_id
        if not category_id:
            return None
        return self._wallpaper_source_manager.find_category(category_id)

    def _ws_update_param_controls(self, ref: WallpaperCategoryRef | None) -> None:
        self._ws_param_controls = []
        if self._ws_param_container is None:
            return
        if ref is None:
            self._ws_param_container.content = None
            self._ws_param_container.visible = False
            if self._ws_param_container.page is not None:
                self._ws_param_container.update()
            return

        record = self._wallpaper_source_manager.get_record(ref.source_id)
        if record is None:
            self._ws_param_container.content = None
            self._ws_param_container.visible = False
            if self._ws_param_container.page is not None:
                self._ws_param_container.update()
            return

        preset_id = ref.category.param_preset_id
        preset = record.spec.parameters.get(preset_id) if preset_id else None
        cached_values = self._ws_param_cache.get(ref.category_id, {})
        controls: list[_WSParameterControl] = []
        if preset is not None:
            for option in preset.options:
                if getattr(option, "hidden", False):
                    continue
                try:
                    control = self._ws_make_parameter_control(
                        option,
                        cached_values.get(option.key),
                    )
                except Exception as exc:
                    logger.error("构建参数控件失败: {error}", error=str(exc))
                    continue
                controls.append(control)

        self._ws_param_controls = controls

        message = (
            "根据需要调整参数，然后点击“获取壁纸”。"
            if controls
            else "此分类无需额外参数，可直接点击“获取壁纸”。"
        )

        body_controls: list[ft.Control] = [
            ft.Text(message, size=12, color=ft.Colors.GREY),
        ]
        if controls:
            body_controls.append(
                ft.Column(
                    [control.display for control in controls],
                    spacing=12,
                    tight=True,
                ),
            )

        self._ws_param_container.content = ft.Container(
            content=ft.Column(body_controls, spacing=12, tight=True),
            bgcolor=self._bgcolor_surface_low,
            padding=12,
            border_radius=8,
        )
        self._ws_param_container.visible = True
        if self._ws_param_container.page is not None:
            self._ws_param_container.update()

    def _ws_make_parameter_control(
        self,
        option: Any,
        cached_value: Any,
    ) -> _WSParameterControl:
        label = getattr(option, "label", None) or getattr(option, "key", "参数")
        description = getattr(option, "description", None) or ""
        param_type = str(getattr(option, "type", "text") or "text").lower()
        default_value = cached_value
        if default_value is None:
            default_value = getattr(option, "default", None)

        def _wrap_display(control: ft.Control) -> ft.Control:
            if description:
                return ft.Column(
                    [control, ft.Text(description, size=11, color=ft.Colors.GREY)],
                    spacing=4,
                    tight=True,
                )
            return control

        if param_type == "choice":
            choices = list(getattr(option, "choices", []) or [])
            dropdown_options = [
                ft.DropdownOption(key=str(choice), text=str(choice))
                for choice in choices
            ]
            dropdown = ft.Dropdown(
                label=label,
                options=dropdown_options,
                value=None,
                dense=True,
            )

            def setter(value: Any) -> None:
                if value is None and choices:
                    dropdown.value = str(choices[0])
                elif value is None:
                    dropdown.value = None
                else:
                    dropdown.value = str(value)
                if dropdown.page is not None:
                    dropdown.update()

            def getter() -> Any:
                raw = dropdown.value
                return None if raw in (None, "") else raw

            setter(default_value)
            display = _wrap_display(dropdown)
            return _WSParameterControl(option, dropdown, display, getter, setter)

        if param_type == "boolean":
            switch = ft.Switch(label=label, value=bool(default_value))

            def setter(value: Any) -> None:
                switch.value = bool(value)
                if switch.page is not None:
                    switch.update()

            def getter() -> bool:
                return bool(switch.value)

            setter(default_value)
            display = _wrap_display(switch)
            return _WSParameterControl(option, switch, display, getter, setter)

        text_field = ft.TextField(
            label=label,
            value="",
            dense=True,
            hint_text=getattr(option, "placeholder", None) or None,
        )

        def setter(value: Any) -> None:
            if value in (None, ""):
                text_field.value = ""
            else:
                text_field.value = str(value)
            if text_field.page is not None:
                text_field.update()

        def getter() -> Any:
            raw = text_field.value or ""
            return raw.strip()

        setter(default_value)
        display = _wrap_display(text_field)
        return _WSParameterControl(option, text_field, display, getter, setter)

    def _ws_normalize_param_value(self, option: Any, value: Any) -> Any:
        param_type = str(getattr(option, "type", "text") or "text").lower()
        if param_type == "boolean":
            return bool(value)
        if param_type == "choice":
            if value in (None, ""):
                return None
            return str(value)
        text = "" if value is None else str(value)
        text = text.strip()
        return text or None

    def _ws_collect_parameters(self, ref: WallpaperCategoryRef) -> dict[str, Any]:
        record = self._wallpaper_source_manager.get_record(ref.source_id)
        if record is None:
            self._ws_param_cache.pop(ref.category_id, None)
            return {}
        preset_id = ref.category.param_preset_id
        preset = record.spec.parameters.get(preset_id) if preset_id else None
        if preset is None:
            self._ws_param_cache.pop(ref.category_id, None)
            return {}

        option_map = {
            control.option.key: control for control in self._ws_param_controls
        }
        values: dict[str, Any] = {}
        cache_entry: dict[str, Any] = {}

        for option in preset.options:
            key = option.key
            if getattr(option, "hidden", False):
                normalized = self._ws_normalize_param_value(
                    option, getattr(option, "default", None),
                )
                cache_entry[key] = normalized
                if normalized is not None:
                    values[key] = normalized
                continue

            control = option_map.get(key)
            if control is not None:
                raw_value = control.getter()
            else:
                raw_value = getattr(option, "default", None)

            normalized = self._ws_normalize_param_value(option, raw_value)
            cache_entry[key] = normalized
            if normalized is not None:
                values[key] = normalized
            elif str(getattr(option, "type", "")).lower() == "boolean":
                values[key] = False

        self._ws_param_cache[ref.category_id] = cache_entry
        return values

    def _ws_on_source_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        keys: list[str] = data.get("keys", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(keys):
            return
        identifier = keys[index]
        if identifier == self._ws_active_source_id:
            return
        self._ws_active_source_id = identifier
        self._ws_active_primary_key = None
        self._ws_active_secondary_key = None
        self._ws_active_tertiary_key = None
        self._ws_active_leaf_index = 0
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        record = self._ws_hierarchy.get(identifier, {}).get("record")
        self._ws_update_source_info(record)
        self._ws_update_primary_tabs(identifier, preserve_selection=False)
        self._ws_update_fetch_button_state()

    def _ws_on_primary_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        keys: list[str] = data.get("keys", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(keys):
            return
        key = keys[index]
        if key == self._ws_active_primary_key:
            return
        self._ws_active_primary_key = key
        self._ws_active_secondary_key = None
        self._ws_active_tertiary_key = None
        self._ws_active_leaf_index = 0
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        hierarchy_entry = self._ws_hierarchy.get(self._ws_active_source_id, {})
        primary_entry = next(
            (
                entry
                for entry in hierarchy_entry.get("primary_list", [])
                if entry["key"] == key
            ),
            None,
        )
        self._ws_update_secondary_tabs(
            self._ws_active_source_id,
            primary_entry,
            preserve_selection=False,
        )
        self._ws_update_fetch_button_state()

    def _ws_on_secondary_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        keys: list[str] = data.get("keys", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(keys):
            return
        key = keys[index]
        if key == self._ws_active_secondary_key:
            return
        self._ws_active_secondary_key = key
        self._ws_active_tertiary_key = None
        self._ws_active_leaf_index = 0
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        source_id = data.get("source_id")
        primary_key = data.get("primary_key")
        primary_entry = None
        if source_id and primary_key:
            primary_entry = next(
                (
                    entry
                    for entry in self._ws_hierarchy.get(source_id, {}).get(
                        "primary_list", [],
                    )
                    if entry["key"] == primary_key
                ),
                None,
            )
        secondary_entry = None
        if primary_entry is not None:
            secondary_entry = next(
                (
                    entry
                    for entry in primary_entry.get("secondary_list", [])
                    if entry["key"] == key
                ),
                None,
            )
        self._ws_update_tertiary_tabs(secondary_entry, preserve_selection=False)
        self._ws_update_fetch_button_state()

    def _ws_on_tertiary_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        keys: list[str] = data.get("keys", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(keys):
            return
        key = keys[index]
        if key == self._ws_active_tertiary_key:
            return
        self._ws_active_tertiary_key = key
        self._ws_active_leaf_index = 0
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        source_id = data.get("source_id")
        primary_key = data.get("primary_key")
        secondary_key = data.get("secondary_key")
        tertiary_entry = None
        if source_id and primary_key and secondary_key:
            primary_entry = next(
                (
                    entry
                    for entry in self._ws_hierarchy.get(source_id, {}).get(
                        "primary_list", [],
                    )
                    if entry["key"] == primary_key
                ),
                None,
            )
            if primary_entry is not None:
                secondary_entry = next(
                    (
                        entry
                        for entry in primary_entry.get("secondary_list", [])
                        if entry["key"] == secondary_key
                    ),
                    None,
                )
                if secondary_entry is not None:
                    tertiary_entry = next(
                        (
                            entry
                            for entry in secondary_entry.get("tertiary_list", [])
                            if entry["key"] == key
                        ),
                        None,
                    )
        refs = tertiary_entry.get("refs", []) if tertiary_entry else []
        self._ws_update_leaf_tabs(refs, preserve_selection=False)
        self._ws_update_fetch_button_state()

    def _ws_on_leaf_tab_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        if self._ws_updating_ui:
            return
        data = getattr(event.control, "data", {}) or {}
        refs: list[WallpaperCategoryRef] = data.get("refs", [])
        index = getattr(event.control, "selected_index", None)
        if not isinstance(index, int) or index < 0 or index >= len(refs):
            return
        self._ws_active_leaf_index = index
        self._ws_select_leaf(refs[index], force_refresh=False)
        self._ws_update_fetch_button_state()

    def _ws_on_search_change(self, event: ft.ControlEvent) -> None:
        if self._ws_fetch_in_progress:
            return
        raw = getattr(event.control, "value", "") or ""
        self._ws_search_text = raw.strip().lower()
        self._ws_recompute_ui(preserve_selection=False)

    def _ws_fetch_active_category(self, force: bool = False) -> None:
        if self._ws_fetch_in_progress:
            return
        ref = self._ws_get_active_category_ref()
        if ref is None:
            self._ws_set_status("请选择分类", error=False)
            return
        if force:
            self._ws_cached_results.pop(ref.category_id, None)
        try:
            params = self._ws_collect_parameters(ref)
        except ValueError as exc:
            self._ws_set_status(str(exc), error=True)
            return
        self._ws_fetch_in_progress = True
        self._ws_update_fetch_button_state()
        self._ws_start_loading("正在下载壁纸…")
        self.page.run_task(
            self._ws_fetch_category_items,
            ref.category_id,
            params or None,
        )

    def _ws_start_loading(self, message: str) -> None:
        if self._ws_loading_indicator is not None:
            self._ws_loading_indicator.visible = True
            if self._ws_loading_indicator.page is not None:
                self._ws_loading_indicator.update()
        self._ws_set_status(message, error=False)

    def _ws_stop_loading(self) -> None:
        if self._ws_loading_indicator is None:
            return
        self._ws_loading_indicator.visible = False
        if self._ws_loading_indicator.page is not None:
            self._ws_loading_indicator.update()

    def _ws_set_status(self, message: str, *, error: bool = False) -> None:
        if self._ws_status_text is None:
            return
        self._ws_status_text.value = message
        self._ws_status_text.color = ft.Colors.ERROR if error else ft.Colors.GREY
        if self._ws_status_text.page is not None:
            self._ws_status_text.update()

    async def _ws_fetch_category_items(
        self,
        category_id: str,
        params: dict[str, Any] | None,
    ) -> None:
        try:
            items = await self._wallpaper_source_manager.fetch_category_items(
                category_id,
                params=params,
            )
        except WallpaperSourceFetchError as exc:
            logger.error("加载壁纸源失败: {error}", error=str(exc))
            self._ws_stop_loading()
            self._ws_set_status(f"加载失败：{exc}", error=True)
            return
        else:
            self._ws_cached_results[category_id] = items
            if self._ws_active_category_id == category_id:
                self._ws_display_results(category_id, items)
            else:
                self._ws_stop_loading()
        finally:
            self._ws_fetch_in_progress = False
            self._ws_update_fetch_button_state()

    def _ws_display_results(
        self,
        category_id: str,
        items: list[WallpaperItem],
        *,
        status_override: str | None = None,
    ) -> None:
        if self._ws_result_list is None:
            return
        self._ws_stop_loading()
        if self._ws_active_category_id != category_id:
            return
        self._ws_result_list.controls.clear()
        filtered = self._ws_filtered_items(items)
        if not filtered:
            self._ws_item_index = {}
            self._ws_set_status("未找到符合条件的壁纸。", error=False)
        else:
            self._ws_item_index = {item.id: item for item in filtered}
            status_message = status_override or f"共 {len(filtered)} 项壁纸。"
            self._ws_set_status(status_message, error=False)
            for item in filtered:
                self._ws_result_list.controls.append(self._ws_build_result_card(item))
        if self._ws_result_list.page is not None:
            self._ws_result_list.update()

    def _ws_filtered_items(self, items: list[WallpaperItem]) -> list[WallpaperItem]:
        if not self._ws_search_text:
            return items
        term = self._ws_search_text.lower()
        return [item for item in items if self._ws_item_matches(item, term)]

    def _ws_item_matches(self, item: WallpaperItem, term: str) -> bool:
        fields = [
            item.title or "",
            item.description or "",
            item.category_label or "",
            item.api_name or "",
            item.original_url or "",
            item.footer_text or "",
        ]
        return any(term in field.lower() for field in fields if field)

    def _ws_build_result_card(self, item: WallpaperItem) -> ft.Control:
        record = self._wallpaper_source_manager.get_record(item.source_id)
        header = ft.Row(
            [
                ft.Container(
                    content=self._ws_build_logo_control(record, size=36),
                    width=40,
                    height=40,
                    alignment=ft.alignment.center,
                ),
                ft.Column(
                    [
                        ft.Text(
                            record.spec.name if record else item.source_id,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            selectable=False,
                        ),
                        ft.Text(
                            f"{item.category_label} · {item.api_name}",
                            size=11,
                            color=ft.Colors.PRIMARY,
                            selectable=False,
                        ),
                    ],
                    spacing=2,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        if item.preview_base64:
            preview: ft.Control = ft.Image(
                src_base64=item.preview_base64,
                width=220,
                height=124,
                fit=ft.ImageFit.COVER,
            )
        elif item.local_path and item.local_path.exists():
            preview = ft.Image(
                src=str(item.local_path),
                width=220,
                height=124,
                fit=ft.ImageFit.COVER,
            )
        else:
            preview = ft.Container(
                width=220,
                height=124,
                bgcolor=self._bgcolor_surface_low,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.GREY),
            )

        info_blocks: list[ft.Control] = [header]
        if item.title:
            info_blocks.append(
                ft.Text(
                    item.title,
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    selectable=True,
                ),
            )
        if item.description:
            info_blocks.append(
                ft.Text(
                    item.description,
                    size=12,
                    selectable=True,
                ),
            )
        if item.copyright:
            info_blocks.append(
                ft.Text(
                    item.copyright,
                    size=11,
                    color=ft.Colors.GREY,
                    selectable=True,
                ),
            )
        if item.footer_text:
            info_blocks.append(
                ft.Text(
                    item.footer_text,
                    size=11,
                    color=ft.Colors.GREY,
                    selectable=False,
                ),
            )

        actions: list[ft.Control] = [
            ft.FilledTonalButton(
                "预览",
                icon=ft.Icons.VISIBILITY,
                on_click=lambda _, wid=item.id: self._ws_open_preview(wid),
            ),
        ]
        if item.original_url:
            actions.append(
                ft.TextButton(
                    "打开原始链接",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _, url=item.original_url: self.page.launch_url(url),
                ),
            )

        card_body = ft.Column(
            [
                preview,
                ft.Column(info_blocks, spacing=4),
                ft.Row(actions, spacing=8, wrap=True),
            ],
            spacing=12,
            tight=True,
        )
        return ft.Card(content=ft.Container(card_body, padding=12))

    def _ws_open_preview(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if item is None:
            self._show_snackbar("未找到该壁纸。", error=True)
            return
        self._ws_preview_item = item
        self._ws_preview_item_id = item_id
        self.page.go("/resource/wallpaper-preview")

    def _ws_build_preview_image(self, item: WallpaperItem) -> ft.Control:
        if item.local_path and item.local_path.exists():
            return ft.Image(
                src=str(item.local_path),
                fit=ft.ImageFit.CONTAIN,
                expand=True,
            )
        if item.preview_base64:
            return ft.Image(
                src_base64=item.preview_base64,
                fit=ft.ImageFit.CONTAIN,
                expand=True,
            )
        return ft.Container(
            alignment=ft.alignment.center,
            bgcolor=self._bgcolor_surface_low,
            border_radius=8,
            padding=24,
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.IMAGE_NOT_SUPPORTED, size=48, color=ft.Colors.GREY,
                    ),
                    ft.Text("预览不可用", size=12, color=ft.Colors.GREY),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
        )

    def build_wallpaper_preview_view(self) -> ft.View:
        item = self._ws_preview_item

        if item is None:
            placeholder = ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(
                            ft.Icons.IMAGE_SEARCH, size=72, color=ft.Colors.OUTLINE,
                        ),
                        ft.Text("未找到预览内容，请返回资源页面重新选择。", size=14),
                        ft.FilledButton(
                            "返回资源页面",
                            icon=ft.Icons.ARROW_BACK,
                            on_click=lambda _: self.page.go("/"),
                        ),
                    ],
                    spacing=16,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
            )

            body_controls = [placeholder]
            if SHOW_WATERMARK:
                body_controls = [
                    ft.Stack([placeholder, build_watermark()], expand=True),
                ]

            return ft.View(
                "/resource/wallpaper-preview",
                [
                    ft.AppBar(
                        title=ft.Text("壁纸预览"),
                        leading=ft.IconButton(
                            ft.Icons.ARROW_BACK,
                            tooltip="返回",
                            on_click=lambda _: self.page.go("/"),
                        ),
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    ),
                    *body_controls,
                ],
            )

        record = self._wallpaper_source_manager.get_record(item.source_id)
        source_name = record.spec.name if record else item.source_id

        preview_container = ft.Container(
            content=self._ws_build_preview_image(item),
            bgcolor=ft.Colors.SURFACE,
            border_radius=12,
            padding=16,
            expand=True,
            height=420,
        )

        description_blocks: list[ft.Control] = []
        if item.title:
            description_blocks.append(
                ft.Text(item.title, size=20, weight=ft.FontWeight.BOLD),
            )
        description_blocks.append(
            ft.Text(
                f"来源：{source_name} · 分类：{item.category_label} · 接口：{item.api_name}",
                size=12,
                color=ft.Colors.GREY,
                selectable=True,
            ),
        )
        if item.description:
            description_blocks.append(
                ft.Text(item.description, size=13, selectable=True),
            )
        if item.copyright:
            description_blocks.append(
                ft.Text(item.copyright, size=12, color=ft.Colors.GREY, selectable=True),
            )
        if item.local_path:
            description_blocks.append(
                ft.Text(
                    f"文件：{item.local_path}",
                    size=12,
                    color=ft.Colors.GREY,
                    selectable=True,
                ),
            )

        actions: list[ft.Control] = [
            ft.FilledButton(
                "设为壁纸",
                icon=ft.Icons.WALLPAPER,
                on_click=lambda _: self.page.run_task(self._ws_set_wallpaper, item.id),
            ),
            ft.FilledTonalButton(
                "复制图片",
                icon=ft.Icons.CONTENT_COPY,
                on_click=lambda _: self.page.run_task(self._ws_copy_image, item.id),
            ),
            ft.FilledTonalButton(
                "加入收藏",
                icon=ft.Icons.BOOKMARK_ADD,
                on_click=lambda _: self._ws_open_favorite_dialog(item.id),
            ),
        ]
        if item.local_path:
            actions.append(
                ft.TextButton(
                    "复制图片文件",
                    icon=ft.Icons.COPY_ALL,
                    on_click=lambda _: self.page.run_task(self._ws_copy_file, item.id),
                ),
            )
        if item.original_url:
            actions.append(
                ft.TextButton(
                    "打开原始链接",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _: self.page.launch_url(item.original_url),
                ),
            )

        footer_controls: list[ft.Control] = []
        if item.footer_text:
            footer_controls.append(
                ft.Container(
                    bgcolor=self._bgcolor_surface_low,
                    border_radius=8,
                    padding=12,
                    content=ft.Text(item.footer_text, size=12, selectable=True),
                ),
            )

        content_column = ft.Column(
            [
                preview_container,
                ft.Row(actions, spacing=12, wrap=True),
                ft.Column(description_blocks, spacing=8, tight=True),
                *footer_controls,
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        preview_body = ft.Container(content_column, expand=True)

        if SHOW_WATERMARK:
            body = ft.Stack([preview_body, build_watermark()], expand=True)
        else:
            body = preview_body

        return ft.View(
            "/resource/wallpaper-preview",
            [
                ft.AppBar(
                    title=ft.Text(item.title or "壁纸预览"),
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        tooltip="返回",
                        on_click=lambda _: self.page.go("/"),
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                body,
            ],
        )

    def _ws_build_logo_control(
        self,
        record: WallpaperSourceRecord | None,
        *,
        size: int = 44,
    ) -> ft.Control:
        if record is None:
            return ft.Icon(
                ft.Icons.COLOR_LENS, size=size * 0.75, color=ft.Colors.PRIMARY,
            )
        logo = (record.spec.logo or "").strip()
        if not logo:
            return ft.Icon(
                ft.Icons.COLOR_LENS, size=size * 0.75, color=ft.Colors.PRIMARY,
            )
        cached = self._ws_logo_cache.get(record.identifier)
        if cached is None:
            lower = logo.lower()
            if lower.startswith("data:") or lower.startswith("image;base64"):
                _, _, payload = logo.partition(",")
                self._ws_logo_cache[record.identifier] = (payload.strip(), True)
            else:
                self._ws_logo_cache[record.identifier] = (logo, False)
            cached = self._ws_logo_cache[record.identifier]
        payload, is_base64 = cached
        if is_base64 and payload:
            return ft.Image(
                src_base64=payload,
                width=size,
                height=size,
                fit=ft.ImageFit.CONTAIN,
            )
        if payload:
            return ft.Image(
                src=payload,
                width=size,
                height=size,
                fit=ft.ImageFit.CONTAIN,
            )
        return ft.Icon(ft.Icons.COLOR_LENS, size=size * 0.75, color=ft.Colors.PRIMARY)

    def _ws_build_category_icon_control(
        self,
        icon: str | None,
        *,
        size: int = 20,
    ) -> ft.Control | None:
        if not icon:
            return None
        cached = self._ws_category_icon_cache.get(icon)
        if cached is None:
            lower = icon.lower()
            if lower.startswith("data:") or lower.startswith("image;base64"):
                _, _, payload = icon.partition(",")
                self._ws_category_icon_cache[icon] = (payload.strip(), True)
            else:
                self._ws_category_icon_cache[icon] = (icon, False)
            cached = self._ws_category_icon_cache.get(icon)
        if cached is None:
            return None
        payload, is_base64 = cached
        if is_base64 and payload:
            return ft.Image(
                src_base64=payload,
                width=size,
                height=size,
                fit=ft.ImageFit.CONTAIN,
            )
        if payload:
            return ft.Image(
                src=payload,
                width=size,
                height=size,
                fit=ft.ImageFit.CONTAIN,
            )
        return None

    def _ws_find_item(self, item_id: str) -> WallpaperItem | None:
        return self._ws_item_index.get(item_id)

    async def _ws_set_wallpaper(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if not item or not item.local_path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        try:
            await asyncio.to_thread(ltwapi.set_wallpaper, str(item.local_path))
        except Exception as exc:
            logger.error("设置壁纸失败: {error}", error=str(exc))
            self._show_snackbar("设置壁纸失败，请查看日志。", error=True)
            return
        self._show_snackbar("已设置为壁纸。")

    async def _ws_copy_image(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if not item or not item.local_path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        success = await asyncio.to_thread(copy_image_to_clipboard, item.local_path)
        if success:
            self._show_snackbar("已复制图片到剪贴板。")
        else:
            self._show_snackbar("复制图片失败。", error=True)

    async def _ws_copy_file(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if not item or not item.local_path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        success = await asyncio.to_thread(
            copy_files_to_clipboard, [str(item.local_path)],
        )
        if success:
            self._show_snackbar("已复制图片文件到剪贴板。")
        else:
            self._show_snackbar("复制文件失败。", error=True)

    def _ws_open_favorite_dialog(self, item_id: str) -> None:
        item = self._ws_find_item(item_id)
        if item is None:
            self._show_snackbar("未找到该壁纸。", error=True)
            return
        payload = self._ws_make_favorite_payload(item)
        if not payload:
            self._show_snackbar("该壁纸暂无可收藏的内容。", error=True)
            return
        self._open_favorite_editor(payload)

    def _ws_make_favorite_payload(self, item: WallpaperItem) -> dict[str, Any]:
        tags: list[str] = []
        if item.category_label:
            tags.append(item.category_label)
        tags = [tag for tag in dict.fromkeys(tag.strip() for tag in tags if tag)]

        preview_data: str | None = None
        if item.preview_base64:
            mime = item.mime_type or "image/jpeg"
            preview_data = f"data:{mime};base64,{item.preview_base64}"
        elif item.local_path:
            preview_data = str(item.local_path)
        elif item.original_url:
            preview_data = item.original_url

        source_preview = item.original_url or preview_data
        record = self._wallpaper_source_manager.get_record(item.source_id)
        source_title = record.spec.name if record else (item.title or item.source_id)
        source_identifier = f"{item.source_id}:{item.id}"

        favorite_source = FavoriteSource(
            type="wallpaper_source",
            identifier=source_identifier,
            title=source_title,
            url=item.original_url,
            preview_url=source_preview,
            local_path=str(item.local_path) if item.local_path else None,
            extra={
                "api_name": item.api_name,
                "category_label": item.category_label,
                "source_id": item.source_id,
            },
        )

        default_folder = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else "default"
        )

        title = item.title or (item.category_label or source_title)

        payload: dict[str, Any] = {
            "folder_id": default_folder,
            "title": title,
            "description": item.description or "",
            "tags": tags,
            "source": favorite_source,
            "preview_url": preview_data,
            "local_path": str(item.local_path) if item.local_path else None,
            "extra": {
                "api_name": item.api_name,
                "category_label": item.category_label,
                "source_id": item.source_id,
                "original_url": item.original_url,
            },
        }
        return payload

    def _ws_open_source_details(self, record: WallpaperSourceRecord) -> None:
        spec = record.spec
        detail_text = spec.details or spec.description or spec.name
        info_rows: list[ft.Control] = [
            ft.Text(f"标识符：{spec.identifier}", size=12),
            ft.Text(
                f"来源：{'内置' if record.origin == 'builtin' else '用户导入'}",
                size=12,
            ),
            ft.Text(f"版本：{spec.version}", size=12),
            ft.Text(f"分类数量：{len(spec.categories)}", size=12),
            ft.Text(f"接口数量：{len(spec.apis)}", size=12),
            ft.Text(
                f"刷新间隔：{spec.refresh_interval_seconds} 秒",
                size=12,
            ),
        ]

        content_column = ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Container(
                            content=self._ws_build_logo_control(record, size=64),
                            width=72,
                            height=72,
                            alignment=ft.alignment.center,
                        ),
                        ft.Column(
                            [
                                ft.Text(spec.name, size=20, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    f"版本 {spec.version} · {len(spec.categories)} 个分类 · {len(spec.apis)} 个接口",
                                    size=12,
                                    color=ft.Colors.GREY,
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(),
                *info_rows,
                ft.Divider(),
                ft.Text(detail_text, size=13, selectable=True),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=False,
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("壁纸源详情"),
            content=content_column,
            actions=[
                ft.TextButton("关闭", on_click=lambda _: self._close_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._open_dialog(dialog)

    def _ws_open_wallpaper_source_settings(self) -> None:
        self.page.go("/settings")
        self.select_settings_tab("content")

    def _ws_refresh_settings_list(self) -> None:
        if self._ws_settings_list is None:
            return
        records = self._wallpaper_source_manager.list_records()
        self._ws_settings_list.controls.clear()
        if not records:
            self._ws_settings_list.controls.append(
                ft.Text("尚未导入任何壁纸源。", size=12, color=ft.Colors.GREY),
            )
        else:
            for record in records:
                self._ws_settings_list.controls.append(
                    self._build_ws_settings_card(record),
                )
        if self._ws_settings_summary_text is not None:
            enabled_count = sum(1 for record in records if record.enabled)
            self._ws_settings_summary_text.value = (
                f"当前共导入 {len(records)} 个源，已启用 {enabled_count} 个。"
            )
            if self._ws_settings_summary_text.page is not None:
                self._ws_settings_summary_text.update()
        if self._ws_settings_list.page is not None:
            self._ws_settings_list.update()

    def _build_wallpaper_source_settings_section(self) -> ft.Control:
        self._ensure_ws_file_picker()
        self._ws_settings_list = ft.Column(spacing=12, expand=True)
        self._ws_refresh_settings_list()
        records = self._wallpaper_source_manager.list_records()
        enabled_count = sum(1 for record in records if record.enabled)
        header = ft.Row(
            [
                ft.Text("壁纸源", size=18, weight=ft.FontWeight.BOLD),
                ft.Row(
                    [
                        ft.FilledButton(
                            "导入 LTWS",
                            icon=ft.Icons.UPLOAD_FILE,
                            on_click=lambda _: self._open_ws_import_picker(),
                        ),
                        ft.TextButton(
                            "刷新",
                            icon=ft.Icons.REFRESH,
                            on_click=lambda _: self._ws_refresh_settings_list(),
                        ),
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._ws_settings_summary_text = ft.Text(
            f"当前共导入 {len(records)} 个源，已启用 {enabled_count} 个。",
            size=12,
            color=ft.Colors.GREY,
        )
        description_text = ft.Text(
            "支持 Little Tree Wallpaper Source Protocol v3.0 (.ltws)",
            size=12,
            color=ft.Colors.GREY,
        )

        display_mode_dropdown = ft.Dropdown(
            label="显示模式",
            value="merge" if self._ws_merge_display else "split",
            options=[
                ft.DropdownOption(key="split", text="按壁纸源分组"),
                ft.DropdownOption(key="merge", text="合并所有分类"),
            ],
            width=220,
            on_change=self._ws_on_merge_mode_change,
        )
        self._ws_merge_mode_dropdown = display_mode_dropdown
        display_mode_row = ft.Row(
            [display_mode_dropdown],
            alignment=ft.MainAxisAlignment.START,
        )

        return ft.Column(
            [
                header,
                description_text,
                display_mode_row,
                self._ws_settings_summary_text,
                ft.Container(
                    content=self._ws_settings_list,
                    bgcolor=self._bgcolor_surface_low,
                    border_radius=8,
                    padding=12,
                    expand=True,
                ),
            ],
            spacing=12,
        )

    def _build_ws_settings_card(self, record: WallpaperSourceRecord) -> ft.Control:
        spec = record.spec
        subtitle_parts = [
            f"ID: {spec.identifier}",
            f"版本: {spec.version}",
            f"来源: {'内置' if record.origin == 'builtin' else '用户'}",
        ]
        try:
            subtitle_parts.append(f"文件: {record.path}")
        except Exception:
            pass
        subtitle_text = " · ".join(subtitle_parts)
        description = spec.description or "未提供描述。"

        enabled_switch = ft.Switch(
            label="启用",
            value=record.enabled,
            on_change=lambda e, rid=record.identifier: self._ws_toggle_source(
                rid, bool(getattr(e.control, "value", False)),
            ),
        )

        remove_button: ft.Control | None = None
        if record.origin == "user":
            remove_button = ft.TextButton(
                "移除",
                icon=ft.Icons.DELETE_OUTLINE,
                on_click=lambda _: self._ws_confirm_remove(record),
            )

        logo = self._ws_build_logo_control(record, size=40)
        info_column = ft.Column(
            [
                ft.Text(spec.name, size=16, weight=ft.FontWeight.BOLD),
                ft.Text(subtitle_text, size=12, color=ft.Colors.GREY, selectable=True),
                ft.Text(description, size=12, selectable=True),
            ],
            spacing=4,
        )

        header_row = ft.Row(
            [
                ft.Container(
                    content=logo,
                    width=44,
                    height=44,
                    alignment=ft.alignment.center,
                ),
                info_column,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        details_button = ft.TextButton(
            "显示详情",
            icon=ft.Icons.INFO,
            on_click=lambda _: self._ws_open_source_details(record),
        )

        action_row_controls: list[ft.Control] = [details_button, enabled_switch]
        if remove_button is not None:
            action_row_controls.append(remove_button)

        card_content = ft.Column(
            [
                header_row,
                ft.Row(action_row_controls, spacing=12, wrap=True),
            ],
            spacing=12,
        )

        return ft.Card(content=ft.Container(card_content, padding=12))

    def _ws_toggle_source(self, identifier: str, enabled: bool) -> None:
        try:
            self._wallpaper_source_manager.set_enabled(identifier, enabled)
        except WallpaperSourceError as exc:
            logger.error("更新壁纸源状态失败: {error}", error=str(exc))
            self._show_snackbar(f"更新失败：{exc}", error=True)
            self._ws_refresh_settings_list()
            return
        self._show_snackbar("已更新壁纸源状态。")
        self._ws_cached_results.clear()
        if not enabled and self._ws_active_source_id == identifier:
            self._ws_active_category_id = None
        self._ws_refresh_settings_list()
        self._ws_recompute_ui(preserve_selection=False)

    def _ws_on_merge_mode_change(self, event: ft.ControlEvent) -> None:
        raw_value = getattr(event.control, "value", "split")
        merge = str(raw_value) == "merge"
        if merge == self._ws_merge_display:
            return
        self._ws_merge_display = merge
        app_config.set("wallpaper.sources.merge_display", merge)
        self._ws_cached_results.clear()
        self._ws_item_index.clear()
        self._ws_active_source_id = None
        self._ws_active_primary_key = None
        self._ws_active_secondary_key = None
        self._ws_active_tertiary_key = None
        self._ws_active_leaf_index = 0
        self._ws_active_category_id = None
        self._ws_recompute_ui(preserve_selection=False)

    def _ws_confirm_remove(self, record: WallpaperSourceRecord) -> None:
        def _confirm(_: ft.ControlEvent | None = None) -> None:
            self._close_dialog()
            self._ws_remove_source(record.identifier)

        def _cancel(_: ft.ControlEvent | None = None) -> None:
            self._close_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("移除壁纸源"),
            content=ft.Text(f"确定要移除 {record.spec.name} 吗？该操作不可撤销。"),
            actions=[
                ft.TextButton("取消", on_click=_cancel),
                ft.FilledButton("移除", icon=ft.Icons.DELETE, on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._open_dialog(dialog)

    def _ws_remove_source(self, identifier: str) -> None:
        try:
            self._wallpaper_source_manager.remove_source(identifier)
        except WallpaperSourceError as exc:
            logger.error("移除壁纸源失败: {error}", error=str(exc))
            self._show_snackbar(f"移除失败：{exc}", error=True)
            return
        self._show_snackbar("已移除壁纸源。")
        if self._ws_active_source_id == identifier:
            self._ws_active_source_id = (
                self._wallpaper_source_manager.active_source_identifier()
            )
            self._ws_active_category_id = None
        self._ws_cached_results.clear()
        self._ws_refresh_settings_list()
        self._ws_recompute_ui(preserve_selection=False)

    def _ensure_ws_file_picker(self) -> None:
        if self._ws_file_picker is None:
            self._ws_file_picker = ft.FilePicker(
                on_result=self._handle_ws_import_result,
            )
        if self._ws_file_picker not in self.page.overlay:
            self.page.overlay.append(self._ws_file_picker)
            self.page.update()

    def _open_ws_import_picker(self) -> None:
        self._ensure_ws_file_picker()
        if self._ws_file_picker:
            self._ws_file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["ltws"],
            )

    def _handle_ws_import_result(self, event: ft.FilePickerResultEvent) -> None:
        if not event.files:
            return
        file = event.files[0]
        if not file.path:
            self._show_snackbar("未选择有效的文件。", error=True)
            return
        try:
            record = self._wallpaper_source_manager.import_source(Path(file.path))
        except WallpaperSourceImportError as exc:
            logger.error("导入壁纸源失败: {error}", error=str(exc))
            self._show_snackbar(f"导入失败：{exc}", error=True)
            return
        self._show_snackbar(f"已导入壁纸源 {record.spec.name}。")
        self._ws_active_source_id = record.identifier
        self._ws_cached_results.clear()
        self._ws_refresh_settings_list()
        self._ws_recompute_ui(preserve_selection=False)

    def _dismiss_im_info_card(self, _: ft.ControlEvent | None = None) -> None:
        if not self._im_info_visible:
            return
        self._im_info_visible = False
        app_config.set(self._im_notice_dismissed_key, True)
        if self._im_info_card is not None:
            self._im_info_card.visible = False
            if self._im_info_card.page is not None:
                self._im_info_card.update()
        self._im_info_card = None

    def _build_im_info_card(self) -> ft.Control | None:
        if not self._im_info_visible:
            self._im_info_card = None
            return None

        close_button = ft.IconButton(
            icon=ft.Icons.CLOSE,
            tooltip="关闭提示",
            on_click=self._dismiss_im_info_card,
        )

        info_card = ft.Card(
            content=ft.Container(
                ft.Column(
                    controls=[
                        ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.INFO,
                                            size=25,
                                            color=ft.Colors.PRIMARY,
                                        ),
                                        ft.Text(
                                            spans=[
                                                ft.TextSpan("图片源的搜集和配置文件由"),
                                                ft.TextSpan(
                                                    "SR 思锐团队",
                                                    url="https://github.com/SRInternet-Studio/",
                                                    style=ft.TextStyle(
                                                        decoration=ft.TextDecoration.UNDERLINE,
                                                    ),
                                                ),
                                                ft.TextSpan(
                                                    "提供 ，图片内容责任由接口方承担",
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                ft.Row(
                                    [
                                        ft.TextButton(
                                            "查看仓库",
                                            icon=ft.Icons.OPEN_IN_NEW,
                                            url="https://github.com/IntelliMarkets/Wallpaper_API_Index",
                                        ),
                                        close_button,
                                    ],
                                ),
                            ],
                            expand=True,
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                    ],
                ),
                padding=10,
                expand=True,
            ),
        )

        self._im_info_card = info_card
        return info_card

    def _build_im_page(self):
        info_card = self._build_im_info_card()

        self._im_loading_indicator = ft.ProgressRing(width=22, height=22, visible=False)
        self._im_status_text = ft.Text("正在初始化 IntelliMarkets 图片源…", size=12)
        self._im_category_dropdown = ft.Dropdown(
            label="分类",
            options=[],
            on_change=self._on_im_category_change,
            expand=True,
        )
        self._im_sources_list = ft.GridView(
            expand=True,
            runs_count=0,
            max_extent=320,
            child_aspect_ratio=1.2,
            spacing=12,
            run_spacing=12,
            controls=[],
        )

        self._im_search_field = ft.TextField(
            label="搜索",
            hint_text="按名称、简介或路径搜索",
            value=self._im_search_text,
            dense=True,
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_im_search_change,
            expand=False,
        )

        refresh_button = ft.TextButton(
            "刷新",
            icon=ft.Icons.REFRESH,
            on_click=lambda _: self.page.run_task(self._load_im_sources, True),
        )
        self._im_refresh_button = refresh_button

        status_row = ft.Row(
            [
                ft.Row(
                    [self._im_loading_indicator, self._im_status_text],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [refresh_button],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # 镜像优先级设置（默认优先 / 镜像优先）
        current_pref = str(
            app_config.get("im.mirror_preference", "default_first") or "default_first",
        )
        self._im_mirror_pref_dropdown = ft.Dropdown(
            label="镜像优先级",
            value=current_pref,
            options=[
                ft.DropdownOption(key="default_first", text="优先默认"),
                ft.DropdownOption(key="mirror_first", text="优先镜像"),
            ],
            on_change=self._on_im_mirror_pref_change,
            width=180,
        )

        filter_row = ft.Row(
            [
                self._im_category_dropdown,
                self._im_mirror_pref_dropdown,
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=12,
        )

        filter_section = ft.Column(
            [filter_row, self._im_search_field], spacing=6, expand=False,
        )

        content_controls: list[ft.Control] = []
        if info_card is not None:
            content_controls.append(info_card)
        content_controls.extend(
            [
                status_row,
                filter_section,
                ft.Container(
                    content=self._im_sources_list,
                    expand=True,
                ),
            ],
        )

        content_column = ft.Column(
            controls=content_controls,
            expand=True,
            spacing=12,
        )

        self._refresh_im_ui()

        return ft.Container(
            content_column,
            padding=5,
            expand=True,
        )

    async def _reload_bing_wallpaper(self) -> None:
        self.bing_loading = True
        self.bing_error = None
        self._refresh_bing_tab()
        await self._load_bing_wallpaper()

    async def _reload_spotlight_wallpaper(self) -> None:
        self.spotlight_loading = True
        self.spotlight_error = None
        self._refresh_spotlight_tab()
        await self._load_spotlight_wallpaper()

    def _on_im_category_change(self, event: ft.ControlEvent) -> None:
        selected = (
            event.control.value if event and getattr(event, "control", None) else None
        )
        if not selected:
            return
        if selected == self._im_selected_category:
            return
        self._im_selected_category = selected
        self._refresh_im_ui()

    def _on_im_mirror_pref_change(self, event: ft.ControlEvent) -> None:
        """Handle mirror preference change and persist setting, then reload sources."""
        try:
            value = (event.control.value or "default_first").strip()
        except Exception:
            value = "default_first"
        if value not in ("default_first", "mirror_first"):
            value = "default_first"
        # persist setting without requiring DEFAULT_CONFIG changes
        app_config.set("im.mirror_preference", value)
        # trigger reloading sources to apply new order
        if self.page:
            self.page.run_task(self._load_im_sources, True)

    def _on_im_search_change(self, event: ft.ControlEvent) -> None:
        raw_value = ""
        if event and getattr(event, "control", None):
            raw_value = str(getattr(event.control, "value", "") or "")
        normalized = raw_value.strip()
        if normalized == self._im_search_text:
            return
        self._im_search_text = normalized
        self._refresh_im_ui()

    def _im_filtered_sources(
        self, search_term: str,
    ) -> tuple[list[dict[str, Any]], str | None, int]:
        if not self._im_sources_by_category:
            return [], None, 0

        category = self._im_selected_category
        if category is None:
            category = self._im_all_category_key
            self._im_selected_category = category

        if category == self._im_all_category_key:
            aggregated: list[dict[str, Any]] = []
            for items in self._im_sources_by_category.values():
                aggregated.extend(items)
            base_sources = sorted(
                aggregated,
                key=lambda item: (
                    item.get("friendly_name") or item.get("file_name") or ""
                ).lower(),
            )
            resolved_category = self._im_all_category_key
        else:
            if category not in self._im_sources_by_category:
                category = next(iter(self._im_sources_by_category), None)
                if category is None:
                    return [], None, 0
                self._im_selected_category = category
            base_sources = list(self._im_sources_by_category.get(category, []))
            resolved_category = category

        if not search_term:
            return base_sources, resolved_category, len(base_sources)

        filtered = [
            item for item in base_sources if self._im_source_matches(item, search_term)
        ]
        return filtered, resolved_category, len(base_sources)

    def _im_source_matches(self, source: dict[str, Any], term: str) -> bool:
        term_lower = term.strip().lower()
        if not term_lower:
            return True

        candidates: list[str] = []
        for key in ("friendly_name", "intro", "file_name", "path", "link", "category"):
            value = source.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

        parameters = source.get("parameters") or []
        if isinstance(parameters, Sequence):
            for param in parameters:
                if not isinstance(param, dict):
                    continue
                for param_key in ("friendly_name", "name"):
                    value = param.get(param_key)
                    if isinstance(value, str) and value:
                        candidates.append(value)

        for candidate in candidates:
            if term_lower in candidate.lower():
                return True

        return False

    # -----------------------------
    # IntelliMarkets 专用镜像策略
    # -----------------------------
    def _im_tarball_candidates(self) -> list[str]:
        logger.info("构建 IntelliMarkets 仓库 tarball 镜像候选列表...")
        owner = self._im_repo_owner
        repo = self._im_repo_name
        branch = self._im_repo_branch
        # 分别构建官方列表和镜像列表，以便于重新排序
        official = [
            f"https://api.github.com/repos/{owner}/{repo}/tarball/{branch}",
            f"https://codeload.github.com/{owner}/{repo}/tar.gz/{branch}",
        ]
        mirror = [
            f"https://api.kkgithub.com/repos/{owner}/{repo}/tarball/{branch}",
            f"https://codeload.kkgithub.com/{owner}/{repo}/tar.gz/{branch}",
        ]
        fallback = [
            f"https://gh-proxy.com/https://api.github.com/repos/{owner}/{repo}/tarball/{branch}",
        ]
        preference = str(
            app_config.get("im.mirror_preference", "default_first") or "default_first",
        )
        logger.info(f"使用镜像优先级设置：{preference}")
        if preference == "mirror_first":
            return [*mirror, *official, *fallback]
        return [*official, *mirror, *fallback]

    def _im_raw_mirrors(self, relative_path: str) -> list[str]:
        # 为 raw 文件构建镜像候选：jsDelivr、Statically
        owner = self._im_repo_owner
        repo = self._im_repo_name
        branch = self._im_repo_branch
        encoded_path = quote(relative_path, safe="/")
        return [
            f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{encoded_path}",
            f"https://cdn.statically.io/gh/{owner}/{repo}/{branch}/{encoded_path}",
        ]

    def _im_request_headers(self, *, binary: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {
            "User-Agent": f"LittleTreeWallpaperNext/{BUILD_VERSION}",
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token.strip()}"
        if not binary:
            headers["Accept"] = "application/vnd.github+json"
        return headers

    async def _fetch_bytes_with_mirrors(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        binary: bool = False,
        timeout: float = 30.0,
        candidates: list[str] | None = None,
    ) -> bytes:
        errors: list[str] = []
        headers = self._im_request_headers(binary=binary)
        trial_list = candidates if candidates else [url]
        for candidate in trial_list:
            try:
                async with session.get(
                    candidate, headers=headers, timeout=timeout,
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    errors.append(f"{candidate} -> HTTP {resp.status}")
            except Exception as exc:  # pragma: no cover - network variability
                errors.append(f"{candidate}: {exc}")
        raise RuntimeError("; ".join(errors))

    def _build_github_raw_url(self, relative_path: str) -> str:
        encoded = quote(relative_path, safe="/")
        return (
            f"https://raw.githubusercontent.com/{self._im_repo_owner}/"
            f"{self._im_repo_name}/{self._im_repo_branch}/{encoded}"
        )

    def _build_github_html_url(self, relative_path: str) -> str:
        encoded = quote(relative_path, safe="/")
        return (
            f"https://github.com/{self._im_repo_owner}/"
            f"{self._im_repo_name}/blob/{self._im_repo_branch}/{encoded}"
        )

    def _build_mirror_url(self, mirror: str, raw_url: str) -> str:
        base = mirror.rstrip("/")
        return f"{base}/{raw_url}"

    def _copy_im_link(self, url: str, label: str) -> None:
        if not url:
            self._show_snackbar("链接不可用", error=True)
            return
        try:
            pyperclip.copy(url)
        except Exception as exc:  # pragma: no cover - clipboard issues
            logger.error(f"复制链接失败: {exc}")
            self._show_snackbar("复制失败，请手动复制", error=True)
            return
        self._show_snackbar(f"{label}已复制")

    def _build_im_source_card(self, source: dict[str, Any]) -> ft.Control:
        friendly_name = (
            source.get("friendly_name") or source.get("file_name") or "未命名"
        )
        intro = source.get("intro") or ""

        # 尝试展示来源 logo（来自 source['icon']，通常为链接），若不存在则显示占位图标
        logo_src = source.get("icon")
        if isinstance(logo_src, str) and logo_src.strip():
            # 直接使用远程/本地链接，Flet 会在运行时加载
            logo_control: ft.Control = ft.Container(
                ft.Image(
                    src=logo_src,
                    width=48,
                    height=48,
                    fit=ft.ImageFit.COVER,
                ),
                width=56,
                height=56,
                padding=ft.padding.all(4),
                border_radius=6,
            )
        else:
            logo_control = ft.Container(
                ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, size=28, color=ft.Colors.GREY),
                width=56,
                height=56,
                alignment=ft.alignment.center,
                bgcolor=self._bgcolor_surface_low,
                border_radius=6,
            )

        # 主要内容区域
        content_area = ft.Column(
            [
                ft.Row(
                    [
                        logo_control,
                        ft.Column(
                            [
                                ft.Text(
                                    friendly_name, size=16, weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(intro, size=12, color=ft.Colors.GREY),
                            ],
                            expand=True,
                            spacing=4,
                        ),
                    ],
                    spacing=8,
                ),
            ],
        )

        # 右下角的打开按钮
        open_button = ft.Container(
            content=ft.FilledTonalButton(
                "打开",
                icon=ft.Icons.PLAY_ARROW,
                on_click=lambda _=None, item=source: self._open_im_source_detail_page(
                    item,
                ),
            ),
            alignment=ft.alignment.bottom_right,
            margin=10,
        )

        # 整个卡片容器
        card_content = ft.Stack(
            [
                ft.Container(content_area, padding=16),
                open_button,
            ],
        )

        return ft.Card(
            content=card_content,
            height=140,
        )

    def _im_source_id(self, source: dict[str, Any]) -> str:
        candidate = (
            source.get("path") or source.get("file_name") or source.get("friendly_name")
        )
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        return f"source-{hashlib.sha1(json.dumps(source, sort_keys=True).encode('utf-8')).hexdigest()}"

    def _open_im_source_detail_page(self, source: dict[str, Any]) -> None:
        self._cancel_im_fetch_task()
        self._im_active_source = source
        self._im_last_results = []
        if self.page is not None:
            self.page.go("/resource/im-source")

    def build_im_source_execution_view(self) -> ft.View:
        route = "/resource/im-source"
        source = self._im_active_source

        if source is None:
            self._im_param_controls = []
            self._im_batch_count_field = None
            self._im_run_button = None
            self._im_result_container = None
            self._im_result_status_text = None
            self._im_result_spinner = None

            placeholder = ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.IMAGE_SEARCH, size=72, color=ft.Colors.OUTLINE),
                        ft.Text("尚未选择图片源，请返回资源页面重新选择。", size=14),
                        ft.FilledButton(
                            "返回资源页面",
                            icon=ft.Icons.ARROW_BACK,
                            on_click=lambda _: self.page.go("/"),
                        ),
                    ],
                    spacing=16,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
                padding=32,
            )

            body = (
                ft.Stack([placeholder, build_watermark()], expand=True)
                if SHOW_WATERMARK
                else placeholder
            )

            return ft.View(
                route,
                [
                    ft.AppBar(
                        title=ft.Text("IntelliMarkets 图片源"),
                        leading=ft.IconButton(
                            ft.Icons.ARROW_BACK,
                            tooltip="返回",
                            on_click=lambda _: self.page.go("/"),
                        ),
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    ),
                    body,
                ],
            )

        friendly_name = (
            source.get("friendly_name") or source.get("file_name") or "未命名图片源"
        )
        intro = source.get("intro") or ""

        header = ft.Row(
            [
                # ft.IconButton(
                #     icon=ft.Icons.ARROW_BACK,
                #     tooltip="返回",
                #     on_click=lambda _: self._close_im_detail_page(),
                # ),
                ft.Column(
                    [
                        ft.Text(friendly_name, size=24, weight=ft.FontWeight.BOLD),
                        ft.Text(intro, size=14, color=ft.Colors.GREY),
                    ],
                    expand=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
        )

        parameter_controls = self._build_im_parameter_controls(source)
        if not parameter_controls:
            params_section = ft.Text("此图片源无需额外参数。", size=12, color=ft.Colors.GREY)
        else:
            params_section = ft.Column(
                [control.display for control in parameter_controls],
                spacing=12,
                tight=True,
            )

        self._im_param_controls = parameter_controls

        self._im_batch_count_field = ft.Dropdown(
            label="获取次数",
            options=[
                ft.DropdownOption(key=str(i), text=f"{i}次") for i in range(1, 11)
            ],
            value="1",
            width=120,
        )

        self._im_run_button = ft.FilledButton(
            "获取壁纸",
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda _: self._start_im_batch_execution(),
        )

        self._im_result_status_text = ft.Text("尚未获取", size=12, color=ft.Colors.GREY)
        self._im_result_spinner = ft.ProgressRing(width=20, height=20, visible=False)
        self._im_result_container = ft.Column(
            spacing=12, expand=True, scroll=ft.ScrollMode.AUTO,
        )

        main_content = ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("参数设置", size=16, weight=ft.FontWeight.W_500),
                            params_section,
                            ft.Row(
                                [
                                    self._im_batch_count_field,
                                    self._im_run_button,
                                ],
                                alignment=ft.MainAxisAlignment.START,
                                spacing=16,
                            ),
                            ft.Row(
                                [self._im_result_spinner, self._im_result_status_text],
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                    ),
                    padding=16,
                    bgcolor=self._bgcolor_surface_low,
                    border_radius=8,
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        "获取结果", size=16, weight=ft.FontWeight.W_500,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.START,
                            ),
                            ft.Container(
                                content=self._im_result_container,
                                expand=True,
                            ),
                        ],
                    ),
                    expand=True,
                    padding=16,
                ),
            ],
            expand=True,
        )

        detail_body = ft.Container(
            content=ft.Column(
                [
                    header,
                    ft.Divider(),
                    main_content,
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            expand=True,
            padding=16,
        )

        body = (
            ft.Stack([detail_body, build_watermark()], expand=True)
            if SHOW_WATERMARK
            else detail_body
        )

        return ft.View(
            route,
            [
                ft.AppBar(
                    title=ft.Text(friendly_name),
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        tooltip="返回",
                        on_click=lambda _: self._close_im_detail_page(),
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                body,
            ],
        )

    def _close_im_detail_page(self) -> None:
        """关闭IM壁纸源详情页面"""
        self._cancel_im_fetch_task()
        self._im_last_results = []
        if self.page is not None:
            self.page.go("/")

    def _set_im_status(self, message: str, *, error: bool = False) -> None:
        if self._im_result_status_text is None:
            return
        self._im_result_status_text.value = message
        self._im_result_status_text.color = ft.Colors.ERROR if error else ft.Colors.GREY
        if self._im_result_status_text.page is not None:
            self._im_result_status_text.update()

    def _build_im_parameter_controls(
        self, source: dict[str, Any],
    ) -> list[_IMParameterControl]:
        parameters = (source.get("content") or {}).get("parameters") or []
        source_id = self._im_source_id(source)
        cached = self._im_cached_inputs.get(source_id, {})
        controls: list[_IMParameterControl] = []
        for index, param in enumerate(parameters):
            try:
                control = self._make_im_parameter_control(param or {}, cached, index)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"构建参数控件失败: {exc}")
                continue
            controls.append(control)
        return controls

    def _make_im_parameter_control(
        self,
        param: dict[str, Any],
        cached: dict[str, Any],
        index: int,
    ) -> _IMParameterControl:
        param_type = str(param.get("type") or "string").lower()
        name = param.get("name")
        key = name or f"__path_segment_{index}"
        friendly = param.get("friendly_name") or name or f"参数 {index + 1}"
        required = bool(param.get("required"))
        split_str = param.get("split_str")
        default_value = self._im_initial_param_value(param, cached.get(key))

        def apply_default(setter: Callable[[Any], None]) -> None:
            try:
                setter(default_value)
            except Exception:
                pass

        if param_type == "enum":
            values = param.get("value") or []
            friendly_values = param.get("friendly_value") or []
            value_map: dict[str, Any] = {}
            options: list[ft.dropdown.Option] = []
            for idx, raw in enumerate(values):
                label = friendly_values[idx] if idx < len(friendly_values) else str(raw)
                option_key = str(idx)
                options.append(ft.dropdown.Option(text=label, key=option_key))
                value_map[option_key] = raw

            dropdown = ft.Dropdown(
                label=friendly,
                options=options,
                value=None,
                dense=True,
            )

            def getter() -> Any:
                selected = dropdown.value
                if selected is None:
                    if required:
                        raise ValueError("请选择一个选项")
                    return None
                return value_map.get(selected)

            def setter(value: Any) -> None:
                target_key = None
                for option_key, raw in value_map.items():
                    if raw == value or str(raw) == str(value):
                        target_key = option_key
                        break
                dropdown.value = target_key
                if dropdown.page is not None:
                    dropdown.update()

            apply_default(setter)
            return _IMParameterControl(param, dropdown, dropdown, getter, setter, key)

        if param_type in {"boolean", "bool"}:
            switch = ft.Switch(label=friendly, value=bool(default_value or False))

            def getter() -> bool:
                return bool(switch.value)

            def setter(value: Any) -> None:
                switch.value = bool(value)
                if switch.page is not None:
                    switch.update()

            apply_default(setter)
            return _IMParameterControl(param, switch, switch, getter, setter, key)

        if param_type in {"integer", "int"}:
            field = ft.TextField(
                label=friendly,
                value="",
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
            )

            def getter() -> Any:
                raw = (field.value or "").strip()
                if not raw:
                    if required:
                        raise ValueError("请输入数值")
                    return None
                try:
                    value = int(raw)
                except ValueError:
                    raise ValueError("请输入合法的整数") from None
                if param.get("min_value") is not None and value < int(
                    param.get("min_value"),
                ):
                    raise ValueError(f"最小值为 {param.get('min_value')}")
                if param.get("max_value") is not None and value > int(
                    param.get("max_value"),
                ):
                    raise ValueError(f"最大值为 {param.get('max_value')}")
                return value

            def setter(value: Any) -> None:
                field.value = "" if value is None else str(value)
                if field.page is not None:
                    field.update()

            apply_default(setter)
            return _IMParameterControl(param, field, field, getter, setter, key)

        if param_type in {"number", "float", "double"}:
            field = ft.TextField(
                label=friendly,
                value="",
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
            )

            def getter() -> Any:
                raw = (field.value or "").strip()
                if not raw:
                    if required:
                        raise ValueError("请输入数值")
                    return None
                try:
                    value = float(raw)
                except ValueError:
                    raise ValueError("请输入合法的数值") from None
                if param.get("min_value") is not None and value < float(
                    param.get("min_value"),
                ):
                    raise ValueError(f"最小值为 {param.get('min_value')}")
                if param.get("max_value") is not None and value > float(
                    param.get("max_value"),
                ):
                    raise ValueError(f"最大值为 {param.get('max_value')}")
                return value

            def setter(value: Any) -> None:
                field.value = "" if value is None else str(value)
                if field.page is not None:
                    field.update()

            apply_default(setter)
            return _IMParameterControl(param, field, field, getter, setter, key)

        if param_type in {"list", "array"}:
            field = ft.TextField(
                label=friendly,
                value="",
                dense=True,
                multiline=True,
                min_lines=1,
                max_lines=4,
                hint_text=f"使用{split_str or '换行'}分隔多个取值",
            )

            def getter() -> Any:
                raw = (field.value or "").strip()
                if not raw:
                    if required:
                        raise ValueError("请输入至少一个值")
                    return []
                values: list[str]
                if split_str:
                    values = [
                        segment.strip()
                        for segment in raw.split(split_str)
                        if segment.strip()
                    ]
                else:
                    tokens = re.split(r"[\s,;]+", raw)
                    values = [segment.strip() for segment in tokens if segment.strip()]
                if required and not values:
                    raise ValueError("请输入至少一个值")
                return values

            def setter(value: Any) -> None:
                if isinstance(value, list):
                    field.value = (split_str or "\n").join(str(item) for item in value)
                elif value is None:
                    field.value = ""
                else:
                    field.value = str(value)
                if field.page is not None:
                    field.update()

            apply_default(setter)
            return _IMParameterControl(param, field, field, getter, setter, key)

        # default: string parameter
        field = ft.TextField(
            label=friendly,
            value="",
            dense=True,
        )

        def getter() -> Any:
            raw = field.value or ""
            raw = raw.strip()
            if not raw and required:
                raise ValueError("请输入参数值")
            return raw or None

        def setter(value: Any) -> None:
            field.value = "" if value in (None, "") else str(value)
            if field.page is not None:
                field.update()

        apply_default(setter)
        return _IMParameterControl(param, field, field, getter, setter, key)

    def _im_initial_param_value(self, param: dict[str, Any], cached_value: Any) -> Any:
        if cached_value not in (None, ""):
            return cached_value
        param_type = str(param.get("type") or "string").lower()
        value = param.get("value")
        if param_type == "enum":
            if isinstance(value, list) and value:
                return value[0]
            return None
        if param_type in {"list", "array"}:
            if isinstance(value, list):
                return value
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []
        if isinstance(value, (str, int, float, bool)):
            return value
        return None

    def _im_set_control_error(self, control: ft.Control, message: str | None) -> None:
        if hasattr(control, "error_text"):
            try:
                control.error_text = message
            except Exception:
                pass
            if control.page is not None:
                control.update()

    def _im_is_empty_value(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, Sequence) and not value:
            return True
        return False

    def _collect_im_parameters(self) -> list[tuple[dict[str, Any], Any]]:
        collected: list[tuple[dict[str, Any], Any]] = []
        errors = False
        current_cache: dict[str, Any] = {}
        for control in self._im_param_controls:
            param = control.config
            required = bool(param.get("required"))
            try:
                value = control.getter()
            except ValueError as exc:
                self._im_set_control_error(control.control, str(exc))
                errors = True
                continue
            self._im_set_control_error(control.control, None)
            if self._im_is_empty_value(value):
                current_cache[control.key] = None
                if required:
                    self._im_set_control_error(control.control, "此参数为必填")
                    errors = True
                continue
            current_cache[control.key] = value
            collected.append((param, value))

        if self._im_active_source is not None:
            source_id = self._im_source_id(self._im_active_source)
            self._im_cached_inputs[source_id] = current_cache

        if errors:
            raise ValueError("invalid parameters")
        return collected

    def _im_param_summary(
        self, param_pairs: list[tuple[dict[str, Any], Any]],
    ) -> dict[str, str]:
        summary: dict[str, str] = {}
        for param, value in param_pairs:
            label = param.get("friendly_name") or param.get("name") or "参数"
            summary[label] = self._im_format_value(value)
        return summary

    def _build_im_request(
        self,
        source: dict[str, Any],
        param_pairs: list[tuple[dict[str, Any], Any]],
    ) -> dict[str, Any]:
        method = (source.get("func") or "GET").upper()
        raw_url = (source.get("link") or "").strip()
        if not raw_url:
            raise ValueError("图片源缺少请求链接")

        base_url, _, query_part = raw_url.partition("?")
        base_url = base_url.rstrip("/")
        query_pairs: list[tuple[str, str]] = []
        if query_part:
            existing_pairs = parse_qsl(query_part, keep_blank_values=True)
            query_pairs.extend(existing_pairs)

        path_segments: list[str] = []
        body_payload: dict[str, Any] = {}
        headers = (source.get("content") or {}).get("headers") or {}

        for param, value in param_pairs:
            name = param.get("name")
            prepared_query = self._im_prepare_param_value(param, value, as_query=True)
            prepared_body = self._im_prepare_param_value(param, value, as_query=False)
            if name in (None, ""):
                values = (
                    prepared_query
                    if isinstance(prepared_query, list)
                    else [prepared_query]
                )
                for segment in values:
                    if segment is None:
                        continue
                    encoded = quote(str(segment).strip("/"))
                    if encoded:
                        path_segments.append(encoded)
                continue

            if method in {"GET", "DELETE"}:
                if isinstance(prepared_query, list):
                    for item in prepared_query:
                        if item is None:
                            continue
                        query_pairs.append((name, str(item)))
                elif prepared_query is not None:
                    query_pairs.append((name, str(prepared_query)))
            elif prepared_body is not None:
                body_payload[name] = prepared_body

        final_url = base_url
        if path_segments:
            final_url = "/".join(
                segment for segment in [base_url, *path_segments] if segment
            )
        if query_pairs:
            final_url = f"{final_url}?{urlencode(query_pairs, doseq=True)}"

        return {
            "url": final_url,
            "method": method,
            "body": body_payload if body_payload else None,
            "headers": headers,
            "query_pairs": query_pairs,
        }

    def _im_prepare_param_value(
        self, param: dict[str, Any], value: Any, *, as_query: bool,
    ) -> Any:
        split_str = param.get("split_str")
        if isinstance(value, list):
            if split_str and as_query:
                return split_str.join(str(item) for item in value)
            return [self._im_format_scalar(item, as_query=as_query) for item in value]
        if isinstance(value, tuple):
            return [self._im_format_scalar(item, as_query=as_query) for item in value]
        return self._im_format_scalar(value, as_query=as_query)

    def _im_format_scalar(self, value: Any, *, as_query: bool) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value and as_query else ("false" if as_query else value)
        if isinstance(value, (int, float)):
            return str(value) if as_query else value
        if isinstance(value, (str, bytes)):
            return (
                value.decode("utf-8", errors="ignore")
                if isinstance(value, bytes)
                else value
            )
        if isinstance(value, Sequence):
            return [self._im_format_scalar(item, as_query=as_query) for item in value]
        return json.dumps(value, ensure_ascii=False)

    def _start_im_batch_execution(self) -> None:
        if self.page is None:
            return
        if self._im_running:
            return
        self._cancel_im_fetch_task()
        task = self.page.run_task(self._execute_im_source_batch)
        self._im_fetch_task = task
        if task is not None:
            task.add_done_callback(self._on_im_fetch_task_done)

    def _cancel_im_fetch_task(self) -> None:
        task = self._im_fetch_task
        if task is None:
            return
        if not task.done():
            task.cancel()
        self._im_fetch_task = None
        self._reset_im_execution_state()

    def _on_im_fetch_task_done(self, task: asyncio.Task[Any]) -> None:
        if self._im_fetch_task is task:
            self._im_fetch_task = None
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            pass

    async def _execute_im_source_batch(self) -> None:
        """批量执行 IM 壁纸源获取，支持执行 1-10 次请求"""
        active_source = self._im_active_source
        if active_source is None:
            self._show_snackbar("请先选择图片源。", error=True)
            return
        if self._im_running:
            return

        # 获取批量数量
        batch_count = 1
        if self._im_batch_count_field and self._im_batch_count_field.value:
            try:
                batch_count = int(self._im_batch_count_field.value)
                batch_count = max(1, min(10, batch_count))  # 限制在1-10之间
            except (ValueError, TypeError):
                batch_count = 1

        self._im_running = True
        if self._im_run_button is not None:
            self._im_run_button.disabled = True
            if self._im_run_button.page is not None:
                self._im_run_button.update()

        if self._im_result_spinner is not None:
            self._im_result_spinner.visible = True
            if self._im_result_spinner.page is not None:
                self._im_result_spinner.update()

        self._set_im_status(f"准备执行 {batch_count} 次请求...")

        try:
            param_pairs = self._collect_im_parameters()
        except ValueError:
            self._set_im_status("参数填写不完整，请检查后重试。", error=True)
            self._reset_im_execution_state()
            return

        try:
            request_info = self._build_im_request(active_source, param_pairs)
        except Exception as exc:
            logger.error(f"构建请求失败: {exc}")
            self._set_im_status(f"构建请求失败：{exc}", error=True)
            self._reset_im_execution_state()
            return

        try:
            all_images: list[dict[str, Any]] = []
            # 统一进行多次获取以确保批量次数
            for i in range(batch_count):
                if self._im_active_source is not active_source:
                    return
                self._set_im_status(f"正在执行第 {i + 1}/{batch_count} 次请求...")
                result_payload = await self._fetch_im_source_result(
                    active_source, request_info, param_pairs,
                )
                images = result_payload.get("images", []) or []
                if images:
                    all_images.extend(images)
                if self._im_active_source is not active_source:
                    return
                await asyncio.sleep(0.8)  # 增加间隔时间，避免请求过于频繁

            if self._im_active_source is not active_source:
                return

            self._im_last_results = all_images
            total_images = len(all_images)
            if total_images:
                self._set_im_status(
                    f"获取成功！共执行 {batch_count} 次请求，累计 {total_images} 张壁纸。",
                )
            else:
                self._set_im_status(
                    f"已完成 {batch_count} 次请求，但未返回任何图片。",
                    error=True,
                )

            # 更新结果视图
            await self._update_im_batch_results_view(all_images)

            # 发送事件
            event_payload = {
                "success": True,
                "source": active_source,
                "request": request_info,
                "images": [image.get("local_path") for image in all_images],
                "timestamp": time.time(),
                "parameters": self._im_param_summary(param_pairs),
                "batch_count": batch_count,
                "image_count": total_images,
            }
            self._emit_im_source_event("resource.im_source.executed", event_payload)

            # 发送执行完成事件（用于插件监听获取完成状态）
            self._emit_im_source_event("resource.im_source.executed", event_payload)

        except asyncio.CancelledError:
            if self._im_active_source is active_source:
                self._set_im_status("获取已取消")
            raise
        except Exception as exc:  # pragma: no cover - network errors
            logger.error(f"执行图片源失败: {exc}")
            self._set_im_status(f"执行失败：{exc}", error=True)

            # 合并失败信息到事件载荷中
            failed_event_payload = {
                "success": False,
                "source": active_source,
                "request": request_info,
                "error": str(exc),
                "timestamp": time.time(),
                # 添加批量获取相关的额外信息
                "source_id": self._im_source_id(active_source) if active_source else None,
                "source_name": active_source.get("friendly_name", "未知源") if active_source else "未知源",
                "results": [],
                "fetch_count": 0,
                "requested_count": batch_count,
            }
            self._emit_im_source_event("resource.im_source.executed", failed_event_payload)
        finally:
            self._reset_im_execution_state()

    def _supports_multiple_images(self, source: dict[str, Any]) -> bool:
        """检查源是否支持一次返回多张图片"""
        # 这里可以添加逻辑判断源是否支持多图片
        # 目前默认为支持，后续可以基于源的配置来判断
        return True

    def _reset_im_execution_state(self) -> None:
        """重置执行状态"""
        self._im_running = False
        if self._im_run_button is not None:
            self._im_run_button.disabled = False
            if self._im_run_button.page is not None:
                self._im_run_button.update()
        if self._im_result_spinner is not None:
            self._im_result_spinner.visible = False
            if self._im_result_spinner.page is not None:
                self._im_result_spinner.update()

    async def _fetch_im_source_result(
        self,
        source: dict[str, Any],
        request_info: dict[str, Any],
        param_pairs: list[tuple[dict[str, Any], Any]],
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=90)
        method = request_info["method"]
        url = request_info["url"]
        headers = request_info.get("headers") or {}
        body = request_info.get("body")

        request_kwargs: dict[str, Any] = {"headers": headers}
        if body and method not in {"GET", "HEAD"}:
            request_kwargs["json"] = body

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **request_kwargs) as resp:
                status = resp.status
                response_headers = {k: v for k, v in resp.headers.items()}
                content_type = response_headers.get("Content-Type", "")
                raw_bytes = await resp.read()

                if status >= 400:
                    snippet = raw_bytes.decode("utf-8", errors="ignore")[:200]
                    raise RuntimeError(f"HTTP {status}: {snippet}")

                image_cfg = ((source.get("content") or {}).get("response") or {}).get(
                    "image",
                ) or {}
                response_type = (image_cfg.get("content_type") or "URL").upper()
                content_type_main = (content_type or "").split(";")[0].lower()

                payload: Any | None = None
                binary_payload: bytes | None = None

                if response_type == "BINARY" and not content_type_main.startswith(
                    "application/json",
                ):
                    binary_payload = raw_bytes
                else:
                    text_payload = (
                        raw_bytes.decode("utf-8", errors="ignore") if raw_bytes else ""
                    )
                    if text_payload:
                        try:
                            payload = json.loads(text_payload)
                        except json.JSONDecodeError as exc:
                            if response_type == "BINARY":
                                binary_payload = raw_bytes
                            else:
                                raise RuntimeError(f"解析接口响应失败：{exc}") from exc
                    else:
                        payload = {}

                return await self._process_im_response(
                    source,
                    request_info,
                    param_pairs,
                    payload,
                    binary_payload,
                    response_headers,
                    content_type_main,
                )

    async def _process_im_response(
        self,
        source: dict[str, Any],
        request_info: dict[str, Any],
        param_pairs: list[tuple[dict[str, Any], Any]],
        payload: Any,
        binary_content: bytes | None,
        headers: dict[str, str],
        content_type: str,
    ) -> dict[str, Any]:
        response_cfg = (source.get("content") or {}).get("response") or {}
        image_cfg = response_cfg.get("image") or {}
        response_type = (image_cfg.get("content_type") or "URL").upper()
        storage_dir = self._im_storage_dir(source)
        timestamp = time.time()
        param_summary = self._im_param_summary(param_pairs)

        images: list[dict[str, Any]] = []

        if response_type == "BINARY":
            if not binary_content:
                raise RuntimeError("接口未返回图片数据")
            path = await asyncio.to_thread(
                self._im_save_image_bytes,
                storage_dir,
                binary_content,
                0,
                headers.get("Content-Type"),
            )
            preview = self._im_make_preview_data(path)
            image_entry = {
                "id": uuid.uuid4().hex,
                "local_path": str(path),
                "original_url": None,
                "source_id": self._im_source_id(source),
                "source_path": source.get("path"),
                "source_title": source.get("friendly_name") or source.get("file_name"),
                "parameters": param_summary,
                "executed_at": timestamp,
                "preview_mime": preview[0] if preview else None,
                "preview_base64": preview[1] if preview else None,
                "details": [],
            }
            images.append(image_entry)
        else:
            if payload is None:
                raise RuntimeError("接口未返回 JSON 数据")
            image_values = self._extract_im_path_values(payload, image_cfg.get("path"))
            if image_cfg.get("is_list"):
                image_values = self._im_flatten_image_values(image_values)
            if not image_values:
                raise RuntimeError("未在响应中找到图片链接")

            for idx, raw in enumerate(image_values):
                if raw in (None, ""):
                    continue
                if isinstance(raw, dict):
                    raw = (
                        raw.get("url")
                        or raw.get("src")
                        or raw.get("image")
                        or raw.get("href")
                    )
                if raw in (None, ""):
                    continue

                local_path: Path | None = None
                original_url: str | None = None

                if image_cfg.get("is_base64"):
                    try:
                        data_bytes = base64.b64decode(str(raw))
                    except Exception as exc:  # pragma: no cover - invalid payload
                        logger.error(f"解码 Base64 图片失败: {exc}")
                        continue
                    local_path = await asyncio.to_thread(
                        self._im_save_image_bytes,
                        storage_dir,
                        data_bytes,
                        idx,
                        headers.get("Content-Type"),
                    )
                else:
                    original_url = str(raw)
                    download_path = await asyncio.to_thread(
                        self._im_download_via_url,
                        original_url,
                        storage_dir,
                    )
                    if not download_path:
                        continue
                    local_path = Path(download_path)

                if local_path is None:
                    continue

                preview = self._im_make_preview_data(local_path)
                image_entry = {
                    "id": uuid.uuid4().hex,
                    "local_path": str(local_path),
                    "original_url": original_url,
                    "source_id": self._im_source_id(source),
                    "source_path": source.get("path"),
                    "source_title": source.get("friendly_name")
                    or source.get("file_name"),
                    "parameters": param_summary,
                    "executed_at": timestamp,
                    "preview_mime": preview[0] if preview else None,
                    "preview_base64": preview[1] if preview else None,
                    "details": [],
                }
                images.append(image_entry)

        per_image_details: list[list[tuple[str, str]]] = [
            [] for _ in range(len(images))
        ]
        global_details: list[tuple[str, str]] = []

        others_sections = response_cfg.get("others") or []
        if payload is not None:
            for section in others_sections:
                entries = section.get("data") or []
                for item in entries:
                    label = (
                        item.get("friendly_name")
                        or section.get("friendly_name")
                        or item.get("name")
                        or "附加信息"
                    )
                    values = self._extract_im_path_values(payload, item.get("path"))
                    if not values:
                        continue
                    mapping = bool(
                        item.get("one-to-one-mapping") or item.get("one_to_one_mapping"),
                    )
                    if mapping:
                        for idx, value in enumerate(values):
                            if idx < len(per_image_details):
                                formatted = self._im_format_value(value)
                                if formatted:
                                    per_image_details[idx].append((label, formatted))
                    else:
                        formatted = self._im_format_value(values)
                        if formatted:
                            global_details.append((label, formatted))

        for idx, image in enumerate(images):
            image["details"] = (
                per_image_details[idx] if idx < len(per_image_details) else []
            )
            image["global_details"] = global_details
            image["favorite_identifier"] = f"{image['source_id']}:{image['id']}"

        return {
            "images": images,
            "global_details": global_details,
            "parameters": param_summary,
            "headers": headers,
            "source": source,
            "request": request_info,
            "timestamp": timestamp,
        }

    def _im_storage_dir(self, source: dict[str, Any]) -> Path:
        slug = self._favorite_filename_slug(
            source.get("friendly_name") or source.get("file_name") or "intellimarkets",
            "intellimarkets",
        )
        directory = (CACHE_DIR / "intellimarkets" / slug).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _im_save_image_bytes(
        self,
        directory: Path,
        data: bytes,
        index: int,
        content_type: str | None,
    ) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        ext = None
        if content_type:
            ext = mimetypes.guess_extension(content_type)
        if not ext:
            ext = ".jpg"
        filename = f"{int(time.time())}-{index}{ext}"
        path = directory / filename
        path.write_bytes(data)
        return path

    def _im_download_via_url(self, url: str, directory: Path) -> str | None:
        try:
            return ltwapi.download_file(url, save_path=str(directory))
        except Exception as exc:  # pragma: no cover - network errors
            logger.error(f"下载图片失败：{exc}")
            return None

    def _im_make_preview_data(self, path: Path) -> tuple[str, str] | None:
        try:
            data = path.read_bytes()
        except Exception as exc:  # pragma: no cover - filesystem errors
            logger.error(f"读取图片失败：{exc}")
            return None
        mime, _ = mimetypes.guess_type(path.name)
        if not mime:
            mime = "image/jpeg"
        encoded = base64.b64encode(data).decode("ascii")
        return mime, encoded

    def _im_parse_path_tokens(self, path: str | None) -> list[tuple[str, Any]]:
        if not path:
            return []
        tokens: list[tuple[str, Any]] = []
        buffer = []
        i = 0
        while i < len(path):
            ch = path[i]
            if ch == ".":
                if buffer:
                    tokens.append(("key", "".join(buffer)))
                    buffer.clear()
                i += 1
                continue
            if ch == "[":
                if buffer:
                    tokens.append(("key", "".join(buffer)))
                    buffer.clear()
                j = path.find("]", i)
                if j == -1:
                    break
                content = path[i + 1 : j]
                if content == "*":
                    tokens.append(("wildcard", None))
                else:
                    try:
                        tokens.append(("index", int(content)))
                    except ValueError:
                        tokens.append(("key", content))
                i = j + 1
                continue
            buffer.append(ch)
            i += 1
        if buffer:
            tokens.append(("key", "".join(buffer)))
        return tokens

    def _extract_im_path_values(self, payload: Any, path: str | None) -> list[Any]:
        tokens = self._im_parse_path_tokens(path)
        if not tokens:
            if payload in (None, ""):
                return []
            if isinstance(payload, list):
                return payload
            return [payload]

        results: list[Any] = []

        def traverse(current: Any, index: int) -> None:
            if index >= len(tokens):
                results.append(current)
                return
            token_type, token_value = tokens[index]
            if token_type == "key":
                if isinstance(current, dict) and token_value in current:
                    traverse(current[token_value], index + 1)
            elif token_type == "index":
                if isinstance(current, Sequence) and not isinstance(
                    current, (str, bytes),
                ):
                    try:
                        traverse(current[token_value], index + 1)
                    except (IndexError, TypeError):
                        return
            elif token_type == "wildcard":
                if isinstance(current, dict):
                    for value in current.values():
                        traverse(value, index + 1)
                elif isinstance(current, Sequence) and not isinstance(
                    current, (str, bytes),
                ):
                    for value in current:
                        traverse(value, index + 1)

        traverse(payload, 0)
        return results

    def _im_flatten_image_values(self, values: Sequence[Any]) -> list[Any]:
        flattened: list[Any] = []
        for value in values:
            if isinstance(value, Sequence) and not isinstance(
                value, (str, bytes, bytearray),
            ):
                flattened.extend(self._im_flatten_image_values(value))
            else:
                flattened.append(value)
        return flattened

    def _im_format_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, (int, float, str)):
            return str(value)
        if isinstance(value, dict):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            formatted = [
                self._im_format_value(item) for item in value if item not in (None, "")
            ]
            return "、".join(filter(None, formatted))
        return str(value)

    async def _update_im_batch_results_view(self, images: list[dict[str, Any]]) -> None:
        """更新批量获取结果视图，显示图片网格和操作按钮"""
        if self._im_result_container is None:
            return

        self._im_result_container.controls.clear()

        if not images:
            self._im_result_container.controls.append(
                ft.Text("暂无图片结果。", size=14, color=ft.Colors.GREY),
            )
        else:
            # 创建图片网格视图
            image_grid = ft.GridView(
                expand=True,
                runs_count=0,
                max_extent=420,
                child_aspect_ratio=1.0,
                spacing=20,
                run_spacing=20,
                controls=[self._build_im_image_card(image) for image in images],
            )
            self._im_result_container.controls.append(image_grid)

        if self._im_result_container.page is not None:
            self._im_result_container.update()

    def _build_im_image_card(self, image: dict[str, Any]) -> ft.Control:
        """构建单个图片卡片，支持收藏、壁纸、下载等操作"""
        preview_base64 = image.get("preview_base64")
        local_path = image.get("local_path")
        file_name = Path(local_path).name if local_path else "未知文件"
        original_url = image.get("original_url")
        image_id = image.get("id", f"img_{hash(str(image))}")

        # 图片预览
        if preview_base64:
            preview_control = ft.Image(
                src_base64=preview_base64,
                width=200,
                height=150,
                fit=ft.ImageFit.COVER,
            )
        elif local_path and Path(local_path).exists():
            preview_control = ft.Image(
                src=str(local_path),
                width=200,
                height=150,
                fit=ft.ImageFit.COVER,
            )
        else:
            preview_control = ft.Container(
                width=200,
                height=150,
                bgcolor=self._bgcolor_surface_low,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.GREY),
            )

        # 主要操作按钮
        main_actions = ft.Row(
            [
                ft.FilledTonalButton(
                    "收藏",
                    icon=ft.Icons.BOOKMARK_ADD,
                    on_click=lambda _, img_id=image_id: self._handle_im_add_favorite(
                        img_id,
                    ),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                    expand=True,
                ),
                ft.FilledTonalButton(
                    "壁纸",
                    icon=ft.Icons.WALLPAPER,
                    on_click=lambda _, img_id=image_id: self.page.run_task(
                        self._handle_im_set_wallpaper, img_id,
                    ),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                    expand=True,
                ),
                ft.FilledTonalButton(
                    "下载",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda _, img_id=image_id: self._handle_im_download_image(
                        img_id,
                    ),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                    expand=True,
                ),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        # 获取插件扩展的菜单项
        plugin_menu_items = self._get_plugin_im_menu_items(image_id, image)

        # 更多操作菜单
        more_menu_items = [
            ft.PopupMenuItem(
                text="另存为",
                on_click=lambda _, img_id=image_id: self._handle_im_save_as(img_id),
            ),
            ft.PopupMenuItem(
                text="复制图片",
                on_click=lambda _, img_id=image_id: self.page.run_task(
                    self._handle_im_copy_image, img_id,
                ),
            ),
            ft.PopupMenuItem(
                text="复制文件",
                on_click=lambda _, img_id=image_id: self.page.run_task(
                    self._handle_im_copy_file, img_id,
                ),
            ),
            ft.Divider(),
            ft.PopupMenuItem(
                text="打开原始链接",
                on_click=lambda _, img_id=image_id: self._handle_im_open_original(
                    img_id,
                ),
                disabled=not original_url,
            ),
        ]

        # 添加插件提供的菜单项
        more_menu_items.extend(plugin_menu_items)

        more_menu = ft.PopupMenuButton(
            items=more_menu_items, icon=ft.Icons.MORE_VERT, tooltip="更多操作",
        )

        # 图片信息
        info_section = ft.Column(
            [
                ft.Text(
                    file_name,
                    size=12,
                    weight=ft.FontWeight.W_500,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Text(
                    f"路径: {local_path[:30]}..."
                    if local_path and len(local_path) > 30
                    else f"路径: {local_path}",
                    size=10,
                    color=ft.Colors.GREY,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            spacing=2,
        )

        # 卡片内容
        card_content = ft.Container(
            ft.Column(
                [
                    ft.Container(
                        content=preview_control,
                        alignment=ft.alignment.center,
                    ),
                    info_section,
                    ft.Container(
                        content=ft.Row(
                            [
                                main_actions,
                                more_menu,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=ft.padding.symmetric(vertical=8),
                    ),
                ],
                spacing=8,
            ),
            padding=16,  # 添加内边距
        )

        return ft.Card(
            content=card_content,
            elevation=2,
        )

    def _handle_im_download_image(self, image_id: str) -> None:
        """处理下载图片操作"""
        # 查找对应的图片数据
        image_data = None
        for img in self._im_last_results:
            if img.get("id") == image_id:
                image_data = img
                break

        if not image_data:
            self._show_snackbar("找不到指定的图片。", error=True)
            return

        local_path = image_data.get("local_path")
        if not local_path or not Path(local_path).exists():
            self._show_snackbar("图片文件不存在。", error=True)
            return

        # 触发下载逻辑
        self._download_file(
            local_path,
            Path(local_path).name,
        )

        # 发送事件
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "download",
                "image_id": image_id,
                "image_data": image_data,
                "source": self._im_active_source,
            },
        )

    def _handle_im_save_as(self, image_id: str) -> None:
        """处理另存为操作"""
        # 查找对应的图片数据
        image_data = None
        for img in self._im_last_results:
            if img.get("id") == image_id:
                image_data = img
                break

        if not image_data:
            self._show_snackbar("找不到指定的图片。", error=True)
            return

        local_path = image_data.get("local_path")
        if not local_path or not Path(local_path).exists():
            self._show_snackbar("图片文件不存在。", error=True)
            return

        # 打开另存为对话框
        self._im_save_picker = ft.FilePicker(on_result=self._on_im_save_file_result)
        self._im_pending_save_source = image_data
        self.page.overlay.append(self._im_save_picker)
        self.page.update()

        self._im_save_picker.save_file(
            dialog_title="另存为",
            file_name=Path(local_path).name,
            allowed_extensions=["jpg", "jpeg", "png", "bmp", "gif", "webp"],
        )

    def _on_im_save_file_result(self, e: ft.FilePickerResultEvent) -> None:
        """另存为文件选择回调"""
        if e.path and self._im_pending_save_source:
            try:
                import shutil

                source_path = Path(self._im_pending_save_source.get("local_path", ""))
                target_path = Path(e.path)
                shutil.copy2(source_path, target_path)
                self._show_snackbar(f"已保存到: {e.path}")

                # 发送事件
                self._emit_im_source_event(
                    "resource.im_source.action",
                    {
                        "action": "save_as",
                        "target_path": e.path,
                        "image_data": self._im_pending_save_source,
                        "source": self._im_active_source,
                    },
                )
            except Exception as exc:
                self._show_snackbar(f"保存失败: {exc}", error=True)

        # 清理
        if self._im_save_picker in self.page.overlay:
            self.page.overlay.remove(self._im_save_picker)
        self._im_pending_save_source = None
        self.page.update()

    def _handle_im_open_original(self, image_id: str) -> None:
        """处理打开原始链接操作"""
        # 查找对应的图片数据
        image_data = None
        for img in self._im_last_results:
            if img.get("id") == image_id:
                image_data = img
                break

        if not image_data:
            self._show_snackbar("找不到指定的图片。", error=True)
            return

        original_url = image_data.get("original_url")
        if not original_url:
            self._show_snackbar("没有可用的原始链接。", error=True)
            return

        # 在默认浏览器中打开
        import webbrowser

        webbrowser.open(original_url)

        # 发送事件
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "open_original",
                "image_data": image_data,
                "source": self._im_active_source,
            },
        )

    def _get_plugin_im_menu_items(
        self, image_id: str, image_data: dict[str, Any],
    ) -> list[ft.PopupMenuItem]:
        """获取插件提供的IM壁纸源菜单项"""
        plugin_menu_items = []

        if not self.plugin_service:
            return plugin_menu_items

        try:
            # 查询所有插件是否有IM壁纸源菜单扩展
            plugins = self.plugin_service.list_plugins()
            for plugin in plugins:
                if plugin.status != PluginStatus.ACTIVE:
                    continue

                # 这里可以扩展插件接口，让插件提供自定义菜单项
                # 暂时使用事件系统来查询插件
                if self.event_bus:
                    menu_items = self._query_plugin_im_menu_items(
                        plugin.identifier, image_id, image_data,
                    )
                    if menu_items:
                        plugin_menu_items.extend(menu_items)
        except Exception as exc:
            logger.error(f"获取插件菜单项失败: {exc}")

        return plugin_menu_items

    def _query_plugin_im_menu_items(
        self, plugin_id: str, image_id: str, image_data: dict[str, Any],
    ) -> list[ft.PopupMenuItem]:
        """查询特定插件的IM壁纸源菜单项"""
        # 这里可以实现具体的插件查询逻辑
        # 目前返回空列表，可以后续扩展
        return []

    def _download_file(self, file_path: str, file_name: str) -> None:
        """下载文件到配置文件指定的目录"""
        # 使用下载管理器获取配置的位置
        download_folder_path = download_manager.get_download_folder_path(app_config)
        if not download_folder_path:
            self._show_snackbar("尚未配置下载目录。", error=True)
            return

        # 确保下载文件夹存在
        try:
            download_folder_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.error(f"创建下载目录失败: {exc}")
            self._show_snackbar("创建下载目录失败。", error=True)
            return

        def _copy() -> Path:
            target = self._generate_resolve_target_path(download_folder_path, file_name)
            shutil.copy2(file_path, target)
            return target

        try:
            final_path = asyncio.to_thread(_copy)
            # 等待异步操作完成
            self.page.run_task(lambda: self._handle_download_complete(final_path))
        except Exception as exc:
            logger.error("下载失败: {error}", error=str(exc))
            self._show_snackbar("下载失败，请查看日志。", error=True)

    async def _handle_download_complete(self, final_path_task) -> None:
        """处理下载完成"""
        try:
            final_path = await final_path_task
            self._show_snackbar(f"已下载到 {final_path}")

            # 发送下载完成事件
            if self._im_active_source:
                self._emit_im_source_event(
                    "resource.im_source.action",
                    {
                        "action": "download",
                        "source_id": self._im_source_id(self._im_active_source),
                        "result": "success",
                        "file_path": str(final_path),
                    },
                )
        except Exception as exc:
            logger.error("下载完成处理失败: {error}", error=str(exc))
            self._show_snackbar("下载失败，请查看日志。", error=True)

    def _build_im_result_card(
        self,
        result: dict[str, Any],
        payload: dict[str, Any],
    ) -> ft.Control:
        preview_base64 = result.get("preview_base64")
        preview_control: ft.Control
        if preview_base64:
            preview_control = ft.Image(
                src_base64=preview_base64,
                width=220,
                height=124,
                fit=ft.ImageFit.COVER,
            )
        else:
            preview_control = ft.Container(
                width=220,
                height=124,
                bgcolor=self._bgcolor_surface_low,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.GREY),
            )

        local_path = result.get("local_path")
        file_name = Path(local_path).name if local_path else "未知文件"
        original_url = result.get("original_url")

        parameter_texts: list[ft.Control] = []
        parameters = payload.get("parameters") or result.get("parameters") or {}
        if parameters:
            parameter_texts.append(
                ft.Text("请求参数", size=12, weight=ft.FontWeight.W_500),
            )
            for key, value in parameters.items():
                parameter_texts.append(
                    ft.Text(f"{key}：{value}", size=12, selectable=True),
                )

        detail_texts: list[ft.Control] = []
        for label, value in result.get("details") or []:
            detail_texts.append(ft.Text(f"{label}：{value}", size=12, selectable=True))

        for label, value in payload.get("global_details") or []:
            detail_texts.append(ft.Text(f"{label}：{value}", size=12, selectable=True))

        result_id = result.get("id")

        actions: list[ft.Control] = [
            ft.IconButton(
                icon=ft.Icons.WALLPAPER,
                tooltip="设为壁纸",
                on_click=lambda _, rid=result_id: self.page.run_task(
                    self._handle_im_set_wallpaper,
                    rid,
                ),
            ),
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY,
                tooltip="复制图片",
                on_click=lambda _, rid=result_id: self.page.run_task(
                    self._handle_im_copy_image,
                    rid,
                ),
            ),
            ft.IconButton(
                icon=ft.Icons.COPY_ALL,
                tooltip="复制图片文件",
                on_click=lambda _, rid=result_id: self.page.run_task(
                    self._handle_im_copy_file,
                    rid,
                ),
            ),
            ft.IconButton(
                icon=ft.Icons.BOOKMARK_ADD,
                tooltip="加入收藏",
                on_click=lambda _, rid=result_id: self._handle_im_add_favorite(rid),
            ),
        ]

        if original_url:
            actions.append(
                ft.IconButton(
                    icon=ft.Icons.OPEN_IN_NEW,
                    tooltip="打开原始链接",
                    on_click=lambda _, url=original_url: self.page.launch_url(url),
                ),
            )



        info_column = ft.Column(
            [
                ft.Text(file_name, size=14, weight=ft.FontWeight.BOLD, selectable=True),
                ft.Text(
                    original_url or "本地文件",
                    size=12,
                    color=ft.Colors.GREY,
                    selectable=True,
                ),
                ft.Column(parameter_texts, spacing=4),
                ft.Column(detail_texts, spacing=4),
                ft.Row(actions, spacing=8, wrap=True),
            ],
            spacing=8,
            expand=True,
        )

        return ft.Card(
            content=ft.Container(
                ft.Row(
                    [preview_control, info_column],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=12,
            ),
        )

    def _find_im_result(self, result_id: str | None) -> dict[str, Any] | None:
        if result_id is None:
            return None
        for item in self._im_last_results:
            if item.get("id") == result_id:
                return item
        return None

    async def _handle_im_set_wallpaper(self, result_id: str | None) -> None:
        result = self._find_im_result(result_id)
        if not result:
            self._show_snackbar("未找到图片。", error=True)
            return
        path = result.get("local_path")
        if not path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        try:
            await asyncio.to_thread(ltwapi.set_wallpaper, path)
        except Exception as exc:  # pragma: no cover - platform specific errors
            logger.error(f"设置壁纸失败：{exc}")
            self._show_snackbar("设置壁纸失败，请查看日志。", error=True)
            self._emit_im_source_event(
                "resource.im_source.action",
                {
                    "action": "set_wallpaper",
                    "success": False,
                    "result": result,
                    "error": str(exc),
                },
            )
            return
        self._show_snackbar("已设置为壁纸。")
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "set_wallpaper",
                "success": True,
                "result": result,
            },
        )

    async def _handle_im_copy_image(self, result_id: str | None) -> None:
        result = self._find_im_result(result_id)
        if not result:
            self._show_snackbar("未找到图片。", error=True)
            return
        path = result.get("local_path")
        if not path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        try:
            await asyncio.to_thread(copy_image_to_clipboard, path)
        except Exception as exc:  # pragma: no cover - platform dependent
            logger.error(f"复制图片失败：{exc}")
            self._show_snackbar("复制图片失败。", error=True)
            self._emit_im_source_event(
                "resource.im_source.action",
                {
                    "action": "copy_image",
                    "success": False,
                    "result": result,
                    "error": str(exc),
                },
            )
            return
        self._show_snackbar("已复制图片到剪贴板。")
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "copy_image",
                "success": True,
                "result": result,
            },
        )

    async def _handle_im_copy_file(self, result_id: str | None) -> None:
        result = self._find_im_result(result_id)
        if not result:
            self._show_snackbar("未找到图片。", error=True)
            return
        path = result.get("local_path")
        if not path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        try:
            await asyncio.to_thread(copy_files_to_clipboard, [path])
        except Exception as exc:  # pragma: no cover - platform dependent
            logger.error(f"复制图片文件失败：{exc}")
            self._show_snackbar("复制图片文件失败。", error=True)
            self._emit_im_source_event(
                "resource.im_source.action",
                {
                    "action": "copy_file",
                    "success": False,
                    "result": result,
                    "error": str(exc),
                },
            )
            return
        self._show_snackbar("已将图片文件复制到剪贴板。")
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "copy_file",
                "success": True,
                "result": result,
            },
        )

    def _handle_im_add_favorite(self, result_id: str | None) -> None:
        result = self._find_im_result(result_id)
        if not result:
            self._show_snackbar("未找到图片。", error=True)
            return
        local_path = result.get("local_path")
        if not local_path:
            self._show_snackbar("图片文件不存在。", error=True)
            return
        folder_id = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else None
        )
        favorite_source = FavoriteSource(
            type="intellimarkets",
            identifier=result.get("favorite_identifier") or uuid.uuid4().hex,
            title=result.get("source_title") or "IntelliMarkets",
            url=result.get("original_url"),
            preview_url=result.get("original_url"),
            local_path=str(local_path),
            extra={
                "executed_at": result.get("executed_at"),
                "source_path": result.get("source_path"),
                "parameters": result.get("parameters"),
            },
        )
        item, created = self._favorite_manager.add_or_update_item(
            folder_id=folder_id,
            title=Path(local_path).name,
            source=favorite_source,
            local_path=str(local_path),
            extra=dict(favorite_source.extra or {}),
            description="",
            tags=None,
        )
        self._favorite_manager.update_localization(
            item.id,
            status="completed",
            local_path=str(local_path),
            folder_path=None,
            message=None,
        )
        if created:
            self._show_snackbar("已添加到收藏。")
        else:
            self._show_snackbar("已更新收藏记录。")
        self._refresh_favorite_tabs()
        self._emit_im_source_event(
            "resource.im_source.action",
            {
                "action": "favorite",
                "success": True,
                "result": result,
            },
        )

    # 不再提供“打开所在文件夹”的行为

    def _emit_im_source_event(self, event_name: str, payload: dict[str, Any]) -> None:
        try:
            self._emit_resource_event(event_name, payload)
        except Exception as exc:  # pragma: no cover - event bus errors
            logger.error(f"分发事件 {event_name} 失败：{exc}")

    def _refresh_im_ui(self) -> None:
        search_term = (self._im_search_text or "").strip()
        filtered_sources, resolved_category, base_count = self._im_filtered_sources(
            search_term,
        )
        match_count = len(filtered_sources)
        search_active = bool(search_term)
        display_term = (
            search_term.replace("\r", " ").replace("\n", " ") if search_active else ""
        )
        if search_active and len(display_term) > 24:
            display_term = f"{display_term[:21]}..."

        if self._im_search_field:
            self._im_search_field.value = self._im_search_text
            if self._im_search_field.page is not None:
                self._im_search_field.update()

        if self._im_loading_indicator:
            self._im_loading_indicator.visible = self._im_loading
        if self._im_refresh_button:
            self._im_refresh_button.disabled = self._im_loading

        if self._im_status_text:
            if self._im_error:
                self._im_status_text.value = f"加载失败：{self._im_error}"
                self._im_status_text.color = ft.Colors.ERROR
            elif self._im_loading and not self._im_sources_by_category:
                self._im_status_text.value = "正在加载 IntelliMarkets 图片源…"
                self._im_status_text.color = ft.Colors.GREY
            elif self._im_sources_by_category:
                category_count = len(self._im_sources_by_category)
                summary = (
                    f"共 {category_count} 个分类 / {self._im_total_sources} 个图片源"
                )
                if self._im_last_updated:
                    formatted = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(self._im_last_updated),
                    )
                    summary += f" · 更新于 {formatted}"
                if search_active:
                    summary += f' · 搜索 "{display_term}" 匹配 {match_count} 项'
                self._im_status_text.value = summary
                self._im_status_text.color = ft.Colors.GREY
            else:
                self._im_status_text.value = "尚未加载图片源"
                self._im_status_text.color = ft.Colors.GREY

        if self._im_category_dropdown:
            options: list[ft.dropdown.Option] = [
                ft.dropdown.Option(
                    key=self._im_all_category_key, text=self._im_all_category_label,
                ),
            ]
            options.extend(
                ft.dropdown.Option(key=name, text=name)
                for name in self._im_sources_by_category.keys()
            )
            self._im_category_dropdown.options = options
            if self._im_sources_by_category:
                if resolved_category is None:
                    resolved_category = self._im_all_category_key
                self._im_category_dropdown.value = resolved_category
                self._im_category_dropdown.disabled = False
            else:
                self._im_category_dropdown.value = self._im_all_category_key
                self._im_category_dropdown.disabled = True

        if self._im_sources_list:
            if self._im_loading and not self._im_sources_by_category:
                self._im_sources_list.controls = [
                    ft.Container(
                        ft.Column(
                            [
                                ft.ProgressRing(width=32, height=32),
                                ft.Text("正在拉取图片源列表…"),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=20,
                    ),
                ]
            elif self._im_error and not self._im_sources_by_category:
                self._im_sources_list.controls = [
                    ft.Container(
                        ft.Text(self._im_error, color=ft.Colors.ERROR),
                        padding=20,
                    ),
                ]
            elif filtered_sources:
                self._im_sources_list.controls = [
                    self._build_im_source_card(item) for item in filtered_sources
                ]
            else:
                if self._im_sources_by_category:
                    if search_active and base_count > 0:
                        message = f'未找到与 "{display_term}" 匹配的图片源'
                    else:
                        message = "该分类暂无图片源"
                else:
                    message = "尚未加载图片源"
                self._im_sources_list.controls = [
                    ft.Container(ft.Text(message), padding=20),
                ]

        if self.page:
            self.page.update()

    async def _load_im_sources(self, force: bool = False) -> None:
        if self._im_loading:
            return
        self._im_loading = True
        self._im_error = None
        self._refresh_im_ui()

        # 构建 tarball 候选列表（官方与镜像）
        tarball_candidates = self._im_tarball_candidates()
        logger.info(f"IntelliMarkets 图片源下载候选：{tarball_candidates}")

        timeout = aiohttp.ClientTimeout(total=60)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                tarball_bytes = await self._fetch_bytes_with_mirrors(
                    session,
                    tarball_candidates[0],
                    binary=True,
                    timeout=timeout.total,
                    candidates=tarball_candidates,
                )
            logger.info("成功获取 IntelliMarkets 图片源数据，开始解析内容…")

            categories: dict[str, list[dict[str, Any]]] = {}
            total_sources = 0
            tar_stream = io.BytesIO(tarball_bytes)
            with tarfile.open(fileobj=tar_stream, mode="r:gz") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    if not member.name.lower().endswith(".json"):
                        continue
                    parts = member.name.split("/", 1)
                    if len(parts) < 2:
                        continue
                    relative_path = parts[1]
                    if not relative_path:
                        continue
                    relative_segments = relative_path.split("/")
                    if not relative_segments:
                        continue

                    if len(relative_segments) == 1:
                        category_name = "未分类"
                        file_name = relative_segments[0]
                    else:
                        category_name = relative_segments[0]
                        file_name = relative_segments[-1]

                    if not file_name.lower().endswith(".json"):
                        continue

                    extracted = tar.extractfile(member)
                    if extracted is None:
                        continue
                    raw_bytes = extracted.read()
                    text = raw_bytes.decode("utf-8-sig", errors="ignore")
                    try:
                        config_payload = json.loads(text)
                    except json.JSONDecodeError as exc:
                        logger.error(
                            "解析 IntelliMarkets 图片源失败: {path} -> {error}",
                            path=relative_path,
                            error=str(exc),
                        )
                        continue

                    raw_url = self._build_github_raw_url(relative_path)
                    html_url = self._build_github_html_url(relative_path)
                    # 专用于程序内部的 raw 镜像候选（不展示给用户）
                    raw_mirror_candidates = self._im_raw_mirrors(relative_path)

                    source_info: dict[str, Any] = {
                        "category": category_name,
                        "path": relative_path,
                        "file_name": file_name,
                        "friendly_name": config_payload.get("friendly_name")
                        or file_name,
                        "intro": config_payload.get("intro") or "",
                        "icon": config_payload.get("icon"),
                        "link": config_payload.get("link"),
                        "func": config_payload.get("func") or "GET",
                        "apicore_version": config_payload.get("APICORE_version"),
                        "parameters": config_payload.get("parameters"),
                        "response": config_payload.get("response"),
                        "raw_url": raw_url,
                        "html_url": html_url,
                        "raw_mirror_candidates": raw_mirror_candidates,
                        "size": member.size,
                        "content": config_payload,
                    }

                    categories.setdefault(category_name, []).append(source_info)
                    total_sources += 1
            logger.info(
                "IntelliMarkets 图片源解析完成，共加载 {count} 个图片源。",
                count=total_sources,
            )
            for items in categories.values():
                items.sort(
                    key=lambda item: (
                        item.get("friendly_name") or item.get("file_name") or ""
                    ).lower(),
                )

            self._im_sources_by_category = categories
            self._im_total_sources = total_sources
            if self._im_selected_category is None or (
                self._im_selected_category != self._im_all_category_key
                and self._im_selected_category not in categories
            ):
                self._im_selected_category = (
                    self._im_all_category_key if categories else None
                )
            self._im_last_updated = time.time()
        except Exception as exc:  # pragma: no cover - network variability
            logger.error(f"加载 IntelliMarkets 图片源失败: {exc}")
            self._im_error = str(exc)
            self._im_sources_by_category = {}
            self._im_total_sources = 0
        finally:
            self._im_loading = False
            self._refresh_im_ui()

    # ------------------------------------------------------------------
    # favorite helpers
    # ------------------------------------------------------------------
    def _favorite_folders(self) -> list[FavoriteFolder]:
        try:
            return self._favorite_manager.list_folders()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"加载收藏夹失败: {exc}")
            return []

    def _favorite_tab_ids(self, folders: list[FavoriteFolder]) -> list[str]:
        return ["__all__"] + [folder.id for folder in folders]

    def _build_favorite_tabs_list(self, folders: list[FavoriteFolder]) -> list[ft.Tab]:
        self._favorite_item_localize_controls = {}
        self._favorite_item_wallpaper_buttons = {}
        self._favorite_item_export_buttons = {}
        tabs: list[ft.Tab] = [
            ft.Tab(
                text="全部",
                icon=ft.Icons.ALL_INBOX,
                content=self._build_favorite_folder_view("__all__"),
            ),
        ]
        for folder in folders:
            icon = ft.Icons.STAR if folder.id == "default" else ft.Icons.FOLDER_SPECIAL
            tabs.append(
                ft.Tab(
                    text=folder.name,
                    icon=icon,
                    content=self._build_favorite_folder_view(folder.id),
                ),
            )
        return tabs

    def _favorite_preview_source(self, item: FavoriteItem) -> tuple[str, str] | None:
        for candidate in (
            item.localization.local_path,
            item.local_path,
        ):
            if not candidate:
                continue
            try:
                path = Path(candidate)
                if not path.exists():
                    continue
                resolved = path.resolve()
                try:
                    mtime = resolved.stat().st_mtime
                except Exception:
                    mtime = time.time()
                cached = self._favorite_preview_cache.get(item.id)
                if cached and abs(cached[0] - mtime) < 1e-6:
                    return ("base64", cached[1])
                data = resolved.read_bytes()
                encoded = base64.b64encode(data).decode("ascii")
                if len(self._favorite_preview_cache) >= 32:
                    oldest_key = next(iter(self._favorite_preview_cache))
                    self._favorite_preview_cache.pop(oldest_key, None)
                self._favorite_preview_cache[item.id] = (mtime, encoded)
                return ("base64", encoded)
            except Exception as exc:
                logger.warning("加载本地预览失败: {error}", error=str(exc))
        if item.preview_url:
            return ("url", item.preview_url)
        if item.source.url:
            return ("url", item.source.url)
        return None

    def _favorite_filename_slug(self, raw: str, fallback: str) -> str:
        cleaned = "".join(
            ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_"
            for ch in (raw or "").strip()
        ).strip()
        cleaned = re.sub(r"\s+", "-", cleaned)
        return cleaned or fallback

    def _favorite_default_package_path(self, item: FavoriteItem) -> Path:
        exports_dir = self._favorite_manager.localization_root().parent / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        base_name = self._favorite_filename_slug(item.title or "favorite", item.id[:8])
        candidate = (exports_dir / f"{base_name}.ltwfav").resolve()
        counter = 1
        while candidate.exists():
            candidate = (exports_dir / f"{base_name}-{counter}.ltwfav").resolve()
            counter += 1
        return candidate

    def _favorite_default_asset_path(
        self, item: FavoriteItem, source_path: Path,
    ) -> Path:
        exports_dir = self._favorite_manager.localization_root().parent / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        suffix = source_path.suffix or ""
        base_name = self._favorite_filename_slug(item.title or "favorite", item.id[:8])
        candidate = (exports_dir / f"{base_name}{suffix}").resolve()
        counter = 1
        while candidate.exists():
            candidate = (exports_dir / f"{base_name}-{counter}{suffix}").resolve()
            counter += 1
        return candidate

    def _set_item_localizing(self, item_id: str, active: bool) -> None:
        if active:
            self._favorite_localizing_items.add(item_id)
            self._favorite_preview_cache.pop(item_id, None)
        else:
            self._favorite_localizing_items.discard(item_id)
        button: ft.IconButton | None = None
        indicator: ft.Control | None = None
        controls = self._favorite_item_localize_controls.get(item_id)
        if controls:
            button, indicator = controls
        if indicator is not None:
            indicator.visible = active
            if indicator.page is not None:
                indicator.update()
        if button is not None:
            button.visible = not active
            if not active:
                current_item = self._favorite_manager.get_item(item_id)
                has_localized = (
                    current_item is not None
                    and current_item.localization.status == "completed"
                    and current_item.localization.local_path
                    and Path(current_item.localization.local_path).exists()
                )
                button.disabled = has_localized
                button.tooltip = "已完成本地化" if has_localized else "本地化此收藏"
            if button.page is not None:
                button.update()
        wallpaper_button = self._favorite_item_wallpaper_buttons.get(item_id)
        if wallpaper_button is not None:
            wallpaper_button.disabled = active
            if wallpaper_button.page is not None:
                wallpaper_button.update()
        export_button = self._favorite_item_export_buttons.get(item_id)
        if export_button is not None:
            export_button.disabled = active
            if export_button.page is not None:
                export_button.update()

    def _show_localization_progress(self, total: int) -> None:
        self._favorite_batch_total = max(total, 0)
        self._favorite_batch_done = 0
        if self._favorite_localization_spinner is not None:
            self._favorite_localization_spinner.visible = True
        if self._favorite_localization_progress_bar is not None:
            self._favorite_localization_progress_bar.value = 0.0
            self._favorite_localization_progress_bar.visible = True
        if self._favorite_localization_status_text is not None:
            self._favorite_localization_status_text.value = (
                f"正在本地化 0/{total} 项收藏…" if total else "正在本地化…"
            )
        if self._favorite_localization_status_row is not None:
            self._favorite_localization_status_row.visible = True
        for control in (
            self._favorite_localization_status_text,
            self._favorite_localization_progress_bar,
            self._favorite_localization_spinner,
            self._favorite_localization_status_row,
        ):
            if control is not None and control.page is not None:
                control.update()

    def _update_localization_progress(self, increment: int = 1) -> None:
        if self._favorite_batch_total <= 0:
            return
        self._favorite_batch_done = min(
            self._favorite_batch_total,
            self._favorite_batch_done + max(0, increment),
        )
        if self._favorite_localization_progress_bar is not None:
            self._favorite_localization_progress_bar.value = (
                self._favorite_batch_done / self._favorite_batch_total
            )
        if self._favorite_localization_status_text is not None:
            self._favorite_localization_status_text.value = f"已本地化 {self._favorite_batch_done}/{self._favorite_batch_total} 项收藏"
        for control in (
            self._favorite_localization_status_text,
            self._favorite_localization_progress_bar,
        ):
            if control is not None and control.page is not None:
                control.update()

    def _finish_localization_progress(self, success: int, total: int) -> None:
        if self._favorite_localization_spinner is not None:
            self._favorite_localization_spinner.visible = False
        if self._favorite_localization_progress_bar is not None:
            self._favorite_localization_progress_bar.value = 1.0 if total else 0.0
            self._favorite_localization_progress_bar.visible = total > 0
        if self._favorite_localization_status_text is not None:
            self._favorite_localization_status_text.value = (
                f"本地化完成：成功 {success}/{total} 项" if total else "本地化完成"
            )
        for control in (
            self._favorite_localization_status_text,
            self._favorite_localization_progress_bar,
            self._favorite_localization_spinner,
            self._favorite_localization_status_row,
        ):
            if control is not None and control.page is not None:
                control.update()

        async def _hide_row_later() -> None:
            await asyncio.sleep(2)
            if self._favorite_localization_status_row is not None:
                self._favorite_localization_status_row.visible = False
                if self._favorite_localization_status_row.page is not None:
                    self._favorite_localization_status_row.update()

        if total > 0:
            self.page.run_task(_hide_row_later)

    def _build_favorite_folder_view(self, folder_id: str) -> ft.Control:
        items = self._favorite_manager.list_items(
            None if folder_id in (None, "__all__") else folder_id,
        )
        if not items:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.INBOX, size=48, color=ft.Colors.OUTLINE),
                        ft.Text("这里还没有收藏，去添加一个吧~"),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                padding=32,
                expand=True,
            )

        grid = ft.GridView(
            expand=True,
            runs_count=0,
            max_extent=360,
            child_aspect_ratio=1.15,
            spacing=16,
            run_spacing=16,
            auto_scroll=False,
        )
        for item in items:
            grid.controls.append(self._build_favorite_card(item))

        if folder_id in (None, "__all__"):
            folder_label = "全部收藏"
        else:
            folder = self._favorite_manager.get_folder(folder_id)
            folder_label = folder.name if folder else "收藏夹"

        header_row = ft.Row(
            [
                ft.Text(folder_label, size=14, weight=ft.FontWeight.BOLD),
                ft.Text(f"共 {len(items)} 项收藏", size=12, color=ft.Colors.GREY),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=ft.Column(
                [
                    header_row,
                    grid,
                ],
                spacing=12,
                expand=True,
            ),
            padding=ft.Padding(12, 12, 12, 16),
            expand=True,
        )

    def _build_favorite_card(self, item: FavoriteItem) -> ft.Control:
        preview_src = self._favorite_preview_source(item)
        preview_kwargs: dict[str, Any] = {
            "width": 160,
            "height": 96,
            "fit": ft.ImageFit.COVER,
            "border_radius": 12,
        }
        if preview_src:
            source_type, value = preview_src
            if source_type == "base64":
                preview_control = ft.Image(src_base64=value, **preview_kwargs)
            else:
                preview_control = ft.Image(src=value, **preview_kwargs)
        else:
            preview_control = ft.Container(
                width=preview_kwargs["width"],
                height=preview_kwargs["height"],
                border_radius=preview_kwargs["border_radius"],
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.OUTLINE),
            )

        max_tag_badges = 6
        tag_controls: list[ft.Control]
        if item.tags:
            tag_controls = [
                ft.Container(
                    content=ft.Text(
                        tag,
                        size=11,
                        color=ft.Colors.ON_SECONDARY_CONTAINER,
                    ),
                    padding=ft.Padding(8, 4, 8, 4),
                    border_radius=ft.border_radius.all(12),
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                )
                for tag in item.tags[:max_tag_badges]
            ]
            overflow_count = len(item.tags) - max_tag_badges
            if overflow_count > 0:

                def _open_tags_dialog(
                    _: ft.ControlEvent | None = None,
                    entry: FavoriteItem = item,
                ) -> None:
                    self._show_favorite_tags_dialog(entry)

                overflow_badge = ft.GestureDetector(
                    on_tap=_open_tags_dialog,
                    mouse_cursor=ft.MouseCursor.CLICK,
                    content=ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.LABEL_OUTLINE,
                                    size=12,
                                    color=ft.Colors.GREY,
                                ),
                                ft.Text(
                                    f"+{overflow_count}",
                                    size=11,
                                    color=ft.Colors.GREY,
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(10, 4, 10, 4),
                        border_radius=ft.border_radius.all(12),
                        bgcolor=ft.Colors.with_opacity(
                            0.08, ft.Colors.SECONDARY_CONTAINER,
                        ),
                    ),
                )
                tag_controls.append(overflow_badge)
        else:
            tag_controls = [ft.Text("未添加标签", size=11, color=ft.Colors.GREY)]

        ai_controls: list[ft.Control] = []
        if item.ai.suggested_tags:
            ai_controls.append(
                ft.Text(
                    f"AI 建议：{', '.join(item.ai.suggested_tags)}",
                    size=11,
                    color=ft.Colors.SECONDARY,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            )
        elif item.ai.status in {"pending", "running"}:
            ai_controls.append(
                ft.Text("AI 正在分析…", size=11, color=ft.Colors.SECONDARY),
            )
        elif item.ai.status == "failed":
            ai_controls.append(ft.Text("AI 分析失败", size=11, color=ft.Colors.ERROR))

        info_column = ft.Column(
            [
                ft.Text(
                    item.title,
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Text(
                    item.description or "暂无描述",
                    size=12,
                    color=ft.Colors.GREY,
                    max_lines=3,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Row(
                    controls=tag_controls,
                    spacing=6,
                    run_spacing=6,
                    wrap=True,
                ),
            ],
            spacing=8,
            expand=True,
        )

        if item.source.title or item.source.type:
            info_column.controls.append(
                ft.Text(
                    f"来源：{item.source.title or item.source.type}",
                    size=11,
                    color=ft.Colors.GREY,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            )

        localization = item.localization
        if localization.status == "completed" and localization.local_path:
            info_column.controls.append(
                ft.Text(
                    "已本地化",
                    size=11,
                    color=getattr(ft.Colors, "GREEN_400", ft.Colors.GREEN),
                ),
            )
        elif localization.status == "pending":
            info_column.controls.append(
                ft.Text("正在本地化…", size=11, color=ft.Colors.SECONDARY),
            )
        elif localization.status == "failed":
            info_column.controls.append(
                ft.Text(
                    localization.message or "本地化失败",
                    size=11,
                    color=ft.Colors.ERROR,
                ),
            )
        else:
            info_column.controls.append(
                ft.Text("未本地化", size=11, color=ft.Colors.GREY),
            )

        if ai_controls:
            info_column.controls.extend(ai_controls)

        is_localized = (
            item.localization.status == "completed"
            and item.localization.local_path
            and Path(item.localization.local_path).exists()
        )

        localize_button = ft.IconButton(
            icon=ft.Icons.DOWNLOAD_FOR_OFFLINE,
            tooltip="本地化此收藏",
            on_click=lambda _, item_id=item.id: self._handle_localize_single_item(
                item_id,
            ),
        )
        if is_localized:
            localize_button.disabled = True
            localize_button.tooltip = "已完成本地化"
        localize_indicator = ft.Container(
            content=ft.ProgressRing(width=20, height=20),
            alignment=ft.alignment.center,
            width=40,
            height=40,
        )
        is_localizing = (
            item.id in self._favorite_localizing_items
            or item.localization.status in {"pending"}
        )
        localize_button.visible = not is_localizing
        localize_indicator.visible = is_localizing
        localization_stack = ft.Stack(
            controls=[localize_button, localize_indicator],
            width=40,
            height=40,
        )
        self._favorite_item_localize_controls[item.id] = (
            localize_button,
            localize_indicator,
        )

        set_wallpaper_button = ft.IconButton(
            icon=ft.Icons.WALLPAPER,
            tooltip="设为壁纸",
            on_click=lambda _, item_id=item.id: self._handle_set_favorite_wallpaper(
                item_id,
            ),
            disabled=is_localizing,
        )
        export_button = ft.IconButton(
            icon=ft.Icons.UPLOAD_FILE,
            tooltip="导出此收藏",
            on_click=lambda _, item_id=item.id: self._handle_export_single_item(
                item_id,
            ),
            disabled=is_localizing,
        )
        self._favorite_item_wallpaper_buttons[item.id] = set_wallpaper_button
        self._favorite_item_export_buttons[item.id] = export_button

        action_buttons: list[ft.Control] = [
            localization_stack,
            set_wallpaper_button,
            export_button,
            ft.IconButton(
                icon=ft.Icons.EDIT,
                tooltip="编辑收藏",
                on_click=lambda _, item_id=item.id: self._edit_favorite(item_id),
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                tooltip="移除收藏",
                on_click=lambda _, item_id=item.id: self._remove_favorite(item_id),
            ),
        ]

        if item.source.url:
            action_buttons.append(
                ft.IconButton(
                    icon=ft.Icons.OPEN_IN_NEW,
                    tooltip="打开来源链接",
                    on_click=lambda _, url=item.source.url: self.page.launch_url(url),
                ),
            )

        actions_row = ft.Row(
            action_buttons,
            alignment=ft.MainAxisAlignment.END,
            spacing=4,
            wrap=True,
            run_spacing=4,
        )

        body_row = ft.Row(
            [preview_control, info_column],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        footer_column = ft.Column(
            [
                ft.Divider(
                    height=1,
                    thickness=1,
                    color=ft.Colors.with_opacity(0.08, ft.Colors.OUTLINE),
                ),
                actions_row,
            ],
            spacing=12,
        )

        card_body = ft.Column(
            [body_row, footer_column],
            spacing=12,
            expand=True,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        card_container = ft.Container(
            width=320,
            height=280,
            padding=16,
            content=card_body,
        )

        card = ft.Card(elevation=1, content=card_container)

        return ft.Container(width=320, height=280, content=card)

    def _show_favorite_tags_dialog(self, item: FavoriteItem) -> None:
        tags = list(item.tags or [])
        if not tags:
            return

        tag_items = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.TAG, size=14, color=ft.Colors.SECONDARY),
                        ft.Text(tag, size=12),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(12, 6, 12, 6),
                border_radius=ft.border_radius.all(8),
                bgcolor=ft.colors.with_opacity(0.04, ft.Colors.SECONDARY_CONTAINER),
            )
            for tag in tags
        ]

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"“{item.title or '收藏'}”的全部标签"),
            content=ft.Container(
                width=360,
                content=ft.Column(
                    [
                        ft.Text(
                            f"共 {len(tags)} 个标签",
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                        ft.Container(
                            height=240,
                            content=ft.Column(
                                controls=tag_items,
                                spacing=8,
                                tight=True,
                                scroll=ft.ScrollMode.AUTO,
                            ),
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[ft.TextButton("关闭", on_click=lambda _: self._close_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _parse_tag_input(self, raw: str) -> list[str]:
        if not raw:
            return []
        normalized = raw.replace("，", ",").replace("、", ",")
        tokens = re.split(r"[\s,;]+", normalized)
        return [token.strip() for token in tokens if token.strip()]

    def _update_favorite_folder_toolbar(self) -> None:
        edit_button = self._favorite_edit_folder_button
        delete_button = self._favorite_delete_folder_button
        current_folder = self._favorite_selected_folder
        manage_enabled = current_folder not in (None, "__all__")
        if edit_button is not None:
            edit_button.disabled = not manage_enabled
            if edit_button.page is not None:
                edit_button.update()
        if delete_button is not None:
            delete_enabled = manage_enabled and current_folder != "default"
            delete_button.disabled = not delete_enabled
            if delete_button.page is not None:
                delete_button.update()

    async def _localize_favorite_item(self, item: FavoriteItem) -> bool:
        if (
            item.localization.status == "completed"
            and item.localization.local_path
            and Path(item.localization.local_path).exists()
        ):
            return True
        if item.local_path and Path(item.local_path).exists():
            destination = await asyncio.to_thread(
                self._favorite_manager.localize_item_from_file,
                item.id,
                item.local_path,
            )
            return destination is not None
        download_url = item.preview_url or item.source.preview_url or item.source.url
        if not download_url:
            logger.warning("收藏缺少可下载地址，跳过本地化: {item}", item=item.id)
            return False
        downloads_dir = (
            self._favorite_manager.localization_root() / "__downloads"
        ).resolve()
        downloads_dir.mkdir(parents=True, exist_ok=True)
        temp_name = f"{item.id}-{uuid.uuid4().hex}"
        downloaded_path = await asyncio.to_thread(
            ltwapi.download_file,
            download_url,
            downloads_dir,
            temp_name,
        )
        if not downloaded_path:
            return False
        destination = await asyncio.to_thread(
            self._favorite_manager.localize_item_from_file,
            item.id,
            str(downloaded_path),
        )
        # 清理临时文件
        try:
            Path(downloaded_path).unlink(missing_ok=True)
        except Exception:
            pass
        return destination is not None

    async def _ensure_favorite_local_copy(self, item: FavoriteItem) -> str | None:
        for candidate in (item.localization.local_path, item.local_path):
            if candidate and Path(candidate).exists():
                return str(Path(candidate))
        success = await self._localize_favorite_item(item)
        if not success:
            return None
        refreshed = self._favorite_manager.get_item(item.id) or item
        for candidate in (refreshed.localization.local_path, refreshed.local_path):
            if candidate and Path(candidate).exists():
                return str(Path(candidate))
        return None

    def _handle_localize_current_folder(self, _: ft.ControlEvent | None = None) -> None:
        folder_id = self._favorite_selected_folder
        items = self._favorite_manager.list_items(
            None if folder_id in (None, "__all__") else folder_id,
        )
        if not items:
            self._show_snackbar("当前视图没有可本地化的收藏。")
            return

        button = self._favorite_localize_button
        if button is not None:
            button.disabled = True
            button.update()

        async def _runner() -> None:
            success = 0
            self._show_localization_progress(len(items))
            for item in items:
                self._favorite_manager.update_localization(
                    item.id,
                    status="pending",
                    local_path=item.localization.local_path,
                    folder_path=item.localization.folder_path,
                )
                self._set_item_localizing(item.id, True)
                try:
                    current_item = self._favorite_manager.get_item(item.id) or item
                    if await self._localize_favorite_item(current_item):
                        success += 1
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error(f"本地化收藏失败: {exc}")
                finally:
                    self._set_item_localizing(item.id, False)
                    self._update_localization_progress()
            self._refresh_favorite_tabs()
            if button is not None:
                button.disabled = False
                button.update()
            self._finish_localization_progress(success, len(items))
            self._show_snackbar(f"已本地化 {success}/{len(items)} 项收藏。")

        self.page.run_task(_runner)

    def _handle_localize_single_item(self, item_id: str) -> None:
        item = self._favorite_manager.get_item(item_id)
        if not item:
            self._show_snackbar("未找到指定的收藏。", error=True)
            return

        self._favorite_manager.update_localization(
            item_id,
            status="pending",
            local_path=item.localization.local_path,
            folder_path=item.localization.folder_path,
        )
        self._set_item_localizing(item_id, True)

        async def _runner() -> None:
            try:
                target_item = self._favorite_manager.get_item(item_id) or item
                success = await self._localize_favorite_item(target_item)
                if success:
                    self._show_snackbar(f"收藏“{item.title}”已本地化。")
                else:
                    self._show_snackbar("本地化失败，请检查网络或文件。", error=True)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"本地化收藏失败: {exc}")
                self._show_snackbar("本地化失败，请查看日志。", error=True)
            finally:
                self._set_item_localizing(item_id, False)
                self._refresh_favorite_tabs()

        self.page.run_task(_runner)

    def _handle_set_favorite_wallpaper(self, item_id: str) -> None:
        item = self._favorite_manager.get_item(item_id)
        if not item:
            self._show_snackbar("未找到指定的收藏。", error=True)
            return

        button = self._favorite_item_wallpaper_buttons.get(item_id)
        if button is not None:
            button.disabled = True
            if button.page is not None:
                button.update()

        pre_existing_local = False
        for candidate in (
            item.localization.local_path,
            item.local_path,
        ):
            if candidate and Path(candidate).exists():
                pre_existing_local = True
                break

        async def _runner() -> None:
            if not pre_existing_local:
                self._set_item_localizing(item_id, True)
            try:
                target_item = self._favorite_manager.get_item(item_id) or item
                local_path = await self._ensure_favorite_local_copy(target_item)
                if not local_path:
                    self._show_snackbar(
                        "无法准备壁纸文件，请尝试先本地化。", error=True,
                    )
                    return
                await asyncio.to_thread(ltwapi.set_wallpaper, local_path)
                self._show_snackbar("壁纸设置成功。")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"设置收藏壁纸失败: {exc}")
                self._show_snackbar("设置壁纸失败，请查看日志。", error=True)
            finally:
                if not pre_existing_local:
                    self._set_item_localizing(item_id, False)
                    self._refresh_favorite_tabs()
                refreshed_button = self._favorite_item_wallpaper_buttons.get(item_id)
                if refreshed_button is not None:
                    refreshed_button.disabled = False
                    if refreshed_button.page is not None:
                        refreshed_button.update()

        self.page.run_task(_runner)

    def _handle_export_single_item(self, item_id: str) -> None:
        item = self._favorite_manager.get_item(item_id)
        if not item:
            self._show_snackbar("未找到指定的收藏。", error=True)
            return

        export_button = self._favorite_item_export_buttons.get(item_id)
        if export_button is not None:
            export_button.disabled = True
            if export_button.page is not None:
                export_button.update()

        pre_existing_local = False
        for candidate in (
            item.localization.local_path,
            item.local_path,
        ):
            if candidate and Path(candidate).exists():
                pre_existing_local = True
                break

        if not pre_existing_local:
            self._set_item_localizing(item_id, True)

        package_path = self._favorite_default_package_path(item)

        async def _runner() -> None:
            try:
                target_item = self._favorite_manager.get_item(item_id) or item
                local_path = await self._ensure_favorite_local_copy(target_item)
                if local_path:
                    source = Path(local_path)
                    export_path = self._favorite_default_asset_path(target_item, source)
                    await asyncio.to_thread(shutil.copy2, source, export_path)
                    self._show_snackbar(f"收藏文件已复制到 {export_path}。")
                    return

                exported_path = await asyncio.to_thread(
                    self._favorite_manager.export_items,
                    package_path,
                    [item_id],
                )
                self._show_snackbar(f"收藏已导出到 {exported_path}。")
            except ValueError as exc:
                logger.error(f"导出收藏失败: {exc}")
                self._show_snackbar(str(exc), error=True)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"导出收藏失败: {exc}")
                self._show_snackbar("导出失败，请查看日志。", error=True)
            finally:
                if not pre_existing_local:
                    self._set_item_localizing(item_id, False)
                    self._refresh_favorite_tabs()
                refreshed = self._favorite_item_export_buttons.get(item_id)
                if refreshed is not None:
                    refreshed.disabled = False
                    if refreshed.page is not None:
                        refreshed.update()

        self.page.run_task(_runner)

    def _open_export_dialog(self) -> None:
        folders = self._favorite_folders()
        if not folders:
            self._show_snackbar("没有可导出的收藏夹。", error=True)
            return

        default_folder = self._favorite_selected_folder
        selected_ids: set[str] = set()
        if default_folder and default_folder not in ("__all__", ""):
            selected_ids.add(default_folder)
        elif default_folder == "__all__":
            selected_ids.update(folder.id for folder in folders)

        folder_checkboxes: list[tuple[ft.Checkbox, str]] = []
        select_all_checkbox = ft.Checkbox(
            label="全部收藏夹",
            value=default_folder == "__all__",
        )
        export_button_holder: dict[str, ft.Control | None] = {"button": None}

        def _sync_selection(_: ft.ControlEvent | None = None) -> None:
            if select_all_checkbox.value:
                selected_ids.clear()
                selected_ids.update(folder.id for folder in folders)
                for checkbox, _ in folder_checkboxes:
                    checkbox.value = True
            else:
                selected_ids.clear()
                for checkbox, folder_id in folder_checkboxes:
                    if checkbox.value:
                        selected_ids.add(folder_id)
            button_control = export_button_holder["button"]
            if isinstance(button_control, ft.Control):
                button_control.disabled = not bool(selected_ids)
                button_control.update()

        for folder in folders:
            checkbox = ft.Checkbox(
                label=folder.name,
                value=folder.id in selected_ids or not selected_ids,
            )
            checkbox.on_change = _sync_selection
            folder_checkboxes.append((checkbox, folder.id))

        select_all_checkbox.on_change = _sync_selection

        exports_dir = self._favorite_manager.localization_root().parent / "exports"
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        default_path = (exports_dir / f"favorites-{timestamp}.ltwfav").resolve()
        path_field = ft.TextField(
            label="导出文件 (.ltwfav)",
            value=str(default_path),
            autofocus=True,
            expand=True,
        )

        status_text = ft.Text("选择要导出的收藏夹，并指定导出文件路径。", size=12)

        def _submit(_: ft.ControlEvent | None = None) -> None:
            if not selected_ids:
                self._show_snackbar("请至少选择一个收藏夹。", error=True)
                return
            target = Path(path_field.value).expanduser()

            async def _runner() -> None:
                export_button = export_button_holder["button"]
                if isinstance(export_button, ft.Control):
                    export_button.disabled = True
                    export_button.update()
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    folder_list = list(selected_ids)
                    await asyncio.to_thread(
                        self._favorite_manager.export_folders,
                        target,
                        folder_list,
                    )
                    self._show_snackbar(f"收藏已导出到 {target}。")
                    self._close_dialog()
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error(f"导出收藏失败: {exc}")
                    self._show_snackbar("导出失败，请检查日志。", error=True)
                finally:
                    if isinstance(export_button, ft.Control):
                        export_button.disabled = False
                        export_button.update()

            self.page.run_task(_runner)

        export_button = ft.FilledButton(
            "导出",
            icon=ft.Icons.CLOUD_UPLOAD,
            on_click=_submit,
        )
        export_button_holder["button"] = export_button

        content = ft.Container(
            width=420,
            content=ft.Column(
                [
                    status_text,
                    select_all_checkbox,
                    ft.Column([cb for cb, _ in folder_checkboxes], spacing=4),
                    path_field,
                ],
                spacing=12,
                tight=True,
            ),
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("导出收藏"),
            content=content,
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                export_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)
        _sync_selection()  # 初始化按钮状态

    def _open_import_dialog(self) -> None:
        path_field = ft.TextField(
            label="导入文件 (.ltwfav)",
            autofocus=True,
            expand=True,
        )

        status_text = ft.Text("选择导入包后，系统会合并收藏夹及收藏记录。", size=12)

        def _submit(_: ft.ControlEvent | None = None) -> None:
            path = Path(path_field.value).expanduser()
            if not path.exists():
                self._show_snackbar("指定的导入文件不存在。", error=True)
                return

            async def _runner() -> None:
                import_button.disabled = True
                import_button.update()
                try:
                    folders, items = await asyncio.to_thread(
                        self._favorite_manager.import_folders,
                        path,
                    )
                    self._show_snackbar(
                        f"导入完成：新增收藏夹 {folders} 个，收藏 {items} 条。",
                    )
                    self._favorite_selected_folder = "__all__"
                    self._refresh_favorite_tabs()
                    self._close_dialog()
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error(f"导入收藏失败: {exc}")
                    self._show_snackbar("导入失败，请检查日志。", error=True)
                finally:
                    import_button.disabled = False
                    import_button.update()

            self.page.run_task(_runner)

        import_button = ft.FilledButton(
            "导入",
            icon=ft.Icons.FILE_UPLOAD,
            on_click=_submit,
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("导入收藏"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    [status_text, path_field],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                import_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _on_favorite_tab_change(self, event: ft.ControlEvent) -> None:
        folders = self._favorite_folders()
        index = getattr(event.control, "selected_index", 0) if event.control else 0
        if index <= 0 or not folders:
            self._favorite_selected_folder = "__all__"
        else:
            normalized_index = min(index - 1, len(folders) - 1)
            self._favorite_selected_folder = folders[normalized_index].id
        self._update_favorite_folder_toolbar()
        self.page.update()

    def _refresh_favorite_tabs(self) -> None:
        if not self._favorite_tabs:
            return
        folders = self._favorite_folders()
        tab_ids = self._favorite_tab_ids(folders)
        if self._favorite_selected_folder not in tab_ids:
            self._favorite_selected_folder = "__all__"
        tabs_control = self._favorite_tabs
        tabs_control.tabs = self._build_favorite_tabs_list(folders)
        tabs_control.selected_index = tab_ids.index(self._favorite_selected_folder)
        if tabs_control.page is not None:
            tabs_control.update()
        self._update_favorite_folder_toolbar()
        if self.page is not None and tabs_control.page is not None:
            self.page.update()

    def _select_favorite_folder(self, folder_id: str) -> None:
        self._favorite_selected_folder = folder_id
        self._refresh_favorite_tabs()

    def _remove_favorite(self, item_id: str) -> None:
        if self._favorite_manager.remove_item(item_id):
            self._show_snackbar("已移除收藏。")
            self._favorite_preview_cache.pop(item_id, None)
            self._refresh_favorite_tabs()
        else:
            self._show_snackbar("未找到指定的收藏。", error=True)

    def _edit_favorite(self, item_id: str) -> None:
        item = self._favorite_manager.get_item(item_id)
        if not item:
            self._show_snackbar("未找到指定的收藏。", error=True)
            return
        payload = {
            "title": item.title,
            "description": item.description,
            "tags": list(item.tags),
            "source": item.source,
            "preview_url": item.preview_url,
            "local_path": item.local_path,
            "extra": dict(item.extra),
            "folder_id": item.folder_id,
        }
        self._open_favorite_editor(payload, item_id=item.id)

    def _schedule_favorite_classification(self, item_id: str) -> None:
        async def _runner() -> None:
            await self._favorite_manager.maybe_classify_item(item_id)
            self._refresh_favorite_tabs()

        self.page.run_task(_runner)

    def _open_new_folder_dialog(
        self,
        on_created: Callable[[FavoriteFolder], None] | None = None,
    ) -> None:
        name_field = ft.TextField(label="收藏夹名称", autofocus=True)
        description_field = ft.TextField(
            label="描述 (可选)",
            multiline=True,
            max_lines=3,
        )

        def _submit(_: ft.ControlEvent | None = None) -> None:
            folder = self._favorite_manager.create_folder(
                name_field.value or "",
                description=description_field.value or "",
            )
            self._close_dialog()
            self._show_snackbar("收藏夹已创建。")
            self._favorite_selected_folder = folder.id
            self._refresh_favorite_tabs()
            if on_created:
                on_created(folder)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("新建收藏夹"),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    [name_field, description_field],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledTonalButton("创建", icon=ft.Icons.CHECK, on_click=_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _handle_edit_current_folder(self, _: ft.ControlEvent | None = None) -> None:
        folder_id = self._favorite_selected_folder
        if folder_id in (None, "__all__"):
            self._show_snackbar("请先选择一个具体的收藏夹。", error=True)
            return
        self._open_edit_folder_dialog(folder_id)

    def _open_edit_folder_dialog(self, folder_id: str) -> None:
        folder = self._favorite_manager.get_folder(folder_id)
        if not folder:
            self._show_snackbar("未找到要编辑的收藏夹。", error=True)
            return

        name_field = ft.TextField(
            label="收藏夹名称",
            value=folder.name,
            autofocus=True,
        )
        description_field = ft.TextField(
            label="描述 (可选)",
            value=folder.description,
            multiline=True,
            max_lines=3,
        )

        def _submit(_: ft.ControlEvent | None = None) -> None:
            updated = self._favorite_manager.rename_folder(
                folder_id,
                name=name_field.value,
                description=description_field.value,
            )
            self._close_dialog()
            if updated:
                self._favorite_selected_folder = folder_id
                self._show_snackbar("收藏夹已更新。")
                self._refresh_favorite_tabs()
            else:
                self._show_snackbar("收藏夹更新失败。", error=True)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑收藏夹"),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    [name_field, description_field],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledButton("保存", icon=ft.Icons.SAVE, on_click=_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _handle_delete_current_folder(self, _: ft.ControlEvent | None = None) -> None:
        folder_id = self._favorite_selected_folder
        if folder_id in (None, "__all__"):
            self._show_snackbar("请选择要删除的收藏夹。", error=True)
            return
        if folder_id == "default":
            self._show_snackbar("默认收藏夹无法删除。", error=True)
            return
        self._confirm_delete_folder(folder_id)

    def _confirm_delete_folder(self, folder_id: str) -> None:
        folder = self._favorite_manager.get_folder(folder_id)
        if not folder:
            self._show_snackbar("未找到要删除的收藏夹。", error=True)
            return

        def _delete(_: ft.ControlEvent | None = None) -> None:
            success = self._favorite_manager.delete_folder(folder_id)
            self._close_dialog()
            if success:
                self._favorite_selected_folder = "default"
                self._show_snackbar("收藏夹已删除，内容已移动到默认收藏夹。")
                self._refresh_favorite_tabs()
            else:
                self._show_snackbar("删除收藏夹失败。", error=True)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("删除收藏夹"),
            content=ft.Text(
                f"确定要删除收藏夹“{folder.name}”吗？该收藏夹中的所有收藏将被移动到默认收藏夹。",
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledTonalButton(
                    "删除",
                    icon=ft.Icons.DELETE_FOREVER,
                    bgcolor=ft.Colors.ERROR_CONTAINER,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    on_click=_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _open_favorite_editor(
        self,
        payload: dict[str, Any] | None,
        item_id: str | None = None,
    ) -> None:
        if not payload:
            self._show_snackbar("当前没有可收藏的内容。", error=True)
            return

        folders = self._favorite_folders()

        def _refresh_dropdown(selected: str | None = None) -> None:
            folder_dropdown.options = [
                ft.DropdownOption(key=folder.id, text=folder.name)
                for folder in self._favorite_folders()
            ]
            valid_values = {option.key for option in folder_dropdown.options}
            if selected and selected in valid_values:
                folder_dropdown.value = selected
            elif folder_dropdown.value not in valid_values and valid_values:
                folder_dropdown.value = next(iter(valid_values))
            folder_dropdown.update()

        initial_folder = payload.get("folder_id")
        if not initial_folder or initial_folder == "__all__":
            initial_folder = (
                self._favorite_selected_folder
                if self._favorite_selected_folder != "__all__"
                else "default"
            )

        folder_dropdown = ft.Dropdown(
            label="收藏夹",
            value=initial_folder,
            options=[
                ft.DropdownOption(key=folder.id, text=folder.name) for folder in folders
            ]
            or [ft.DropdownOption(key="default", text="默认收藏夹")],
            expand=True,
        )

        def _create_folder(_: ft.ControlEvent | None = None) -> None:
            self._open_new_folder_dialog(
                on_created=lambda folder: _refresh_dropdown(folder.id),
            )

        title_field = ft.TextField(
            label="标题",
            value=payload.get("title", ""),
            autofocus=True,
        )
        description_field = ft.TextField(
            label="描述",
            value=payload.get("description", ""),
            multiline=True,
            max_lines=4,
        )
        tags_field = ft.TextField(
            label="标签",
            value=", ".join(payload.get("tags", [])),
            helper_text="使用逗号、空格或分号分隔多个标签",
        )

        preview_src = payload.get("preview_url") or payload.get("local_path")
        if not preview_src and isinstance(payload.get("source"), FavoriteSource):
            preview_src = payload["source"].url

        preview_control: ft.Control
        if preview_src:
            preview_control = ft.Image(
                src=preview_src,
                width=200,
                height=110,
                fit=ft.ImageFit.COVER,
                border_radius=8,
            )
        else:
            preview_control = ft.Container(
                width=200,
                height=110,
                border_radius=8,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.IMAGE_OUTLINED, color=ft.Colors.OUTLINE),
            )

        def _submit(_: ft.ControlEvent | None = None) -> None:
            selected_folder = folder_dropdown.value or "default"
            tags = self._parse_tag_input(tags_field.value)

            if item_id:
                self._favorite_manager.update_item(
                    item_id,
                    folder_id=selected_folder,
                    title=title_field.value,
                    description=description_field.value,
                    tags=tags,
                )
                result_item = self._favorite_manager.get_item(item_id)
                created = False
                if result_item is None:
                    self._show_snackbar("收藏更新失败。", error=True)
                    return
            else:
                result_item, created = self._favorite_manager.add_or_update_item(
                    folder_id=selected_folder,
                    title=title_field.value or payload.get("title", ""),
                    description=description_field.value or "",
                    tags=tags,
                    source=payload.get("source"),
                    preview_url=payload.get("preview_url"),
                    local_path=payload.get("local_path"),
                    extra=payload.get("extra"),
                    merge_tags=True,
                )

            self._favorite_selected_folder = selected_folder
            self._close_dialog()
            message = "收藏成功！" if created else "收藏已更新。"
            self._show_snackbar(message)
            self._refresh_favorite_tabs()
            self._schedule_favorite_classification(result_item.id)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑收藏" if item_id else "添加到收藏"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                folder_dropdown,
                                ft.IconButton(
                                    icon=ft.Icons.CREATE_NEW_FOLDER,
                                    tooltip="新建收藏夹",
                                    on_click=_create_folder,
                                ),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                        preview_control,
                        title_field,
                        description_field,
                        tags_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledButton("保存", icon=ft.Icons.CHECK, on_click=_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    def _make_current_wallpaper_payload(self) -> dict[str, Any] | None:
        path = self.wallpaper_path
        if not path:
            return None
        try:
            resolved = Path(path).resolve()
            preview_uri = resolved.as_uri()
        except Exception:
            resolved = Path(path)
            preview_uri = path
        source = FavoriteSource(
            type="system_wallpaper",
            identifier=f"file::{resolved}",
            title="当前系统壁纸",
            url=None,
            preview_url=preview_uri,
            local_path=path,
            extra={"origin": "home"},
        )
        return {
            "title": resolved.name,
            "description": "来自当前桌面的壁纸",
            "tags": ["系统壁纸"],
            "source": source,
            "preview_url": preview_uri,
            "local_path": path,
            "extra": {"path": path},
        }

    def _make_bing_favorite_payload(self) -> dict[str, Any] | None:
        if not self.bing_wallpaper_url or not self.bing_wallpaper:
            return None
        identifier = self.bing_wallpaper.get("startdate") or self.bing_wallpaper_url
        title = self.bing_wallpaper.get("title", "Bing 每日壁纸")
        description = self.bing_wallpaper.get("copyright", "")
        source = FavoriteSource(
            type="bing",
            identifier=str(identifier),
            title=title,
            url=self.bing_wallpaper_url,
            preview_url=self.bing_wallpaper_url,
            extra=dict(self.bing_wallpaper),
        )
        return {
            "title": title,
            "description": description,
            "tags": ["Bing", "每日壁纸"],
            "source": source,
            "preview_url": self.bing_wallpaper_url,
            "extra": {"bing": dict(self.bing_wallpaper)},
        }

    def _make_spotlight_favorite_payload(self) -> dict[str, Any] | None:
        if not self.spotlight_wallpaper or not self.spotlight_wallpaper_url:
            return None
        index = min(self.spotlight_current_index, len(self.spotlight_wallpaper) - 1)
        data = self.spotlight_wallpaper[index]
        url = data.get("url")
        identifier = url or data.get("ctaUri") or f"spotlight-{index}"
        title = data.get("title", "Windows 聚焦壁纸")
        description = data.get("description", "")
        source = FavoriteSource(
            type="windows_spotlight",
            identifier=str(identifier),
            title=title,
            url=url,
            preview_url=url,
            extra=dict(data),
        )
        return {
            "title": title,
            "description": description,
            "tags": ["Windows Spotlight"],
            "source": source,
            "preview_url": url,
            "extra": {"spotlight": dict(data)},
        }

    def _build_bing_daily_content(self):
        copy_menu = None

        def _set_wallpaper(url):
            nonlocal bing_loading_info, bing_pb

            def progress_callback(value, value1):
                nonlocal bing_pb
                bing_pb.value = value / value1
                self.page.update()

            bing_loading_info.visible = True
            bing_pb.visible = True

            set_button.disabled = True
            favorite_button.disabled = True
            download_to_config_button.disabled = True
            save_as_button.disabled = True

            _disable_copy_button()

            self.resource_tabs.disabled = True

            self.page.update()

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("获取Bing壁纸数据时出现问题"),
                content=ft.Text(
                    "你可以重试或手动下载壁纸后设置壁纸，若无法解决请联系开发者。",
                ),
                actions=[
                    ft.TextButton(
                        "关闭", on_click=lambda e: setattr(dlg, "open", False),
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                open=False,
            )

            wallpaper_path = ltwapi.download_file(
                url,
                CACHE_DIR / "wallpapers",
                "Ltw-Wallpaper",
                progress_callback=progress_callback,
            )
            if wallpaper_path:
                self._emit_download_completed("bing", "set_wallpaper", wallpaper_path)
                ltwapi.set_wallpaper(wallpaper_path)
                self._emit_bing_action(
                    "set_wallpaper",
                    True,
                    {"file_path": str(wallpaper_path)},
                )

            else:
                dlg.open = True
                logger.error("Bing 壁纸下载失败")
                self._emit_bing_action("set_wallpaper", False)

            bing_pb.value = 0
            bing_loading_info.visible = False
            bing_pb.visible = False
            set_button.disabled = False
            favorite_button.disabled = False
            download_to_config_button.disabled = False
            save_as_button.disabled = False
            _enable_copy_button()

            self.resource_tabs.disabled = False

            self.page.update()

        def _sanitize_filename(raw: str, fallback: str) -> str:
            cleaned = "".join(
                ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_"
                for ch in (raw or "").strip()
            ).strip()
            return cleaned or fallback

        def _copy_link():
            if not self.bing_wallpaper_url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("当前没有可用的链接哦~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    ),
                )
                self._emit_bing_action("copy_link", False)
                return
            pyperclip.copy(self.bing_wallpaper_url)
            self.page.open(
                ft.SnackBar(
                    ft.Text("链接已复制，快去分享吧~"),
                ),
            )
            self._emit_bing_action("copy_link", True)

        def _handle_bing_download(action: str):
            """处理Bing壁纸下载功能"""
            nonlocal bing_loading_info, bing_pb
            nonlocal \
                set_button, \
                favorite_button, \
                download_to_config_button, \
                save_as_button, \
                copy_button, \
                copy_menu

            if not self.bing_wallpaper_url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("当前没有可用的壁纸资源~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    ),
                )
                return

            def progress_callback(value, total):
                if total:
                    bing_pb.value = value / total
                    self.page.update()

            bing_loading_info.value = "正在下载壁纸…"
            bing_loading_info.visible = True
            bing_pb.visible = True

            set_button.disabled = True
            favorite_button.disabled = True
            download_to_config_button.disabled = True
            save_as_button.disabled = True
            _disable_copy_button()
            if copy_menu:
                copy_menu.disabled = True
            self.resource_tabs.disabled = True

            self.page.update()

            if action == "save_as":
                # 另存为功能，打开文件选择器
                self._ensure_bing_save_picker()
                filename = _sanitize_filename(title, "Bing-Wallpaper") + ".jpg"
                self._bing_save_picker.save_file(file_name=filename)
            elif action == "download":
                # 使用下载管理器获取配置的位置
                download_folder_path = download_manager.get_download_folder_path(app_config)
                if not download_folder_path:
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("尚未配置下载目录，请在设置中配置。"),
                            bgcolor=ft.Colors.ON_ERROR,
                        ),
                    )
                    _reset_bing_ui()
                    return

                # 确保下载文件夹存在
                try:
                    download_folder_path.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    logger.error(f"创建下载目录失败: {exc}")
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("创建下载目录失败，请检查设置。"),
                            bgcolor=ft.Colors.ON_ERROR,
                        ),
                    )
                    _reset_bing_ui()
                    return

                filename = _sanitize_filename(title, "Bing-Wallpaper") + ".jpg"

                try:
                    final_path = ltwapi.download_file(
                        self.bing_wallpaper_url,
                        download_folder_path,
                        filename,
                        progress_callback=progress_callback,
                    )

                    if final_path:
                        self._emit_download_completed("bing", "download", final_path)
                        self.page.open(
                            ft.SnackBar(
                                ft.Text(f"已下载到 {final_path}"),
                            ),
                        )
                    else:
                        raise Exception("下载失败")

                except Exception as exc:
                    logger.error("Bing 壁纸下载失败: {error}", error=str(exc))
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("下载失败，请稍后再试~"),
                            bgcolor=ft.Colors.ON_ERROR,
                        ),
                    )

            _reset_bing_ui()

        def _reset_bing_ui():
            """重置Bing UI状态"""
            bing_pb.value = 0
            bing_loading_info.visible = False
            bing_pb.visible = False
            set_button.disabled = False
            favorite_button.disabled = False
            download_to_config_button.disabled = False
            save_as_button.disabled = False
            _enable_copy_button()
            self.resource_tabs.disabled = False
            self.page.update()

        def _handle_copy(action: str):
            nonlocal bing_loading_info, bing_pb
            nonlocal \
                set_button, \
                favorite_button, \
                download_to_config_button, \
                save_as_button, \
                copy_button, \
                copy_menu

            if action == "link":
                _copy_link()
                return

            if not self.bing_wallpaper_url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("当前没有可用的壁纸资源~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    ),
                )
                self._emit_bing_action(action, False)
                return

            def progress_callback(value, total):
                if total:
                    bing_pb.value = value / total
                    self.page.update()

            bing_loading_info.value = (
                "正在准备复制…" if action.startswith("copy_") else "正在下载壁纸…"
            )
            bing_loading_info.visible = True
            bing_pb.visible = True

            set_button.disabled = True
            favorite_button.disabled = True
            download_to_config_button.disabled = True
            save_as_button.disabled = True
            _disable_copy_button()
            if copy_menu:
                copy_menu.disabled = True
            self.resource_tabs.disabled = True

            self.page.update()

            filename = _sanitize_filename(title, "Bing-Wallpaper")
            wallpaper_path = ltwapi.download_file(
                self.bing_wallpaper_url,
                CACHE_DIR / "wallpapers",
                filename,
                progress_callback=progress_callback,
            )

            if not wallpaper_path:
                logger.error("Bing 壁纸复制时下载失败")
                self.page.open(
                    ft.SnackBar(
                        ft.Text("下载失败，请稍后再试~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    ),
                )
                self._emit_bing_action(action, False)
            else:
                self._emit_download_completed("bing", action, wallpaper_path)
                if action == "copy_image":
                    if copy_image_to_clipboard(wallpaper_path):
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("图片已复制，可直接粘贴~"),
                            ),
                        )
                        self._emit_bing_action(action, True)
                    else:
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("复制图片失败，请稍后再试~"),
                                bgcolor=ft.Colors.ON_ERROR,
                            ),
                        )
                        self._emit_bing_action(action, False)
                elif action == "copy_file":
                    if copy_files_to_clipboard([wallpaper_path]):
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("文件已复制到剪贴板~"),
                            ),
                        )
                        self._emit_bing_action(action, True)
                    else:
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("复制文件失败，请稍后再试~"),
                                bgcolor=ft.Colors.ON_ERROR,
                            ),
                        )
                        self._emit_bing_action(action, False)

            bing_pb.value = 0
            bing_loading_info.visible = False
            bing_pb.visible = False
            set_button.disabled = False
            favorite_button.disabled = False
            download_to_config_button.disabled = False
            save_as_button.disabled = False
            _enable_copy_button()
            self.resource_tabs.disabled = False

            self.page.update()

        def _disable_copy_button():
            nonlocal copy_menu, copy_button
            copy_menu.disabled = True
            copy_button.bgcolor = ft.Colors.OUTLINE_VARIANT
            copy_button.content.controls[0].color = ft.Colors.OUTLINE
            copy_button.content.controls[1].color = ft.Colors.OUTLINE
            self.page.update()

        def _enable_copy_button():
            nonlocal copy_menu, copy_button
            copy_menu.disabled = False
            copy_button.bgcolor = ft.Colors.SECONDARY_CONTAINER
            copy_button.content.controls[0].color = ft.Colors.ON_SECONDARY_CONTAINER
            copy_button.content.controls[1].color = ft.Colors.ON_SECONDARY_CONTAINER
            self.page.update()

        if self.bing_loading:
            return self._build_bing_loading_indicator()
        if not self.bing_wallpaper_url:
            message = "Bing 壁纸加载失败，请稍后再试～"
            if self.bing_error:
                message = f"Bing 壁纸加载失败：{self.bing_error}"
            return ft.Container(
                ft.Column(
                    [
                        ft.Text(message, selectable=True),
                        ft.TextButton(
                            "重试",
                            icon=ft.Icons.REFRESH,
                            on_click=lambda _: self.page.run_task(
                                self._reload_bing_wallpaper,
                            ),
                        ),
                    ],
                    spacing=12,
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=16,
            )
        title = self.bing_wallpaper.get("title", "Bing 每日壁纸")
        desc = self.bing_wallpaper.get("copyright", "")
        bing_loading_info = ft.Text("正在获取信息……")
        bing_pb = ft.ProgressBar(value=0)
        bing_pb.visible = False
        bing_loading_info.visible = False
        set_button = ft.FilledTonalButton(
            "设为壁纸",
            icon=ft.Icons.WALLPAPER,
            on_click=lambda e: _set_wallpaper(self.bing_wallpaper_url),
        )
        favorite_button = ft.FilledTonalButton(
            "收藏",
            icon=ft.Icons.STAR,
            on_click=lambda _: self._open_favorite_editor(
                self._make_bing_favorite_payload(),
            ),
        )
        # 下载按钮 - 两个独立按钮
        download_to_config_button = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.DOWNLOAD, ft.Colors.ON_SECONDARY_CONTAINER, size=17),
                    ft.Text("下载", color=ft.Colors.ON_SECONDARY_CONTAINER),
                ],
                spacing=7,
            ),
            padding=7.5,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=50,
            on_click=lambda _: _handle_bing_download("download"),
        )

        save_as_button = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SAVE_AS, ft.Colors.ON_SECONDARY_CONTAINER, size=17),
                    ft.Text("另存为", color=ft.Colors.ON_SECONDARY_CONTAINER),
                ],
                spacing=7,
            ),
            padding=7.5,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=50,
            on_click=lambda _: _handle_bing_download("save_as"),
        )
        copy_button_content = ft.Row(
            controls=[
                ft.Icon(ft.Icons.COPY, ft.Colors.ON_SECONDARY_CONTAINER, size=17),
                ft.Text("复制"),
            ],
            spacing=7,
        )
        copy_button = ft.Container(
            content=copy_button_content,
            padding=7.5,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=50,
        )
        copy_menu = ft.PopupMenuButton(
            content=copy_button,
            tooltip="复制壁纸链接、图片或图片文件",
            items=[
                ft.PopupMenuItem(
                    icon=ft.Icons.LINK,
                    text="复制链接",
                    on_click=lambda _: _handle_copy("link"),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.IMAGE,
                    text="复制图片",
                    on_click=lambda _: _handle_copy("copy_image"),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.FOLDER_COPY,
                    text="复制图片文件",
                    on_click=lambda _: _handle_copy("copy_file"),
                ),
            ],
        )

        extra_actions = self._build_plugin_actions(self.bing_action_factories)
        actions_row = ft.Row(
            [
                *[
                    set_button,
                    favorite_button,
                    download_to_config_button,
                    save_as_button,
                    copy_menu,
                ],
                *extra_actions,
            ],
        )

        return ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Image(
                                src=self.bing_wallpaper_url,
                                width=160,
                                height=90,
                                fit=ft.ImageFit.COVER,
                                border_radius=8,
                            ),
                            ft.Column(
                                [
                                    ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
                                    ft.Text(desc, size=12, color=ft.Colors.GREY),
                                    ft.Row(
                                        [
                                            ft.TextButton("测验", icon=ft.Icons.LAUNCH),
                                            ft.TextButton("详情", icon=ft.Icons.LAUNCH),
                                        ],
                                    ),
                                ],
                                spacing=6,
                            ),
                        ],
                    ),
                    actions_row,
                    bing_loading_info,
                    bing_pb,
                ],
            ),
            padding=16,
        )

    def _build_spotlight_daily_content(self):
        copy_menu = None
        copy_button = None
        copy_icon = None
        copy_text = None

        def _sanitize_filename(raw: str, fallback: str) -> str:
            cleaned = "".join(
                ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_"
                for ch in (raw or "").strip()
            ).strip()
            return cleaned or fallback

        def _update_details(idx: int):
            nonlocal title, description, copy_rights, info_button
            self.spotlight_current_index = idx
            spotlight = self.spotlight_wallpaper[idx]
            title.value = spotlight.get("title", "无标题")
            description.value = spotlight.get("description", "无描述")
            copy_rights.value = spotlight.get("copyright", "无版权信息")

            info_url = spotlight.get("ctaUri")
            if info_url:
                info_button.text = "了解详情"
                info_button.disabled = False
                info_button.on_click = lambda e, url=info_url: self.page.launch_url(url)
            else:
                info_button.text = "了解详情"
                info_button.disabled = True
                info_button.on_click = None
            self._emit_resource_event(
                "resource.spotlight.updated",
                self._spotlight_event_payload(),
            )

        def _change_photo(e):
            data = json.loads(e.data)
            if not data:
                return
            idx = int(data[0])
            _update_details(idx)
            self.page.update()

        def _copy_link():
            spotlight = (
                self.spotlight_wallpaper[self.spotlight_current_index]
                if self.spotlight_wallpaper
                else {}
            )
            url = spotlight.get("url") if isinstance(spotlight, dict) else None
            if not url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("当前壁纸缺少下载链接，暂时无法复制~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    ),
                )
                self._emit_spotlight_action("copy_link", False)
                return
            pyperclip.copy(url)
            self.page.open(
                ft.SnackBar(
                    ft.Text("壁纸链接已复制，快去分享吧~"),
                ),
            )
            self._emit_spotlight_action("copy_link", True)

        def _handle_download(action: str):
            nonlocal spotlight_loading_info, spotlight_pb
            nonlocal set_button, favorite_button, spotlight_download_to_config_button, spotlight_save_as_button, copy_button
            nonlocal segmented_button, copy_menu

            normalized_action = "set_wallpaper" if action == "set" else action

            spotlight = (
                self.spotlight_wallpaper[self.spotlight_current_index]
                if self.spotlight_wallpaper
                else {}
            )
            url = spotlight.get("url")
            if not url:
                self.page.open(
                    ft.SnackBar(
                        ft.Text("未找到壁纸地址，暂时无法下载~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    ),
                )
                self._emit_spotlight_action(normalized_action, False)
                return

            def progress_callback(value, total):
                if total:
                    spotlight_pb.value = value / total
                    self.page.update()

            spotlight_loading_info.value = (
                "正在准备复制…" if action.startswith("copy_") else "正在下载壁纸…"
            )
            spotlight_loading_info.visible = True
            spotlight_pb.visible = True

            set_button.disabled = True
            favorite_button.disabled = True
            spotlight_download_to_config_button.disabled = True
            spotlight_save_as_button.disabled = True
            _disable_copy_button()
            segmented_button.disabled = True
            self.resource_tabs.disabled = True

            self.page.update()

            filename = _sanitize_filename(
                spotlight.get("title"),
                f"Windows-Spotlight-{self.spotlight_current_index + 1}",
            )

            wallpaper_path = ltwapi.download_file(
                url,
                CACHE_DIR / "wallpapers",
                filename,
                progress_callback=progress_callback,
            )

            success = wallpaper_path is not None
            handled = False
            if success:
                self._emit_download_completed(
                    "spotlight", normalized_action, wallpaper_path,
                )
            if success and action == "set":
                try:
                    ltwapi.set_wallpaper(wallpaper_path)
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("壁纸设置成功啦~ (๑•̀ㅂ•́)و✧"),
                        ),
                    )
                except Exception as exc:
                    logger.error(f"设置壁纸失败: {exc}")
                    success = False
                handled = True
                self._emit_spotlight_action(
                    normalized_action,
                    success,
                    {"file_path": str(wallpaper_path) if wallpaper_path else None},
                )
            elif success and action == "download":
                # 使用下载管理器获取配置的位置
                download_folder_path = download_manager.get_download_folder_path(app_config)
                if download_folder_path:
                    try:
                        # 确保下载文件夹存在
                        download_folder_path.mkdir(parents=True, exist_ok=True)

                        # 复制文件到配置的下载位置
                        import shutil
                        final_path = download_folder_path / filename
                        shutil.copy2(wallpaper_path, final_path)

                        # 删除缓存文件
                        wallpaper_path.unlink()

                        self.page.open(
                            ft.SnackBar(
                                ft.Text(f"壁纸下载完成，已保存到 {final_path}"),
                            ),
                        )

                        self._emit_download_completed("spotlight", "download", final_path)
                    except Exception as exc:
                        logger.error(f"复制文件到下载目录失败: {exc}")
                        self.page.open(
                            ft.SnackBar(
                                ft.Text("下载完成，但保存到配置目录失败"),
                                bgcolor=ft.Colors.ON_ERROR,
                            ),
                        )
                        # 如果复制失败，仍然使用缓存文件路径
                        final_path = wallpaper_path
                else:
                    # 如果没有配置下载位置，使用缓存文件
                    final_path = wallpaper_path
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("壁纸下载完成，但未配置下载位置"),
                        ),
                    )

                handled = True
                self._emit_spotlight_action(
                    normalized_action,
                    success,
                    {"file_path": str(final_path) if final_path else None},
                )
            elif success and action == "save_as":
                # 另存为功能，打开文件选择器
                self._ensure_spotlight_save_picker()
                filename = _sanitize_filename(
                    spotlight.get("title"),
                    f"Windows-Spotlight-{self.spotlight_current_index + 1}",
                ) + ".jpg"
                self._spotlight_save_picker.save_file(file_name=filename)
                handled = True
            elif success and action == "copy_image":
                handled = True
                if copy_image_to_clipboard(wallpaper_path):
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("图片已复制，可直接粘贴~"),
                        ),
                    )
                    self._emit_spotlight_action(normalized_action, True)
                else:
                    success = False
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("复制图片失败，请稍后再试~"),
                            bgcolor=ft.Colors.ON_ERROR,
                        ),
                    )
                    self._emit_spotlight_action(normalized_action, False)
            elif success and action == "copy_file":
                handled = True
                if copy_files_to_clipboard([wallpaper_path]):
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("文件已复制到剪贴板~"),
                        ),
                    )
                    self._emit_spotlight_action(normalized_action, True)
                else:
                    success = False
                    self.page.open(
                        ft.SnackBar(
                            ft.Text("复制文件失败，请稍后再试~"),
                            bgcolor=ft.Colors.ON_ERROR,
                        ),
                    )
                    self._emit_spotlight_action(normalized_action, False)

            if not success and not handled:
                logger.error("Windows 聚焦壁纸下载失败")
                self.page.open(
                    ft.SnackBar(
                        ft.Text("下载失败，请稍后再试~"),
                        bgcolor=ft.Colors.ON_ERROR,
                    ),
                )
                self._emit_spotlight_action(normalized_action, False)

            spotlight_loading_info.visible = False
            spotlight_pb.visible = False
            spotlight_pb.value = 0

            set_button.disabled = False
            favorite_button.disabled = False
            spotlight_download_to_config_button.disabled = False
            spotlight_save_as_button.disabled = False
            _enable_copy_button()
            segmented_button.disabled = False
            self.resource_tabs.disabled = False

            self.page.update()

        def _handle_copy_action(option: str):
            if option == "link":
                _copy_link()
            else:
                _handle_download(option)

        def _disable_copy_button():
            nonlocal copy_menu, copy_button, copy_icon, copy_text
            if copy_menu:
                copy_menu.disabled = True
            if copy_button:
                copy_button.bgcolor = ft.Colors.OUTLINE_VARIANT
                copy_button.disabled = True
            if copy_icon:
                copy_icon.color = ft.Colors.OUTLINE
            if copy_text:
                copy_text.color = ft.Colors.OUTLINE
            self.page.update()

        def _enable_copy_button():
            nonlocal copy_menu, copy_button, copy_icon, copy_text
            if copy_menu:
                copy_menu.disabled = False
            if copy_button:
                copy_button.bgcolor = ft.Colors.SECONDARY_CONTAINER
                copy_button.disabled = False
            if copy_icon:
                copy_icon.color = ft.Colors.ON_SECONDARY_CONTAINER
            if copy_text:
                copy_text.color = ft.Colors.ON_SECONDARY_CONTAINER
            self.page.update()

        if self.spotlight_loading:
            return self._build_spotlight_loading_indicator()
        if not self.spotlight_wallpaper_url:
            message = "Windows 聚焦壁纸加载失败，请稍后再试～"
            if self.spotlight_error:
                message = f"Windows 聚焦壁纸加载失败：{self.spotlight_error}"
            return ft.Container(
                ft.Column(
                    [
                        ft.Text(message, selectable=True),
                        ft.TextButton(
                            "重试",
                            icon=ft.Icons.REFRESH,
                            on_click=lambda _: self.page.run_task(
                                self._reload_spotlight_wallpaper,
                            ),
                        ),
                    ],
                    spacing=12,
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=16,
            )
        title = ft.Text()
        description = ft.Text(size=12)
        copy_rights = ft.Text(size=12, color=ft.Colors.GREY)
        info_button = ft.FilledTonalButton(
            "了解详情", icon=ft.Icons.INFO, disabled=True,
        )
        set_button = ft.FilledTonalButton(
            "设为壁纸",
            icon=ft.Icons.WALLPAPER,
            on_click=lambda e: _handle_download("set"),
        )
        favorite_button = ft.FilledTonalButton(
            "收藏",
            icon=ft.Icons.STAR,
            on_click=lambda _: self._open_favorite_editor(
                self._make_spotlight_favorite_payload(),
            ),
        )
        # Windows聚焦下载按钮 - 两个独立按钮
        spotlight_download_to_config_button = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.DOWNLOAD, ft.Colors.ON_SECONDARY_CONTAINER, size=17),
                    ft.Text("下载", color=ft.Colors.ON_SECONDARY_CONTAINER),
                ],
                spacing=7,
            ),
            padding=7.5,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=50,
            on_click=lambda e: _handle_download("download"),
        )

        spotlight_save_as_button = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SAVE_AS, ft.Colors.ON_SECONDARY_CONTAINER, size=17),
                    ft.Text("另存为", color=ft.Colors.ON_SECONDARY_CONTAINER),
                ],
                spacing=7,
            ),
            padding=7.5,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=50,
            on_click=lambda e: _handle_download("save_as"),
        )
        copy_icon = ft.Icon(
            ft.Icons.COPY, color=ft.Colors.ON_SECONDARY_CONTAINER, size=17,
        )
        copy_text = ft.Text("复制", color=ft.Colors.ON_SECONDARY_CONTAINER)
        copy_button = ft.Container(
            content=ft.Row(
                controls=[copy_icon, copy_text],
                spacing=7,
            ),
            padding=7.5,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=50,
        )
        copy_menu = ft.PopupMenuButton(
            content=copy_button,
            tooltip="复制壁纸链接、图片或图片文件",
            items=[
                ft.PopupMenuItem(
                    icon=ft.Icons.LINK,
                    text="复制链接",
                    on_click=lambda _: _handle_copy_action("link"),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.IMAGE,
                    text="复制图片",
                    on_click=lambda _: _handle_copy_action("copy_image"),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.FOLDER_COPY,
                    text="复制图片文件",
                    on_click=lambda _: _handle_copy_action("copy_file"),
                ),
            ],
        )

        spotlight_loading_info = ft.Text("正在获取信息……")
        spotlight_loading_info.visible = False
        spotlight_pb = ft.ProgressBar(value=0)
        spotlight_pb.visible = False

        segmented_button = ft.SegmentedButton(
            segments=[
                ft.Segment(
                    value=str(index),
                    label=ft.Text(f"图{index + 1}"),
                    icon=ft.Icon(ft.Icons.PHOTO),
                )
                for index in range(len(self.spotlight_wallpaper_url))
            ],
            allow_multiple_selection=False,
            selected={"0"},
            on_change=_change_photo,
        )

        _update_details(0)
        extra_spotlight_actions = self._build_plugin_actions(
            self.spotlight_action_factories,
        )
        spotlight_actions_row = ft.Row(
            [
                *[
                    set_button,
                    favorite_button,
                    spotlight_download_to_config_button,
                    spotlight_save_as_button,
                    copy_menu,
                ],
                *extra_spotlight_actions,
            ],
        )

        return ft.Container(
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Image(
                                src=url,
                                width=160,
                                height=90,
                                fit=ft.ImageFit.COVER,
                                border_radius=8,
                            )
                            for url in self.spotlight_wallpaper_url
                        ],
                    ),
                    segmented_button,
                    title,
                    description,
                    copy_rights,
                    ft.Row([info_button]),
                    spotlight_actions_row,
                    spotlight_loading_info,
                    spotlight_pb,
                ],
            ),
            padding=16,
        )

    def _build_sniff(self) -> ft.Control:
        self._ensure_sniff_save_picker()

        self._sniff_url_field = ft.TextField(
            label="页面链接",
            hint_text="输入包含图片的网页链接",
            autofocus=False,
            expand=True,
            on_submit=lambda _: self.page.run_task(self._sniff_start),
        )
        self._sniff_fetch_button = ft.FilledButton(
            "开始嗅探",
            icon=ft.Icons.SEARCH,
            on_click=lambda _: self.page.run_task(self._sniff_start),
        )
        clear_button = ft.IconButton(
            ft.Icons.CLEAR_ALL,
            tooltip="清空结果",
            on_click=lambda _: self._sniff_reset(clear_url=False),
        )

        header_row = ft.Row(
            [
                self._sniff_url_field,
                self._sniff_fetch_button,
                clear_button,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        self._sniff_progress = ft.ProgressRing(width=18, height=18)
        self._sniff_progress.visible = False
        self._sniff_status_text = ft.Text(
            "请输入链接并点击开始嗅探。",
            size=12,
            color=ft.Colors.GREY,
        )

        status_row = ft.Row(
            [
                self._sniff_progress,
                self._sniff_status_text,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._sniff_task_text = ft.Text("", size=12, color=ft.Colors.PRIMARY)
        self._sniff_task_bar = ft.ProgressBar(value=0, expand=True)
        self._sniff_task_container = ft.Column(
            [self._sniff_task_text, self._sniff_task_bar],
            spacing=6,
        )
        self._sniff_task_container.visible = False

        set_wallpaper_button = ft.FilledTonalButton(
            "设为壁纸",
            icon=ft.Icons.WALLPAPER,
            disabled=True,
            on_click=lambda _: self.page.run_task(self._sniff_set_wallpaper),
        )
        copy_image_button = ft.FilledTonalButton(
            "复制图片",
            icon=ft.Icons.CONTENT_COPY,
            disabled=True,
            on_click=lambda _: self.page.run_task(self._sniff_copy_image),
        )
        favorite_button = ft.FilledTonalButton(
            "收藏",
            icon=ft.Icons.BOOKMARK_ADD,
            disabled=True,
            on_click=lambda _: self._sniff_collect_selected(),
        )
        copy_file_button = ft.FilledTonalButton(
            "复制文件",
            icon=ft.Icons.FOLDER_COPY,
            disabled=True,
            on_click=lambda _: self.page.run_task(self._sniff_copy_files),
        )
        copy_link_button = ft.FilledTonalButton(
            "复制链接",
            icon=ft.Icons.LINK,
            disabled=True,
            on_click=lambda _: self._sniff_copy_links(),
        )
        download_button = ft.FilledTonalButton(
            "下载",
            icon=ft.Icons.DOWNLOAD,
            disabled=True,
            on_click=lambda _: self.page.run_task(self._sniff_download),
        )
        save_as_button = ft.FilledTonalButton(
            "另存为",
            icon=ft.Icons.SAVE_ALT,
            disabled=True,
            on_click=lambda _: self._sniff_request_save_as(),
        )

        self._sniff_action_buttons = {
            "wallpaper": set_wallpaper_button,
            "copy_image": copy_image_button,
            "favorite": favorite_button,
            "copy_file": copy_file_button,
            "copy_link": copy_link_button,
            "download": download_button,
            "save_as": save_as_button,
        }

        self._sniff_selection_text = ft.Text(
            "未选择图片",
            size=12,
            color=ft.Colors.GREY,
        )

        actions_row = ft.Row(
            [
                set_wallpaper_button,
                favorite_button,
                copy_image_button,
                copy_file_button,
                copy_link_button,
                download_button,
                save_as_button,
            ],
            spacing=8,
            wrap=True,
            run_spacing=8,
        )

        self._sniff_grid = ft.GridView(
            expand=True,
            max_extent=220,
            child_aspect_ratio=1,
            spacing=12,
            run_spacing=12,
        )

        self._sniff_empty_placeholder = ft.Container(
            expand=True,
            alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.IMAGE_SEARCH, size=72, color=ft.Colors.OUTLINE),
                    ft.Text(
                        "暂无图片，请输入链接后开始嗅探。",
                        size=13,
                        color=ft.Colors.GREY,
                    ),
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        )

        content_stack = ft.Stack(
            controls=[self._sniff_empty_placeholder, self._sniff_grid],
            expand=True,
        )

        body = ft.Column(
            [
                ft.Text("嗅探", size=30),
                ft.Text(
                    "输入网页链接获取其中的图片，支持单选与多选操作。",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                header_row,
                status_row,
                self._sniff_task_container,
                ft.Row(
                    [self._sniff_selection_text],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                actions_row,
                ft.Divider(),
                content_stack,
            ],
            spacing=12,
            expand=True,
        )

        self._sniff_update_actions()
        self._sniff_update_placeholder_visibility()

        return ft.Container(body, expand=True, padding=16)

    # -----------------------------
    # 嗅探功能实现
    # -----------------------------
    def _ensure_sniff_save_picker(self) -> None:
        if self._sniff_save_picker is None:
            self._sniff_save_picker = ft.FilePicker(
                on_result=self._handle_sniff_directory_result,
            )
        if self._sniff_save_picker not in self.page.overlay:
            self.page.overlay.append(self._sniff_save_picker)
            self.page.update()

    def _sniff_update_placeholder_visibility(self) -> None:
        has_images = bool(self._sniff_images)
        if self._sniff_empty_placeholder is not None:
            self._sniff_empty_placeholder.visible = not has_images
            if self._sniff_empty_placeholder.page is not None:
                self._sniff_empty_placeholder.update()
        if self._sniff_grid is not None:
            self._sniff_grid.visible = has_images
            if self._sniff_grid.page is not None:
                self._sniff_grid.update()

    def _sniff_update_actions(self) -> None:
        count = len(self._sniff_selected_ids)
        for key, control in self._sniff_action_buttons.items():
            if self._sniff_actions_busy:
                control.disabled = True
            elif key in {"wallpaper", "copy_image"}:
                control.disabled = count != 1
            else:
                control.disabled = count == 0
            if control.page is not None:
                control.update()
        if self._sniff_selection_text is not None:
            self._sniff_selection_text.value = (
                "未选择图片" if count == 0 else f"已选择 {count} 张图片"
            )
            if self._sniff_selection_text.page is not None:
                self._sniff_selection_text.update()

    def _sniff_update_task_controls(self) -> None:
        for ctrl in (
            self._sniff_task_text,
            self._sniff_task_bar,
            self._sniff_task_container,
        ):
            if ctrl is not None and ctrl.page is not None:
                ctrl.update()

    def _sniff_set_actions_enabled(self, enabled: bool) -> None:
        self._sniff_actions_busy = not enabled
        if self._sniff_fetch_button is not None:
            self._sniff_fetch_button.disabled = not enabled
            if self._sniff_fetch_button.page is not None:
                self._sniff_fetch_button.update()
        self._sniff_update_actions()

    def _sniff_task_start(self, message: str) -> None:
        self._sniff_set_actions_enabled(False)
        if self._sniff_task_text is not None:
            self._sniff_task_text.value = message
        if self._sniff_task_bar is not None:
            self._sniff_task_bar.value = None
        if self._sniff_task_container is not None:
            self._sniff_task_container.visible = True
        self._sniff_update_task_controls()

    def _sniff_task_finish(self, message: str | None = None) -> None:
        if self._sniff_task_text is not None and message:
            self._sniff_task_text.value = message
        if self._sniff_task_bar is not None:
            self._sniff_task_bar.value = 0
        if self._sniff_task_container is not None:
            self._sniff_task_container.visible = False
        self._sniff_set_actions_enabled(True)
        self._sniff_update_task_controls()

    def _sniff_reset(self, *, clear_url: bool = True) -> None:
        self._sniff_images.clear()
        self._sniff_image_index.clear()
        self._sniff_selected_ids.clear()
        if clear_url and self._sniff_url_field is not None:
            self._sniff_url_field.value = ""
            if self._sniff_url_field.page is not None:
                self._sniff_url_field.update()
        if self._sniff_status_text is not None:
            self._sniff_status_text.value = "请输入链接并点击开始嗅探。"
            if self._sniff_status_text.page is not None:
                self._sniff_status_text.update()
        if self._sniff_grid is not None:
            self._sniff_grid.controls.clear()
            if self._sniff_grid.page is not None:
                self._sniff_grid.update()
        if self._sniff_task_container is not None:
            self._sniff_task_container.visible = False
        if self._sniff_task_bar is not None:
            self._sniff_task_bar.value = 0
        self._sniff_update_task_controls()
        self._sniff_update_actions()
        self._sniff_update_placeholder_visibility()

    def _sniff_set_loading(self, loading: bool, message: str | None = None) -> None:
        if self._sniff_progress is not None:
            self._sniff_progress.visible = loading
            if self._sniff_progress.page is not None:
                self._sniff_progress.update()
        if self._sniff_fetch_button is not None:
            self._sniff_fetch_button.disabled = loading
            if self._sniff_fetch_button.page is not None:
                self._sniff_fetch_button.update()
        if message and self._sniff_status_text is not None:
            self._sniff_status_text.value = message
            if self._sniff_status_text.page is not None:
                self._sniff_status_text.update()

    async def _sniff_start(self) -> None:
        url = self._sniff_url_field.value.strip() if self._sniff_url_field else ""
        if not url:
            self._show_snackbar("请输入有效的链接。", error=True)
            return
        self._sniff_set_loading(True, "正在嗅探图片…")
        try:
            images = await self._sniff_service.sniff(url)
        except SniffServiceError as exc:
            logger.warning("嗅探失败: {}", exc)
            if self._sniff_status_text is not None:
                self._sniff_status_text.value = str(exc)
                if self._sniff_status_text.page is not None:
                    self._sniff_status_text.update()
            self._show_snackbar(str(exc), error=True)
            return
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("嗅探意外失败: {}", exc)
            if self._sniff_status_text is not None:
                self._sniff_status_text.value = "嗅探失败，请稍后重试。"
                if self._sniff_status_text.page is not None:
                    self._sniff_status_text.update()
            self._show_snackbar("嗅探失败，请稍后重试。", error=True)
            return
        finally:
            self._sniff_set_loading(False)

        self._sniff_images = list(images)
        self._sniff_image_index = {image.id: image for image in images}
        self._sniff_selected_ids.clear()
        self._sniff_source_url = url

        if self._sniff_status_text is not None:
            if images:
                self._sniff_status_text.value = f"共发现 {len(images)} 张图片"
            else:
                self._sniff_status_text.value = "未找到可用图片，尝试其他链接。"
            if self._sniff_status_text.page is not None:
                self._sniff_status_text.update()

        self._sniff_render_grid()
        self._sniff_update_actions()
        self._sniff_update_placeholder_visibility()
        if not images:
            self._show_snackbar("未发现图片，请检查链接。")

    def _sniff_render_grid(self) -> None:
        if self._sniff_grid is None:
            return
        self._sniff_grid.controls.clear()
        for image in self._sniff_images:
            self._sniff_grid.controls.append(self._sniff_build_tile(image))
        if self._sniff_grid.page is not None:
            self._sniff_grid.update()

    def _sniff_build_tile(self, image: SniffedImage) -> ft.Control:
        selected = image.id in self._sniff_selected_ids
        border_color = ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT
        border_width = 3 if selected else 1

        image_control = ft.Image(
            src=image.url,
            fit=ft.ImageFit.COVER,
            expand=True,
        )

        check_badge = ft.Container(
            width=28,
            height=28,
            border_radius=20,
            bgcolor=ft.Colors.PRIMARY,
            alignment=ft.alignment.center,
            content=ft.Icon(ft.Icons.CHECK, size=18, color=ft.Colors.WHITE),
            visible=selected,
        )

        stack = ft.Stack(
            controls=[
                image_control,
                ft.Container(
                    alignment=ft.alignment.top_right, padding=8, content=check_badge,
                ),
            ],
            expand=True,
        )

        return ft.Container(
            content=stack,
            border=ft.border.all(border_width, border_color),
            border_radius=12,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            tooltip=f"{image.filename}\n{image.url}",
            on_click=lambda _: self._sniff_toggle_selection(image.id),
        )

    def _sniff_toggle_selection(self, image_id: str) -> None:
        if image_id in self._sniff_selected_ids:
            self._sniff_selected_ids.remove(image_id)
        else:
            self._sniff_selected_ids.add(image_id)
        self._sniff_render_grid()
        self._sniff_update_actions()

    def _sniff_get_selected_images(self) -> list[SniffedImage]:
        return [
            self._sniff_image_index[image_id]
            for image_id in self._sniff_selected_ids
            if image_id in self._sniff_image_index
        ]

    async def _sniff_set_wallpaper(self) -> None:
        images = self._sniff_get_selected_images()
        if len(images) != 1:
            self._show_snackbar("请选择一张图片。", error=True)
            return
        image = images[0]
        self._sniff_task_start("正在设置壁纸…")
        try:
            cached_path = await self._sniff_service.ensure_cached(image)
            await asyncio.to_thread(ltwapi.set_wallpaper, str(cached_path))
        except Exception as exc:
            logger.error("设为壁纸失败: {}", exc)
            self._show_snackbar("设为壁纸失败，请查看日志。", error=True)
        else:
            self._show_snackbar("已设置为壁纸。")
        finally:
            self._sniff_task_finish()

    def _sniff_collect_selected(self) -> None:
        images = self._sniff_get_selected_images()
        if not images:
            self._show_snackbar("请先选择图片。", error=True)
            return
        if len(images) == 1:
            payload = self._sniff_make_favorite_payload(images[0])
            if not payload:
                self._show_snackbar("无法添加收藏。", error=True)
                return
            self._open_favorite_editor(payload)
            return
        self._sniff_open_batch_favorite_dialog(images)

    def _sniff_make_favorite_payload(self, image: SniffedImage) -> dict[str, Any]:
        favorite_source = FavoriteSource(
            type="sniff",
            identifier=image.id,
            title=image.filename,
            url=image.url,
            preview_url=image.url,
            extra={"source_url": self._sniff_source_url},
        )
        default_folder = (
            self._favorite_selected_folder
            if self._favorite_selected_folder not in {"__all__", "__default__"}
            else "default"
        )
        return {
            "folder_id": default_folder,
            "title": image.filename,
            "description": "",
            "tags": ["sniff"],
            "source": favorite_source,
            "preview_url": image.url,
            "extra": {
                "url": image.url,
                "from": "sniff",
                "source_url": self._sniff_source_url,
            },
        }

    def _sniff_open_batch_favorite_dialog(self, images: Sequence[SniffedImage]) -> None:
        folders = self._favorite_folders()
        if not folders:
            self._show_snackbar("暂无可用的收藏夹，请先创建一个。", error=True)
            return

        initial_folder = self._favorite_selected_folder
        if initial_folder in {None, "__all__", "__default__"}:
            initial_folder = folders[0].id if folders else "default"

        folder_dropdown = ft.Dropdown(
            label="收藏夹",
            value=initial_folder,
            expand=True,
        )

        def _refresh_dropdown(selected: str | None = None) -> None:
            folder_dropdown.options = [
                ft.DropdownOption(key=folder.id, text=folder.name)
                for folder in self._favorite_folders()
            ] or [ft.DropdownOption(key="default", text="默认收藏夹")]
            new_value = selected or folder_dropdown.value
            option_keys = {opt.key for opt in folder_dropdown.options}
            folder_dropdown.value = (
                new_value
                if new_value in option_keys
                else next(iter(option_keys), "default")
            )
            if folder_dropdown.page is not None:
                folder_dropdown.update()

        def _create_folder(_: ft.ControlEvent | None = None) -> None:
            self._open_new_folder_dialog(
                on_created=lambda folder: _refresh_dropdown(folder.id),
            )

        _refresh_dropdown(initial_folder)

        status_text = ft.Text(
            f"将添加 {len(images)} 张图片到收藏。", size=12, color=ft.Colors.GREY,
        )

        def _submit(_: ft.ControlEvent | None = None) -> None:
            target_folder = folder_dropdown.value or "default"
            created_count = 0
            try:
                for image in images:
                    payload = self._sniff_make_favorite_payload(image)
                    payload["folder_id"] = target_folder
                    item, created = self._favorite_manager.add_or_update_item(
                        folder_id=payload["folder_id"],
                        title=payload.get("title", image.filename),
                        description=payload.get("description", ""),
                        tags=payload.get("tags", []),
                        source=payload.get("source"),
                        preview_url=payload.get("preview_url"),
                        local_path=payload.get("local_path"),
                        extra=payload.get("extra"),
                        merge_tags=True,
                    )
                    if created:
                        created_count += 1
                    self._schedule_favorite_classification(item.id)
            except Exception as exc:
                logger.error("批量收藏失败: {}", exc)
                self._show_snackbar("收藏失败，请查看日志。", error=True)
                return

            self._favorite_selected_folder = target_folder
            self._close_dialog()
            if created_count and created_count != len(images):
                self._show_snackbar(
                    f"已收藏 {len(images)} 张图片，其中 {created_count} 张为新项目。",
                )
            else:
                self._show_snackbar(f"已收藏 {len(images)} 张图片。")
            self._refresh_favorite_tabs()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("批量收藏"),
            content=ft.Container(
                width=360,
                content=ft.Column(
                    [
                        status_text,
                        ft.Row(
                            [
                                folder_dropdown,
                                ft.IconButton(
                                    icon=ft.Icons.CREATE_NEW_FOLDER,
                                    tooltip="新建收藏夹",
                                    on_click=_create_folder,
                                ),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.FilledButton("收藏", icon=ft.Icons.CHECK, on_click=_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self._open_dialog(dialog)

    async def _sniff_copy_image(self) -> None:
        images = self._sniff_get_selected_images()
        if len(images) != 1:
            self._show_snackbar("请选择一张图片。", error=True)
            return
        try:
            cached_path = await self._sniff_service.ensure_cached(images[0])
            success = await asyncio.to_thread(copy_image_to_clipboard, cached_path)
        except Exception as exc:
            logger.error("复制图片失败: {}", exc)
            self._show_snackbar("复制图片失败。", error=True)
            return
        if success:
            self._show_snackbar("图片已复制到剪贴板。")
        else:
            self._show_snackbar("复制图片失败。", error=True)

    async def _sniff_copy_files(self) -> None:
        images = self._sniff_get_selected_images()
        if not images:
            self._show_snackbar("请先选择图片。", error=True)
            return
        self._sniff_task_start("正在复制文件…")
        try:
            cached_paths = await asyncio.gather(
                *[self._sniff_service.ensure_cached(image) for image in images],
            )
            path_strings = [str(path) for path in cached_paths]
            success = await asyncio.to_thread(copy_files_to_clipboard, path_strings)
        except Exception as exc:
            logger.error("复制文件失败: {}", exc)
            self._show_snackbar("复制文件失败。", error=True)
        else:
            if success:
                self._show_snackbar("文件已复制到剪贴板。")
            else:
                self._show_snackbar("复制文件失败。", error=True)
        finally:
            self._sniff_task_finish()

    def _sniff_copy_links(self) -> None:
        images = self._sniff_get_selected_images()
        if not images:
            self._show_snackbar("请先选择图片。", error=True)
            return
        links = (
            ",".join(image.url for image in images)
            if len(images) > 1
            else images[0].url
        )
        try:
            pyperclip.copy(links)
        except (
            pyperclip.PyperclipException
        ) as exc:  # pragma: no cover - platform specific
            logger.error("复制链接失败: {}", exc)
            self._show_snackbar("复制链接失败。", error=True)
            return
        self._show_snackbar("链接已复制。")

    async def _sniff_download(self) -> None:
        images = self._sniff_get_selected_images()
        if not images:
            self._show_snackbar("请先选择图片。", error=True)
            return
        # 使用下载管理器获取配置的位置
        download_folder_path = download_manager.get_download_folder_path(app_config)
        if not download_folder_path:
            self._show_snackbar("尚未配置下载目录。", error=True)
            return
        base_dir = download_folder_path
        if len(images) > 1:
            folder_name = time.strftime("sniff-%Y%m%d-%H%M%S")
            target_dir = base_dir / folder_name
        else:
            target_dir = base_dir
        self._sniff_task_start("正在下载图片…")
        try:
            paths = await self._sniff_service.download_many(images, target_dir)
        except Exception as exc:
            logger.error("下载失败: {}", exc)
            self._show_snackbar("下载失败，请查看日志。", error=True)
        else:
            if paths:
                if len(paths) == 1:
                    self._show_snackbar(f"已下载到 {paths[0]}")
                else:
                    self._show_snackbar(f"已下载 {len(paths)} 张图片。")
            else:
                self._show_snackbar("下载失败，请重试。", error=True)
        finally:
            self._sniff_task_finish()

    def _sniff_request_save_as(self) -> None:
        images = self._sniff_get_selected_images()
        if not images:
            self._show_snackbar("请先选择图片。", error=True)
            return
        if self._sniff_save_picker is None:
            self._ensure_sniff_save_picker()
        self._sniff_pending_save_ids = {image.id for image in images}
        if self._sniff_save_picker is not None:
            self._sniff_save_picker.get_directory_path()

    def _handle_sniff_directory_result(self, event: ft.FilePickerResultEvent) -> None:
        pending = self._sniff_pending_save_ids
        self._sniff_pending_save_ids = None
        if not pending:
            return
        if not event.path:
            return
        selected = [
            self._sniff_image_index[image_id]
            for image_id in pending
            if image_id in self._sniff_image_index
        ]
        if not selected:
            return
        target_dir = Path(event.path)
        self.page.run_task(self._sniff_save_to_directory, target_dir, selected)

    async def _sniff_save_to_directory(
        self, directory: Path, images: Sequence[SniffedImage],
    ) -> None:
        self._sniff_task_start("正在保存图片…")
        try:
            paths = await self._sniff_service.download_many(images, directory)
        except Exception as exc:
            logger.error("另存为失败: {}", exc)
            self._show_snackbar("另存为失败，请查看日志。", error=True)
        else:
            if paths:
                self._show_snackbar(f"已保存 {len(paths)} 张图片。")
            else:
                self._show_snackbar("未保存任何图片。", error=True)
        finally:
            self._sniff_task_finish()

    def _favorite_loading_placeholder(self) -> ft.Control:
        logger.debug("显示收藏页加载占位符")
        return ft.Container(
            expand=True,
            alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.ProgressRing(width=56, height=56, stroke_width=4),
                    ft.Text("正在准备收藏页…", size=13, color=ft.Colors.GREY),
                ],
                spacing=16,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

    def _build_favorite(self):
        holder = ft.Container(expand=True)
        self._favorite_view_holder = holder
        holder.content = self._favorite_loading_placeholder()
        self._start_favorite_initialization()
        return holder

    def show_favorite_loading(self) -> None:
        if self._favorite_view_holder is None:
            return
        self._favorite_view_holder.content = self._favorite_loading_placeholder()
        if self._favorite_view_holder.page is not None:
            self._favorite_view_holder.update()
        overlay = self._favorite_loading_overlay
        if overlay is not None:
            overlay.visible = False
            if overlay.page is not None:
                overlay.update()
        self._favorite_view_loading = False
        self._start_favorite_initialization()

    def _start_favorite_initialization(self) -> None:
        if self._favorite_view_loading:
            return
        self._favorite_view_loading = True

        async def _runner() -> None:
            try:
                await asyncio.sleep(0)
                await self._initialize_favorite_view()
            finally:
                self._favorite_view_loading = False
                overlay = self._favorite_loading_overlay
                if overlay is not None:
                    overlay.visible = False
                    if overlay.page is not None:
                        overlay.update()

        if self.page is not None:
            self.page.run_task(_runner)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_runner())
        else:
            loop.create_task(_runner())

    async def _initialize_favorite_view(self) -> None:
        if self._favorite_view_cache is None:
            view = self._create_favorite_view()
            self._favorite_view_cache = view
        else:
            view = self._favorite_view_cache
            await asyncio.sleep(0)

        if self._favorite_view_holder is not None:
            self._favorite_view_holder.content = view
            if self._favorite_view_holder.page is not None:
                self._favorite_view_holder.update()
        if self._favorite_loading_overlay is not None:
            self._favorite_loading_overlay.visible = False
            if self._favorite_loading_overlay.page is not None:
                self._favorite_loading_overlay.update()
        if self.page is not None:
            self.page.update()

    def _create_favorite_view(self):
        self._favorite_tabs = ft.Tabs(
            animation_duration=300,
            expand=True,
            on_change=self._on_favorite_tab_change,
        )
        self._favorite_tabs_container = ft.Container(self._favorite_tabs, expand=True)
        overlay_surface = getattr(ft.Colors, "SURFACE_VARIANT", ft.Colors.SURFACE)
        self._favorite_loading_overlay = ft.Container(
            visible=False,
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.06, overlay_surface),
            alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.ProgressRing(width=48, height=48, stroke_width=4),
                    ft.Text("正在刷新收藏内容…", size=12, color=ft.Colors.GREY),
                ],
                spacing=16,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        favorite_body_stack = ft.Stack(
            controls=[
                self._favorite_tabs_container,
                self._favorite_loading_overlay,
            ],
            expand=True,
        )

        self._favorite_edit_folder_button = ft.IconButton(
            icon=ft.Icons.EDIT_NOTE,
            tooltip="编辑当前收藏夹",
            disabled=True,
            on_click=self._handle_edit_current_folder,
        )
        self._favorite_delete_folder_button = ft.IconButton(
            icon=ft.Icons.DELETE_SWEEP,
            tooltip="删除当前收藏夹",
            disabled=True,
            on_click=self._handle_delete_current_folder,
        )
        self._favorite_localize_button = ft.IconButton(
            icon=ft.Icons.DOWNLOAD_FOR_OFFLINE,
            tooltip="本地化当前视图收藏",
            on_click=self._handle_localize_current_folder,
        )
        self._favorite_export_button = ft.IconButton(
            icon=ft.Icons.CLOUD_UPLOAD,
            tooltip="导出收藏",
            on_click=lambda _: self._open_export_dialog(),
        )
        self._favorite_import_button = ft.IconButton(
            icon=ft.Icons.FILE_UPLOAD,
            tooltip="导入收藏",
            on_click=lambda _: self._open_import_dialog(),
        )

        # 添加“本地图片到收藏”入口
        add_local_fav_button = ft.FilledTonalButton(
            "添加本地图片",
            icon=ft.Icons.ADD_PHOTO_ALTERNATE,
            on_click=lambda _: self._open_add_local_favorite_picker(),
        )

        navigation_row = ft.Row(
            [
                ft.TextButton(
                    "查看全部",
                    icon=ft.Icons.ALL_INBOX,
                    on_click=lambda _: self._select_favorite_folder("__all__"),
                ),
            ],
            spacing=8,
        )

        folder_actions = ft.Row(
            controls=[
                ft.FilledTonalButton(
                    "新建收藏夹",
                    icon=ft.Icons.CREATE_NEW_FOLDER,
                    on_click=lambda _: self._open_new_folder_dialog(),
                ),
                self._favorite_edit_folder_button,
                self._favorite_delete_folder_button,
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
            alignment=ft.MainAxisAlignment.START,
        )

        data_actions = ft.Row(
            controls=[
                add_local_fav_button,
                self._favorite_localize_button,
                self._favorite_export_button,
                self._favorite_import_button,
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="刷新收藏列表",
                    on_click=lambda _: self._refresh_favorite_tabs(),
                ),
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
            alignment=ft.MainAxisAlignment.START,
        )

        self._favorite_localization_spinner = ft.ProgressRing(width=18, height=18)
        self._favorite_localization_spinner.visible = False
        self._favorite_localization_status_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY,
        )
        self._favorite_localization_progress_bar = ft.ProgressBar(
            value=0.0,
            expand=True,
            height=6,
        )
        self._favorite_localization_progress_bar.visible = False
        progress_row = ft.Row(
            [
                self._favorite_localization_spinner,
                self._favorite_localization_status_text,
                ft.Container(
                    content=self._favorite_localization_progress_bar,
                    expand=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        progress_row.visible = False
        self._favorite_localization_status_row = progress_row

        toolbar = ft.Column(
            [
                navigation_row,
                folder_actions,
                data_actions,
                progress_row,
            ],
            spacing=8,
            tight=True,
        )

        self._refresh_favorite_tabs()

        return ft.Container(
            ft.Column(
                [
                    ft.Text("收藏", size=30),
                    ft.Text(
                        "管理你的收藏、标签和收藏夹。",
                        size=12,
                        color=ft.Colors.GREY,
                    ),
                    ft.Container(toolbar, padding=ft.Padding(0, 12, 0, 12)),
                    favorite_body_stack,
                ],
                spacing=8,
                expand=True,
            ),
            expand=True,
            padding=16,
        )

    def _build_test(self):
        return ft.Column(
            [
                ft.Text("测试和调试", size=30),
                ft.Text("这里是测试和调试专用区域"),
                ft.Button(
                    "打开初次运行向导", on_click=lambda _: self.page.go("/first-run"),
                ),
                ft.Button(
                    "添加启动项", on_click=lambda _: StartupManager().enable_startup(),
                ),
                ft.Button(
                    "移除启动项", on_click=lambda _: StartupManager().disable_startup(),
                ),
                ft.Button(
                    "显示启动项状态",
                    on_click=lambda _: self._show_snackbar(
                        f"启动项状态: {'已启用' if StartupManager().is_startup_enabled() else '未启用'}",
                    ),
                ),
            ],
            expand=True,
        )

    def _handle_confirm_nsfw(self):
        app_config.set("wallpaper.allow_nsfw", True)

    def _confirm_nsfw(self):
        # Checkboxes and state sync
        adult_cb = ft.Checkbox(label="我已年满 18 周岁")
        legal_cb = ft.Checkbox(label="我确认我所在国家或地区的法律允许浏览包含成人内容")

        confirm_btn = ft.TextButton(
            "确认",
            disabled=True,
            on_click=lambda _: self._handle_confirm_nsfw(),
        )

        def _sync_state(_: ft.ControlEvent | None = None) -> None:
            confirm_btn.disabled = not (bool(adult_cb.value) and bool(legal_cb.value))
            if confirm_btn.page is not None:
                confirm_btn.update()

        adult_cb.on_change = _sync_state
        legal_cb.on_change = _sync_state

        self._confirm_nsfw_dialog = ft.AlertDialog(
            title=ft.Text("确认允许显示可能包含成人内容"),
            content=ft.Column(
                [
                    ft.Text(
                        "为遵守相关法律法规，我们不会向法律禁止地区和未成年人提供此类内容。继续之前，请确认以下事项：",
                    ),
                    adult_cb,
                    legal_cb,
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                confirm_btn,
            ],
        )
        self._open_dialog(self._confirm_nsfw_dialog)

    def _refresh_theme_profiles(
        self, *, initial: bool = False, show_feedback: bool = False,
    ) -> None:
        if self._theme_locked:
            if show_feedback:
                self._show_snackbar(
                    self._theme_lock_reason or "当前已锁定主题配置。",
                    error=True,
                )
            self._render_theme_cards()
            return
        if self._theme_list_handler is None:
            if not initial and show_feedback:
                self._show_snackbar("主题接口不可用。", error=True)
            self._theme_profiles = []
            self._render_theme_cards()
            return

        try:
            result = self._theme_list_handler()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"刷新主题列表失败: {exc}")
            if show_feedback:
                self._show_snackbar("刷新主题列表失败。", error=True)
            return

        profiles: list[dict[str, Any]] | None = None
        message: str | None = None
        if isinstance(result, PluginOperationResult):
            message = result.message
            if isinstance(result.data, list):
                profiles = result.data
        elif isinstance(result, list):
            profiles = result

        if profiles is not None:
            self._theme_profiles = list(profiles)
            self._render_theme_cards()
            if show_feedback:
                note = message or "主题列表已更新。"
                self._show_snackbar(note)
        else:
            if show_feedback or not initial:
                self._show_snackbar(message or "无法获取主题列表。", error=True)
            self._theme_profiles = []
            self._render_theme_cards()

    def _find_theme_profile(self, identifier: str | None) -> dict[str, Any] | None:
        if not identifier:
            return None
        for profile in self._theme_profiles:
            if str(profile.get("id")) == identifier:
                return profile
        return None

    def _theme_profile_display_name(self, identifier: str | None) -> str:
        if not identifier or identifier.strip().lower() in {"default", "system"}:
            return "默认主题"
        profile = self._find_theme_profile(identifier)
        if profile:
            name = profile.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return identifier

    @staticmethod
    def _theme_preview_text(
        text: str | None, limit: int = 80,
    ) -> tuple[str, str | None]:
        if not isinstance(text, str) or not text.strip():
            return "暂无简介", None
        clean = text.strip()
        if len(clean) <= limit:
            return clean, clean
        head = clean[: max(0, limit - 1)]
        return head + "…", clean

    def _render_theme_cards(self) -> None:
        wrap = self._theme_cards_wrap
        if wrap is None:
            return

        cards: list[ft.Control] = []
        for profile in self._theme_profiles:
            card = self._build_theme_card(profile)
            if card is not None:
                cards.append(card)

        if not cards:
            placeholder = ft.Container(
                content=ft.Column(
                    [
                        ft.Text("暂无可用主题。", size=12),
                        ft.Text(
                            "导入主题文件或检查主题目录。",
                            size=11,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    spacing=4,
                    tight=True,
                ),
                bgcolor=self._bgcolor_surface_low,
                width=260,
                height=220,
                padding=ft.padding.all(20),
                border_radius=ft.border_radius.all(12),
            )
            cards.append(placeholder)

        wrap.controls = cards
        if wrap.page is not None and self.page is not None:
            self.page.update()

    def _build_theme_card(self, profile: dict[str, Any]) -> ft.Control | None:
        identifier = str(profile.get("id") or "").strip()
        if not identifier:
            return None

        name = str(profile.get("name") or identifier)
        is_active = bool(profile.get("is_active"))
        author = profile.get("author")
        description = profile.get("summary") or profile.get("description")
        details = (
            profile.get("details") if isinstance(profile.get("details"), str) else None
        )
        preview_text, tooltip_text = self._theme_preview_text(description)
        if tooltip_text is None and details:
            tooltip_text = details.strip()

        logo_src = profile.get("logo")
        if isinstance(logo_src, str) and logo_src.strip():
            logo_control: ft.Control = ft.Container(
                content=ft.Image(
                    src=logo_src.strip(),
                    width=42,
                    height=42,
                    fit=ft.ImageFit.COVER,
                ),
                width=42,
                height=42,
                border_radius=ft.border_radius.all(8),
            )
        else:
            logo_control = ft.Container(
                content=ft.Icon(ft.Icons.PALETTE),
                width=42,
                height=42,
                border_radius=ft.border_radius.all(8),
                alignment=ft.alignment.center,
            )

        name_column_controls: list[ft.Control] = [
            ft.Text(name, weight=ft.FontWeight.BOLD, size=15),
        ]
        if isinstance(author, str) and author.strip():
            name_column_controls.append(
                ft.Text(f"作者：{author.strip()}", size=12, color=ft.Colors.GREY),
            )

        name_column = ft.Column(
            controls=name_column_controls,
            spacing=2,
            expand=True,
            tight=True,
        )

        status_badge: ft.Control | None = None
        if is_active:
            status_badge = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE,
                            size=16,
                            color=ft.Colors.ON_PRIMARY_CONTAINER,
                        ),
                        ft.Text("当前", size=12, color=ft.Colors.ON_PRIMARY_CONTAINER),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=ft.border_radius.all(12),
                bgcolor=ft.Colors.PRIMARY_CONTAINER,
            )

        title_row_children: list[ft.Control] = [logo_control, name_column]
        if status_badge is not None:
            title_row_children.append(status_badge)

        source = str(profile.get("source") or "").strip()
        source_label = ""
        if source == "builtin":
            source_label = "来源：内置主题"
        elif source == "file":
            source_label = "来源：主题目录"
        elif source == "custom":
            source_label = "来源：自定义路径"

        description_text = ft.Text(
            preview_text,
            size=12,
            color=ft.Colors.GREY,
            tooltip=tooltip_text,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        body_controls: list[ft.Control] = [
            ft.Row(
                title_row_children,
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.START,
            ),
            description_text,
        ]

        if source_label:
            body_controls.append(ft.Text(source_label, size=11, color=ft.Colors.GREY))

        website = (
            profile.get("website") if isinstance(profile.get("website"), str) else None
        )

        apply_disabled = is_active or self._theme_locked
        actions: list[ft.Control] = [
            ft.FilledButton(
                "应用",
                icon=ft.Icons.CHECK_CIRCLE,
                disabled=apply_disabled,
                tooltip=(
                    self._theme_lock_reason or "当前已锁定主题配置。"
                    if self._theme_locked
                    else None
                ),
                on_click=lambda _=None, pid=identifier: self._apply_theme_profile(pid),
            ),
            ft.OutlinedButton(
                "详情",
                icon=ft.Icons.INFO_OUTLINE,
                on_click=lambda _=None, pid=identifier: self._open_theme_detail_dialog(
                    pid,
                ),
            ),
        ]

        if website and website.strip():
            actions.append(
                ft.TextButton(
                    "访问主页",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _=None, url=website.strip(): self.page.launch_url(
                        url,
                    ),
                ),
            )

        body_controls.append(ft.Container(expand=True))
        body_controls.append(
            ft.Row(
                spacing=8,
                run_spacing=8,
                controls=actions,
            ),
        )

        bgcolor = (
            ft.Colors.SECONDARY_CONTAINER if is_active else self._bgcolor_surface_low
        )
        border_color = ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE_VARIANT
        border_width = 2 if is_active else 1

        return ft.Container(
            content=ft.Column(body_controls, spacing=10),
            width=260,
            height=220,
            padding=ft.padding.all(12),
            border=ft.border.all(border_width, border_color),
            border_radius=ft.border_radius.all(12),
            bgcolor=bgcolor,
        )

    def _apply_theme_profile(self, identifier: str) -> None:
        if self._theme_apply_handler is None:
            self._show_snackbar("主题应用接口不可用。", error=True)
            return
        if self._theme_locked:
            self._show_snackbar(
                self._theme_lock_reason or "当前已锁定主题配置。",
                error=True,
            )
            return
        try:
            result = self._theme_apply_handler(identifier)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"应用主题失败: {exc}")
            self._show_snackbar("应用主题失败。", error=True)
            return

        if isinstance(result, PluginOperationResult):
            if result.success:
                self._show_snackbar(result.message or "主题已应用。")
            elif result.error == "permission_pending":
                self._show_snackbar(result.message or "等待用户授权。")
                return
            else:
                self._show_snackbar(result.message or "主题应用失败。", error=True)
                return
        else:
            self._show_snackbar("主题已应用。")

        self._refresh_theme_profiles(initial=True)

    def _open_theme_detail_dialog(self, identifier: str) -> None:
        profile = self._find_theme_profile(identifier)
        if not profile:
            self._show_snackbar("未找到主题详情。", error=True)
            return

        name = str(profile.get("name") or identifier)
        author = profile.get("author")
        website = (
            profile.get("website") if isinstance(profile.get("website"), str) else None
        )
        description = profile.get("description")
        details = profile.get("details")
        path = profile.get("path")
        source = profile.get("source")
        is_active = bool(profile.get("is_active"))

        info_lines: list[str] = []
        if isinstance(author, str) and author.strip():
            info_lines.append(f"作者：{author.strip()}")
        if source == "builtin":
            info_lines.append("来源：内置主题")
        elif source == "file":
            info_lines.append("来源：主题目录")
        elif source == "custom":
            info_lines.append("来源：自定义路径")
        if isinstance(path, str) and path:
            info_lines.append(f"文件：{path}")

        summary_text = description or "暂无简介"

        content_controls: list[ft.Control] = [
            ft.Text(summary_text, size=13),
        ]
        if details and isinstance(details, str) and details.strip():
            content_controls.append(
                ft.Markdown(
                    details.strip(),
                    selectable=True,
                    auto_follow_links=True,
                ),
            )

        if info_lines:
            content_controls.append(
                ft.Column(
                    [
                        ft.Text(line, size=12, color=ft.Colors.GREY)
                        for line in info_lines
                    ],
                    spacing=4,
                    tight=True,
                ),
            )

        actions: list[ft.Control] = [
            ft.TextButton("关闭", on_click=lambda _: self._close_dialog()),
        ]

        if website and website.strip():
            actions.insert(
                0,
                ft.TextButton(
                    "打开网站",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda _=None, url=website.strip(): self.page.launch_url(
                        url,
                    ),
                ),
            )

        if not is_active:

            def _apply_and_close(_: ft.ControlEvent | None = None) -> None:
                self._close_dialog()
                self._apply_theme_profile(identifier)

            actions.append(
                ft.FilledButton(
                    "应用此主题",
                    icon=ft.Icons.CHECK_CIRCLE,
                    on_click=_apply_and_close,
                ),
            )

        dialog = ft.AlertDialog(
            title=ft.Text(name, weight=ft.FontWeight.BOLD),
            content=ft.Column(content_controls, spacing=12, tight=True, width=420),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._theme_detail_dialog = dialog
        self._open_dialog(dialog)

    def _handle_refresh_theme_list(self, _: ft.ControlEvent | None = None) -> None:
        self._refresh_theme_profiles(show_feedback=True)

    def _ensure_theme_file_picker(self) -> None:
        if self._theme_file_picker is None:
            self._theme_file_picker = ft.FilePicker(
                on_result=self._handle_theme_import_result,
            )
        if self._theme_file_picker not in self.page.overlay:
            self.page.overlay.append(self._theme_file_picker)
            self.page.update()

    def _open_theme_import_picker(self, _: ft.ControlEvent | None = None) -> None:
        if self._theme_locked:
            self._show_snackbar(self._theme_lock_reason or "当前已锁定主题配置。", error=True)
            return
        if self._theme_manager is None:
            self._show_snackbar("主题目录不可用。", error=True)
            return
        self._ensure_theme_file_picker()
        if self._theme_file_picker:
            self._theme_file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
            )

    def _handle_theme_import_result(self, event: ft.FilePickerResultEvent) -> None:
        if self._theme_locked:
            self._show_snackbar(self._theme_lock_reason or "当前已锁定主题配置。", error=True)
            return
        if self._theme_manager is None or not event.files:
            return
        file = event.files[0]
        if not file.path:
            self._show_snackbar("未选择有效的主题文件。", error=True)
            return
        try:
            result = self._theme_manager.import_theme(Path(file.path))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"导入主题失败: {exc}")
            self._show_snackbar(f"导入主题失败：{exc}", error=True)
            return

        metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
        name = metadata.get("name") or Path(file.path).stem
        self._show_snackbar(f"已导入主题：{name}")
        self._refresh_theme_profiles(initial=True)

    def _open_theme_directory(self, _: ft.ControlEvent | None = None) -> None:
        if self._theme_locked:
            self._show_snackbar(self._theme_lock_reason or "当前已锁定主题配置。", error=True)
            return
        if self._theme_manager is None:
            self._show_snackbar("主题目录不可用。", error=True)
            return
        try:
            directory = self._theme_manager.themes_dir.resolve()
            self.page.launch_url(directory.as_uri())
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"打开主题目录失败: {exc}")
            self._show_snackbar("无法打开主题目录。", error=True)

    def _build_theme_settings_controls(self) -> list[ft.Control]:
        notice: ft.Control | None = None
        if self._theme_locked:
            original_label = self._theme_profile_display_name(self._theme_lock_profile)
            notice_lines: list[ft.Control] = [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.EVENT, color=ft.Colors.GREY),
                        ft.Text(
                            "12月13日国家公祭日，已暂停主题导入与切换。",
                            size=13,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    f"原主题：{original_label}",
                    size=12,
                    color=ft.Colors.GREY,
                ),
            ]
            if self._theme_lock_reason:
                notice_lines.append(
                    ft.Text(
                        self._theme_lock_reason,
                        size=12,
                        color=ft.Colors.GREY,
                    ),
                )
            notice = ft.Container(
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                padding=ft.padding.all(12),
                border_radius=ft.border_radius.all(12),
                content=ft.Column(
                    notice_lines,
                    spacing=6,
                    tight=True,
                ),
            )

        actions_wrap: ft.Row | None = None
        helper_text: ft.Text | None = None
        if not self._theme_locked:
            refresh_button = ft.IconButton(
                icon=ft.Icons.REFRESH,
                tooltip="刷新",
                on_click=self._handle_refresh_theme_list,
            )

            controls_row: list[ft.Control] = [refresh_button]

            if self._theme_manager is not None:
                controls_row.append(
                    ft.FilledButton(
                        "导入主题 (.json)",
                        icon=ft.Icons.UPLOAD_FILE,
                        on_click=self._open_theme_import_picker,
                    ),
                )
                controls_row.append(
                    ft.TextButton(
                        "打开主题目录",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=self._open_theme_directory,
                    ),
                )

            actions_wrap = ft.Row(
                spacing=8, run_spacing=8, controls=controls_row, wrap=True,
            )

            helper_text = ft.Text(
                "选择下方卡片可查看主题详情，点击“应用”即可生效。",
                size=12,
                color=ft.Colors.GREY,
            )

        cards_wrap = ft.Row(
            spacing=12, run_spacing=12, wrap=True, scroll=ft.ScrollMode.AUTO,
        )
        self._theme_cards_wrap = cards_wrap
        self._render_theme_cards()

        controls: list[ft.Control] = []
        if notice is not None:
            controls.append(notice)
        if actions_wrap is not None:
            controls.append(actions_wrap)
        if helper_text is not None:
            controls.append(helper_text)
        controls.append(cards_wrap)

        return [
            ft.Column(
                controls=controls,
                spacing=12,
                tight=True,
            ),
        ]

    def build_settings_view(self):
        def _change_nsfw(e: ft.ControlEvent):
            switch = getattr(e, "control", None)
            if switch is None:
                return
            new_val = bool(getattr(switch, "value", False))

            # Turning off: no confirmation needed.
            if not new_val:
                app_config.set("wallpaper.allow_nsfw", False)
                return

            # Turning on: require confirmation. Revert switch to off first.
            switch.value = False
            if switch.page is not None:
                switch.update()

            # Show confirm dialog.
            self._confirm_nsfw()

            # Wire dialog buttons to apply/revert the switch value.
            dlg = getattr(self, "_confirm_nsfw_dialog", None)
            try:
                if dlg and getattr(dlg, "actions", None):
                    # actions = [cancel_btn, confirm_btn]
                    cancel_btn = dlg.actions[0] if len(dlg.actions) > 0 else None
                    confirm_btn = dlg.actions[1] if len(dlg.actions) > 1 else None

                    if confirm_btn:

                        def _on_confirm(_: ft.ControlEvent | None = None):
                            self._handle_confirm_nsfw()
                            switch.value = True
                            if switch.page is not None:
                                switch.update()
                            self._close_dialog()

                        confirm_btn.on_click = _on_confirm

                    if cancel_btn:

                        def _on_cancel(_: ft.ControlEvent | None = None):
                            switch.value = False
                            if switch.page is not None:
                                switch.update()
                            self._close_dialog()

                        cancel_btn.on_click = _on_cancel
            except Exception:
                logger.error("Failed to wire dialog buttons")

        def tab_content(title: str, *controls: ft.Control):
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(title, size=24),
                        ft.Column(list(controls), spacing=12),
                    ],
                    spacing=16,
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=20,
                expand=True,
            )

        third_party_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text("第三方用户协议(部分)", weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [
                                ft.Button(
                                    "IntelliMarkets用户协议",
                                    icon=ft.Icons.OPEN_IN_NEW,
                                    on_click=lambda _: self.page.launch_url(
                                        "https://github.com/SRInternet-Studio/Wallpaper-generator/blob/NEXT-PREVIEW/DISCLAIMER.md",
                                    ),
                                ),
                                ft.Button(
                                    "pollinations.ai 用户协议",
                                    icon=ft.Icons.OPEN_IN_NEW,
                                    on_click=lambda _: self.page.launch_url(
                                        "https://enter.pollinations.ai/terms",
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.TextButton(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda _: setattr(third_party_sheet, "open", False)
                            or self.page.update(),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=50,
            ),
            open=False,
        )
        license_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text("依赖版权信息", weight=ft.FontWeight.BOLD),
                        ft.Markdown(
                            self._get_license_text(),
                            selectable=True,
                            auto_follow_links=True,
                        ),
                        ft.TextButton(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda _: setattr(license_sheet, "open", False)
                            or self.page.update(),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                    scroll=ft.ScrollMode.ALWAYS,
                ),
                padding=50,
            ),
            open=False,
        )
        thank_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text(
                            "感谢以下朋友对开发工作的支持",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Markdown(
                            """@[炫饭的芙芙](https://space.bilibili.com/1669914811) ❤️""",
                            selectable=True,
                            auto_follow_links=True,
                        ),
                        ft.Markdown(
                            """@[Giampaolo-zzp](https://github.com/Giampaolo-zzp) | @茜语茜寻""",
                            selectable=True,
                            auto_follow_links=True,
                        ),
                        ft.TextButton(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda _: setattr(thank_sheet, "open", False)
                            or self.page.update(),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                    scroll=ft.ScrollMode.ALWAYS,
                ),
                padding=50,
            ),
            open=False,
        )
        spoon_sheet = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Text(
                            "特别感谢以下人员在本程序开发阶段的赞助",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text("（按照金额排序 | 相同金额按昵称排序）", size=10),
                        ft.Markdown(
                            """炫饭的芙芙 | 130￥ 👑\n\nGiampaolo-zzp | 50￥\n\nKyle | 30￥\n\n昊阳（漩涡7人） | 8.88￥\n\n蔡亩 | 6￥\n\n小苗 | 6￥\n\nZero | 6￥\n\n遮天s忏悔 | 5.91￥\n\n青山如岱 | 5￥\n\nLYC(luis) | 1￥\n\nFuruya | 0.01￥\n\nwzr | 0.01￥""",
                            selectable=True,
                            auto_follow_links=False,
                        ),
                        ft.TextButton(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda _: setattr(spoon_sheet, "open", False)
                            or self.page.update(),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                    scroll=ft.ScrollMode.ALWAYS,
                ),
                padding=50,
            ),
            open=False,
        )
        general = tab_content(
            "通用",
            self._build_home_settings_section(),
            self._build_startup_settings_section(),
        )
        download = tab_content("下载", self._build_download_settings_section())
        resource = tab_content(
            "内容",
            ft.Text("是否允许 NSFW 内容？"),
            ft.Switch(
                value=app_config.get("wallpaper.allow_nsfw", False),
                on_change=_change_nsfw,
            ),
            ft.Divider(),
            self._build_wallpaper_source_settings_section(),
        )

        theme_dropdown = ft.Dropdown(
            label="界面主题",
            value=app_config.get("ui.theme", "auto"),
            options=[
                ft.DropdownOption(key="auto", text="跟随系统/主题"),
                ft.DropdownOption(key="light", text="浅色"),
                ft.DropdownOption(key="dark", text="深色"),
            ],
            on_change=self._change_theme_mode,
            width=220,
            disabled=self._theme_locked,
            tooltip=(
                self._theme_lock_reason or "当前已锁定主题配置。"
                if self._theme_locked
                else None
            ),
        )

        # 提示：当使用非默认主题配置时，建议将界面主题设为“跟随系统/主题”
        current_theme_profile = (
            str(app_config.get("ui.theme_profile", "default")).strip().lower()
        )
        use_custom_theme_profile = current_theme_profile != "default"

        reminder_text = None
        if use_custom_theme_profile and not self._theme_locked:
            reminder_text = ft.Row(
                [
                    ft.Icon(ft.Icons.INFO, size=15),
                    ft.Text(
                        "已启用主题配置，建议将“界面主题”设置为“跟随系统/主题”，否则可能与主题配色冲突。",
                        size=12,
                    ),
                ],
            )

        theme_lock_tip = None
        if self._theme_locked:
            theme_lock_tip = ft.Text(
                self._theme_lock_reason or "主题设置已锁定。",
                size=12,
                color=ft.Colors.GREY,
            )

        theme_controls = self._build_theme_settings_controls()
        theme_section = ft.Column(
            controls=[ft.Text("主题", size=18, weight=ft.FontWeight.BOLD)]
            + theme_controls,
            spacing=8,
        )
        wallpaper_tab = tab_content(
            "壁纸设置",
            self._build_auto_change_settings_section(),
        )
        appearance = tab_content(
            "外观",
            # 界面主题
            ft.Column(
                [
                    ft.Text("界面", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [theme_dropdown],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    *([reminder_text] if reminder_text else []),
                    *([theme_lock_tip] if theme_lock_tip else []),
                ],
                spacing=8,
            ),
            # 主题配置
            ft.Container(height=8),
            theme_section,
        )
        about = tab_content(
            "关于",
            ft.Text(f"小树壁纸 Next v{VER}", size=16),
            ft.Text(
                f"{BUILD_VERSION}\nCopyright © 2023-2025 Little Tree Studio",
                size=12,
                color=ft.Colors.GREY,
            ),
            ft.Text(
                "部分壁纸源由 小树壁纸资源中心 和 IntelliMarkets-壁纸源市场 提供\nAI 生成由 pollinations.ai 提供\n\n当您使用本软件时，即表示您接受小树工作室用户协议及第三方数据提供方条款。",
                size=12,
                color=ft.Colors.GREY,
            ),
            ft.Row(
                controls=[
                    ft.TextButton(
                        "查看特别鸣谢",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(thank_sheet, "open", True)
                        or self.page.update(),
                    ),
                    ft.TextButton(
                        "查看赞助列表",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(spoon_sheet, "open", True)
                        or self.page.update(),
                    ),
                ],
            ),
            ft.Row(
                controls=[
                    ft.TextButton(
                        "查看许可证",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: self.page.launch_url(
                            "https://www.gnu.org/licenses/agpl-3.0.html",
                        ),
                    ),
                    ft.TextButton(
                        "查看依赖版权信息",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(license_sheet, "open", True)
                        or self.page.update(),
                    ),
                    ft.TextButton(
                        "查看用户协议",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: self.page.launch_url(
                            "https://docs.zsxiaoshu.cn/terms/wallpaper/user_agreement/",
                        ),
                    ),
                    ft.TextButton(
                        "查看二次开发协议",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: self.page.launch_url(
                            "https://docs.zsxiaoshu.cn/terms/wallpaper/secondary_development_agreement/",
                        ),
                    ),
                    ft.TextButton(
                        "查看数据提供方条款",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _: setattr(third_party_sheet, "open", True)
                        or self.page.update(),
                    ),
                ],
            ),
        )

        settings_tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            padding=12,
            tabs=[
                ft.Tab(text="通用", icon=ft.Icons.SETTINGS, content=general),
                ft.Tab(text="壁纸", icon=ft.Icons.IMAGE, content=wallpaper_tab),
                ft.Tab(text="资源", icon=ft.Icons.WALLPAPER, content=resource),
                ft.Tab(text="下载", icon=ft.Icons.DOWNLOAD, content=download),
                ft.Tab(text="外观", icon=ft.Icons.PALETTE, content=appearance),
                ft.Tab(text="关于", icon=ft.Icons.INFO, content=about),
                ft.Tab(
                    text="插件",
                    icon=ft.Icons.EXTENSION,
                    content=self._build_plugin_settings_content(),
                ),
            ],
            expand=True,
        )
        self._settings_tabs = settings_tabs
        self._settings_tab_indices = {
            "general": 0,
            "wallpaper": 1,
            "auto": 1,
            "auto_change": 1,
            "resource": 2,
            "content": 2,
            "download": 3,
            "ui": 4,
            "appearance": 4,
            "about": 5,
            "plugins": 6,
            "plugin": 6,
        }
        if self._pending_settings_tab:
            pending = None
            # Try numeric pending index first
            try:
                pending_idx = int(self._pending_settings_tab)
                if 0 <= pending_idx < len(settings_tabs.tabs):
                    pending = pending_idx
            except Exception:
                pass
            if pending is None:
                pending = self._settings_tab_indices.get(self._pending_settings_tab)
            if pending is not None:
                settings_tabs.selected_index = pending
            self._pending_settings_tab = None

        settings_body_controls = [settings_tabs]
        if SHOW_WATERMARK:
            settings_body_controls.append(build_watermark())

        return ft.View(
            "/settings",
            [
                ft.AppBar(
                    title=ft.Text("设置"),
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        tooltip="返回",
                        on_click=lambda _: self.page.go("/"),
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                ft.Stack(controls=settings_body_controls, expand=True),
                license_sheet,
                thank_sheet,
                spoon_sheet,
                third_party_sheet,
            ],
        )

    def build_test_warning_page(self):
        countdown_seconds = 5
        countdown_hint = ft.Text(
            f"请认真阅读提示，{countdown_seconds} 秒后可继续。",
            text_align=ft.TextAlign.CENTER,
        )
        enter_button = ft.Button(
            text=f"{countdown_seconds} 秒后可继续",
            icon=ft.Icons.NAVIGATE_NEXT,
            disabled=True,
            on_click=lambda _: self.page.go(self._test_warning_next_route),
        )

        async def _count_down():
            remaining = countdown_seconds
            while remaining > 0:
                enter_button.text = f"{remaining} 秒后可继续"
                countdown_hint.value = f"请认真阅读提示，{remaining} 秒后可继续。"
                self.page.update()
                await asyncio.sleep(1)
                remaining -= 1
            enter_button.text = "进入下一步"
            countdown_hint.value = "已确认提示，现在可以继续。"
            enter_button.disabled = False
            self.page.update()

        self.page.run_task(_count_down)

        return ft.View(
            "/test-warning",
            [
                ft.AppBar(
                    title=ft.Text("测试版警告"),
                    leading=ft.Icon(ft.Icons.WARNING),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.WARNING, color=ft.Colors.ORANGE, size=40),
                            ft.Text("测试版警告", size=30, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                "您正在使用小树壁纸 Next 的测试版。测试版可能包含不稳定的功能，甚至会导致数据丢失等严重问题。\n如果您不确定自己在做什么，请前往官网下载稳定版应用。",
                                text_align=ft.TextAlign.CENTER,
                            ),
                            countdown_hint,
                            enter_button,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                    alignment=ft.alignment.center,
                    padding=50,
                    expand=True,
                ),
            ],
        )

    def build_first_run_page(self):
        tips = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.PRIMARY),
                        ft.Text("确认系统壁纸权限已授予，以确保自动更换生效。"),
                    ],
                    spacing=16,
                    tight=True,
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.IMAGE_SEARCH, color=ft.Colors.PRIMARY),
                        ft.Text("浏览“资源”页挑选壁纸源，或从本地导入自定义源。"),
                    ],
                    spacing=16,
                    tight=True,
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.STAR_BORDER, color=ft.Colors.PRIMARY),
                        ft.Text("在“收藏”页整理你喜欢的壁纸，快速查找。"),
                    ],
                    spacing=16,
                    tight=True,
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=18,
            tight=True,
        )

        buttons = ft.Row(
            [
                ft.TextButton(
                    "跳过本次引导",
                    on_click=lambda _: self.finish_first_run(show_feedback=False),
                ),
                ft.FilledButton(
                    "完成并开始使用",
                    icon=ft.Icons.CHECK_CIRCLE,
                    on_click=lambda _: self.finish_first_run(show_feedback=True),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        status_text = (
            "首次运行向导" if self._first_run_pending else "再次查看首次运行指引"
        )

        return ft.View(
            "/first-run",
            [
                ft.AppBar(
                    title=ft.Text(status_text),
                    leading=ft.Icon(ft.Icons.FLAG),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Text(
                                "欢迎使用小树壁纸 Next！",
                                size=26,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "我们为你准备了几个快速提示，帮助你快速了解主要功能。",
                                size=14,
                                color=ft.Colors.GREY,
                            ),
                            ft.Divider(opacity=0),
                            tips,
                            ft.Container(
                                ft.Column(
                                    [
                                        ft.Text(
                                            f"当前版本：{BUILD_VERSION}",
                                            size=12,
                                            color=ft.Colors.GREY,
                                        ),
                                        ft.Text(
                                            "如果稍后需要再次查看，可以从“测试和调试”页打开此页面。",
                                            size=12,
                                            color=ft.Colors.GREY,
                                        ),
                                    ],
                                    spacing=4,
                                ),
                                padding=ft.padding.only(top=12, bottom=24),
                            ),
                            buttons,
                        ],
                        spacing=18,
                        expand=True,
                    ),
                    alignment=ft.alignment.center,
                    padding=ft.padding.all(32),
                    expand=True,
                ),
            ],
        )

    def build_conflict_warning_page(self) -> ft.View:
        conflicts = list(self._startup_conflicts)
        has_conflict = bool(conflicts)

        title_text = (
            "检测到同类软件正在运行" if has_conflict else "未检测到同类壁纸软件"
        )
        description_text = (
            "下列应用可能会干扰小树壁纸Next的功能，请考虑先关闭它们，或忽略继续使用。"
            if has_conflict
            else "当前没有检测到潜在冲突，可以直接继续使用应用。"
        )

        conflict_cards: list[ft.Control] = []
        if has_conflict:
            for entry in conflicts:
                process_rows = [
                    ft.Text(f"- {proc}", selectable=True) for proc in entry.processes
                ]
                card_elements: list[ft.Control] = [
                    ft.Text(
                        entry.title,
                        size=20,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Column(process_rows, spacing=4, tight=True),
                ]
                if entry.note:
                    card_elements.append(
                        ft.Text(
                            entry.note,
                            color=ft.Colors.SECONDARY,
                            size=12,
                        ),
                    )
                conflict_cards.append(
                    ft.Card(
                        content=ft.Container(
                            ft.Column(card_elements, spacing=8, tight=True),
                            padding=20,
                        ),
                    ),
                )

        continue_button_label = "忽略并继续" if has_conflict else "继续"

        content_column_children: list[ft.Control] = [
            ft.Text(
                title_text,
                size=26,
                weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Text(
                description_text,
                text_align=ft.TextAlign.CENTER,
                size=14,
            ),
        ]
        content_column_children.extend(conflict_cards)
        content_column_children.append(
            ft.Row(
                [
                    ft.FilledButton(
                        continue_button_label,
                        icon=ft.Icons.CHECK_CIRCLE,
                        on_click=lambda _: self.page.go(self._conflict_next_route),
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        )

        return ft.View(
            "/conflict-warning",
            [
                ft.AppBar(
                    title=ft.Text("冲突提示"),
                    leading=ft.Icon(ft.Icons.WARNING_AMBER),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                ft.Container(
                    ft.Column(
                        content_column_children,
                        spacing=20,
                        alignment=ft.MainAxisAlignment.START,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                    expand=True,
                    padding=ft.padding.symmetric(horizontal=40, vertical=32),
                    alignment=ft.alignment.center,
                ),
            ],
        )

    def _change_theme_mode(self, e: ft.ControlEvent) -> None:
        if self._theme_locked:
            self._show_snackbar(
                self._theme_lock_reason or "当前已锁定主题配置。",
                error=True,
            )
            return
        value = e.control.value
        if value == "dark":
            self.page.theme_mode = ft.ThemeMode.DARK
            app_config.set("ui.theme", "dark")

        elif value == "light":
            self.page.theme_mode = ft.ThemeMode.LIGHT
            app_config.set("ui.theme", "light")
        else:
            self.page.theme_mode = ft.ThemeMode.SYSTEM
            app_config.set("ui.theme", "auto")
        self.page.update()

    def _ensure_bing_save_picker(self) -> None:
        """确保Bing保存文件选择器已初始化"""
        if self._bing_save_picker is None:
            self._bing_save_picker = ft.FilePicker(
                on_result=self._handle_bing_save_result,
            )
            if self._bing_save_picker not in self.page.overlay:
                self.page.overlay.append(self._bing_save_picker)

    def _handle_bing_save_result(self, event: ft.FilePickerResultEvent) -> None:
        """处理Bing另存为结果"""
        if not event.files:
            return

        file_path = event.files[0].path
        if not file_path:
            return

        try:
            def progress_callback(value, total):
                if total:
                    # 这里需要从外部获取bing_pb和bing_loading_info，但目前作用域有问题
                    pass

            # 直接下载到用户选择的路径
            filename = Path(file_path).name
            final_path = ltwapi.download_file(
                self.bing_wallpaper_url,
                Path(file_path).parent,
                filename,
                progress_callback=progress_callback,
            )

            if final_path:
                self._emit_download_completed("bing", "save_as", final_path)
                self.page.open(
                    ft.SnackBar(
                        ft.Text(f"已保存到 {final_path}"),
                    ),
                )
            else:
                raise Exception("下载失败")

        except Exception as exc:
            logger.error("Bing 壁纸另存为失败: {error}", error=str(exc))
            self.page.open(
                ft.SnackBar(
                    ft.Text("另存为失败，请稍后再试~"),
                    bgcolor=ft.Colors.ON_ERROR,
                ),
            )

    def _ensure_spotlight_save_picker(self) -> None:
        """确保Windows聚焦保存文件选择器已初始化"""
        if self._spotlight_save_picker is None:
            self._spotlight_save_picker = ft.FilePicker(
                on_result=self._handle_spotlight_save_result,
            )
            if self._spotlight_save_picker not in self.page.overlay:
                self.page.overlay.append(self._spotlight_save_picker)

    def _handle_spotlight_save_result(self, event: ft.FilePickerResultEvent) -> None:
        """处理Windows聚焦另存为结果"""
        if not event.files:
            return

        file_path = event.files[0].path
        if not file_path:
            return

        try:
            # 获取当前聚焦壁纸信息
            spotlight = (
                self.spotlight_wallpaper[self.spotlight_current_index]
                if self.spotlight_wallpaper
                else {}
            )
            url = spotlight.get("url")

            if not url:
                raise Exception("未找到壁纸地址")

            def progress_callback(value, total):
                pass  # 另存为不显示进度

            # 直接下载到用户选择的路径
            filename = Path(file_path).name
            final_path = ltwapi.download_file(
                url,
                Path(file_path).parent,
                filename,
                progress_callback=progress_callback,
            )

            if final_path:
                self._emit_download_completed("spotlight", "save_as", final_path)
                self.page.open(
                    ft.SnackBar(
                        ft.Text(f"已保存到 {final_path}"),
                    ),
                )
            else:
                raise Exception("下载失败")

        except Exception as exc:
            logger.error("Windows 聚焦壁纸另存为失败: {error}", error=str(exc))
            self.page.open(
                ft.SnackBar(
                    ft.Text("另存为失败，请稍后再试~"),
                    bgcolor=ft.Colors.ON_ERROR,
                ),
            )
