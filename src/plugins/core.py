"""Core application plugin providing built-in pages."""

from __future__ import annotations

import flet as ft

from app.constants import MODE, FIRST_RUN_MARKER_VERSION
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
            context.metadata.get("plugin_permissions")
            if isinstance(context.metadata.get("plugin_permissions"), dict)
            else {}
        )
        event_definitions = context.list_event_definitions()
        theme_manager = context.metadata.get("theme_manager")
        theme_profiles = []
        metadata_profiles = context.metadata.get("theme_profiles")
        if isinstance(metadata_profiles, list):
            theme_profiles = metadata_profiles

        first_run_required_version = context.metadata.get("first_run_required_version")
        try:
            first_run_required_version = (
                int(first_run_required_version)
                if first_run_required_version is not None
                else FIRST_RUN_MARKER_VERSION
            )
        except (TypeError, ValueError):
            first_run_required_version = FIRST_RUN_MARKER_VERSION

        first_run_pending = bool(context.metadata.get("first_run_pending"))

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
            theme_manager=theme_manager,
            theme_list_handler=context.list_themes,
            theme_apply_handler=context.set_theme_profile,
            theme_profiles=theme_profiles,
            first_run_required_version=first_run_required_version,
            first_run_pending=first_run_pending,
            first_run_next_route="/",
        )
        context.metadata["core_pages"] = pages
        startup_conflicts = list(context.metadata.get("startup_conflicts") or [])
        pages.set_startup_conflicts(startup_conflicts)

        startup_sequence: list[str] = []
        if MODE == "TEST":
            startup_sequence.append("/test-warning")
        if first_run_pending:
            startup_sequence.append("/first-run")
        if startup_conflicts:
            startup_sequence.append("/conflict-warning")

        def _next_route(route: str) -> str:
            try:
                index = startup_sequence.index(route)
            except ValueError:
                return "/"
            return startup_sequence[index + 1] if index + 1 < len(startup_sequence) else "/"

        pages.set_test_warning_next_route(_next_route("/test-warning"))
        pages.set_first_run_next_route(_next_route("/first-run"))
        pages.set_conflict_next_route(_next_route("/conflict-warning"))

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
                id="generate",
                label="生成",
                icon=ft.Icons.AUTO_AWESOME_OUTLINED,
                selected_icon=ft.Icons.AUTO_AWESOME,
                content=pages.generate,
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

        context.add_route_view(
            AppRouteView(route="/settings", builder=pages.build_settings_view)
        )
        from app.plugins.base import PluginSettingsPage

        def _make_settings_route(entry: PluginSettingsPage) -> AppRouteView:
            route_path = f"/settings/plugin/{entry.plugin_identifier}"

            def _builder(pid: str = entry.plugin_identifier) -> ft.View:
                return pages.build_plugin_settings_view(pid)

            return AppRouteView(route=route_path, builder=_builder)

        for entry in pages.iter_plugin_settings_pages():
            context.add_route_view(_make_settings_route(entry))
        context.add_route_view(
            AppRouteView(route="/test-warning", builder=pages.build_test_warning_page)
        )
        context.add_route_view(
            AppRouteView(
                route="/resource/wallpaper-preview",
                builder=pages.build_wallpaper_preview_view,
            )
        )
        context.add_route_view(
            AppRouteView(route="/first-run", builder=pages.build_first_run_page)
        )
        context.add_route_view(
            AppRouteView(
                route="/conflict-warning",
                builder=pages.build_conflict_warning_page,
            )
        )

        initial_route = startup_sequence[0] if startup_sequence else "/"
        context.set_initial_route(initial_route or "/")

        context.add_startup_hook(lambda: pages.refresh_hitokoto())


PLUGIN = CorePlugin()
