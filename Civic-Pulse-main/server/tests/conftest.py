"""Shared pytest fixtures for the Civic Pulse backend test suite."""

from __future__ import annotations

import httpx
import pytest

from app.main import app


@pytest.fixture
async def client() -> httpx.AsyncClient:
    """Async FastAPI test client using the supported ASGI transport API.

    ``httpx.ASGITransport`` does not run the application lifespan, so these
    tests remain independent of PostgreSQL, Redis, and MinIO availability.
    """
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client
