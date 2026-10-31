"""Regional voice synthesis for policy explainers.

The preferred engine is AI4Bharat's ``indic-parler-tts`` model, which produces
natural Indian-language speech from a short speaker-description prompt.  It is
called through the Hugging Face Inference API when ``HF_API_TOKEN`` is set.

Because demo / CI machines frequently have no Hugging Face token and no network,
the module degrades in two further tiers:

1. ``edge-tts`` neural voices (free, no key required) for six Indian locales.
2. A locally generated, valid MPEG-1 Layer III frame buffer so uploads, database
   writes, and UI playback flows can still be exercised fully offline.

All tiers return the same public contract: ``(audio_url, duration_sec)``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import httpx

from app.core.exceptions import ValidationException
from app.core.settings import get_settings
from app.core.storage import storage_service

try:  # edge-tts is optional at runtime; offline tier 3 covers missing installs.
    import edge_tts
except Exception:  # noqa: BLE001
    edge_tts = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Supported voices
# --------------------------------------------------------------------------- #

SUPPORTED_REGIONAL_VOICES: dict[str, dict[str, str]] = {
    "hi-IN": {
        "language_name": "Hindi",
        "edge_voice": "hi-IN-SwaraNeural",
        "ai4bharat_caption": (
            "A clear, warm female Hindi voice speaking at a measured pace. "
            "The tone is friendly, trustworthy, and suitable for explaining "
            "government policy and citizen rights."
        ),
    },
    "ta-IN": {
        "language_name": "Tamil",
        "edge_voice": "ta-IN-PallaviNeural",
        "ai4bharat_caption": (
            "A clear, expressive female Tamil voice with a calm, reassuring "
            "delivery. The pronunciation is precise and easy to follow for "
            "citizens listening to a public policy explainer."
        ),
    },
    "mr-IN": {
        "language_name": "Marathi",
        "edge_voice": "mr-IN-AarohiNeural",
        "ai4bharat_caption": (
            "A natural, friendly female Marathi voice speaking clearly at a "
            "moderate pace, with an informative and trustworthy tone for civic "
            "policy explanations."
        ),
    },
    "te-IN": {
        "language_name": "Telugu",
        "edge_voice": "te-IN-ShrutiNeural",
        "ai4bharat_caption": (
            "A warm, articulate female Telugu voice with a steady, measured "
            "pace. The delivery is approachable and authoritative, suited to a "
            "government scheme explainer."
        ),
    },
    "bn-IN": {
        "language_name": "Bengali",
        "edge_voice": "bn-IN-TanishaaNeural",
        "ai4bharat_caption": (
            "A pleasant, clear female Bengali voice with a gentle and confident "
            "tone, speaking at a comfortable pace for public information and "
            "citizen guidance."
        ),
    },
    "en-IN": {
        "language_name": "Indian English",
        "edge_voice": "en-IN-NeerjaNeural",
        "ai4bharat_caption": (
            "A clear Indian English female voice with a professional, warm "
            "delivery and a moderate pace, suitable for explaining government "
            "policy to the general public."
        ),
    },
}

_AI4BHARAT_TTS_URL = "https://api-inference.huggingface.co/models/{model}"
_DEFAULT_AI4BHARAT_MODEL = "ai4bharat/indic-parler-tts"
_EDGE_TTS_TIMEOUT_SECONDS = 8.0

#: A valid MPEG-1 Layer III frame header: 128 kbps, 44.1 kHz, joint stereo.
_MP3_FRAME_HEADER = b"\xff\xfb\x90\x64"
_MP3_FRAME_LENGTH = 417
_MP3_FRAMES_PER_SECOND = 38.28


# --------------------------------------------------------------------------- #
# Tier 1 — AI4Bharat IndicParler TTS via Hugging Face
# --------------------------------------------------------------------------- #

async def _try_hf_tts(text_script: str, caption: str) -> bytes | None:
    """Call the AI4Bharat model on Hugging Face; return ``None`` without a token."""
    settings = get_settings()
    token = (getattr(settings, "HF_API_TOKEN", "") or "").strip()
    if not token:
        return None

    model = (
        getattr(settings, "AI4BHARAT_TTS_MODEL", _DEFAULT_AI4BHARAT_MODEL)
        or _DEFAULT_AI4BHARAT_MODEL
    ).strip()
    url = _AI4BHARAT_TTS_URL.format(model=model)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "audio/mpeg, audio/*",
    }
    payload = {
        "inputs": text_script,
        "parameters": {"description": caption},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        audio = response.content
        content_type = response.headers.get("content-type", "").lower()

    if not audio:
        raise ValueError("AI4Bharat TTS returned an empty audio payload.")
    if "json" in content_type or audio.lstrip()[:1] in (b"{", b"["):
        raise ValueError("AI4Bharat TTS returned an error document instead of audio.")
    return audio


# --------------------------------------------------------------------------- #
# Tier 2 — free edge-tts neural voices
# --------------------------------------------------------------------------- #

async def _try_edge_tts(text_script: str, voice: str) -> bytes:
    """Stream MP3 bytes from the free ``edge-tts`` neural service."""
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed.")

    communicate = edge_tts.Communicate(text=text_script, voice=voice)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            audio.extend(chunk["data"])

    if not audio:
        raise RuntimeError("edge-tts returned no audio data.")
    return bytes(audio)


# --------------------------------------------------------------------------- #
# Tier 3 — offline MPEG frame buffer
# --------------------------------------------------------------------------- #

def _offline_mp3_bytes(duration_sec: int) -> bytes:
    """Return a valid-headered MPEG-1 Layer III frame buffer.

    The payload of each frame is zero-filled.  It is intentionally a
    deterministic fallback for offline CI / demos rather than speech; the
    duration and container-level MP3 header are valid so downstream players and
    tests can process the asset.
    """
    frame_count = max(1, int(round(max(duration_sec, 1) * _MP3_FRAMES_PER_SECOND)))
    frame = _MP3_FRAME_HEADER + bytes(_MP3_FRAME_LENGTH - len(_MP3_FRAME_HEADER))
    return frame * frame_count


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

async def synthesize_regional_explainer_audio(
    text_script: str,
    language_code: str,
    explainer_id: str,
) -> tuple[str, int]:
    """Synthesise a regional-language explainer and upload it as MP3.

    Parameters
    ----------
    text_script:
        Plain-language script to speak.
    language_code:
        One of :data:`SUPPORTED_REGIONAL_VOICES` (e.g. ``"hi-IN"``).
    explainer_id:
        Identifier used to build the storage filename.

    Returns
    -------
    tuple[str, int]
        Public audio URL and estimated duration in seconds.

    Raises
    ------
    ValidationException
        If *language_code* is not supported.
    """
    voice_config = SUPPORTED_REGIONAL_VOICES.get(language_code)
    if voice_config is None:
        supported = ", ".join(sorted(SUPPORTED_REGIONAL_VOICES))
        raise ValidationException(
            code="UNSUPPORTED_LANGUAGE",
            message=(
                f"Unsupported language code '{language_code}'. "
                f"Supported languages: {supported}."
            ),
        )

    script = text_script or ""
    duration_sec = max(5, round(len(script.split()) / 2.3))

    settings = get_settings()
    audio_bytes: bytes | None = None

    # Tier 1 — AI4Bharat IndicParler via Hugging Face.
    if (getattr(settings, "HF_API_TOKEN", "") or "").strip():
        try:
            audio_bytes = await _try_hf_tts(
                script,
                voice_config["ai4bharat_caption"],
            )
            if audio_bytes:
                logger.info(
                    "Synthesised %s explainer %s with AI4Bharat (%d bytes).",
                    language_code,
                    explainer_id,
                    len(audio_bytes),
                )
        except Exception as exc:  # noqa: BLE001 — fall through to edge-tts
            logger.warning(
                "AI4Bharat TTS failed for %s (%s); falling back to edge-tts.",
                language_code,
                exc,
            )

    # Tier 2 — free edge-tts neural voice.
    if not audio_bytes:
        try:
            audio_bytes = await asyncio.wait_for(
                _try_edge_tts(script, voice_config["edge_voice"]),
                timeout=_EDGE_TTS_TIMEOUT_SECONDS,
            )
            if audio_bytes:
                logger.info(
                    "Synthesised %s explainer %s with edge-tts (%d bytes).",
                    language_code,
                    explainer_id,
                    len(audio_bytes),
                )
        except Exception as exc:  # noqa: BLE001 — offline / network failure
            logger.warning(
                "edge-tts unavailable for %s (%s); using offline MP3 fallback.",
                language_code,
                exc,
            )

    # Tier 3 — deterministic offline fallback.
    if not audio_bytes:
        audio_bytes = _offline_mp3_bytes(duration_sec)
        logger.info(
            "Generated offline MPEG fallback for %s explainer %s (%d bytes).",
            language_code,
            explainer_id,
            len(audio_bytes),
        )

    audio_url = await storage_service.upload_bytes(
        audio_bytes,
        folder="explainers",
        filename=f"{explainer_id}_{language_code}.mp3",
        content_type="audio/mpeg",
    )
    return audio_url, duration_sec


# --------------------------------------------------------------------------- #
# Celery convenience helper
# --------------------------------------------------------------------------- #

def run_coroutine_safely(coroutine: Any) -> Any:
    """Run *coroutine* from synchronous Celery code, even inside a live loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coroutine)
        except BaseException as exc:  # noqa: BLE001 — re-raised in caller thread
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error["value"]
    return result["value"]
