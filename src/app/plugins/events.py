"""Event system for plugins in Little Tree Wallpaper Next."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


@dataclass(slots=True)
class EventDefinition:
    """Declarative metadata describing a published application event."""

    event_type: str
    description: str = ""
    permission: str | None = None


@dataclass(slots=True)
class PluginEvent:
    """Runtime envelope delivered to plugin listeners."""

    type: str
    payload: Dict[str, Any]
    source: str


EventHandler = Callable[[PluginEvent], None]


@dataclass(slots=True)
class _EventListener:
    plugin_id: str
    handler: EventHandler


class PluginEventBus:
    """Simple synchronous event dispatcher with permission gating."""

    def __init__(
        self,
        permission_resolver: Optional[Callable[[str, str], bool]] = None,
    ) -> None:
        self._permission_resolver = permission_resolver
        self._listeners: Dict[str, List[_EventListener]] = {}
        self._definitions: Dict[str, EventDefinition] = {}
        self._owners: Dict[str, str] = {}
        self._last_events: Dict[str, PluginEvent] = {}

    # ------------------------------------------------------------------
    # configuration helpers
    # ------------------------------------------------------------------
    def register_event(
        self,
        owner: str,
        event_type: str,
        *,
        description: str = "",
        permission: str | None = None,
        overwrite: bool = False,
    ) -> None:
        existing_owner = self._owners.get(event_type)
        if existing_owner and existing_owner != owner and not overwrite:
            logger.warning(
                "事件 {event_type} 已被 {current_owner} 注册，{requester} 的请求已忽略",
                event_type=event_type,
                current_owner=existing_owner,
                requester=owner,
            )
            return
        self._owners[event_type] = owner
        self._definitions[event_type] = EventDefinition(
            event_type=event_type,
            description=description,
            permission=permission,
        )

    def list_event_definitions(self) -> List[EventDefinition]:
        return list(self._definitions.values())

    def reset(self) -> None:
        """Clear listeners and transient state while preserving definitions."""

        self._listeners.clear()
        self._last_events.clear()

    def clear_all(self) -> None:
        """Reset all definitions and listeners."""

        self._listeners.clear()
        self._definitions.clear()
        self._owners.clear()
        self._last_events.clear()

    # ------------------------------------------------------------------
    # subscription helpers
    # ------------------------------------------------------------------
    def subscribe(
        self,
        plugin_id: str,
        event_type: str,
        handler: EventHandler,
        *,
        replay_last: bool = True,
    ) -> Callable[[], None]:
        definition = self._definitions.get(event_type)
        if definition is None:
            logger.warning(
                "插件 {plugin} 订阅未注册事件 {event}",
                plugin=plugin_id,
                event=event_type,
            )
        listener = _EventListener(plugin_id=plugin_id, handler=handler)
        listeners = self._listeners.setdefault(event_type, [])
        listeners.append(listener)

        if replay_last:
            last_event = self._last_events.get(event_type)
            if last_event is not None and self._can_receive(listener, definition):
                self._deliver(listener, last_event)

        def _unsubscribe() -> None:
            current = self._listeners.get(event_type)
            if not current:
                return
            try:
                current.remove(listener)
            except ValueError:
                return
            if not current:
                self._listeners.pop(event_type, None)

        return _unsubscribe

    def emit(
        self,
        event_type: str,
        payload: Dict[str, Any] | None = None,
        *,
        source: str,
    ) -> None:
        definition = self._definitions.get(event_type)
        event = PluginEvent(
            type=event_type,
            payload=dict(payload or {}),
            source=source,
        )
        self._last_events[event_type] = event
        listeners = list(self._listeners.get(event_type, []))
        for listener in listeners:
            if not self._can_receive(listener, definition):
                continue
            self._deliver(listener, event)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _can_receive(
        self,
        listener: _EventListener,
        definition: EventDefinition | None,
    ) -> bool:
        if definition is None or definition.permission is None:
            return True
        if self._permission_resolver is None:
            return False
        try:
            return self._permission_resolver(listener.plugin_id, definition.permission)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "检查事件权限时出错: {error}",
                error=str(exc),
            )
            return False

    def _deliver(self, listener: _EventListener, event: PluginEvent) -> None:
        try:
            listener.handler(event)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "事件处理器执行失败: {error}",
                error=str(exc),
            )


CORE_EVENT_DEFINITIONS: List[EventDefinition] = [
    EventDefinition(
        event_type="resource.bing.updated",
        description="当 Bing 每日壁纸数据刷新时触发。",
        permission="resource_data",
    ),
    EventDefinition(
        event_type="resource.bing.action",
        description="当用户在 Bing 壁纸卡片上执行内置操作（设为壁纸、复制等）时触发。",
        permission="resource_data",
    ),
    EventDefinition(
        event_type="resource.spotlight.updated",
        description="当 Windows 聚焦资源列表更新或选中项发生变化时触发。",
        permission="resource_data",
    ),
    EventDefinition(
        event_type="resource.spotlight.action",
        description="当用户在 Windows 聚焦卡片上执行下载、复制等操作时触发。",
        permission="resource_data",
    ),
    EventDefinition(
        event_type="resource.download.completed",
        description="当内置壁纸下载完成时触发，提供下载来源与文件路径。",
        permission="resource_data",
    ),
    EventDefinition(
        event_type="resource.im_source.executed",
        description="当用户调用 IntelliMarkets 图片源并完成请求时触发。",
        permission="resource_data",
    ),
    EventDefinition(
        event_type="resource.im_source.action",
        description="当用户对 IntelliMarkets 下载结果执行内置操作（设为壁纸、复制、收藏等）时触发。",
        permission="resource_data",
    ),
    
]
