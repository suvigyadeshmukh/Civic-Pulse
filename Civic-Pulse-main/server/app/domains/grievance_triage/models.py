"""Grievance Triage domain ORM models.

A ticket captures the AI-triaged citizen report (including its PostGIS point),
while timeline events record the auditable status history and resolution proof.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GrievanceTicket(Base):
    """A citizen grievance after AI triage, routing, and SLA assignment."""

    __tablename__ = "grievance_tickets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    voice_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    address_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    severity_score: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_triage_summary: Mapped[str] = mapped_column(Text, nullable=False)
    routed_department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id"), index=True, nullable=False
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("grievance_tickets.id", ondelete="SET NULL"), nullable=True
    )
    upvote_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, default="TRIAGED", nullable=False)
    sla_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_proof_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class GrievanceTimelineEvent(Base):
    """An auditable status change or resolution note on a grievance."""

    __tablename__ = "grievance_timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("grievance_tickets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    remarks: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    proof_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
