"""Unit tests for policy PDF/OCR clause parsing, embeddings, and regional TTS.

These tests are fully offline.  OCR uses PyMuPDF text extraction, embedding
tests force the deterministic local fallback, and TTS tests exercise the
offline MPEG tier while mocking object-storage upload.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import fitz
import pytest

from app.core.exceptions import ValidationException
from app.domains.policy_explainer import ingestion_parser, voice_synthesizer


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _build_multi_page_policy_pdf() -> tuple[bytes, list[str]]:
    """Create a two-page in-memory policy PDF with numbered sections."""
    page_texts = [
        (
            "Section 1. Short title and commencement.\n"
            "This scheme may be called the Rural Water Support Scheme 2026. "
            "It applies to all eligible households in notified villages and "
            "municipal wards. Every application must include proof of residence "
            "issued within the last six months.\n\n"
            "Section 2. Eligibility criteria.\n"
            "A household is eligible when its annual income is below the "
            "notified threshold, it resides in a notified service area, and no "
            "member has received the same benefit in the current financial "
            "year. Applicants must submit identity documents and a self "
            "declaration confirming their household details. The competent "
            "authority may verify the information with the revenue records.\n\n"
            "Section 3. Application procedure.\n"
            "Applications are submitted to the local revenue office or through "
            "the citizen portal. The office must issue an acknowledgement "
            "receipt immediately and complete verification within thirty "
            "working days. Applicants shall be informed of the decision by SMS "
            "and through the portal status page."
        ),
        (
            "Section 4. Grievance redressal.\n"
            "Any applicant whose claim is rejected may file a grievance within "
            "sixty days. The grievance officer must hear the applicant and "
            "record the reasons in writing. Appeals are decided by the sub "
            "divisional magistrate within forty five days. A copy of the final "
            "order shall be provided free of cost to the applicant.\n\n"
            "Section 5. Penalties and safeguards.\n"
            "False information may lead to cancellation of benefits and "
            "recovery of amounts already paid. No benefit shall be denied "
            "without a written order. Records must be maintained for seven "
            "years. The department shall publish quarterly statistics on "
            "applications, approvals, rejections, and grievances received."
        ),
    ]

    document = fitz.open()
    try:
        for text in page_texts:
            page = document.new_page()
            page.insert_textbox(
                fitz.Rect(50, 50, 545, 800),
                text,
                fontsize=10,
                fontname="helv",
            )
        return document.tobytes(), page_texts
    finally:
        document.close()


def _cosine(first: list[float], second: list[float]) -> float:
    return sum(a * b for a, b in zip(first, second))


# --------------------------------------------------------------------------- #
# 1. PDF / OCR clause parser
# --------------------------------------------------------------------------- #

def test_extract_text_and_clauses_from_multi_page_pdf():
    pdf_bytes, page_texts = _build_multi_page_policy_pdf()

    full_raw_text, clauses = ingestion_parser.extract_text_and_clauses_from_pdf(
        pdf_bytes,
        filename="rural_water_scheme.pdf",
    )

    assert "Section 1" in full_raw_text
    assert "Section 4" in full_raw_text
    assert len(clauses) >= 3

    page_numbers = {clause["page_number"] for clause in clauses}
    assert page_numbers == {1, 2}

    assert [clause["chunk_index"] for clause in clauses] == list(range(len(clauses)))
    for clause in clauses:
        assert set(clause) == {"chunk_index", "page_number", "clause_label", "content"}
        assert clause["page_number"] in (1, 2)
        assert clause["clause_label"]
        assert clause["content"] in full_raw_text
        assert len(clause["content"]) <= ingestion_parser.CLAUSE_MAX_CHARS

    # The chunker keeps every full-sized clause between 350 and 650 characters.
    full_sized = [
        clause
        for clause in clauses
        if len(clause["content"]) >= ingestion_parser.CLAUSE_MIN_CHARS
    ]
    assert full_sized, "expected at least one 350+ character clause"
    assert all(
        len(clause["content"]) <= ingestion_parser.CLAUSE_MAX_CHARS
        for clause in clauses
    )

    # At least one label must be a real extracted header.
    assert any(
        clause["clause_label"].lower().startswith("section ")
        for clause in clauses
    )

    assert page_texts[0].split(".")[0].strip() in full_raw_text


def test_extract_text_and_clauses_from_plain_utf8_text():
    raw_text = (
        b"Clause 7. The municipal authority shall publish every draft bylaw "
        b"on its website for public comments. Citizens may submit objections "
        b"within thirty days. The authority must publish a summary of the "
        b"objections and its response before the final notification is issued."
    )

    full_raw_text, clauses = ingestion_parser.extract_text_and_clauses_from_pdf(
        raw_text,
        filename="bylaw.txt",
    )

    assert "Clause 7" in full_raw_text
    assert len(clauses) == 1
    assert clauses[0]["page_number"] == 1
    assert clauses[0]["clause_label"].startswith("Clause 7")
    assert "municipal authority" in clauses[0]["content"]


# --------------------------------------------------------------------------- #
# 2. Deterministic local embeddings
# --------------------------------------------------------------------------- #

async def test_generate_embeddings_normalised_and_semantically_ranked(monkeypatch):
    # Force the offline path regardless of the developer's .env file.
    monkeypatch.setattr(
        ingestion_parser,
        "get_settings",
        lambda: SimpleNamespace(OPENAI_API_KEY="", GEMINI_API_KEY=""),
    )

    related_one = (
        "Section 4. Eligible rural households may apply for the water subsidy "
        "scheme by submitting proof of residence to the local revenue office."
    )
    related_two = (
        "Section 5. Rural households applying for the water subsidy must submit "
        "proof of residence and identity documents to the revenue office."
    )
    unrelated = (
        "Section 9. Commercial spacecraft operators must register orbital debris "
        "mitigation plans with the national space agency before launch."
    )

    vectors = await ingestion_parser.generate_embeddings_for_texts(
        [related_one, related_two, unrelated]
    )

    assert len(vectors) == 3
    for vector in vectors:
        assert len(vector) == ingestion_parser.EMBEDDING_DIMENSIONS
        norm = math.sqrt(sum(value * value for value in vector))
        assert norm == pytest.approx(1.0, abs=1e-9)

    related_similarity = _cosine(vectors[0], vectors[1])
    unrelated_similarity = _cosine(vectors[0], vectors[2])
    assert related_similarity > unrelated_similarity + 0.05
    assert related_similarity > 0.35

    # The local fallback is deterministic across calls.
    second_pass = await ingestion_parser.generate_embeddings_for_texts([related_one])
    assert second_pass[0] == pytest.approx(vectors[0], abs=1e-12)


async def test_generate_embeddings_empty_input():
    assert await ingestion_parser.generate_embeddings_for_texts([]) == []


# --------------------------------------------------------------------------- #
# 3. Regional voice synthesis
# --------------------------------------------------------------------------- #

async def test_regional_tts_offline_fallback_for_hindi_and_tamil(monkeypatch):
    uploaded: list[tuple[bytes, str, str, str]] = []

    async def fake_upload(
        data: bytes,
        folder: str,
        filename: str,
        content_type: str,
    ) -> str:
        uploaded.append((data, folder, filename, content_type))
        return f"https://media.example/{folder}/{filename}"

    async def offline_edge(*_args, **_kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(
        voice_synthesizer,
        "get_settings",
        lambda: SimpleNamespace(
            HF_API_TOKEN="",
            AI4BHARAT_TTS_MODEL="ai4bharat/indic-parler-tts",
        ),
    )
    monkeypatch.setattr(voice_synthesizer.storage_service, "upload_bytes", fake_upload)
    monkeypatch.setattr(voice_synthesizer, "_try_edge_tts", offline_edge)

    script = (
        "This scheme provides clean drinking water to eligible rural households. "
        "Submit proof of residence at your local revenue office."
    )

    hindi_url, hindi_duration = await voice_synthesizer.synthesize_regional_explainer_audio(
        script,
        "hi-IN",
        "explainer-hi-001",
    )
    tamil_url, tamil_duration = await voice_synthesizer.synthesize_regional_explainer_audio(
        script,
        "ta-IN",
        "explainer-ta-001",
    )

    assert hindi_url.endswith(".mp3")
    assert tamil_url.endswith(".mp3")
    assert hindi_duration == max(5, round(len(script.split()) / 2.3))
    assert tamil_duration == hindi_duration

    assert len(uploaded) == 2
    for data, folder, filename, content_type in uploaded:
        assert data.startswith(b"\xff\xfb\x90\x64")
        assert len(data) > 1000
        assert folder == "explainers"
        assert filename.endswith(".mp3")
        assert content_type == "audio/mpeg"

    assert "hi-IN" in uploaded[0][2]
    assert "ta-IN" in uploaded[1][2]


async def test_regional_tts_rejects_unsupported_language():
    with pytest.raises(ValidationException) as exc_info:
        await voice_synthesizer.synthesize_regional_explainer_audio(
            "This should never be synthesised.",
            "xx-INVALID",
            "explainer-bad-001",
        )

    assert exc_info.value.code == "UNSUPPORTED_LANGUAGE"
    assert exc_info.value.status_code == 422
    assert "xx-INVALID" in exc_info.value.message


def test_supported_regional_voices_cover_required_locales():
    assert set(voice_synthesizer.SUPPORTED_REGIONAL_VOICES) == {
        "hi-IN",
        "ta-IN",
        "mr-IN",
        "te-IN",
        "bn-IN",
        "en-IN",
    }
    assert (
        voice_synthesizer.SUPPORTED_REGIONAL_VOICES["hi-IN"]["edge_voice"]
        == "hi-IN-SwaraNeural"
    )
    assert (
        voice_synthesizer.SUPPORTED_REGIONAL_VOICES["ta-IN"]["edge_voice"]
        == "ta-IN-PallaviNeural"
    )
