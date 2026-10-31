"""Identity domain business logic.

All database access for registration, authentication, department lookup, and
the encrypted Citizen Vault lives here. Routers stay thin and only translate
service results into the shared :class:`ApiEnvelope`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import (
    create_access_token,
    decrypt_pii_dict,
    encrypt_pii_dict,
    hash_password,
    verify_password,
)
from app.domains.identity.models import CitizenVault, Department, User
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


class IdentityService:
    """Stateless service encapsulating identity and vault operations."""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalise_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _to_user_dto(user: User) -> UserDto:
        return UserDto(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            preferred_language=user.preferred_language,
            department_id=user.department_id,
        )

    @staticmethod
    def _to_department_dto(department: Department) -> DepartmentDto:
        return DepartmentDto(
            id=department.id,
            code=department.code,
            name=department.name,
            categories_handled=list(department.categories_handled or []),
            sla_hours_critical=department.sla_hours_critical,
            sla_hours_high=department.sla_hours_high,
            sla_hours_medium=department.sla_hours_medium,
            sla_hours_low=department.sla_hours_low,
            contact_email=department.contact_email,
        )

    @staticmethod
    def _to_vault_dto(vault: CitizenVault) -> CitizenVaultResponseDto:
        decrypted_pii = decrypt_pii_dict(vault.encrypted_pii_blob)
        return CitizenVaultResponseDto(
            vault_id=vault.id,
            user_id=vault.user_id,
            pii_secret=PiiSecretPayload.model_validate(decrypted_pii),
            public_profile=PublicProfilePayload.model_validate(vault.public_profile or {}),
            document_urls=list(vault.document_urls or []),
            updated_at=vault.updated_at or datetime.now(UTC),
        )

    @staticmethod
    async def _get_vault(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> CitizenVault | None:
        result = await db.execute(select(CitizenVault).where(CitizenVault.user_id == user_id))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    async def register_user(
        self,
        db: AsyncSession,
        payload: RegisterRequest,
    ) -> AuthResponseDto:
        """Create an account, hash its password, and issue an access token."""
        email = self._normalise_email(payload.email)

        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is not None:
            raise ConflictException(
                code="EMAIL_ALREADY_EXISTS",
                message="An account with this email already exists.",
            )

        department_id: uuid.UUID | None = None
        if payload.department_code:
            department = (
                await db.execute(
                    select(Department).where(
                        Department.code == payload.department_code.strip().upper()
                    )
                )
            ).scalar_one_or_none()
            if department is None:
                raise ValidationException(
                    code="INVALID_DEPARTMENT_CODE",
                    message="The requested department could not be found.",
                )
            department_id = department.id

        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name.strip(),
            role=payload.role,
            preferred_language=payload.preferred_language,
            department_id=department_id,
            is_active=True,
        )
        db.add(user)

        try:
            await db.commit()
        except IntegrityError:
            # A concurrent registration may have won the unique-email race.
            await db.rollback()
            raise ConflictException(
                code="EMAIL_ALREADY_EXISTS",
                message="An account with this email already exists.",
            )

        await db.refresh(user)
        token = create_access_token(subject=str(user.id), role=user.role)
        return AuthResponseDto(
            access_token=token,
            user=self._to_user_dto(user),
        )

    async def authenticate_user(
        self,
        db: AsyncSession,
        payload: LoginRequest,
    ) -> AuthResponseDto:
        """Validate credentials and issue an access token."""
        email = self._normalise_email(payload.email)
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

        if (
            user is None
            or not verify_password(payload.password, user.password_hash)
            or not user.is_active
        ):
            raise UnauthorizedException(
                code="INVALID_CREDENTIALS",
                message="Invalid email or password.",
            )

        token = create_access_token(subject=str(user.id), role=user.role)
        return AuthResponseDto(
            access_token=token,
            user=self._to_user_dto(user),
        )

    async def get_user_by_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> UserDto:
        """Return a user profile or raise a controlled 404."""
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise NotFoundException(
                code="USER_NOT_FOUND",
                message="User not found.",
            )
        return self._to_user_dto(user)

    # ------------------------------------------------------------------ #
    # Citizen Vault
    # ------------------------------------------------------------------ #

    async def upsert_citizen_vault(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: CitizenVaultUpsertRequest,
    ) -> CitizenVaultResponseDto:
        """Encrypt PII and create or replace the citizen's vault."""
        encrypted_blob = encrypt_pii_dict(payload.pii_secret.model_dump())
        public_profile = payload.public_profile.model_dump()
        document_urls = list(payload.document_urls)

        vault = await self._get_vault(db, user_id)
        if vault is None:
            vault = CitizenVault(
                user_id=user_id,
                encrypted_pii_blob=encrypted_blob,
                public_profile=public_profile,
                document_urls=document_urls,
            )
            db.add(vault)
        else:
            vault.encrypted_pii_blob = encrypted_blob
            vault.public_profile = public_profile
            vault.document_urls = document_urls

        try:
            await db.commit()
        except IntegrityError:
            # Concurrent first-write raced the unique user_id constraint.
            await db.rollback()
            vault = await self._get_vault(db, user_id)
            if vault is None:
                raise
            vault.encrypted_pii_blob = encrypted_blob
            vault.public_profile = public_profile
            vault.document_urls = document_urls
            await db.commit()

        await db.refresh(vault)
        return self._to_vault_dto(vault)

    async def get_decrypted_vault(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> CitizenVaultResponseDto:
        """Return the decrypted vault, auto-initialising it on first access.

        First-time users (including Playwright agent runs) must never crash on
        a missing vault, so a default encrypted vault is persisted and returned.
        """
        vault = await self._get_vault(db, user_id)
        if vault is None:
            default_pii = PiiSecretPayload()
            default_profile = PublicProfilePayload()
            vault = CitizenVault(
                user_id=user_id,
                encrypted_pii_blob=encrypt_pii_dict(default_pii.model_dump()),
                public_profile=default_profile.model_dump(),
                document_urls=[],
            )
            db.add(vault)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                vault = await self._get_vault(db, user_id)
                if vault is None:
                    raise
            await db.refresh(vault)

        return self._to_vault_dto(vault)

    # ------------------------------------------------------------------ #
    # Departments
    # ------------------------------------------------------------------ #

    async def list_departments(self, db: AsyncSession) -> list[DepartmentDto]:
        """Return every department ordered by its stable code."""
        result = await db.execute(select(Department).order_by(Department.code))
        return [self._to_department_dto(department) for department in result.scalars().all()]
