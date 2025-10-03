"""Core application plugin providing built-in pages."""

from __future__ import annotations

import flet as ft

from app.constants import MODE
from app.core.pages import Pages
from app.plugins import (
    AppNavigationView,
    AppRouteView,
    Plugin,
    PluginContext,
    PluginManifest,
)


class CorePlugin(Plugin):
    manifest = PluginManifest(
        identifier="core",
        name="Core Pages",
        version="1.0.0",
        description="Little Tree Wallpaper Next 内置的页面与导航。",
        author="Little Tree Studio",
    )

    # Backwards compatibility for legacy code paths referencing ``name`` / ``version``
    name = manifest.name
    version = manifest.version

    def activate(self, context: PluginContext) -> None:  # type: ignore[override]
        if context.plugin_service:
            try:
                runtime_info = context.plugin_service.list_plugins()
            except Exception:  # pragma: no cover - defensive fall-back
                runtime_info = list(context.metadata.get("plugin_runtime", []))
        else:
            runtime_info = list(context.metadata.get("plugin_runtime", []))

        known_permissions = (
            context.metadata.get("plugin_permissions") if isinstance(context.metadata.get("plugin_permissions"), dict) else {}
        )
        event_definitions = context.list_event_definitions()

        pages = Pages(
            context.page,
            bing_action_factories=context.bing_action_factories,
            spotlight_action_factories=context.spotlight_action_factories,
            settings_pages=context.settings_pages,
            event_bus=context.event_bus,
            plugin_service=context.plugin_service,
            plugin_runtime=runtime_info,
            known_permissions=known_permissions,
            event_definitions=event_definitions,
            global_data=context.global_data,
        )
        context.metadata["core_pages"] = pages

        navigation_views = [
            AppNavigationView(
                id="home",
                label="首页",
                icon=ft.Icons.HOME_OUTLINED,
                selected_icon=ft.Icons.HOME,
                content=pages.home,
            ),
            AppNavigationView(
                id="resource",
                label="资源",
                icon=ft.Icons.ARCHIVE_OUTLINED,
                selected_icon=ft.Icons.ARCHIVE,
                content=pages.resource,
            ),
            AppNavigationView(
                id="sniff",
                label="嗅探",
                icon=ft.Icons.WIFI_FIND_OUTLINED,
                selected_icon=ft.Icons.WIFI_FIND,
                content=pages.sniff,
            ),
            AppNavigationView(
                id="favorite",
                label="收藏",
                icon=ft.Icons.STAR_OUTLINE,
                selected_icon=ft.Icons.STAR,
                content=pages.favorite,
            ),
        ]

        if MODE != "STABLE":
            navigation_views.append(
                AppNavigationView(
                    id="test",
                    label="测试和调试\n(仅限测试版)",
                    icon=ft.Icons.SCIENCE_OUTLINED,
                    selected_icon=ft.Icons.SCIENCE,
                    content=pages.test,
                )
            )

        for view in navigation_views:
            context.add_navigation_view(view)

        context.add_route_view(AppRouteView(route="/settings", builder=pages.build_settings_view))
        for entry in pages.iter_plugin_settings_pages():
            context.add_route_view(
                AppRouteView(
                    route=f"/settings/plugin/{entry.plugin_identifier}",
                    builder=lambda pid=entry.plugin_identifier: pages.build_plugin_settings_view(pid),
                )
            )
        context.add_route_view(
            AppRouteView(route="/test-warning", builder=pages.build_test_warning_page)
        )

        if MODE == "TEST":
            context.set_initial_route("/test-warning")
        else:
            context.set_initial_route("/")

        context.add_startup_hook(lambda: pages.refresh_hitokoto())


PLUGIN = CorePlugin()
