"""Civic Pulse — Core Infrastructure Unit & Integration Tests.

Unit and mocked API tests run without PostgreSQL, Redis, or MinIO. Tests marked
``integration`` probe live services when their ports are reachable and skip
with an explicit reason otherwise.

Validates the contracts of app.core:
- Settings parsing & caching
- SQLAlchemy DeclarativeBase naming convention
- Argon2id password hashing & verification
- JWT creation, decoding, expiry, and tamper rejection
- AES-256-GCM PII Vault field-level encryption
- AppException hierarchy and API error envelopes
- Generic ApiEnvelope and PaginatedMeta schemas
- Request-ID middleware and custom 404 envelopes
- Health endpoint healthy/degraded behaviour with mocked dependencies
- RBAC role enforcement and CurrentUserContext
- Live PostgreSQL, Redis, and MinIO connectivity (integration)
"""

from __future__ import annotations

import asyncio
import socket
import uuid
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
import pytest
from botocore.exceptions import BotoCoreError
from fastapi import FastAPI
from jose import JWTError

import app.core.security as security
import app.main as main_module
from app.core.database import (
    NAMING_CONVENTION,
    Base,
    verify_db_connection_and_extensions,
)
from app.core.dependencies import CurrentUserContext, require_roles
from app.core.exceptions import (
    AppException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
    register_exception_handlers,
)
from app.core.pagination import ApiEnvelope, PaginatedMeta, PaginationParams
from app.core.redis_bus import redis_client
from app.core.security import (
    _decode_pii_key,
    create_access_token,
    decode_access_token,
    decrypt_pii_dict,
    encrypt_pii_dict,
    hash_password,
    verify_password,
)
from app.core.settings import Settings, get_settings
from app.core.storage import storage_service
from app.main import app

REQUIRED_EXTENSIONS = {"pgcrypto", "postgis", "uuid-ossp", "vector"}


# ========================================================================== #
# Settings & database metadata
# ========================================================================== #

def test_settings_singleton_and_defaults():
    s = get_settings()
    assert isinstance(s, Settings)
    assert s.APP_ENV in ("development", "test", "staging", "production")
    assert "postgresql" in s.DATABASE_URL
    assert "redis" in s.REDIS_URL
    assert s.S3_BUCKET_NAME == "civicpulse-media"
    assert isinstance(s.CORS_ORIGINS, list)
    assert len(s.CORS_ORIGINS) >= 2
    assert get_settings() is s


def test_settings_cors_parsing_variants():
    assert Settings(CORS_ORIGINS="http://a, http://b").CORS_ORIGINS == [
        "http://a",
        "http://b",
    ]
    assert Settings(CORS_ORIGINS='["http://a","http://b"]').CORS_ORIGINS == [
        "http://a",
        "http://b",
    ]
    assert Settings(CORS_ORIGINS=["http://a"]).CORS_ORIGINS == ["http://a"]


