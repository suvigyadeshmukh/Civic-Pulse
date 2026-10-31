"""Civic Pulse — FastAPI application entry-point.

Responsibilities:
    * ``lifespan`` context manager — verifies DB extensions, bootstraps S3 bucket
    * CORS and Request-ID middleware
    * Dynamic domain router mounting (``importlib`` + ``try/except ImportError``)
    * WebSocket endpoint for real-time agent event streaming
    * ``/health`` probe
"""

from __future__ import annotations

import importlib
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.database import engine, verify_db_connection_and_extensions
from app.core.exceptions import register_exception_handlers
from app.core.pagination import ApiEnvelope
from app.core.redis_bus import redis_client, redis_health_check
from app.core.settings import get_settings
from app.core.storage import storage_service
from app.core.ws_manager import ws_manager

logger = logging.getLogger(__name__)


# ========================================================================== #
# Lifespan — startup / shutdown hooks
# ========================================================================== #

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager (FastAPI 0.109+)."""
    settings = get_settings()

    # ---- Startup --------------------------------------------------------- #
    logger.info("Civic Pulse starting in '%s' mode …", settings.APP_ENV)

    # 1. Verify PostgreSQL connectivity and required extensions. The probe
    #    reports degraded state instead of raising, so a temporarily
    #    unavailable database does not abort optional startup diagnostics.
    try:
        db_info = await verify_db_connection_and_extensions()
        if db_info.get("database") == "connected":
            logger.info("Database verification: %s", db_info)
        else:
            logger.warning("Database verification degraded: %s", db_info)
    except Exception:
        logger.exception("Database verification FAILED — aborting startup.")
        raise

    # 2. Ensure S3 bucket and public-read policy exist. When S3/MinIO is
    #    unreachable, the service activates a local-disk fallback instead of
    #    raising, so application startup never depends on object storage.
    try:
        await storage_service.ensure_bucket_exists()
        if storage_service.using_local_fallback:
            logger.warning(
                "S3 storage unavailable — using local disk fallback at '%s'.",
                storage_service.local_root,
            )
        else:
            logger.info("S3 storage ready — bucket '%s'.", settings.S3_BUCKET_NAME)
    except Exception:
        logger.exception("S3 bucket bootstrap FAILED — aborting startup.")
        raise

    logger.info("Civic Pulse ready — serving on %s:%s", settings.SERVER_HOST, settings.SERVER_PORT)

    yield  # ---- application runs here ----

    # ---- Shutdown -------------------------------------------------------- #
    logger.info("Civic Pulse shutting down …")
    await redis_client.aclose()
    logger.info("Redis connection closed.")
    await engine.dispose()
    logger.info("Database engine disposed.")


# ========================================================================== #
# FastAPI application
# ========================================================================== #

_settings = get_settings()

app = FastAPI(
    title="Civic Pulse API",
    description=(
        "Digital Governance & Public Information Platform — "
        "Identity, Policy Explainer, Grievance Triage, "
        "Bureaucracy Agent, Fact Verification"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _settings.DEBUG else None,
    redoc_url="/redoc" if _settings.DEBUG else None,
)


# ========================================================================== #
# Middleware
# ========================================================================== #

# 1. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. Request-ID — assigns a UUID to every request and exposes it in the
#    response header ``X-Request-ID`` so log correlation is trivial.
class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique ``request_id`` to ``request.state`` and set the
    ``X-Request-ID`` response header.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)


# ========================================================================== #
# Exception handlers
# ========================================================================== #

register_exception_handlers(app)


# ========================================================================== #
# Local-disk media fallback
# ========================================================================== #
# When S3/MinIO is unreachable, StorageService writes uploads under
# ``server/.local_storage/<bucket>/``. Expose that directory over HTTP so the
# React SPA can still stream media in offline/development mode.
_storage_root = storage_service.local_root
_storage_root.mkdir(parents=True, exist_ok=True)
app.mount(
    "/local-media",
    StaticFiles(directory=str(_storage_root)),
    name="local-media",
)


# ========================================================================== #
# Dynamic domain router mounting
# ========================================================================== #

# Each domain module exposes a ``router`` attribute (``APIRouter``).
# We import them lazily so Person 2 and Person 3 never cause Git merge
# conflicts in this file — a missing domain module is simply skipped.

_DOMAIN_ROUTER_CONFIG: list[dict[str, str | list[str]]] = [
    {
        "module": "app.domains.identity.router",
        "prefix": "/api/v1",
        "tags": ["Identity & Auth"],
    },
    {
        "module": "app.domains.policy_explainer.router",
        "prefix": "/api/v1",
        "tags": ["Policy Explainer"],
    },
    {
        "module": "app.domains.grievance_triage.router",
        "prefix": "/api/v1",
        "tags": ["Grievance Triage"],
    },
    {
        "module": "app.domains.bureaucracy_agent.router",
        "prefix": "/api/v1",
        "tags": ["Bureaucracy Agent"],
    },
    {
        # The bureaucracy-agent exposes a second router at /mock-gov-portal
        # for the simulated legacy government portal used during demos.
        "module": "app.domains.bureaucracy_agent.mock_legacy_portal",
        "prefix": "/mock-gov-portal",
        "tags": ["Mock Gov Portal"],
        "attr": "mock_portal_router",
    },
    {
        "module": "app.domains.fact_verification.router",
        "prefix": "/api/v1",
        "tags": ["Fact Verification"],
    },
]


def _mount_domain_routers(application: FastAPI) -> None:
    """Dynamically import and include each domain's ``APIRouter``.

    A failure in a single domain (missing module, import-time exception, or an
    invalid/missing ``router`` attribute) is logged and skipped so that the
    remaining domains still mount and the application can start.
    """
    for cfg in _DOMAIN_ROUTER_CONFIG:
        module_path = str(cfg["module"])
        prefix = str(cfg["prefix"])
        tags: list[str] = list(cfg.get("tags", []))  # type: ignore[arg-type]
        attr_name: str = str(cfg.get("attr", "router"))

        try:
            mod = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            logger.warning(
                "Skipping router %s: module not found (%s).",
                module_path,
                exc,
            )
            continue
        except Exception:
            logger.exception(
                "Skipping router %s during application bootstrap.",
                module_path,
            )
            continue

        domain_router = getattr(mod, attr_name, None)
        if not isinstance(domain_router, APIRouter):
            logger.warning(
                "Skipping router %s: missing or invalid APIRouter instance "
                "(attribute '%s').",
                module_path,
                attr_name,
            )
            continue

        try:
            application.include_router(domain_router, prefix=prefix, tags=tags)
        except Exception:
            logger.exception(
                "Skipping router %s during application bootstrap.",
                module_path,
            )
            continue

        logger.info("Successfully mounted router: %s → %s", module_path, prefix)


_mount_domain_routers(app)


# ========================================================================== #
# WebSocket — real-time agent event stream
# ========================================================================== #

@app.websocket("/ws/agent/{run_id}")
async def ws_agent_stream(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint for streaming real-time events (e.g.
    ``STEP_UPDATE``, ``AGENT_HITL_REQUIRED``) from a Celery worker to the
    connected React client.

    The :class:`~app.core.ws_manager.ConnectionManager` subscribes to the
    Redis Pub/Sub channel ``ws:channel:<run_id>`` and forwards every
    published JSON message.
    """
    await ws_manager.connect(run_id, websocket)
    try:
        await ws_manager.subscribe_and_forward(run_id, websocket)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected — run_id=%s", run_id)
    finally:
        ws_manager.disconnect(run_id, websocket)


