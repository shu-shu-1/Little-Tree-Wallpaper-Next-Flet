"""Plugin infrastructure exports."""

from app.favorites import (
    FavoriteAIInfo,
    FavoriteAIResult,
    FavoriteCollection,
    FavoriteFolder,
    FavoriteItem,
    FavoriteManager,
    FavoriteSource,
)

from .base import (
    AppNavigationView,
    AppRouteView,
    Plugin,
    PluginContext,
    PluginDependencySpec,
    PluginKind,
    PluginManifest,
    PluginService,
    PluginSettingsPage,
    PluginSettingsTab,
)
from .data import (
    GlobalDataAccess,
    GlobalDataEntry,
    GlobalDataError,
    GlobalDataNamespace,
    GlobalDataSnapshot,
    GlobalDataStore,
    NamespaceNotFound,
    NamespaceOwnershipError,
    NamespaceRegistrationError,
    PermissionDenied,
)
from .events import CORE_EVENT_DEFINITIONS, EventDefinition, PluginEvent, PluginEventBus
from .favorites_api import FavoriteService
from .manager import PluginImportResult, PluginManager
from .operations import PluginOperationResult, PluginPermissionError
from .permissions import (
    KNOWN_PERMISSIONS,
    PermissionState,
    PluginPermission,
    ensure_permission_states,
    normalize_permission_state,
)
from .runtime import PluginRuntimeInfo, PluginStatus

__all__ = [
    "CORE_EVENT_DEFINITIONS",
    "KNOWN_PERMISSIONS",
    "AppNavigationView",
    "AppRouteView",
    "EventDefinition",
    "FavoriteAIInfo",
    "FavoriteAIResult",
    "FavoriteCollection",
    "FavoriteFolder",
    "FavoriteItem",
    "FavoriteManager",
    "FavoriteService",
    "FavoriteSource",
    "GlobalDataAccess",
    "GlobalDataEntry",
    "GlobalDataError",
    "GlobalDataNamespace",
    "GlobalDataSnapshot",
    "GlobalDataStore",
    "NamespaceNotFound",
    "NamespaceOwnershipError",
    "NamespaceRegistrationError",
    "PermissionDenied",
    "PermissionState",
    "Plugin",
    "PluginContext",
    "PluginDependencySpec",
    "PluginEvent",
    "PluginEventBus",
    "PluginImportResult",
    "PluginKind",
    "PluginManager",
    "PluginManifest",
    "PluginOperationResult",
    "PluginPermission",
    "PluginPermissionError",
    "PluginRuntimeInfo",
    "PluginService",
    "PluginSettingsPage",
    "PluginSettingsTab",
    "PluginStatus",
    "ensure_permission_states",
    "normalize_permission_state",
]
