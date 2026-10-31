"""Celery tasks for the Grievance Triage domain."""

from __future__ import annotations

from app.worker import celery_app


@celery_app.task(name="grievance_triage.health_check")
def health_check() -> str:
    """Trivial worker task used to confirm Celery wiring is functional."""
    return "ok"
