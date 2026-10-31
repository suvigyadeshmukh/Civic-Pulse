"""Civic Pulse — WebSocket connection manager with Redis Pub/Sub bridging.

Maintains a mapping of ``channel_id`` → ``WebSocket`` and provides a long-lived
:meth:`subscribe_and_forward` coroutine that subscribes to a Redis Pub/Sub
channel and streams every JSON message straight to the connected React client.

Typical flow (bureaucracy-agent example):
    1. Client opens ``ws://host/ws/agent/<run_id>``
    2. FastAPI endpoint calls ``manager.connect(run_id, websocket)``
    3. FastAPI endpoint ``await``s ``manager.subscribe_and_forward(run_id, websocket)``
    4. A Celery worker publishes ``STEP_UPDATE`` via ``publish_ws_event(run_id, {...})``
    5. This manager receives the message on ``ws:channel:<run_id>`` and
       forwards it to the WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_WS_CHANNEL_PREFIX = "ws:channel"


class ConnectionManager:
    """Manages active WebSocket connections keyed by ``channel_id``.

    Designed to be instantiated **once** at module level and shared by the
    FastAPI application.
    """

    def __init__(self) -> None:
        # channel_id → set of connected WebSocket instances
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self, channel_id: str, websocket: WebSocket) -> None:
        """Accept the WebSocket handshake and register it under *channel_id*."""
        await websocket.accept()
        self._connections[channel_id].add(websocket)
        logger.info(
            "WebSocket connected — channel=%s  (total=%d)",
            channel_id,
            len(self._connections[channel_id]),
        )

    def disconnect(self, channel_id: str, websocket: WebSocket) -> None:
        """Remove *websocket* from the connection pool for *channel_id*."""
        self._connections[channel_id].discard(websocket)
        if not self._connections[channel_id]:
            del self._connections[channel_id]
        logger.info("WebSocket disconnected — channel=%s", channel_id)

    @property
    def active_channels(self) -> list[str]:
        """Return a snapshot of channel IDs with at least one connection."""
        return list(self._connections.keys())

    # ------------------------------------------------------------------ #
    # Direct send helper (used outside the Pub/Sub loop if needed)
    # ------------------------------------------------------------------ #

    async def send_json_to_channel(
        self,
        channel_id: str,
        payload: dict,
    ) -> None:
        """Push *payload* as JSON to **every** WebSocket on *channel_id*."""
        dead: list[WebSocket] = []
        for ws in self._connections.get(channel_id, set()):
            try:
                await ws.send_json(payload)
            except (WebSocketDisconnect, RuntimeError):
                dead.append(ws)
        for ws in dead:
            self._connections[channel_id].discard(ws)

    # ------------------------------------------------------------------ #
    # Redis Pub/Sub → WebSocket bridge
    # ------------------------------------------------------------------ #

    async def subscribe_and_forward(
        self,
        channel_id: str,
        websocket: WebSocket,
    ) -> None:
        """Subscribe to Redis ``ws:channel:<channel_id>`` and relay every
        published message to *websocket* until the client disconnects.

        This coroutine is meant to be ``await``-ed inside the WebSocket
        endpoint — it blocks until the socket closes or an error occurs.
        """
        settings = get_settings()
        sub_client: aioredis.Redis = aioredis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        pubsub = sub_client.pubsub()
        channel_name = f"{_WS_CHANNEL_PREFIX}:{channel_id}"

        try:
            await pubsub.subscribe(channel_name)
            logger.info("Subscribed to Redis channel: %s", channel_name)

            # We run two concurrent tasks:
            #   1. Listen for Redis messages and forward them to the WebSocket
            #   2. Listen for incoming WebSocket messages (pings / close frames)
            # When either exits, both are cancelled.

            async def _relay_from_redis() -> None:
                """Forward Redis Pub/Sub messages to the WebSocket."""
                async for raw_message in pubsub.listen():
                    if raw_message["type"] != "message":
                        continue
                    data_str: str = raw_message["data"]
                    try:
                        payload = json.loads(data_str)
                        await websocket.send_json(payload)
                    except (json.JSONDecodeError, TypeError):
                        # Forward raw string if not valid JSON
                        await websocket.send_text(data_str)

            async def _drain_websocket() -> None:
                """Consume client frames so we detect disconnects promptly."""
                try:
                    while True:
                        await websocket.receive_text()
                except WebSocketDisconnect:
                    return

            # Run both; first to exit cancels the other.
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(_relay_from_redis()),
                    asyncio.create_task(_drain_websocket()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected — channel=%s", channel_id)
        except Exception:
            logger.exception("Error in subscribe_and_forward for channel=%s", channel_id)
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.aclose()
            await sub_client.aclose()
            self.disconnect(channel_id, websocket)


# Module-level singleton
ws_manager = ConnectionManager()

