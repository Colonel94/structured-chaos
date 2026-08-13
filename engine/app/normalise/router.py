"""Normalisation router — dispatch a source document to the right normaliser by MIME (EDD §2.3).

One entry point for the pipeline's ``normalise`` stage. Audio→ASR, image→OCR, PDF→text-layer-or-OCR,
text→passthrough. An unknown/undecodable type is **not** an error — the original is already stored
immutably; we return empty normalised text with a ``meta['unsupported']`` note so the case records
that something arrived we could not read, rather than dropping it silently.
"""

from __future__ import annotations

from ..backends.interfaces import ASRBackend
from ..backends.registry import get_asr
from .audio import normalise_audio
from .models import NormalisedContent
from .pdf import normalise_pdf
from .text import normalise_text


async def normalise(
    source_document_id: str,
    data: bytes,
    mime: str,
    *,
    asr: ASRBackend | None = None,
) -> NormalisedContent:
    """Normalise one source document's bytes into anchored text. ``asr`` may be injected (tests use
    a fake); otherwise the config-selected backend is used."""
    if mime.startswith("audio/"):
        return await normalise_audio(source_document_id, data, mime, asr=asr or get_asr())
    if mime.startswith("image/"):
        from .ocr import normalise_image  # lazy: paddle is container-only

        return await normalise_image(source_document_id, data, mime)
    if mime == "application/pdf":
        return await normalise_pdf(source_document_id, data)
    if mime.startswith("text/"):
        return normalise_text(source_document_id, data.decode("utf-8", errors="replace"))

    # Unknown type — retained immutably upstream, but nothing to normalise here.
    return NormalisedContent(
        source_document_id=source_document_id,
        text="",
        language="und",
        spans=[],
        stage="normalise.raw",
        model="none",
        model_version="unsupported",
        meta={"unsupported": mime},
    )
