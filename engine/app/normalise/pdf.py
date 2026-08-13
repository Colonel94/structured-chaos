"""PDF normalisation — digital text layer, with a rasterise→OCR fallback (EDD §2.3, §11).

Two kinds of PDF arrive: a *digital* PDF with a real text layer (forwarded invoice/receipt), and a
*photographed/scanned* PDF that is really an image (the stamped bilingual doc of Phase 0.5). We try
the text layer first with **pdfplumber** (MIT — never PyMuPDF/AGPL), giving ``{page, bbox}`` spans
straight from the layout. If there is effectively no text layer, we rasterise each page with
**pypdfium2** (BSD/Apache) and hand the page images to OCR — the vision path.

OCR is container-only (PaddleOCR, PREREQUISITES §3). On a host without it, a scanned PDF is returned
``degraded`` (with any partial text and an ``meta['ocr']='unavailable'`` note) rather than crashing —
the pipeline then leaves the normalise stage re-claimable so a later container run actually OCRs it,
instead of committing an empty result as done (H3).
"""

from __future__ import annotations

import io
import re
import time

from ..config import settings
from ..obs.logging import get_logger
from .models import NormalisedContent, NormalisedSpan

log = get_logger(__name__)

# Below this many characters of *meaningful* text (boilerplate stripped), treat the PDF as image-only
# and rasterise. Raised from a naive 16 so a scanned PDF carrying only a scanner footer/watermark is
# not mistaken for a digital one (H4).
_TEXT_LAYER_MIN_CHARS = 40
# Cap pages rasterised/OCR'd so a 500-page scan can't OOM the worker (L5). Logged, never silent.
_MAX_OCR_PAGES = 20
# Scanner apps stamp a footer/watermark into an otherwise image-only PDF's text layer — strip it
# before deciding "is there a real digital text layer?" (H4: "Scanned by CamScanner" = 21 chars).
_SCANNER_BOILERPLATE = re.compile(r"scanned by |cam\s?scanner|created with", re.IGNORECASE)


def _meaningful(text: str) -> str:
    """Text minus known scanner boilerplate lines — what actually counts as a digital text layer."""
    return "\n".join(
        ln for ln in text.splitlines() if ln.strip() and not _SCANNER_BOILERPLATE.search(ln)
    ).strip()


def _rasterise_pages(data: bytes, *, dpi: int = 200) -> list[bytes]:
    """Render each PDF page (capped at ``_MAX_OCR_PAGES``) to a PNG byte-string (~200 DPI) for the
    OCR/vision path. Guarded import — a host without pypdfium2 raises, handled by the caller."""
    import pypdfium2 as pdfium

    out: list[bytes] = []
    doc = pdfium.PdfDocument(io.BytesIO(data))
    try:
        n = len(doc)
        if n > _MAX_OCR_PAGES:
            log.info("normalise.pdf.page_cap", total=n, capped_to=_MAX_OCR_PAGES)
        for i in range(min(n, _MAX_OCR_PAGES)):
            bitmap = doc[i].render(scale=dpi / 72)
            buf = io.BytesIO()
            bitmap.to_pil().save(buf, format="PNG")
            out.append(buf.getvalue())
    finally:
        doc.close()
    return out


def _text_layer(data: bytes) -> tuple[str, list[NormalisedSpan]]:
    """Extract the digital text layer as line-level ``{page, bbox}`` spans (empty if none)."""
    import pdfplumber

    spans: list[NormalisedSpan] = []
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            for line in page.extract_text_lines():
                txt = str(line.get("text", "")).strip()
                if not txt:
                    continue
                spans.append(
                    NormalisedSpan(
                        text=txt,
                        kind="pdf_text",
                        locator={
                            "page": page.page_number,
                            "bbox": [
                                float(line["x0"]),
                                float(line["top"]),
                                float(line["x1"]),
                                float(line["bottom"]),
                            ],
                        },
                    )
                )
                parts.append(txt)
    return "\n".join(parts), spans


async def normalise_pdf(source_document_id: str, data: bytes) -> NormalisedContent:
    """Normalise a PDF: digital text layer if present, else rasterise pages and OCR them.

    A PDF whose text layer is only scanner boilerplate (or nothing) is treated as image-only. If OCR
    is unavailable on this host, the result is marked ``degraded`` so the pipeline leaves the stage
    re-claimable and a later container run actually OCRs it (H3) — while still returning any text we
    did extract rather than discarding it (M5)."""
    text, spans = _text_layer(data)
    if len(_meaningful(text)) >= _TEXT_LAYER_MIN_CHARS:
        return NormalisedContent(
            source_document_id=source_document_id,
            text=text,
            language="und",
            spans=spans,
            stage="normalise.pdf",
            model="pdfplumber",
            model_version="text-layer",
        )

    # Image-only (or footer-only) PDF → rasterise + OCR each page (OCR is container-only).
    try:
        page_pngs = _rasterise_pages(data)
    except Exception as e:  # noqa: BLE001 — pypdfium2 absent / unrenderable PDF (L5)
        return _degraded(
            source_document_id, text, spans, {"pdf": f"rasterise_failed: {type(e).__name__}"}
        )

    # OCR availability must be tested at CALL time, not import time: `app.normalise.ocr` imports fine
    # on a host without paddle (paddle is loaded lazily inside the engine), so the ImportError only
    # surfaces when we actually run OCR. Catch it here → DEGRADED, so a container re-run re-OCRs (H3),
    # keeping any text we did extract (M5).
    try:
        from .ocr import ocr_image_bytes

        t0 = time.perf_counter()
        ocr_spans: list[NormalisedSpan] = []
        parts = []
        for page_no, png in enumerate(page_pngs, start=1):
            for line, bbox, conf in ocr_image_bytes(png):
                ocr_spans.append(
                    NormalisedSpan(
                        text=line,
                        kind="image_region",
                        locator={"page": page_no, "bbox": bbox},
                        confidence=conf,
                    )
                )
                parts.append(line)
    except Exception:  # noqa: BLE001 — OCR unavailable on this host / OCR engine failure
        return _degraded(
            source_document_id, text, spans, {"ocr": "unavailable", "pages": str(len(page_pngs))}
        )
    return NormalisedContent(
        source_document_id=source_document_id,
        text="\n".join(parts),
        language=settings.ocr_lang,
        spans=ocr_spans,
        stage="normalise.pdf",
        model="pypdfium2+paddleocr",
        model_version="scanned",
        usage={"wall_ms": (time.perf_counter() - t0) * 1000.0},
        interface="ocr",
    )


def _degraded(
    source_document_id: str, text: str, spans: list[NormalisedSpan], meta: dict[str, str]
) -> NormalisedContent:
    """A PDF we could not fully normalise (couldn't rasterise, or OCR unavailable). Keep any text we
    extracted (M5) and mark ``degraded`` so the pipeline leaves the stage re-claimable (H3)."""
    return NormalisedContent(
        source_document_id=source_document_id,
        text=text,
        language="und",
        spans=spans,
        stage="normalise.pdf",
        model="pdfplumber+pypdfium2",
        model_version="scanned",
        meta=meta,
        degraded=True,
    )
