"""Identity domain ORM models.

Three tables back authentication, civic profile ownership, and the encrypted
Citizen Vault:

* ``departments`` — municipal routing targets and their SLA configuration.
* ``users`` — authenticated citizens, business owners, officers, and admins.
* ``citizen_vaults`` — AES-256-GCM encrypted PII plus a non-sensitive profile.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Department(Base):
    """A municipal department that receives routed grievances."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    categories_handled: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    sla_hours_critical: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    sla_hours_high: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    sla_hours_medium: Mapped[int] = mapped_column(Integer, default=72, nullable=False)
    sla_hours_low: Mapped[int] = mapped_column(Integer, default=168, nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    """An authenticated Civic Pulse account."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="CITIZEN", nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(15), default="hi-IN", nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CitizenVault(Base):
    """Encrypted citizen PII plus a shareable, non-sensitive public profile."""

    __tablename__ = "citizen_vaults"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    encrypted_pii_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    public_profile: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    document_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
