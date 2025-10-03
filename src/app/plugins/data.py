"""Global data registry shared between core and plugins."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from loguru import logger

PermissionResolver = Callable[[str, str], bool]


class GlobalDataError(RuntimeError):
    """Base error for global data operations."""


class NamespaceRegistrationError(GlobalDataError):
    """Raised when attempting to (re)register an invalid namespace."""


class NamespaceNotFound(GlobalDataError):
    """Raised when the requested namespace does not exist."""


class NamespaceOwnershipError(GlobalDataError):
    """Raised when a plugin tries to mutate a namespace it doesn't own."""


class PermissionDenied(GlobalDataError):
    """Raised when a plugin attempts to access protected data without permission."""


@dataclass(slots=True)
class GlobalDataEntry:
    """Single record stored within a namespace."""

    identifier: str
    namespace: str
    owner: str
    payload: Dict[str, Any]
    revision: int
    created_at: float
    updated_at: float

    def snapshot(self) -> "GlobalDataSnapshot":
        return GlobalDataSnapshot(
            namespace=self.namespace,
            identifier=self.identifier,
            owner=self.owner,
            payload=dict(self.payload),
            revision=self.revision,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


@dataclass(slots=True)
class GlobalDataNamespace:
    """Metadata describing a global data namespace."""

    identifier: str
    owner: str
    description: str = ""
    permission: str | None = None
    entries: Dict[str, GlobalDataEntry] = field(default_factory=dict)
    latest_id: str | None = None

    def describe(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "owner": self.owner,
            "description": self.description,
            "permission": self.permission,
            "entry_count": len(self.entries),
            "latest_id": self.latest_id,
        }


@dataclass(slots=True)
class GlobalDataSnapshot:
    """Immutable view of a stored global data entry."""

    namespace: str
    identifier: str
    owner: str
    payload: Dict[str, Any]
    revision: int
    created_at: float
    updated_at: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "identifier": self.identifier,
            "owner": self.owner,
            "payload": dict(self.payload),
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class GlobalDataStore:
    """Authoritative registry of shared plugin data."""

    def __init__(self, permission_resolver: PermissionResolver | None = None) -> None:
        self._namespaces: Dict[str, GlobalDataNamespace] = {}
        self._permission_resolver = permission_resolver

    # ------------------------------------------------------------------
    # namespace helpers
    # ------------------------------------------------------------------
    def register_namespace(
        self,
        owner: str,
        identifier: str,
        *,
        description: str = "",
        permission: str | None = None,
        overwrite: bool = False,
    ) -> None:
        if not identifier:
            raise NamespaceRegistrationError("命名空间标识符不能为空")

        namespace = self._namespaces.get(identifier)
        if namespace:
            if namespace.owner != owner and not overwrite:
                raise NamespaceRegistrationError(
                    f"命名空间 {identifier} 已由 {namespace.owner} 拥有"
                )
            if namespace.owner != owner and overwrite:
                logger.warning(
                    "命名空间 {ns} 由 {current_owner} 拥有，现由 {owner} 强制覆盖",
                    ns=identifier,
                    current_owner=namespace.owner,
                    owner=owner,
                )
                self._namespaces[identifier] = GlobalDataNamespace(
                    identifier=identifier,
                    owner=owner,
                    description=description,
                    permission=permission,
                    entries=namespace.entries if overwrite else {},
                    latest_id=namespace.latest_id if overwrite else None,
                )
                return
            # same owner - update metadata in-place without clearing entries
            namespace.description = description or namespace.description
            if permission is not None:
                namespace.permission = permission
            return

        self._namespaces[identifier] = GlobalDataNamespace(
            identifier=identifier,
            owner=owner,
            description=description,
            permission=permission,
        )

    def list_namespaces(self) -> List[GlobalDataNamespace]:
        return list(self._namespaces.values())

    def describe_namespaces(self) -> List[Dict[str, Any]]:
        return [ns.describe() for ns in self._namespaces.values()]

    def namespace_permission(self, identifier: str) -> str | None:
        namespace = self._namespaces.get(identifier)
        if not namespace:
            raise NamespaceNotFound(identifier)
        return namespace.permission

    # ------------------------------------------------------------------
    # data helpers
    # ------------------------------------------------------------------
    def publish(
        self,
        owner: str,
        namespace_id: str,
        entry_id: str,
        payload: Dict[str, Any],
    ) -> GlobalDataSnapshot:
        namespace = self._namespaces.get(namespace_id)
        if namespace is None:
            raise NamespaceNotFound(namespace_id)
        if namespace.owner != owner:
            raise NamespaceOwnershipError(
                f"插件 {owner} 无权写入命名空间 {namespace_id}"
            )
        if not entry_id:
            raise GlobalDataError("数据条目 ID 不能为空")

        now = time.time()
        existing = namespace.entries.get(entry_id)
        revision = (existing.revision + 1) if existing else 1
        entry = GlobalDataEntry(
            identifier=entry_id,
            namespace=namespace_id,
            owner=owner,
            payload=dict(payload),
            revision=revision,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        namespace.entries[entry_id] = entry
        namespace.latest_id = entry_id
        return entry.snapshot()

    def get_entry(
        self,
        plugin_id: str,
        namespace_id: str,
        entry_id: str,
    ) -> GlobalDataSnapshot | None:
        namespace = self._namespaces.get(namespace_id)
        if namespace is None:
            raise NamespaceNotFound(namespace_id)
        if not self._can_access(plugin_id, namespace.permission):
            raise PermissionDenied(namespace.permission or "")
        entry = namespace.entries.get(entry_id)
        if entry is None:
            return None
        return entry.snapshot()

    def list_entries(
        self,
        plugin_id: str,
        namespace_id: str,
    ) -> List[GlobalDataSnapshot]:
        namespace = self._namespaces.get(namespace_id)
        if namespace is None:
            raise NamespaceNotFound(namespace_id)
        if not self._can_access(plugin_id, namespace.permission):
            raise PermissionDenied(namespace.permission or "")
        return [entry.snapshot() for entry in namespace.entries.values()]

    def latest_entry(
        self,
        plugin_id: str,
        namespace_id: str,
    ) -> GlobalDataSnapshot | None:
        namespace = self._namespaces.get(namespace_id)
        if namespace is None:
            raise NamespaceNotFound(namespace_id)
        if not self._can_access(plugin_id, namespace.permission):
            raise PermissionDenied(namespace.permission or "")
        latest_id = namespace.latest_id
        if not latest_id:
            return None
        entry = namespace.entries.get(latest_id)
        if entry is None:
            return None
        return entry.snapshot()

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _can_access(self, plugin_id: str, permission: str | None) -> bool:
        if permission is None:
            return True
        if self._permission_resolver is None:
            return False
        try:
            return self._permission_resolver(plugin_id, permission)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "检查全局数据权限失败: {error}",
                error=str(exc),
            )
            return False


class GlobalDataAccess:
    """Plugin-scoped helper wrapping :class:`GlobalDataStore`."""

    def __init__(self, plugin_id: str, store: GlobalDataStore) -> None:
        self._plugin_id = plugin_id
        self._store = store

    # Namespace helpers -------------------------------------------------
    def register_namespace(
        self,
        identifier: str,
        *,
        description: str = "",
        permission: str | None = None,
        overwrite: bool = False,
    ) -> None:
        self._store.register_namespace(
            owner=self._plugin_id,
            identifier=identifier,
            description=description,
            permission=permission,
            overwrite=overwrite,
        )

    def list_namespaces(self) -> List[Dict[str, Any]]:
        namespaces = self._store.list_namespaces()
        result: List[Dict[str, Any]] = []
        for namespace in namespaces:
            if namespace.permission and not self._store._can_access(
                self._plugin_id, namespace.permission
            ):
                continue
            result.append(namespace.describe())
        return result

    # Data helpers ------------------------------------------------------
    def publish(self, namespace_id: str, entry_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = self._store.publish(
            owner=self._plugin_id,
            namespace_id=namespace_id,
            entry_id=entry_id,
            payload=payload,
        )
        return snapshot.as_dict()

    def get(self, namespace_id: str, entry_id: str) -> Dict[str, Any] | None:
        try:
            snapshot = self._store.get_entry(
                plugin_id=self._plugin_id,
                namespace_id=namespace_id,
                entry_id=entry_id,
            )
        except PermissionDenied:
            return None
        return snapshot.as_dict() if snapshot else None

    def latest(self, namespace_id: str) -> Dict[str, Any] | None:
        try:
            snapshot = self._store.latest_entry(
                plugin_id=self._plugin_id,
                namespace_id=namespace_id,
            )
        except PermissionDenied:
            return None
        return snapshot.as_dict() if snapshot else None

    def list(self, namespace_id: str) -> List[Dict[str, Any]]:
        try:
            snapshots = self._store.list_entries(
                plugin_id=self._plugin_id,
                namespace_id=namespace_id,
            )
        except PermissionDenied:
            return []
        return [snapshot.as_dict() for snapshot in snapshots]


__all__ = [
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
]
