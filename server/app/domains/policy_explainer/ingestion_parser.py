"""Policy PDF / OCR ingestion and offline-safe embedding generation.

The policy explainer pipeline accepts citizen-uploaded or administrator-uploaded
government notifications.  Those documents arrive either as real PDFs (often
scanned) or as plain UTF-8 text.  This module turns them into retrieval-ready
clause chunks and 1536-dimensional embeddings.

Two important offline guarantees are implemented here:

* OCR is opportunistic.  If PyMuPDF extracts less than 30 non-whitespace
  characters from a page, the page is rasterised and passed through
  ``pytesseract``.  A missing Tesseract binary never aborts ingestion.
* Embeddings do not require a third-party API.  When no OpenAI / Gemini key is
  configured (or the remote call fails), a deterministic SHA-256 feature-hashing
  embedding is produced locally.  The resulting vectors are L2-normalised and
  compatible with the ``vector(1536)`` pgvector column.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import unicodedata
from typing import Any

import fitz
import httpx

from app.core.settings import get_settings

try:  # OCR dependencies are optional at import time (missing Tesseract binary).
    import pytesseract
except Exception:  # noqa: BLE001
    pytesseract = None  # type: ignore[assignment]

try:
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------------- #

EMBEDDING_DIMENSIONS = 1536

CLAUSE_MIN_CHARS = 350
CLAUSE_MAX_CHARS = 650
CLAUSE_OVERLAP_CHARS = 80

OCR_MIN_NON_WHITESPACE_CHARS = 30
OCR_RENDER_DPI = 200

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
GEMINI_EMBEDDING_MODEL = "text-embedding-004"
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
GEMINI_EMBEDDINGS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_EMBEDDING_MODEL}:batchEmbedContents"
)

#: Matches "Section 4", "Clause 12(3)", "Article IV", "Schedule 2", etc.
CLAUSE_HEADER_PATTERN = re.compile(
    r"(?:Section|Clause|Article|Rule|Schedule|Para)\s+[\dA-Za-z.\-()]+",
    re.IGNORECASE,
)

#: Paragraph / sentence / line boundaries used to keep chunks semantic.
_BOUNDARY_PATTERN = re.compile(r"(?:\n\s*\n|(?<=[.!?;])\s+|\n)")

#: Weights for local feature hashing.  Word bigrams carry the most signal,
#: character n-grams help with Indian-language morphology and spelling variants.
_WORD_WEIGHT = 1.0
_BIGRAM_WEIGHT = 1.6
_CHAR_NGRAM_WEIGHTS = {3: 0.30, 4: 0.35, 5: 0.30}


# --------------------------------------------------------------------------- #
# Text normalisation & clause chunking
# --------------------------------------------------------------------------- #

def _non_whitespace_count(text: str) -> int:
    """Return the number of non-whitespace characters in *text*."""
    return sum(1 for char in text if not char.isspace())


def _normalise_page_text(text: str) -> str:
    """Collapse PDF/OCR whitespace while preserving paragraph structure."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _chunk_text_offsets(
    text: str,
    *,
    min_chars: int = CLAUSE_MIN_CHARS,
    max_chars: int = CLAUSE_MAX_CHARS,
    overlap: int = CLAUSE_OVERLAP_CHARS,
) -> list[tuple[int, int]]:
    """Split *text* into semantic character windows with a fixed overlap.

    Chunks are kept inside ``[min_chars, max_chars]`` wherever the source text
    allows it.  Boundaries are preferred at paragraph breaks, sentence endings,
    and finally whitespace, so a clause is rarely cut mid-sentence.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [(0, len(text))]

    offsets: list[tuple[int, int]] = []
    length = len(text)
    start = 0

    while start < length:
        hard_end = min(start + max_chars, length)
        if hard_end >= length:
            end = length
        else:
            # Leave a small margin so trimming surrounding whitespace still
            # leaves a chunk at or above the requested minimum size.
            lower_bound = min(start + min_chars + 24, hard_end)
            boundary = _BOUNDARY_PATTERN.search(text, lower_bound, hard_end)
            end = boundary.end() if boundary else hard_end
            if end <= start:
                end = hard_end

        offsets.append((start, end))
        if end >= length:
            break

        next_start = end - overlap
        if next_start <= start:
            next_start = start + max(1, min_chars - overlap)
        start = next_start

    # A short final tail is ugly for retrieval.  Re-balance it with the
    # penultimate chunk (or merge the two when they comfortably fit).
    if len(offsets) > 1:
        last_start, last_end = offsets[-1]
        if last_end - last_start < min_chars:
            prev_start, _ = offsets[-2]
            desired_start = max(
                prev_start + min_chars - overlap,
                last_end - max_chars,
            )
            if last_end - desired_start < min_chars + 8:
                # Both chunks still fit inside one max-sized chunk.
                offsets[-2] = (prev_start, last_end)
                offsets.pop()
            else:
                offsets[-2] = (
                    prev_start,
                    min(desired_start + overlap, last_end),
                )
                offsets[-1] = (desired_start, last_end)

    # Trim surrounding whitespace, keeping offsets aligned with the source.
    trimmed: list[tuple[int, int]] = []
    for chunk_start, chunk_end in offsets:
        while chunk_start < chunk_end and text[chunk_start].isspace():
            chunk_start += 1
        while chunk_end > chunk_start and text[chunk_end - 1].isspace():
            chunk_end -= 1
        if chunk_end > chunk_start:
            trimmed.append((chunk_start, chunk_end))

    # Trimming can shave a character or two off a boundary-aligned window.
    # Re-extend such chunks so every clause in a long enough page is at least
    # ``min_chars`` characters.  Prefer moving the start backwards, which only
    # increases overlap with the predecessor and never truncates later chunks.
    if len(text) >= min_chars:
        adjusted: list[tuple[int, int]] = []
        for chunk_start, chunk_end in trimmed:
            if chunk_end - chunk_start >= min_chars:
                adjusted.append((chunk_start, chunk_end))
                continue

            new_start = max(0, chunk_end - min_chars)
            while new_start > 0 and text[new_start].isspace():
                new_start -= 1
            if chunk_end - new_start >= min_chars:
                adjusted.append((new_start, chunk_end))
                continue

            new_end = min(length, chunk_start + min_chars)
            while new_end < length and text[new_end - 1].isspace():
                new_end += 1
            adjusted.append((chunk_start, new_end))
        trimmed = adjusted

    return trimmed


def _extract_clause_label(
    page_text: str,
    chunk_start: int,
    chunk_end: int,
    page_number: int,
    local_index: int,
) -> str:
    """Return the most relevant clause header for a chunk.

    The label is anchored to the start of the chunk (or the nearest preceding
    header on the same page), not the first header that happens to appear later
    inside the chunk.  Documents without formal headers get a stable
    ``Page N, Clause M`` fallback label.
    """
    # A chunk that begins exactly on a header is a new clause.
    match = CLAUSE_HEADER_PATTERN.match(page_text, chunk_start)
    if match is not None:
        return match.group(0).strip()

    # Overlap windows can begin a few characters before/inside a header.
    nearby = CLAUSE_HEADER_PATTERN.search(
        page_text[chunk_start : min(chunk_end, chunk_start + 32)]
    )
    if nearby is not None and nearby.start() <= 8:
        return nearby.group(0).strip()

    preceding: re.Match[str] | None = None
    for candidate in CLAUSE_HEADER_PATTERN.finditer(page_text, 0, max(chunk_start, 0)):
        preceding = candidate
    if preceding is not None:
        return preceding.group(0).strip()

    return f"Page {page_number}, Clause {local_index}"


def _ocr_page(page: Any) -> str:
    """Render *page* and OCR it.  Any failure is logged and treated as no text."""
    try:
        pixmap = page.get_pixmap(dpi=OCR_RENDER_DPI)
    except Exception as exc:  # noqa: BLE001 — OCR must never abort ingestion
        logger.warning("Could not rasterise PDF page for OCR: %s", exc)
        return ""

    try:
        if Image is None or pytesseract is None:
            logger.warning("OCR fallback skipped: Pillow or pytesseract is unavailable.")
            return ""

        mode = "RGBA" if pixmap.alpha else "RGB"
        image = Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)
        if mode != "RGB":
            image = image.convert("RGB")
        return pytesseract.image_to_string(image) or ""
    except Exception as exc:  # noqa: BLE001 — missing Tesseract binary is common
        logger.warning("OCR fallback unavailable or failed: %s", exc)
        return ""


def _extract_pdf_pages(file_bytes: bytes) -> list[tuple[int, str]]:
    """Extract page text from a PDF, with OCR fallback for scanned pages."""
    pages: list[tuple[int, str]] = []
    document = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            try:
                page_text = page.get_text("text") or ""
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not extract text from page %d: %s", page_number, exc)
                page_text = ""

            if _non_whitespace_count(page_text) < OCR_MIN_NON_WHITESPACE_CHARS:
                ocr_text = _ocr_page(page)
                if _non_whitespace_count(ocr_text) > _non_whitespace_count(page_text):
                    logger.info("OCR recovered text for page %d.", page_number)
                    page_text = ocr_text

            pages.append((page_number, page_text))
    finally:
        document.close()
    return pages


def extract_text_and_clauses_from_pdf(
    file_bytes: bytes,
    filename: str = "document.pdf",
) -> tuple[str, list[dict]]:
    """Extract raw text and semantic clause chunks from a PDF or UTF-8 text.

    Parameters
    ----------
    file_bytes:
        The uploaded document bytes.  A PDF magic header (``%PDF``) switches on
        PyMuPDF parsing; everything else is decoded as Page 1 UTF-8 text.
    filename:
        Original upload name, retained for logging / future metadata.

    Returns
    -------
    tuple[str, list[dict]]
        ``(full_raw_text, clauses)`` where every clause contains
        ``chunk_index`` (0-based), ``page_number`` (1-based),
        ``clause_label``, and ``content``.
    """
    raw_bytes = bytes(file_bytes or b"")
    pages: list[tuple[int, str]]

    if raw_bytes.startswith(b"%PDF"):
        try:
            pages = _extract_pdf_pages(raw_bytes)
        except Exception as exc:  # noqa: BLE001 — malformed PDFs degrade gracefully
            logger.warning(
                "PDF parsing failed for '%s' (%s); falling back to UTF-8 text.",
                filename,
                exc,
            )
            pages = [(1, raw_bytes.decode("utf-8", errors="replace"))]
    else:
        pages = [(1, raw_bytes.decode("utf-8", errors="replace"))]

    normalised_pages: list[tuple[int, str]] = []
    for page_number, page_text in pages:
        normalised = _normalise_page_text(page_text)
        if normalised:
            normalised_pages.append((page_number, normalised))

    full_raw_text = "\n\n".join(text for _, text in normalised_pages).strip()

    clauses: list[dict] = []
    chunk_index = 0
    for page_number, page_text in normalised_pages:
        offsets = _chunk_text_offsets(page_text)
        for local_index, (chunk_start, chunk_end) in enumerate(offsets, start=1):
            content = page_text[chunk_start:chunk_end].strip()
            if not content:
                continue
            clauses.append(
                {
                    "chunk_index": chunk_index,
                    "page_number": page_number,
                    "clause_label": _extract_clause_label(
                        page_text,
                        chunk_start,
                        chunk_end,
                        page_number,
                        local_index,
                    ),
                    "content": content,
                }
            )
            chunk_index += 1

    return full_raw_text, clauses


# --------------------------------------------------------------------------- #
# Embeddings — remote providers + deterministic local fallback
# --------------------------------------------------------------------------- #

def _l2_normalise(vector: list[float]) -> list[float]:
    """Return the L2-normalised copy of *vector* (all-zero stays zero)."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0] * len(vector)
    return [value / norm for value in vector]


