"""Phase 3 — normalisation router: text / audio / unknown, and provenance-span shapes (EDD §2.3).

No DB. Audio uses the fake ASR backend (deterministic). OCR/PDF-image paths are container-only
(PaddleOCR) and are exercised in the container, not here.
"""

from __future__ import annotations

from app.backends.fake import FakeASR
from app.normalise.router import normalise


async def test_text_passthrough_has_char_range_span() -> None:
    c = await normalise("doc-1", b"delivery was late", "text/plain")
    assert c.stage == "normalise.text"
    assert c.text == "delivery was late"
    assert len(c.spans) == 1
    span = c.spans[0]
    assert span.kind == "char_range"
    assert span.locator == {"char_start": 0, "char_end": len("delivery was late")}


async def test_audio_produces_segment_spans_with_time_locators() -> None:
    c = await normalise("doc-2", b"AUDIO", "audio/ogg", asr=FakeASR())
    assert c.stage == "normalise.audio"
    assert c.model == "faster-whisper"
    assert c.spans, "expected at least one audio segment span"
    span = c.spans[0]
    assert span.kind == "audio_segment"
    assert set(span.locator) == {"t_start", "t_end"}


async def test_unknown_mime_degrades_not_raises() -> None:
    c = await normalise("doc-3", b"\x00\x01\x02", "application/octet-stream")
    assert c.stage == "normalise.raw"
    assert c.text == ""
    assert c.meta.get("unsupported") == "application/octet-stream"


async def test_text_via_router_from_bytes_decodes_utf8() -> None:
    c = await normalise("doc-4", "café münü".encode(), "text/plain")
    assert c.text == "café münü"
