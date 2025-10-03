"""Lightweight IPC broadcast service for plugins."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from multiprocessing.connection import Connection, Listener
from queue import Queue
from typing import Any, Dict, Iterable, Tuple

from loguru import logger

from .paths import RUNTIME_DIR


@dataclass(slots=True)
class IPCSubscription:
    """Handle returned to plugins for receiving IPC messages."""

    subscription_id: str
    channel: str
    queue: Queue

    def get(self, timeout: float | None = None) -> Dict[str, Any] | None:
        """Wait for the next message on this subscription.

        Returns ``None`` if the queue is closed or no message arrives before ``timeout``.
        """

        try:
            return self.queue.get(timeout=timeout)
        except Exception:
            return None

    def close(self) -> None:
        """Signal that no further messages should be read."""

        try:
            self.queue.put_nowait(None)
        except Exception:
            pass


class IPCService:
    """Local named-pipe/TCP based broadcast broker for plugins and external clients."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, IPCSubscription] = {}
        self._channel_index: Dict[str, set[str]] = defaultdict(set)
        self._connection_index: Dict[Connection, set[str]] = {}
        self._connection_lock = threading.RLock()
        self._running = True
        self._listener, self._address = self._create_listener()
        self._accept_thread = threading.Thread(target=self._accept_loop, name="ipc-accept", daemon=True)
        self._accept_thread.start()
        logger.info("IPC 服务已启动，地址：{address}", address=self._address)

    # ------------------------------------------------------------------
    # public API for in-process plugins
    # ------------------------------------------------------------------
    def subscribe(self, channel: str) -> IPCSubscription:
        subscription_id = uuid.uuid4().hex
        queue: Queue = Queue()
        subscription = IPCSubscription(subscription_id=subscription_id, channel=channel, queue=queue)
        with self._lock:
            self._subscriptions[subscription_id] = subscription
            self._channel_index[channel].add(subscription_id)
        return subscription

    def unsubscribe(self, subscription_id: str) -> None:
        with self._lock:
            subscription = self._subscriptions.pop(subscription_id, None)
            if not subscription:
                return
            self._channel_index[subscription.channel].discard(subscription_id)
            if not self._channel_index[subscription.channel]:
                self._channel_index.pop(subscription.channel, None)
        subscription.close()

    def broadcast(
        self,
        channel: str,
        payload: Dict[str, Any],
        *,
        origin: str,
    ) -> None:
        event = {
            "channel": channel,
            "payload": payload,
            "origin": origin,
            "timestamp": time.time(),
        }
        targets: Iterable[IPCSubscription]
        with self._lock:
            targets = [self._subscriptions[sid] for sid in self._channel_index.get(channel, set())]
        for subscription in targets:
            try:
                subscription.queue.put_nowait(dict(event))
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("IPC 消息投递失败: {error}", error=str(exc))
        self._broadcast_external(event)

    def describe(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "address": self._address,
                "channels": {channel: len(subs) for channel, subs in self._channel_index.items()},
                "subscription_count": len(self._subscriptions),
            }

    def shutdown(self) -> None:
        self._running = False
        try:
            self._listener.close()
        except Exception:
            pass
        with self._connection_lock:
            for connection in list(self._connection_index.keys()):
                try:
                    connection.close()
                except Exception:
                    pass
            self._connection_index.clear()
        with self._lock:
            for subscription_id in list(self._subscriptions.keys()):
                self.unsubscribe(subscription_id)

    # ------------------------------------------------------------------
    # listener management
    # ------------------------------------------------------------------
    def _create_listener(self) -> Tuple[Listener, str]:
        if os.name == "nt":
            address = r"\\.\pipe\little-tree-wallpaper-ipc"
            listener = Listener(address, family="AF_PIPE")
            return listener, address
        else:
            socket_path = RUNTIME_DIR / "ipc.sock"
            try:
                socket_path.unlink()
            except FileNotFoundError:
                pass
            listener = Listener(str(socket_path), family="AF_UNIX")
            return listener, str(socket_path)

    def _accept_loop(self) -> None:
        while self._running:
            try:
                connection = self._listener.accept()
            except (OSError, EOFError):
                if not self._running:
                    break
                continue
            with self._connection_lock:
                self._connection_index[connection] = set()
            threading.Thread(
                target=self._handle_connection,
                name="ipc-client",
                args=(connection,),
                daemon=True,
            ).start()

    def _handle_connection(self, connection: Connection) -> None:
        try:
            while self._running:
                try:
                    message = connection.recv()
                except EOFError:
                    break
                except OSError:
                    break
                if not isinstance(message, dict):
                    continue
                action = message.get("action")
                if action == "subscribe":
                    channel = str(message.get("channel"))
                    self._register_external_subscription(connection, channel)
                elif action == "unsubscribe":
                    channel = str(message.get("channel"))
                    self._remove_external_subscription(connection, channel)
                elif action == "publish":
                    channel = str(message.get("channel"))
                    payload = message.get("payload", {})
                    if not isinstance(payload, dict):
                        try:
                            payload = json.loads(json.dumps(payload))
                        except Exception:
                            payload = {"value": payload}
                    self.broadcast(channel, payload, origin="external")
                elif action == "describe":
                    try:
                        connection.send(self.describe())
                    except Exception:
                        continue
                else:
                    continue
        finally:
            with self._connection_lock:
                channels = self._connection_index.pop(connection, set())
            for channel in channels:
                self._remove_external_subscription(connection, channel)
            try:
                connection.close()
            except Exception:
                pass

    def _register_external_subscription(self, connection: Connection, channel: str) -> None:
        with self._connection_lock:
            subscriptions = self._connection_index.setdefault(connection, set())
            subscriptions.add(channel)
        # acknowledge subscription
        try:
            connection.send({"ack": "subscribe", "channel": channel})
        except Exception:  # pragma: no cover - best effort
            pass

    def _remove_external_subscription(self, connection: Connection, channel: str) -> None:
        with self._connection_lock:
            subscriptions = self._connection_index.get(connection)
            if subscriptions and channel in subscriptions:
                subscriptions.discard(channel)
                if not subscriptions:
                    self._connection_index.pop(connection, None)
        try:
            connection.send({"ack": "unsubscribe", "channel": channel})
        except Exception:  # pragma: no cover
            pass

    def _broadcast_external(self, event: Dict[str, Any]) -> None:
        message = dict(event)
        with self._connection_lock:
            targets = list(self._connection_index.keys())
        for connection in targets:
            try:
                connection.send(message)
            except Exception:  # pragma: no cover - remote side may be gone
                self._remove_external_subscription(connection, event["channel"])


__all__ = ["IPCService", "IPCSubscription"]