# ========================================================================== #
# Health-check endpoint
# ========================================================================== #

@app.get(
    "/health",
    response_model=ApiEnvelope[dict],
    tags=["Health"],
    summary="Platform health check",
)
async def health_check() -> dict:
    """Return aggregated health status for Database, Redis, and S3."""
    db_status: dict
    try:
        db_info = await verify_db_connection_and_extensions()
        db_status = {
            "status": "ok" if db_info.get("database") == "connected" else "error",
            **db_info,
        }
    except Exception as exc:
        # Keep the response credential-safe: report only the exception class.
        db_status = {"status": "error", "detail": type(exc).__name__}

    try:
        redis_status = await redis_health_check()
    except Exception as exc:
        logger.warning("Redis health check raised %s.", type(exc).__name__)
        redis_status = {"status": "error", "detail": type(exc).__name__}

    try:
        s3_status = await storage_service.health_check()
    except Exception as exc:
        logger.warning("S3 health check raised %s.", type(exc).__name__)
        s3_status = {"status": "error", "detail": type(exc).__name__}

    overall = all(
        svc.get("status") == "ok"
        for svc in [db_status, redis_status, s3_status]
    )

    return {
        "success": True,
        "data": {
            "status": "healthy" if overall else "degraded",
            "services": {
                "database": db_status,
                "redis": redis_status,
                "s3": s3_status,
            },
        },
    }


# ========================================================================== #
# Root
# ========================================================================== #

@app.get("/", tags=["Root"], include_in_schema=False)
async def root() -> dict:
    """Minimal root response for load-balancer probes."""
    return {
        "service": "civic-pulse-api",
        "version": "0.1.0",
        "docs": "/docs",
    }