def test_database_naming_convention():
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert NAMING_CONVENTION["pk"] == "pk_%(table_name)s"
    assert NAMING_CONVENTION["fk"] == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    assert NAMING_CONVENTION["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert NAMING_CONVENTION["ix"] == "ix_%(column_0_label)s"


# ========================================================================== #
# Password hashing
# ========================================================================== #

def test_security_argon2_password():
    password = "SecureCivicPass!2026"
    hashed = hash_password(password)

    assert hashed != password
    assert password not in hashed
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("IncorrectPass", hashed) is False
    assert verify_password("", hashed) is False

    # Argon2 salts every hash, so identical passwords produce different hashes.
    assert hash_password(password) != hashed


# ========================================================================== #
# JWT access tokens
# ========================================================================== #

def test_security_jwt_token_flow():
    user_id = str(uuid.uuid4())
    token = create_access_token(
        subject=user_id,
        role="OFFICER",
        expires_delta=timedelta(minutes=30),
    )
    claims = decode_access_token(token)

    assert claims["sub"] == user_id
    assert claims["role"] == "OFFICER"
    assert "exp" in claims
    assert "iat" in claims


def test_security_jwt_rejects_expired_token():
    token = create_access_token(
        subject=str(uuid.uuid4()),
        role="CITIZEN",
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_security_jwt_rejects_malformed_token():
    with pytest.raises(JWTError):
        decode_access_token("not-a-valid-jwt")


def test_security_jwt_rejects_wrong_or_missing_signing_configuration(monkeypatch):
    token = create_access_token(subject=str(uuid.uuid4()), role="ADMIN")

    monkeypatch.setattr(
        security,
        "_settings",
        SimpleNamespace(
            JWT_SECRET_KEY="incorrect-secret",
            JWT_ALGORITHM="HS256",
            ACCESS_TOKEN_EXPIRE_MINUTES=60,
        ),
    )
    with pytest.raises(JWTError):
        decode_access_token(token)

    monkeypatch.setattr(
        security,
        "_settings",
        SimpleNamespace(
            JWT_SECRET_KEY=" ",
            JWT_ALGORITHM="HS256",
            ACCESS_TOKEN_EXPIRE_MINUTES=60,
        ),
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


# ========================================================================== #
# PII encryption
# ========================================================================== #

def test_security_pii_vault_aes_gcm():
    pii = {
        "aadhaar": "1234-5678-9012",
        "mobile": "+91-9876543210",
        "home_address": "Flat 402, Lotus Apartments, New Delhi",
    }
    encrypted = encrypt_pii_dict(pii)

    assert isinstance(encrypted, bytes)
    assert len(encrypted) > 28  # 12-byte nonce + ciphertext + 16-byte tag
    assert b"aadhaar" not in encrypted
    assert decrypt_pii_dict(encrypted) == pii


def test_security_pii_rejects_truncated_and_tampered_ciphertext():
    encrypted = encrypt_pii_dict({"mobile": "+91-9876543210"})

    for bad_blob in (
        b"",
        b"short",
        encrypted[:-1],
        encrypted[:12] + b"\x00" * (len(encrypted) - 12),
    ):
        with pytest.raises(AppException) as exc_info:
            decrypt_pii_dict(bad_blob)
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "DECIPHER_ERROR"
        assert exc_info.value.message == "Invalid encrypted payload"


def test_security_pii_key_has_controlled_fallback():
    valid_key = _decode_pii_key(get_settings().PII_ENCRYPTION_KEY)
    assert len(valid_key) == 32

    for invalid_key in ("", "not-valid-base64!!", "c2hvcnQ="):
        derived = _decode_pii_key(invalid_key)
        assert len(derived) == 32
        assert derived == _decode_pii_key(invalid_key)


# ========================================================================== #
# API envelopes, pagination & exception classes
# ========================================================================== #

def test_api_envelope_serialisation_and_optional_fields():
    envelope = ApiEnvelope[dict](data={"key": "value"})
    dumped = envelope.model_dump()

    assert dumped == {
        "success": True,
        "data": {"key": "value"},
        "meta": None,
    }
    assert "meta" not in envelope.model_dump(exclude_none=True)

    meta = PaginatedMeta.build(page=2, page_size=15, total_items=50)
    paginated = ApiEnvelope[dict](data={"key": "value"}, meta=meta)
    assert paginated.success is True
    assert paginated.meta is not None
    assert paginated.meta.total_pages == 4


def test_pagination_params():
    params = PaginationParams(page=3, page_size=20)
    assert params.offset == 40
    assert params.limit == 20


def test_exception_classes():
    e1 = NotFoundException("Citizen record missing", code="CITIZEN_NOT_FOUND")
    assert e1.status_code == 404
    assert e1.code == "CITIZEN_NOT_FOUND"

    e2 = UnauthorizedException()
    assert e2.status_code == 401
    assert e2.code == "UNAUTHORIZED"

    e3 = ForbiddenException()
    assert e3.status_code == 403
    assert e3.code == "FORBIDDEN"

    e4 = ValidationException(field_errors={"email": "Invalid format"})
    assert e4.status_code == 422
    assert "email" in e4.field_errors

    e5 = ConflictException()
    assert e5.status_code == 409
    assert e5.code == "CONFLICT"


def _build_exception_test_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/app-error")
    async def _app_error() -> None:
        raise AppException(
            status_code=418,
            code="TEAPOT",
            message="Short and stout.",
            field_errors={"teapot": "invalid"},
        )

    @test_app.get("/unexpected")
    async def _unexpected() -> None:
        raise RuntimeError("sensitive internal detail")

    return test_app


async def _get(app_under_test: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(
        app=app_under_test,
        raise_app_exceptions=False,
    )
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        return await test_client.get(path)


async def test_app_exception_handler_envelope():
    response = await _get(_build_exception_test_app(), "/app-error")
    body = response.json()

    assert response.status_code == 418
    assert body["success"] is False
    assert body["error"]["code"] == "TEAPOT"
    assert body["error"]["message"] == "Short and stout."
    assert body["error"]["field_errors"] == {"teapot": "invalid"}
    assert "request_id" in body["error"]


async def test_unexpected_exception_handler_hides_internals():
    response = await _get(_build_exception_test_app(), "/unexpected")
    body = response.json()

    assert response.status_code == 500
    assert body["success"] is False
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "sensitive internal detail" not in response.text
    assert "Traceback" not in response.text


# ========================================================================== #
# Mocked API tests (no external services)
# ========================================================================== #

async def test_api_request_id_middleware(client: httpx.AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers


async def test_api_custom_404_envelope(client: httpx.AsyncClient):
    resp = await client.get("/api/v1/non-existent-endpoint-12345")
    body = resp.json()

    assert resp.status_code == 404
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]


async def _healthy_database() -> dict[str, object]:
    return {"database": "connected", "extensions": sorted(REQUIRED_EXTENSIONS)}


async def _healthy_redis() -> dict[str, str]:
    return {"status": "ok", "ping": "True"}


async def _healthy_s3() -> dict[str, object]:
    return {"status": "ok", "bucket": get_settings().S3_BUCKET_NAME}


def _patch_health_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    database=_healthy_database,
    redis=_healthy_redis,
    s3=_healthy_s3,
) -> None:
    monkeypatch.setattr(
        main_module,
        "verify_db_connection_and_extensions",
        database,
    )
    monkeypatch.setattr(main_module, "redis_health_check", redis)
    monkeypatch.setattr(main_module.storage_service, "health_check", s3)


async def test_health_endpoint_reports_healthy_services(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_health_dependencies(monkeypatch)

    resp = await client.get("/health")
    body = resp.json()

    assert resp.status_code == 200
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
    services = body["data"]["services"]
    assert services["database"]["status"] == "ok"
    assert services["database"]["database"] == "connected"
    assert set(services["database"]["extensions"]) == REQUIRED_EXTENSIONS
    assert services["redis"]["status"] == "ok"
    assert services["s3"]["status"] == "ok"
    assert body["meta"] is None


async def test_health_endpoint_never_reports_degraded_database_as_healthy(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def _degraded_database() -> dict[str, object]:
        return {"database": "degraded (DBAPIError)", "extensions": []}

    async def _error_redis() -> dict[str, str]:
        return {"status": "error", "detail": "ConnectionError"}

    async def _error_s3() -> dict[str, object]:
        return {"status": "error", "bucket": "civicpulse-media", "detail": "EndpointConnectionError"}

    _patch_health_dependencies(
        monkeypatch,
        database=_degraded_database,
        redis=_error_redis,
        s3=_error_s3,
    )

    resp = await client.get("/health")
    body = resp.json()

    assert resp.status_code == 200
    assert body["data"]["status"] == "degraded"
    services = body["data"]["services"]
    assert services["database"]["status"] == "error"
    assert services["database"]["database"].startswith("degraded")
    assert services["redis"]["status"] == "error"
    assert services["s3"]["status"] == "error"


async def test_health_endpoint_survives_raising_dependency_probes(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def _raise() -> None:
        raise RuntimeError("service unavailable")

    _patch_health_dependencies(
        monkeypatch,
        database=_raise,
        redis=_raise,
        s3=_raise,
    )

    resp = await client.get("/health")
    body = resp.json()

    assert resp.status_code == 200
    assert body["data"]["status"] == "degraded"
    services = body["data"]["services"]
    assert services["database"]["status"] == "error"
    assert services["redis"]["status"] == "error"
    assert services["s3"]["status"] == "error"


async def test_storage_health_check_handles_connection_errors(monkeypatch):
    class FailingS3Client:
        def head_bucket(self, **kwargs):
            raise BotoCoreError()

    monkeypatch.setattr(storage_service, "_client", FailingS3Client())

    result = await storage_service.health_check()

    assert result["status"] == "error"
    assert result["bucket"] == get_settings().S3_BUCKET_NAME
    assert result["detail"] == "BotoCoreError"


def test_rbac_require_roles_dependency():
    officer_context = CurrentUserContext(
        id=uuid.uuid4(),
        email="officer@civicpulse.gov",
        role="OFFICER",
        preferred_language="hi",
    )
    admin_checker = require_roles(["ADMIN", "OFFICER"])
    assert callable(admin_checker)
    assert officer_context.role == "OFFICER"


# ========================================================================== #
# Live infrastructure integration (skipped when services are unavailable)
# ========================================================================== #

def _host_port(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname or "localhost", parsed.port or default_port


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.mark.integration
async def test_live_postgres_connection_and_extensions():
    settings = get_settings()
    host, port = _host_port(settings.DATABASE_URL, 5432)
    if not _port_open(host, port):
        pytest.skip(f"PostgreSQL not reachable at {host}:{port}")

    try:
        result = await asyncio.wait_for(
            verify_db_connection_and_extensions(),
            timeout=10,
        )
    except asyncio.TimeoutError:
        pytest.skip(f"PostgreSQL connection timed out at {host}:{port}")

    if result["database"] != "connected":
        pytest.skip(
            f"PostgreSQL reachable but not usable ({result['database']})"
        )

    assert REQUIRED_EXTENSIONS.issubset(set(result["extensions"]))


@pytest.mark.integration
async def test_live_redis_read_write():
    settings = get_settings()
    host, port = _host_port(settings.REDIS_URL, 6379)
    if not _port_open(host, port):
        pytest.skip(f"Redis not reachable at {host}:{port}")

    try:
        await asyncio.wait_for(redis_client.ping(), timeout=3)
    except Exception as exc:
        pytest.skip(f"Redis ping failed ({type(exc).__name__})")

    key = f"civicpulse:test:{uuid.uuid4().hex}"
    try:
        await asyncio.wait_for(redis_client.set(key, "ok", ex=30), timeout=3)
        value = await asyncio.wait_for(redis_client.get(key), timeout=3)
        assert value == "ok"
    finally:
        await asyncio.wait_for(redis_client.delete(key), timeout=3)


@pytest.mark.integration
async def test_live_minio_bucket_accessibility():
    settings = get_settings()
    host, port = _host_port(settings.S3_ENDPOINT_URL, 9000)
    if not _port_open(host, port):
        pytest.skip(f"MinIO/S3 not reachable at {host}:{port}")

    try:
        await asyncio.wait_for(storage_service.ensure_bucket_exists(), timeout=15)
        result = await asyncio.wait_for(storage_service.health_check(), timeout=10)
    except Exception as exc:
        pytest.skip(f"MinIO/S3 check failed ({type(exc).__name__})")

    # ensure_bucket_exists() falls back to local disk when S3 is unreachable;
    # a live-connectivity test must not pass on that fallback.
    if storage_service.using_local_fallback or result.get("backend") == "local":
        pytest.skip("MinIO/S3 unreachable — StorageService is using local fallback")

    if result.get("status") != "ok":
        pytest.skip(f"MinIO/S3 bucket not accessible ({result})")

    assert result["backend"] == "s3"
    assert result["bucket"] == settings.S3_BUCKET_NAME
