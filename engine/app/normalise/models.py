"""Normalisation output model (EDD §2, TECH-SPEC §2.3).

Normalisation turns one immutable ``source_document`` (audio / image / PDF / text) into readable
text **plus the provenance spans that anchor every piece of that text back to the original**. The
span ``locator`` is deliberately the exact shape a :class:`app.store.api.Citation` carries, so an
extracted value can cite the span it came from with no translation:

- audio      → ``{"t_start": float, "t_end": float}``  (the VAD utterance — segment-level)
- image/OCR  → ``{"bbox": [x0, y0, x1, y1]}``           (pixel region)
- PDF text   → ``{"page": int, "bbox": [x0, y0, x1, y1]}``
- plain text → ``{"char_start": int, "char_end": int}``

This is what makes the trust gate "click any value → its exact source" answerable (CLAUDE.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A JSON-serialisable locator value. `object` keeps mypy strict honest at call sites.
LocatorValue = object


@dataclass(frozen=True)
class NormalisedSpan:
    """One anchored fragment of normalised text. ``kind`` names the provenance modality; ``locator``
    is the exact-source pointer (shape per :mod:`app.normalise.models`); ``confidence`` is the
    normaliser's own (ASR/OCR) confidence when it has one, else ``None``."""

    text: str
    kind: str  # 'audio_segment' | 'image_region' | 'pdf_text' | 'char_range'
    locator: dict[str, LocatorValue]
    confidence: float | None = None


@dataclass(frozen=True)
class NormalisedContent:
    """The full normalisation result for one source document. ``text`` is the concatenation used by
    extraction; ``spans`` preserve where each part came from; ``stage`` names the normaliser (for
    idempotency-key + provenance); ``model``/``model_version`` identify the ASR/OCR engine used."""

    source_document_id: str
    text: str
    language: str
    spans: list[NormalisedSpan]
    stage: str  # 'normalise.audio' | 'normalise.ocr' | 'normalise.pdf' | 'normalise.text'
    model: str
    model_version: str
    meta: dict[str, str] = field(default_factory=dict)
