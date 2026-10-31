"""Civic Pulse — Celery application and task autodiscovery.

Celery is used for long-running background work:
    * Policy document ingestion & chunking/embedding (``policy_explainer.tasks``)
    * Grievance multimodal triage & spatial dedup (``grievance_triage.tasks``)  — if applicable
    * Bureaucracy-Agent Playwright runs (``bureaucracy_agent.tasks``)
    * Fact-verification media forensics pipelines (``fact_verification.tasks``)

Workers are started via::

    celery -A app.worker.celery_app worker --loglevel=info
"""

from __future__ import annotations

import logging

from celery import Celery

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# ---------------------------------------------------------------------------
# Celery application instance
# ---------------------------------------------------------------------------

celery_app = Celery(
    "civic_pulse",
    broker=_settings.REDIS_URL,
    backend=_settings.REDIS_URL,
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Result backend
    result_expires=3600,
    # Worker tuning
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,
    # Task defaults
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
)

# ---------------------------------------------------------------------------
# Safe autodiscovery — domain task modules are imported only when they exist.
# This means Person 2 and Person 3 can develop independently; missing modules
# are silently skipped until their code is merged.
# ---------------------------------------------------------------------------

_DOMAIN_TASK_MODULES: list[str] = [
    "app.domains.policy_explainer.tasks",
    "app.domains.grievance_triage.tasks",
    "app.domains.bureaucracy_agent.tasks",
    "app.domains.fact_verification.tasks",
]


def _safe_autodiscover() -> list[str]:
    """Try to import each domain task module; return the list of those found."""
    discovered: list[str] = []
    for module_path in _DOMAIN_TASK_MODULES:
        try:
            __import__(module_path)
            discovered.append(module_path)
            logger.info("Celery autodiscovered: %s", module_path)
        except ImportError:
            logger.debug(
                "Celery skipping %s (not implemented yet).",
                module_path,
            )
        except Exception:
            logger.warning(
                "Celery failed to import %s — skipping.",
                module_path,
                exc_info=True,
            )
    return discovered


# Run autodiscovery on import so the worker picks up every available task.
_discovered_modules = _safe_autodiscover()

# Also register via celery's autodiscover_tasks for any late-bound tasks
celery_app.autodiscover_tasks(
    packages=[
        "app.domains.policy_explainer",
        "app.domains.grievance_triage",
        "app.domains.bureaucracy_agent",
        "app.domains.fact_verification",
    ],
    related_name="tasks",
    force=False,
)

