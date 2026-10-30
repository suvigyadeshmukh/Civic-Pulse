"""Civic Pulse — Async Redis client with JSON helpers and Pub/Sub event bus.

Every Celery worker (e.g. Playwright ``STEP_UPDATE``, ``AGENT_HITL_REQUIRED``)
publishes events through :func:`publish_ws_event`, and the FastAPI
:class:`~app.core.ws_manager.ConnectionManager` subscribes to the
corresponding channel to relay updates to the React client over WebSocket.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# ---------------------------------------------------------------------------
# Module-level async Redis client — shared by the entire FastAPI process.
# decode_responses=True so all GET / SUBSCRIBE calls return ``str``.
# ---------------------------------------------------------------------------
redis_client: aioredis.Redis = aioredis.Redis.from_url(
    _settings.REDIS_URL,
    decode_responses=True,
)

# Channel prefix used for WebSocket forwarding
_WS_CHANNEL_PREFIX = "ws:channel"


# ---------------------------------------------------------------------------
# Pub/Sub event bus
# ---------------------------------------------------------------------------

async def publish_ws_event(channel_id: str, event_payload: dict[str, Any]) -> None:
    """Publish a JSON event to the Redis channel ``ws:channel:<channel_id>``.

    Domain-specific Celery tasks call this to push real-time updates (e.g.
    ``STEP_UPDATE``, ``AGENT_HITL_REQUIRED``) that are forwarded to the
    matching WebSocket connection by :class:`~app.core.ws_manager.ConnectionManager`.

    Parameters
    ----------
    channel_id:
        Typically the ``run_id`` UUID of a bureaucracy-agent run.
    event_payload:
        Arbitrary JSON-serialisable dict.
    """
    channel = f"{_WS_CHANNEL_PREFIX}:{channel_id}"
    message = json.dumps(event_payload, ensure_ascii=False, default=str)
    await redis_client.publish(channel, message)
    logger.debug("Published to %s: %s", channel, message[:200])


# ---------------------------------------------------------------------------
# Generic JSON cache helpers
# ---------------------------------------------------------------------------

async def set_json(key: str, val: dict[str, Any], ttl_sec: int = 300) -> None:
    """Serialise *val* as JSON and ``SETEX`` into Redis with a TTL.

    Parameters
    ----------
    key:
        Cache key string (should be namespaced by the caller, e.g.
        ``"factcheck:claim:<id>"``).
    val:
        JSON-serialisable dict.
    ttl_sec:
        Expiry in seconds (default 5 min).
    """
    await redis_client.setex(key, ttl_sec, json.dumps(val, ensure_ascii=False, default=str))


async def get_json(key: str) -> dict[str, Any] | None:
    """Retrieve and deserialise a JSON value from Redis.

    Returns ``None`` if the key does not exist or has expired.
    """
    raw: str | None = await redis_client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Corrupt JSON in Redis key '%s'; ignoring.", key)
        return None


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------

async def redis_health_check() -> dict[str, str]:
    """Ping Redis and return a status dict."""
    try:
        pong: Any = await redis_client.ping()
        return {"status": "ok", "ping": str(pong)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}

