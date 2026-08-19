"""Per-field span attribution — map an extracted value to its EXACT source span (Phase 7, §3).

The trust gate: click any value → the exact sentence, audio segment, or image region it came from, in
under five seconds. Extraction gives values; this locates each one deterministically in the case's
normalised content (no model call), so the citation carries a precise ``locator`` instead of pointing
at the whole document:

- **text source** → ``{char_start, char_end}`` of the value's occurrence in the concatenated normalised
  text (the exact offsets the review UI highlights — sentence/phrase granularity).
- **audio source** → the ``{t_start, t_end}`` of the utterance span whose transcript contains the value
  (segment-level, the accepted PoC granularity — EDD §16.9).
- **image source** → the ``{bbox}`` of the OCR region whose text contains the value.

Offsets are computed against the SAME ordered, ``text <> ''`` document list the store concatenates for
``get_case_normalised_text`` (joined with ``"\\n"``), so a text char range lines up with what the UI
renders. A value that does not appear verbatim (an inferred enum like a category label — not a quote)
yields no span; the caller falls back to a whole-document citation, so provenance is never lost, only
un-highlighted where highlighting would be dishonest.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ..store.api import Citation


def _locate(
    value: str, docs_spans: list[dict[str, Any]]
) -> tuple[UUID, dict[str, Any] | None] | None:
    """Find the value's source span across the case's documents, or None if it appears nowhere verbatim.

    ``base`` tracks the value's offset in the CONCATENATED normalised text ("\\n"-joined, matching
    ``get_case_normalised_text``), so a text match returns offsets valid against what the UI renders.
    """
    needle = value.strip()
    if not needle:
        return None
    low = needle.lower()
    base = 0
    for i, doc in enumerate(docs_spans):
        if i > 0:
            base += 1  # the "\n" separator the store joins documents with
        doc_text = str(doc["text"])
        did = UUID(str(doc["source_document_id"]))
        mime = str(doc["mime"])
        if mime.startswith(("audio/", "image/")):
            # Multi-span source: match within a span → return that span's own locator (segment/region).
            for span in doc.get("spans") or []:
                span_text = str(span.get("text", ""))
                if span_text and low in span_text.lower():
                    locator = span.get("locator")
                    return did, dict(locator) if isinstance(locator, dict) else None
        else:
            idx = doc_text.lower().find(low)
            if idx >= 0:
                return did, {"char_start": base + idx, "char_end": base + idx + len(needle)}
        base += len(doc_text)
    return None


def build_field_citations(
    value: object,
    docs_spans: list[dict[str, Any]],
    *,
    fallback_docs: list[UUID],
) -> list[Citation]:
    """The provenance citations for one extracted value: a single precise ``primary`` citation when the
    value is located in the source, else whole-document ``primary`` citations (provenance is never lost).
    """
    if isinstance(value, str):
        hit = _locate(value, docs_spans)
        if hit is not None:
            did, locator = hit
            return [Citation(source_document_id=did, role="primary", locator=locator)]
    return [Citation(source_document_id=d, role="primary") for d in fallback_docs]
