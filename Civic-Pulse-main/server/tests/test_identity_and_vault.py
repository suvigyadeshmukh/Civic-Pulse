"""Identity, authentication, and encrypted Citizen Vault tests.

The suite has three layers:

1. Offline service tests using a small in-memory fake ``AsyncSession``.
2. Offline HTTP tests with FastAPI dependency overrides and a mocked service.
3. Live PostgreSQL integration tests marked ``integration`` that skip when
   PostgreSQL is unreachable.

SQLite is deliberately not used: ``JSONB``, ``Vector(1536)``, and PostGIS
``Geography`` are PostgreSQL-only types, so the offline layer mocks the session
while the live layer exercises the real schema.
"""

from __future__ import annotations

import asyncio
import socket
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text

import app.domains.grievance_triage.models  # noqa: F401
import app.domains.identity.router as identity_router
import app.domains.policy_explainer.models  # noqa: F401
from app.core.database import AsyncSessionLocal, Base, engine, verify_db_connection_and_extensions
from app.core.dependencies import (
    CurrentUserContext,
    get_current_user,
    get_db,
)
from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_pii_dict,
    encrypt_pii_dict,
    hash_password,
)
from app.core.settings import get_settings
from app.domains.identity.models import CitizenVault, User
from app.domains.identity.schemas import (
    AuthResponseDto,
    CitizenVaultResponseDto,
    CitizenVaultUpsertRequest,
    DepartmentDto,
    LoginRequest,
    PiiSecretPayload,
    PublicProfilePayload,
    RegisterRequest,
    UserDto,
)
from app.domains.identity.service import IdentityService
from app.main import app

REQUIRED_EXTENSIONS = {"pgcrypto", "postgis", "uuid-ossp", "vector"}


# ========================================================================== #
# Fake async session for offline service tests
# ========================================================================== #


