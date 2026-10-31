"""Policy Explainer domain ORM models.

Stores ingested government documents, their embeddable clause chunks, and
multilingual voice explainer runs generated for citizens.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PolicyDocument(Base):
    """A government notification, welfare scheme, or municipal law."""

    __tablename__ = "policy_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reference_code: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    issuing_body: Mapped[str] = mapped_column(String(200), nullable=False)
    target_group: Mapped[str] = mapped_column(String(50), default="CITIZEN", nullable=False)
    source_pdf_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="INDEXED", nullable=False)
    clause_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PolicyClauseChunk(Base):
    """A retrieval-ready chunk of a policy document with its embedding."""

    __tablename__ = "policy_clause_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    clause_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)


class PolicyVoiceExplainer(Base):
    """A multilingual plain-language / voice explanation of a policy."""

    __tablename__ = "policy_voice_explainers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    language_code: Mapped[str] = mapped_column(String(15), nullable=False)
    persona_type: Mapped[str] = mapped_column(String(30), default="CITIZEN", nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(30), nullable=False)
    plain_language_summary: Mapped[str] = mapped_column(Text, nullable=False)
    rights_and_benefits: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    eligibility_evaluation: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    real_world_impacts: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    audio_explainer_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_duration_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
