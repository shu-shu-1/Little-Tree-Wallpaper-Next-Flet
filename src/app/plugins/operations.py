"""Common result helpers for plugin operation calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class PluginPermissionError(PermissionError):
    """Raised when a plugin尝试执行缺少授权的操作。"""

    def __init__(self, permission: str, message: str | None = None) -> None:
        super().__init__(message or f"缺少权限: {permission}")
        self.permission = permission


@dataclass(slots=True)
class PluginOperationResult:
    """Represents the outcome of an operation requested by a plugin."""

    success: bool
    data: Any = None
    error: str | None = None
    message: str | None = None
    permission: str | None = None

    @classmethod
    def ok(cls, data: Any = None, message: str | None = None) -> "PluginOperationResult":
        return cls(success=True, data=data, message=message)

    @classmethod
    def denied(
        cls, permission: str, message: str | None = None
    ) -> "PluginOperationResult":
        return cls(
            success=False,
            error="permission_denied",
            message=message or "缺少所需权限。",
            permission=permission,
        )

    @classmethod
    def pending(
        cls, permission: str, message: str | None = None
    ) -> "PluginOperationResult":
        return cls(
            success=False,
            error="permission_pending",
            message=message or "等待用户授权。",
            permission=permission,
        )

    @classmethod
    def failed(
        cls,
        error: str,
        message: str | None = None,
        *,
        data: Any = None,
    ) -> "PluginOperationResult":
        return cls(success=False, error=error, message=message, data=data)

    def raise_for_error(self) -> None:
        """Convenience helper: 将失败结果转为异常。"""

        if self.success:
            return
        if self.error == "permission_denied" and self.permission:
            raise PluginPermissionError(self.permission, self.message)
        raise RuntimeError(self.message or self.error or "操作未成功执行")


__all__ = ["PluginOperationResult", "PluginPermissionError"]