class _FakeResult:
    """Minimal stand-in for SQLAlchemy's ``Result``."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if self._value is None:
            return []
        if isinstance(self._value, list):
            return list(self._value)
        return [self._value]


class FakeAsyncSession:
    """Queue-driven fake session sufficient for IdentityService tests."""

    def __init__(self, results: list | None = None) -> None:
        self._results = list(results or [])
        self.added: list = []
        self.committed = False
        self.rolled_back = False
        self.refreshed: list = []

    async def execute(self, statement):
        if not self._results:
            raise AssertionError(f"Unexpected execute() call: {statement!r}")
        return _FakeResult(self._results.pop(0))

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        for instance in self.added:
            if getattr(instance, "id", None) is None:
                instance.id = uuid.uuid4()
            if hasattr(instance, "updated_at") and instance.updated_at is None:
                instance.updated_at = datetime.now(UTC)
            if hasattr(instance, "created_at") and instance.created_at is None:
                instance.created_at = datetime.now(UTC)

    async def commit(self) -> None:
        await self.flush()
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, instance) -> None:
        if getattr(instance, "id", None) is None:
            instance.id = uuid.uuid4()
        if hasattr(instance, "updated_at") and instance.updated_at is None:
            instance.updated_at = datetime.now(UTC)
        if hasattr(instance, "created_at") and instance.created_at is None:
            instance.created_at = datetime.now(UTC)
        self.refreshed.append(instance)


@pytest.fixture
def service() -> IdentityService:
    return IdentityService()


# ========================================================================== #
# Schema contracts
# ========================================================================== #


def test_identity_schemas_validate_roles_and_password_length():
    request = RegisterRequest(
        email="Citizen@Example.com",
        password="LongEnough1",
        full_name="Demo Citizen",
    )
    assert request.role == "CITIZEN"
    assert request.preferred_language == "hi-IN"

    with pytest.raises(ValidationError):
        RegisterRequest(
            email="citizen@example.com",
            password="short",
            full_name="Demo Citizen",
        )

    with pytest.raises(ValidationError):
        RegisterRequest(
            email="citizen@example.com",
            password="LongEnough1",
            full_name="Demo Citizen",
            role="MAYOR",
        )


# ========================================================================== #
# Service tests — registration and authentication
# ========================================================================== #


async def test_register_user_hashes_password_and_issues_jwt(service):
    db = FakeAsyncSession([None])  # no existing email

    result = await service.register_user(
        db,
        RegisterRequest(
            email="  Citizen@Example.COM ",
            password="SecurePass123",
            full_name="  Demo Citizen  ",
        ),
    )

    assert db.committed is True
    assert len(db.added) == 1
    user = db.added[0]
    assert user.email == "citizen@example.com"
    assert user.full_name == "Demo Citizen"
    assert user.password_hash != "SecurePass123"
    assert user.password_hash.startswith("$argon2id$")
    assert user.is_active is True

    claims = decode_access_token(result.access_token)
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "CITIZEN"
    assert result.token_type == "bearer"
    assert result.user.email == "citizen@example.com"


async def test_register_user_can_assign_department(service):
    department_id = uuid.uuid4()
    db = FakeAsyncSession([None, SimpleNamespace(id=department_id)])

    result = await service.register_user(
        db,
        RegisterRequest(
            email="officer@example.com",
            password="SecurePass123",
            full_name="Officer",
            role="OFFICER",
            department_code="pwd_roads",
        ),
    )

    assert db.added[0].department_id == department_id
    assert result.user.role == "OFFICER"
    assert result.user.department_id == department_id


async def test_register_user_duplicate_email_raises_conflict(service):
    db = FakeAsyncSession([SimpleNamespace(id=uuid.uuid4())])

    with pytest.raises(ConflictException) as exc_info:
        await service.register_user(
            db,
            RegisterRequest(
                email="citizen@example.com",
                password="SecurePass123",
                full_name="Demo Citizen",
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "EMAIL_ALREADY_EXISTS"
    assert db.added == []


async def test_register_user_unknown_department_raises_validation(service):
    db = FakeAsyncSession([None, None])

    with pytest.raises(ValidationException) as exc_info:
        await service.register_user(
            db,
            RegisterRequest(
                email="officer@example.com",
                password="SecurePass123",
                full_name="Officer",
                role="OFFICER",
                department_code="DOES_NOT_EXIST",
            ),
        )

    assert exc_info.value.code == "INVALID_DEPARTMENT_CODE"


def _build_user(email: str = "citizen@example.com", *, active: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("SecurePass123"),
        full_name="Demo Citizen",
        role="CITIZEN",
        preferred_language="hi-IN",
        is_active=active,
    )


async def test_authenticate_user_success_and_failure(service):
    user = _build_user()

    db = FakeAsyncSession([user])
    result = await service.authenticate_user(
        db,
        LoginRequest(email="  CITIZEN@example.com ", password="SecurePass123"),
    )
    assert result.access_token
    assert result.user.id == user.id

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.authenticate_user(
            FakeAsyncSession([user]),
            LoginRequest(email=user.email, password="WrongPassword"),
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_CREDENTIALS"

    inactive = _build_user(active=False)
    with pytest.raises(UnauthorizedException):
        await service.authenticate_user(
            FakeAsyncSession([inactive]),
            LoginRequest(email=inactive.email, password="SecurePass123"),
        )


async def test_get_user_by_id_returns_dto_or_404(service):
    user = _build_user()
    dto = await service.get_user_by_id(FakeAsyncSession([user]), user.id)
    assert dto.id == user.id
    assert dto.email == user.email

    with pytest.raises(NotFoundException) as exc_info:
        await service.get_user_by_id(FakeAsyncSession([None]), uuid.uuid4())
    assert exc_info.value.code == "USER_NOT_FOUND"


# ========================================================================== #
# Service tests — encrypted Citizen Vault
# ========================================================================== #


async def test_upsert_vault_encrypts_pii_at_rest(service):
    db = FakeAsyncSession([None])
    user_id = uuid.uuid4()
    payload = CitizenVaultUpsertRequest(
        pii_secret=PiiSecretPayload(
            national_id="1234-5678-9012",
            dob="1990-01-01",
            bank_iban="IN00DEMO000000000000",
            phone_number="+91-9000000000",
            portal_pin="1234",
        ),
        public_profile=PublicProfilePayload(
            state="Madhya Pradesh",
            annual_income=240000.0,
            occupation="Small Business Owner",
            category="OBC",
            is_msme=True,
            education_level="Graduate",
        ),
        document_urls=["https://example.com/id.pdf"],
    )

    response = await service.upsert_citizen_vault(db, user_id, payload)

    assert db.committed is True
    assert len(db.added) == 1
    vault = db.added[0]
    assert isinstance(vault, CitizenVault)
    assert vault.user_id == user_id
    assert b"1234-5678-9012" not in vault.encrypted_pii_blob

    decrypted = decrypt_pii_dict(vault.encrypted_pii_blob)
    assert decrypted["national_id"] == "1234-5678-9012"
    assert decrypted["bank_iban"] == "IN00DEMO000000000000"

    assert response.pii_secret.national_id == "1234-5678-9012"
    assert response.public_profile.state == "Madhya Pradesh"
    assert response.document_urls == ["https://example.com/id.pdf"]
    assert response.vault_id == vault.id


async def test_get_vault_auto_creates_default_for_first_time_user(service):
    db = FakeAsyncSession([None])
    user_id = uuid.uuid4()

    response = await service.get_decrypted_vault(db, user_id)

    assert db.committed is True
    assert len(db.added) == 1
    vault = db.added[0]
    assert isinstance(vault, CitizenVault)
    assert vault.user_id == user_id

    assert response.vault_id == vault.id
    assert response.pii_secret.national_id == ""
    assert response.public_profile.state == "Madhya Pradesh"
    assert response.document_urls == []


async def test_get_vault_decrypts_existing_record(service):
    user_id = uuid.uuid4()
    vault = CitizenVault(
        id=uuid.uuid4(),
        user_id=user_id,
        encrypted_pii_blob=encrypt_pii_dict({"national_id": "MP-9999"}),
        public_profile={"state": "Madhya Pradesh", "annual_income": 100000.0},
        document_urls=["https://example.com/doc.pdf"],
        updated_at=datetime.now(UTC),
    )

    response = await service.get_decrypted_vault(
        FakeAsyncSession([vault]),
        user_id,
    )

    assert response.vault_id == vault.id
    assert response.pii_secret.national_id == "MP-9999"
    assert response.public_profile.annual_income == 100000.0
    assert response.document_urls == ["https://example.com/doc.pdf"]


async def test_list_departments_returns_dtos_in_code_order(service):
    departments = [
        SimpleNamespace(
            id=uuid.uuid4(),
            code="PWD_ROADS",
            name="Public Works Department",
            categories_handled=["ROADS"],
            sla_hours_critical=4,
            sla_hours_high=24,
            sla_hours_medium=72,
            sla_hours_low=168,
            contact_email="pwd@civicpulse.gov.in",
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            code="SANITATION_WASTE",
            name="Sanitation & Waste Management",
            categories_handled=["GARBAGE"],
            sla_hours_critical=4,
            sla_hours_high=24,
            sla_hours_medium=72,
            sla_hours_low=168,
            contact_email="sanitation@civicpulse.gov.in",
        ),
    ]

    result = await service.list_departments(FakeAsyncSession([departments]))

    assert [dto.code for dto in result] == ["PWD_ROADS", "SANITATION_WASTE"]
    assert all(isinstance(dto, DepartmentDto) for dto in result)


# ========================================================================== #
# Offline HTTP tests — dependency overrides + mocked service
# ========================================================================== #


@pytest.fixture
def api_overrides():
    """Save and restore FastAPI dependency overrides around each test."""
    saved = dict(app.dependency_overrides)
    yield app.dependency_overrides
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _install_db_override(overrides: dict) -> None:
    async def _override_db():
        yield FakeAsyncSession()

    overrides[get_db] = _override_db


def _build_auth_dto(
    *,
    role: str = "CITIZEN",
    email: str = "citizen@example.com",
) -> AuthResponseDto:
    user = UserDto(
        id=uuid.uuid4(),
        email=email,
        full_name="Demo Citizen",
        role=role,
        preferred_language="hi-IN",
        department_id=None,
    )
    return AuthResponseDto(
        access_token=create_access_token(subject=str(user.id), role=role),
        user=user,
    )


def _build_vault_dto(user_id: uuid.UUID) -> CitizenVaultResponseDto:
    return CitizenVaultResponseDto(
        vault_id=uuid.uuid4(),
        user_id=user_id,
        pii_secret=PiiSecretPayload(national_id="MP-1234"),
        public_profile=PublicProfilePayload(state="Madhya Pradesh"),
        document_urls=["https://example.com/id.pdf"],
        updated_at=datetime.now(UTC),
    )


async def test_api_register_returns_201_and_jwt(client, monkeypatch, api_overrides):
    _install_db_override(api_overrides)
    auth_dto = _build_auth_dto()
    monkeypatch.setattr(
        identity_router._service,
        "register_user",
        AsyncMock(return_value=auth_dto),
    )

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "citizen@example.com",
            "password": "SecurePass123",
            "full_name": "Demo Citizen",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["access_token"] == auth_dto.access_token
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["user"]["email"] == "citizen@example.com"


async def test_api_duplicate_registration_returns_409(client, monkeypatch, api_overrides):
    _install_db_override(api_overrides)
    monkeypatch.setattr(
        identity_router._service,
        "register_user",
        AsyncMock(
            side_effect=ConflictException(
                code="EMAIL_ALREADY_EXISTS",
                message="An account with this email already exists.",
            )
        ),
    )

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "citizen@example.com",
            "password": "SecurePass123",
            "full_name": "Demo Citizen",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "EMAIL_ALREADY_EXISTS"


async def test_api_login_success_and_wrong_password(client, monkeypatch, api_overrides):
    _install_db_override(api_overrides)
    auth_dto = _build_auth_dto()
    monkeypatch.setattr(
        identity_router._service,
        "authenticate_user",
        AsyncMock(return_value=auth_dto),
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "citizen@example.com", "password": "SecurePass123"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["access_token"] == auth_dto.access_token

    monkeypatch.setattr(
        identity_router._service,
        "authenticate_user",
        AsyncMock(
            side_effect=UnauthorizedException(
                code="INVALID_CREDENTIALS",
                message="Invalid email or password.",
            )
        ),
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "citizen@example.com", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_api_me_returns_authenticated_profile(client, monkeypatch, api_overrides):
    user_id = uuid.uuid4()
    _install_db_override(api_overrides)
    api_overrides[get_current_user] = lambda: CurrentUserContext(
        id=user_id,
        email="citizen@example.com",
        role="CITIZEN",
        preferred_language="hi-IN",
    )
    user_dto = UserDto(
        id=user_id,
        email="citizen@example.com",
        full_name="Demo Citizen",
        role="CITIZEN",
        preferred_language="hi-IN",
    )
    monkeypatch.setattr(
        identity_router._service,
        "get_user_by_id",
        AsyncMock(return_value=user_dto),
    )

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == str(user_id)
    assert body["data"]["full_name"] == "Demo Citizen"


async def test_api_vault_put_and_get(client, monkeypatch, api_overrides):
    user_id = uuid.uuid4()
    _install_db_override(api_overrides)
    api_overrides[get_current_user] = lambda: CurrentUserContext(
        id=user_id,
        email="citizen@example.com",
        role="CITIZEN",
        preferred_language="hi-IN",
    )
    vault_dto = _build_vault_dto(user_id)
    put_mock = AsyncMock(return_value=vault_dto)
    get_mock = AsyncMock(return_value=vault_dto)
    monkeypatch.setattr(identity_router._service, "upsert_citizen_vault", put_mock)
    monkeypatch.setattr(identity_router._service, "get_decrypted_vault", get_mock)

    payload = {
        "pii_secret": {"national_id": "MP-1234"},
        "public_profile": {"state": "Madhya Pradesh"},
        "document_urls": ["https://example.com/id.pdf"],
    }
    headers = {"Authorization": "Bearer test-token"}

    response = await client.put("/api/v1/profile/vault", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["pii_secret"]["national_id"] == "MP-1234"

    response = await client.get("/api/v1/profile/vault", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["document_urls"] == ["https://example.com/id.pdf"]

    put_mock.assert_awaited_once()
    get_mock.assert_awaited_once()


async def test_api_departments_returns_list(client, monkeypatch, api_overrides):
    _install_db_override(api_overrides)
    department_dto = DepartmentDto(
        id=uuid.uuid4(),
        code="PWD_ROADS",
        name="Public Works Department",
        categories_handled=["ROADS"],
        sla_hours_critical=4,
        sla_hours_high=24,
        sla_hours_medium=72,
        sla_hours_low=168,
        contact_email="pwd@civicpulse.gov.in",
    )
    monkeypatch.setattr(
        identity_router._service,
        "list_departments",
        AsyncMock(return_value=[department_dto]),
    )

    response = await client.get("/api/v1/departments")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["code"] == "PWD_ROADS"


# ========================================================================== #
# Live PostgreSQL integration
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


@pytest.fixture
async def live_database():
    """Ensure PostgreSQL is reachable, extensions exist, and tables are created."""
    settings = get_settings()
    host, port = _host_port(settings.DATABASE_URL, 5432)
    if not _port_open(host, port):
        pytest.skip(f"PostgreSQL not reachable at {host}:{port}")

    # pytest-asyncio uses a fresh event loop per test. The application engine is
    # a process-global pool, so connections cached by a previous test's loop
    # must be discarded before probing from the current loop.
    await engine.dispose()

    try:
        info = await asyncio.wait_for(
            verify_db_connection_and_extensions(),
            timeout=20,
        )
    except Exception as exc:
        pytest.skip(f"PostgreSQL verification failed ({type(exc).__name__})")

    if info.get("database") != "connected":
        pytest.skip(f"PostgreSQL not usable ({info.get('database')})")

    if not REQUIRED_EXTENSIONS.issubset(set(info.get("extensions", []))):
        pytest.skip(
            "Required PostgreSQL extensions missing: "
            f"{sorted(REQUIRED_EXTENSIONS - set(info.get('extensions', [])))}"
        )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


@pytest.mark.integration
async def test_live_identity_and_vault_flow(client, live_database):
    email = f"pytest_{uuid.uuid4().hex}@civicpulse.gov.in"
    password = "PytestPass123!"
    national_id = "1234-5678-9012"

    register_payload = {
        "email": email,
        "password": password,
        "full_name": "Pytest Citizen",
        "preferred_language": "hi-IN",
    }

    try:
        # 1. Register
        response = await client.post("/api/v1/auth/register", json=register_payload)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["success"] is True
        token = body["data"]["access_token"]
        user_id = body["data"]["user"]["id"]
        assert body["data"]["user"]["email"] == email

        # 2. Duplicate registration
        response = await client.post("/api/v1/auth/register", json=register_payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

        # 3. Login success + failure
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert response.status_code == 200
        token = response.json()["data"]["access_token"]

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

        headers = {"Authorization": f"Bearer {token}"}

        # 4. /auth/me
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["id"] == user_id

        # 5. PUT vault
        vault_payload = {
            "pii_secret": {
                "national_id": national_id,
                "dob": "1990-01-01",
                "bank_iban": "IN00DEMO000000000000",
                "phone_number": "+91-9000000000",
                "portal_pin": "1234",
            },
            "public_profile": {
                "state": "Madhya Pradesh",
                "annual_income": 240000.0,
                "occupation": "Small Business Owner",
                "category": "OBC",
                "is_msme": True,
                "education_level": "Graduate",
            },
            "document_urls": ["https://example.com/id.pdf"],
        }
        response = await client.put(
            "/api/v1/profile/vault",
            json=vault_payload,
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["pii_secret"]["national_id"] == national_id

        # 6. Ciphertext must not contain the plaintext national ID
        async with AsyncSessionLocal() as session:
            vault = (
                await session.execute(
                    select(CitizenVault).where(CitizenVault.user_id == uuid.UUID(user_id))
                )
            ).scalar_one()
            assert national_id.encode() not in vault.encrypted_pii_blob
            decrypted = decrypt_pii_dict(vault.encrypted_pii_blob)
            assert decrypted["national_id"] == national_id

        # 7. GET vault returns decrypted fields
        response = await client.get("/api/v1/profile/vault", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["pii_secret"]["national_id"] == national_id
        assert data["public_profile"]["state"] == "Madhya Pradesh"
        assert data["document_urls"] == ["https://example.com/id.pdf"]

        # 8. Public departments endpoint responds with an envelope
        response = await client.get("/api/v1/departments")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("DELETE FROM users WHERE email = :email"),
                {"email": email},
            )
            await session.commit()


@pytest.mark.integration
async def test_live_first_vault_read_auto_creates(client, live_database):
    email = f"pytest_{uuid.uuid4().hex}@civicpulse.gov.in"
    password = "PytestPass123!"

    try:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": "First Vault Citizen",
            },
        )
        assert response.status_code == 201, response.text
        token = response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get("/api/v1/profile/vault", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["pii_secret"]["national_id"] == ""
        assert data["public_profile"]["state"] == "Madhya Pradesh"
        assert data["document_urls"] == []
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("DELETE FROM users WHERE email = :email"),
                {"email": email},
            )
            await session.commit()
