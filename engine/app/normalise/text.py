"""Plain-text normalisation — the trivial path (EDD §2.3).

A message that already *is* text (a WhatsApp text line, a plain-text note) needs no ASR/OCR: the
whole string is one span with a char-range locator, so an extracted value still points back to the
exact characters it was drawn from.
"""

from __future__ import annotations

from ..config import settings
from .models import NormalisedContent, NormalisedSpan


def normalise_text(
    source_document_id: str, text: str, *, language: str = "und"
) -> NormalisedContent:
    """Wrap already-textual content with a whole-string char-range provenance span."""
    span = NormalisedSpan(
        text=text,
        kind="char_range",
        locator={"char_start": 0, "char_end": len(text)},
    )
    return NormalisedContent(
        source_document_id=source_document_id,
        text=text,
        language=language,
        spans=[span],
        stage="normalise.text",
        model="passthrough",
        model_version=settings.code_version,
    )
