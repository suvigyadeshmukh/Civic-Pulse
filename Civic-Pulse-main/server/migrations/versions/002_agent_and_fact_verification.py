"""Placeholder for the agent and fact-verification schema (Backend Developer B).

This revision is intentionally a no-op so Alembic can load the versions
directory and ``alembic upgrade head`` remains usable while the second
migration is being developed. Backend Developer B should replace the bodies of
``upgrade()`` and ``downgrade()`` with the bureaucracy-agent and fact-
verification tables.

Revision ID: 002
Revises: 001
Create Date: 2026-10-31
"""

from __future__ import annotations

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op placeholder."""


def downgrade() -> None:
    """No-op placeholder."""
