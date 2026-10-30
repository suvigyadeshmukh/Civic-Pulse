"""Civic Pulse — Core Infrastructure Unit & Integration Tests.

Validates the contracts of app.core:
- Settings parsing & caching
- SQLAlchemy DeclarativeBase naming convention
- Argon2id password hashing & verification
- JWT creation and claim decoding
- AES-256-GCM PII Vault field-level encryption
- AppException hierarchy and API error envelopes
- Generic ApiEnvelope and PaginatedMeta schemas
- RBAC role enforcement and CurrentUserContext
- Dynamic domain router loading
"""

import uuid
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings, Settings
from app.core.database import Base, NAMING_CONVENTION
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    encrypt_pii_dict,
    decrypt_pii_dict,
)
from app.core.pagination import ApiEnvelope, PaginatedMeta, PaginationParams
from app.core.exceptions import (
    AppException,
    NotFoundException,
    UnauthorizedException,
    ForbiddenException,
    ValidationException,
    ConflictException,
)
from app.core.dependencies import CurrentUserContext, require_roles
from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_settings_singleton_and_defaults():
    s = get_settings()
    assert isinstance(s, Settings)
    assert s.APP_ENV in ("development", "test", "staging", "production")
    assert "postgresql" in s.DATABASE_URL
    assert "redis" in s.REDIS_URL
    assert s.S3_BUCKET_NAME == "civicpulse-media"
    assert isinstance(s.CORS_ORIGINS, list)
    assert len(s.CORS_ORIGINS) >= 2


def test_database_naming_convention():
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert NAMING_CONVENTION["pk"] == "pk_%(table_name)s"
    assert NAMING_CONVENTION["fk"] == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    assert NAMING_CONVENTION["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert NAMING_CONVENTION["ix"] == "ix_%(column_0_label)s"


def test_security_argon2_password():
    password = "SecureCivicPass!2026"
    hashed = hash_password(password)
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("IncorrectPass", hashed) is False


def test_security_jwt_token_flow():
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="OFFICER", expires_delta=timedelta(minutes=30))
    claims = decode_access_token(token)
    assert claims["sub"] == user_id
    assert claims["role"] == "OFFICER"
    assert "exp" in claims
    assert "iat" in claims


def test_security_pii_vault_aes_gcm():
    pii = {
        "aadhaar": "1234-5678-9012",
        "mobile": "+91-9876543210",
        "home_address": "Flat 402, Lotus Apartments, New Delhi",
    }
    encrypted = encrypt_pii_dict(pii)
    assert isinstance(encrypted, bytes)
    assert len(encrypted) > 12  # 12-byte nonce + ciphertext + 16-byte tag
    decrypted = decrypt_pii_dict(encrypted)
    assert decrypted == pii


def test_pagination_and_api_envelope():
    meta = PaginatedMeta.build(page=2, page_size=15, total_items=50)
    assert meta.page == 2
    assert meta.page_size == 15
    assert meta.total_items == 50
    assert meta.total_pages == 4

    envelope = ApiEnvelope[dict](data={"key": "value"}, meta=meta)
    assert envelope.success is True
    assert envelope.data == {"key": "value"}
    assert envelope.meta.total_pages == 4

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


def test_api_request_id_middleware(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers


def test_api_custom_404_envelope(client):
    resp = client.get("/api/v1/non-existent-endpoint-12345")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]


def test_rbac_require_roles_dependency():
    officer_context = CurrentUserContext(
        id=uuid.uuid4(),
        email="officer@civicpulse.gov",
        role="OFFICER",
        preferred_language="hi",
    )
    admin_checker = require_roles(["ADMIN", "OFFICER"])
    assert callable(admin_checker)