def _hash_token(kind: str, token: str) -> tuple[int, float]:
    """Map a token into a 1536-bucket signed feature space."""
    digest = hashlib.sha256(f"{kind}:{token}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
    sign = 1.0 if digest[4] & 1 else -1.0
    return bucket, sign


def _local_embedding(text: str) -> list[float]:
    """Build a deterministic 1536-dimensional feature-hashing embedding.

    Word unigrams, word bigrams, and character n-grams are hashed with SHA-256
    (never Python's randomised :func:`hash`).  The result is L2-normalised so
    pgvector's cosine distance (``<=>``) ranks semantically overlapping policy
    clauses highly, entirely offline.
    """
    vector = [0.0] * EMBEDDING_DIMENSIONS
    normalised = unicodedata.normalize("NFKC", text or "").lower()
    words = re.findall(r"[^\W_]+", normalised, flags=re.UNICODE)
    if not words:
        return vector

    def add(kind: str, token: str, weight: float) -> None:
        bucket, sign = _hash_token(kind, token)
        vector[bucket] += sign * weight

    for word in words:
        add("w", word, _WORD_WEIGHT)

    for first, second in zip(words, words[1:]):
        add("b", f"{first}_{second}", _BIGRAM_WEIGHT)

    for word in words:
        for n, weight in _CHAR_NGRAM_WEIGHTS.items():
            if len(word) < n:
                continue
            for index in range(len(word) - n + 1):
                add("c", word[index : index + n], weight)

    return _l2_normalise(vector)


def _coerce_api_vectors(vectors: list[Any], expected_count: int) -> list[list[float]]:
    """Validate and normalise vectors returned by a remote embedding provider."""
    if len(vectors) != expected_count:
        raise ValueError(
            f"Embedding provider returned {len(vectors)} vectors for "
            f"{expected_count} inputs."
        )

    result: list[list[float]] = []
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError("Embedding provider did not return 1536-dimensional vectors.")
        result.append(_l2_normalise([float(value) for value in vector]))
    return result


async def _request_openai_embeddings(api_key: str, texts: list[str]) -> list[Any]:
    """Request batched 1536-dimensional embeddings from OpenAI."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_EMBEDDING_MODEL,
        "input": texts,
        "dimensions": EMBEDDING_DIMENSIONS,
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(OPENAI_EMBEDDINGS_URL, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()

    data = sorted(body.get("data", []), key=lambda item: item.get("index", 0))
    return [item.get("embedding") for item in data]


async def _request_gemini_embeddings(api_key: str, texts: list[str]) -> list[Any]:
    """Request batched 1536-dimensional embeddings from Gemini."""
    payload = {
        "requests": [
            {
                "model": f"models/{GEMINI_EMBEDDING_MODEL}",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": EMBEDDING_DIMENSIONS,
            }
            for text in texts
        ]
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            GEMINI_EMBEDDINGS_URL,
            params={"key": api_key},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()

    return [embedding.get("values") for embedding in body.get("embeddings", [])]


async def generate_embeddings_for_texts(texts: list[str]) -> list[list[float]]:
    """Generate 1536-dimensional, L2-normalised embeddings for *texts*.

    Remote providers are attempted only when their API key is configured.  Any
    network, quota, or response-shape failure transparently falls through to the
    deterministic local embedding, so ingesting a policy never depends on an
    online AI service.
    """
    if not texts:
        return []

    settings = get_settings()
    providers: list[tuple[str, str, Any]] = []
    openai_key = (getattr(settings, "OPENAI_API_KEY", "") or "").strip()
    gemini_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if openai_key:
        providers.append(("OpenAI", openai_key, _request_openai_embeddings))
    if gemini_key:
        providers.append(("Gemini", gemini_key, _request_gemini_embeddings))

    for provider_name, api_key, requester in providers:
        try:
            vectors = await requester(api_key, texts)
            return _coerce_api_vectors(vectors, len(texts))
        except Exception as exc:  # noqa: BLE001 — fall back to offline embeddings
            logger.warning(
                "%s embedding request failed (%s); using local embeddings.",
                provider_name,
                exc,
            )

    return [_local_embedding(text) for text in texts]
