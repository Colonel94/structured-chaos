"""Phase 7 — per-field span attribution (the click-to-trace trust gate, §3).

Pure/deterministic (no DB): a value is located in the case's normalised content and its citation carries
the exact span — sentence char-range (text), audio segment, or image region — with a whole-document
fallback when the value is not a verbatim quote, so provenance is never lost.
"""

from __future__ import annotations

from uuid import uuid4

from app.extract.provenance import build_field_citations


def _text_doc(did: object, text: str) -> dict[str, object]:
    return {"source_document_id": str(did), "mime": "text/plain", "text": text, "spans": []}


def test_text_value_gets_exact_char_offsets() -> None:
    did = uuid4()
    docs = [_text_doc(did, "order 4471 arrived crushed and late, I want a refund")]
    cites = build_field_citations("refund", docs, fallback_docs=[did])
    assert len(cites) == 1
    loc = cites[0].locator
    assert loc is not None
    start, end = loc["char_start"], loc["char_end"]
    assert docs[0]["text"][start:end] == "refund"  # offsets land on the value exactly


def test_multi_doc_offsets_account_for_the_join_separator() -> None:
    d0, d1 = uuid4(), uuid4()
    docs = [_text_doc(d0, "first message"), _text_doc(d1, "second says refund please")]
    cites = build_field_citations("refund", docs, fallback_docs=[d0, d1])
    loc = cites[0].locator
    assert loc is not None
    # concatenation is "first message\nsecond says refund please" — the offset is into THAT.
    concat = "first message\nsecond says refund please"
    assert concat[loc["char_start"] : loc["char_end"]] == "refund"
    assert cites[0].source_document_id == d1


def test_audio_value_returns_the_segment_time_range() -> None:
    did = uuid4()
    docs = [
        {
            "source_document_id": str(did),
            "mime": "audio/wav",
            "text": "the cake was crushed",
            "spans": [
                {
                    "text": "the cake",
                    "kind": "audio_segment",
                    "locator": {"t_start": 0.0, "t_end": 1.2},
                },
                {
                    "text": "was crushed",
                    "kind": "audio_segment",
                    "locator": {"t_start": 1.2, "t_end": 2.6},
                },
            ],
        }
    ]
    cites = build_field_citations("crushed", docs, fallback_docs=[did])
    assert cites[0].locator == {"t_start": 1.2, "t_end": 2.6}  # the segment that contains the word


def test_image_value_returns_the_region_bbox() -> None:
    did = uuid4()
    docs = [
        {
            "source_document_id": str(did),
            "mime": "image/png",
            "text": "invoice total 250",
            "spans": [
                {
                    "text": "invoice total 250",
                    "kind": "image_region",
                    "locator": {"bbox": [10, 20, 90, 40]},
                }
            ],
        }
    ]
    cites = build_field_citations("250", docs, fallback_docs=[did])
    assert cites[0].locator == {"bbox": [10, 20, 90, 40]}


def test_inferred_value_falls_back_to_whole_document_citations() -> None:
    """A category enum ("product_fault") is inferred, not quoted — no span, but provenance is kept."""
    d0, d1 = uuid4(), uuid4()
    docs = [_text_doc(d0, "the cake arrived crushed"), _text_doc(d1, "photo attached")]
    cites = build_field_citations("product_fault", docs, fallback_docs=[d0, d1])
    assert [c.source_document_id for c in cites] == [d0, d1]
    assert all(c.locator is None for c in cites)  # un-highlighted, never lost
