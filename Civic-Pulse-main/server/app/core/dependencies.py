"""Civic Pulse — FastAPI shared dependencies.

Contains:
    * ``get_db()`` — yields an ``AsyncSession``
    * ``CurrentUserContext`` — Pydantic model for the authenticated user
    * ``get_current_user()`` — decodes JWT and resolves the user record
    * ``require_roles()`` — RBAC dependency factory
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator
from uuid import UUID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_access_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OAuth2 bearer scheme used by FastAPI's dependency injection and auto-docs
# ---------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ---------------------------------------------------------------------------
# Database session dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a scoped ``AsyncSession``, committing on success and rolling back
    on error.  Used as ``db: AsyncSession = Depends(get_db)`` in router
    signatures.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Authenticated user context
# ---------------------------------------------------------------------------

class CurrentUserContext(BaseModel):
    """Minimal identity payload extracted from the JWT and (optionally)
    enriched from the database.

    Passed as a dependency to any endpoint that requires authentication.
    """

    id: UUID
    email: str = ""
    role: str = "CITIZEN"
    preferred_language: str = Field(default="en", description="ISO 639-1 code")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUserContext:
    """Decode the JWT, optionally verify the user in the database, and return
    a :class:`CurrentUserContext`.

    Fallback behaviour:
        If the ``identity`` domain's ``User`` model is not yet available (i.e.
        Person 2 hasn't implemented it), the dependency gracefully falls back
        to the validated JWT claims so that early integration testing works
        without the identity tables being in place.

    Raises
    ------
    UnauthorizedException
        If the token is invalid, expired, or the user is inactive.
    """
    try:
        claims = decode_access_token(token)
    except JWTError:
        raise UnauthorizedException(message="Invalid or expired access token.")

    subject: str | None = claims.get("sub")
    role: str = claims.get("role", "CITIZEN")

    if not subject:
        raise UnauthorizedException(message="Token is missing a subject claim.")

    try:
        user_id = UUID(subject)
    except ValueError:
        raise UnauthorizedException(message="Token subject is not a valid UUID.")

    # ---- Attempt DB lookup (soft-fail if the model isn't created yet) ---- #
    email = ""
    preferred_language = "en"

    try:
        from app.domains.identity.models import User  # type: ignore[import-untyped]

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            raise UnauthorizedException(message="User account not found.")

        if hasattr(user, "is_active") and not user.is_active:
            raise UnauthorizedException(message="User account is deactivated.")

        email = getattr(user, "email", "")
        role = getattr(user, "role", role)
        preferred_language = getattr(user, "preferred_language", "en")

    except ImportError:
        # Identity module not wired yet — fall back to JWT claims
        logger.debug(
            "identity.models.User not available; using JWT claims for user %s",
            user_id,
        )

    return CurrentUserContext(
        id=user_id,
        email=email,
        role=role,
        preferred_language=preferred_language,
    )


# ---------------------------------------------------------------------------
# Role-based access control dependency factory
# ---------------------------------------------------------------------------

def require_roles(allowed_roles: list[str]):
    """Return a FastAPI dependency that raises :class:`ForbiddenException`
    unless the authenticated user's role is in *allowed_roles*.

    Usage::

        @router.post("/admin/action")
        async def admin_action(
            user: CurrentUserContext = Depends(require_roles(["ADMIN", "OFFICER"])),
        ):
            ...
    """

    async def _check_role(
        user: CurrentUserContext = Depends(get_current_user),
    ) -> CurrentUserContext:
        if user.role not in allowed_roles:
            raise ForbiddenException(
                message=(
                    f"Role '{user.role}' is not authorised. "
                    f"Required: {', '.join(allowed_roles)}."
                ),
            )
        return user

    return _check_role

