"""Celery tasks for the Policy Explainer domain."""

from __future__ import annotations

from app.domains.policy_explainer.voice_synthesizer import (
    run_coroutine_safely,
    synthesize_regional_explainer_audio,
)
from app.worker import celery_app


@celery_app.task(name="policy_explainer.synthesize_voice_task")
def synthesize_voice_task(
    text_script: str,
    language_code: str,
    explainer_id: str,
) -> tuple[str, int]:
    """Synthesise and upload a regional MP3 explainer in a Celery worker."""
    return run_coroutine_safely(
        synthesize_regional_explainer_audio(
            text_script=text_script,
            language_code=language_code,
            explainer_id=explainer_id,
        )
    )
