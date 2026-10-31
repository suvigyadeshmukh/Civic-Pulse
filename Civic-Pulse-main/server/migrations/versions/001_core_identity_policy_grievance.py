"""Core identity, policy, and grievance schema.

Creates all eight tables owned by Backend Developer A:

1. departments
2. users
3. citizen_vaults
4. policy_documents
5. policy_clause_chunks
6. policy_voice_explainers
7. grievance_tickets
8. grievance_timeline_events

Revision ID: 001
Revises: None
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_UUID = postgresql.UUID(as_uuid=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Required PostgreSQL extensions
    # ------------------------------------------------------------------ #
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "postgis"')

    # ------------------------------------------------------------------ #
    # 1. departments
    # ------------------------------------------------------------------ #
    op.create_table(
        "departments",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("categories_handled", _JSONB, nullable=False),
        sa.Column("sla_hours_critical", sa.Integer(), nullable=False),
        sa.Column("sla_hours_high", sa.Integer(), nullable=False),
        sa.Column("sla_hours_medium", sa.Integer(), nullable=False),
        sa.Column("sla_hours_low", sa.Integer(), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
    )
    op.create_index("ix_departments_code", "departments", ["code"], unique=True)

    # ------------------------------------------------------------------ #
    # 2. users
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("role", sa.String(length=30), server_default="CITIZEN", nullable=False),
        sa.Column(
            "preferred_language",
            sa.String(length=15),
            server_default="hi-IN",
            nullable=False,
        ),
        sa.Column("department_id", _UUID, nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_users_department_id_departments",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ------------------------------------------------------------------ #
    # 3. citizen_vaults
    # ------------------------------------------------------------------ #
    op.create_table(
        "citizen_vaults",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("encrypted_pii_blob", sa.LargeBinary(), nullable=False),
        sa.Column("public_profile", _JSONB, nullable=False),
        sa.Column("document_urls", _JSONB, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_citizen_vaults_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_citizen_vaults"),
    )
    op.create_index(
        "ix_citizen_vaults_user_id",
        "citizen_vaults",
        ["user_id"],
        unique=True,
    )

    # ------------------------------------------------------------------ #
    # 4. policy_documents
    # ------------------------------------------------------------------ #
    op.create_table(
        "policy_documents",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("reference_code", sa.String(length=100), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("issuing_body", sa.String(length=200), nullable=False),
        sa.Column(
            "target_group",
            sa.String(length=50),
            server_default="CITIZEN",
            nullable=False,
        ),
        sa.Column("source_pdf_url", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("structured_rules", _JSONB, nullable=False),
        sa.Column("status", sa.String(length=30), server_default="INDEXED", nullable=False),
        sa.Column("clause_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("uploaded_by", _UUID, nullable=True),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_policy_documents_uploaded_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_documents"),
    )
    op.create_index(
        "ix_policy_documents_reference_code",
        "policy_documents",
        ["reference_code"],
        unique=True,
    )

    # ------------------------------------------------------------------ #
    # 5. policy_clause_chunks
    # ------------------------------------------------------------------ #
    op.create_table(
        "policy_clause_chunks",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("policy_id", _UUID, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("clause_label", sa.String(length=120), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policy_documents.id"],
            name="fk_policy_clause_chunks_policy_id_policy_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_clause_chunks"),
    )
    op.create_index(
        "ix_policy_clause_chunks_policy_id",
        "policy_clause_chunks",
        ["policy_id"],
    )

    # ------------------------------------------------------------------ #
    # 6. policy_voice_explainers
    # ------------------------------------------------------------------ #
    op.create_table(
        "policy_voice_explainers",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("policy_id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=True),
        sa.Column("language_code", sa.String(length=15), nullable=False),
        sa.Column(
            "persona_type",
            sa.String(length=30),
            server_default="CITIZEN",
            nullable=False,
        ),
        sa.Column("eligibility_status", sa.String(length=30), nullable=False),
        sa.Column("plain_language_summary", sa.Text(), nullable=False),
        sa.Column("rights_and_benefits", _JSONB, nullable=False),
        sa.Column("eligibility_evaluation", _JSONB, nullable=False),
        sa.Column("real_world_impacts", _JSONB, nullable=False),
        sa.Column("audio_explainer_url", sa.Text(), nullable=True),
        sa.Column(
            "audio_duration_sec",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policy_documents.id"],
            name="fk_policy_voice_explainers_policy_id_policy_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_policy_voice_explainers_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_voice_explainers"),
    )
    op.create_index(
        "ix_policy_voice_explainers_policy_id",
        "policy_voice_explainers",
        ["policy_id"],
    )

    # ------------------------------------------------------------------ #
    # 7. grievance_tickets
    # ------------------------------------------------------------------ #
    op.create_table(
        "grievance_tickets",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("ticket_number", sa.String(length=40), nullable=False),
        sa.Column("reporter_id", _UUID, nullable=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("voice_transcript", sa.Text(), nullable=True),
        sa.Column("media_urls", _JSONB, nullable=False),
        sa.Column(
            "geom",
            Geography(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address_label", sa.String(length=300), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("severity_score", sa.Integer(), nullable=False),
        sa.Column("ai_triage_summary", sa.Text(), nullable=False),
        sa.Column("routed_department_id", _UUID, nullable=False),
        sa.Column("duplicate_of_id", _UUID, nullable=True),
        sa.Column("upvote_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="TRIAGED", nullable=False),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_proof_urls", _JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name="fk_grievance_tickets_reporter_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["routed_department_id"],
            ["departments.id"],
            name="fk_grievance_tickets_routed_department_id_departments",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_id"],
            ["grievance_tickets.id"],
            name="fk_grievance_tickets_duplicate_of_id_grievance_tickets",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_grievance_tickets"),
    )
    op.create_index(
        "ix_grievance_tickets_ticket_number",
        "grievance_tickets",
        ["ticket_number"],
        unique=True,
    )
    op.create_index("ix_grievance_tickets_category", "grievance_tickets", ["category"])
    op.create_index("ix_grievance_tickets_severity", "grievance_tickets", ["severity"])
    op.create_index(
        "ix_grievance_tickets_routed_department_id",
        "grievance_tickets",
        ["routed_department_id"],
    )
    op.create_index("ix_grievance_tickets_status", "grievance_tickets", ["status"])
    op.create_index(
        "ix_grievance_tickets_sla_deadline",
        "grievance_tickets",
        ["sla_deadline"],
    )
    op.create_index(
        "idx_grievance_tickets_geom",
        "grievance_tickets",
        ["geom"],
        postgresql_using="gist",
    )

    # ------------------------------------------------------------------ #
    # 8. grievance_timeline_events
    # ------------------------------------------------------------------ #
    op.create_table(
        "grievance_timeline_events",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("ticket_id", _UUID, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=False),
        sa.Column("actor_id", _UUID, nullable=True),
        sa.Column("proof_url", sa.Text(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["grievance_tickets.id"],
            name="fk_grievance_timeline_events_ticket_id_grievance_tickets",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_grievance_timeline_events_actor_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_grievance_timeline_events"),
    )
    op.create_index(
        "ix_grievance_timeline_events_ticket_id",
        "grievance_timeline_events",
        ["ticket_id"],
    )


def downgrade() -> None:
    op.drop_table("grievance_timeline_events")
    op.drop_table("grievance_tickets")
    op.drop_table("policy_voice_explainers")
    op.drop_table("policy_clause_chunks")
    op.drop_table("policy_documents")
    op.drop_table("citizen_vaults")
    op.drop_table("users")
    op.drop_table("departments")
