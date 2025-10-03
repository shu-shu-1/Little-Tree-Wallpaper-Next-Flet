"""Plugin infrastructure exports."""

from .base import (
    AppNavigationView,
    AppRouteView,
    Plugin,
    PluginContext,
    PluginManifest,
    PluginService,
    PluginSettingsPage,
    PluginSettingsTab,
    PluginKind,
    PluginDependencySpec,
)
from .manager import PluginManager, PluginImportResult
from .permissions import (
    KNOWN_PERMISSIONS,
    PluginPermission,
    PermissionState,
    ensure_permission_states,
    normalize_permission_state,
)
from .operations import PluginOperationResult, PluginPermissionError
from .runtime import PluginRuntimeInfo, PluginStatus
from .events import PluginEventBus, PluginEvent, EventDefinition, CORE_EVENT_DEFINITIONS
from .data import (
    GlobalDataAccess,
    GlobalDataEntry,
    GlobalDataNamespace,
    GlobalDataSnapshot,
    GlobalDataStore,
    GlobalDataError,
    NamespaceNotFound,
    NamespaceOwnershipError,
    NamespaceRegistrationError,
    PermissionDenied,
)

__all__ = [
    "AppNavigationView",
    "AppRouteView",
    "Plugin",
    "PluginContext",
    "PluginManifest",
    "PluginService",
    "PluginSettingsPage",
    "PluginSettingsTab",
    "PluginManager",
    "PluginImportResult",
    "PluginKind",
    "PluginDependencySpec",
    "PluginPermission",
    "PermissionState",
    "KNOWN_PERMISSIONS",
    "ensure_permission_states",
    "normalize_permission_state",
    "PluginOperationResult",
    "PluginPermissionError",
    "PluginRuntimeInfo",
    "PluginStatus",
    "PluginEventBus",
    "PluginEvent",
    "EventDefinition",
    "CORE_EVENT_DEFINITIONS",
    "GlobalDataAccess",
    "GlobalDataEntry",
    "GlobalDataNamespace",
    "GlobalDataSnapshot",
    "GlobalDataStore",
    "GlobalDataError",
    "NamespaceNotFound",
    "NamespaceOwnershipError",
    "NamespaceRegistrationError",
    "PermissionDenied",
]
