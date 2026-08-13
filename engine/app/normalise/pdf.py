"""PDF normalisation — digital text layer, with a rasterise→OCR fallback (EDD §2.3, §11).

Two kinds of PDF arrive: a *digital* PDF with a real text layer (forwarded invoice/receipt), and a
*photographed/scanned* PDF that is really an image (the stamped bilingual doc of Phase 0.5). We try
the text layer first with **pdfplumber** (MIT — never PyMuPDF/AGPL), giving ``{page, bbox}`` spans
straight from the layout. If there is effectively no text layer, we rasterise each page with
**pypdfium2** (BSD/Apache) and hand the page images to OCR — the vision path.

OCR is container-only (PaddleOCR, PREREQUISITES §3). On a host without it, a scanned PDF degrades to
empty text with a ``meta['ocr']='unavailable'`` note rather than crashing — the original is still
stored immutably and can be re-normalised in the container.
"""

from __future__ import annotations

import io

from ..config import settings
from .models import NormalisedContent, NormalisedSpan

# Below this many characters of extractable text, we treat the PDF as image-only and rasterise.
_TEXT_LAYER_MIN_CHARS = 16


def _rasterise_pages(data: bytes, *, dpi: int = 200) -> list[bytes]:
    """Render each PDF page to a PNG byte-string (~200 DPI) for the OCR/vision path."""
    import pypdfium2 as pdfium

    out: list[bytes] = []
    doc = pdfium.PdfDocument(io.BytesIO(data))
    try:
        for page in doc:
            bitmap = page.render(scale=dpi / 72)
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
    """Normalise a PDF: text layer if present, else rasterise pages and OCR them."""
    text, spans = _text_layer(data)
    if len(text) >= _TEXT_LAYER_MIN_CHARS:
        return NormalisedContent(
            source_document_id=source_document_id,
            text=text,
            language="und",
            spans=spans,
            stage="normalise.pdf",
            model="pdfplumber",
            model_version="text-layer",
        )

    # Image-only PDF → rasterise + OCR each page (container-only).
    try:
        from .ocr import ocr_image_bytes
    except Exception:  # noqa: BLE001 — paddle import guard, handled below
        ocr_image_bytes = None  # type: ignore[assignment]

    page_pngs = _rasterise_pages(data)
    if ocr_image_bytes is None:
        return NormalisedContent(
            source_document_id=source_document_id,
            text="",
            language="und",
            spans=[],
            stage="normalise.pdf",
            model="pdfplumber+pypdfium2",
            model_version="scanned",
            meta={"ocr": "unavailable", "pages": str(len(page_pngs))},
        )

    ocr_spans: list[NormalisedSpan] = []
    parts = []
    for page_no, png in enumerate(page_pngs, start=1):
        result = ocr_image_bytes(png)
        for line, bbox, conf in result:
            ocr_spans.append(
                NormalisedSpan(
                    text=line,
                    kind="image_region",
                    locator={"page": page_no, "bbox": bbox},
                    confidence=conf,
                )
            )
            parts.append(line)
    return NormalisedContent(
        source_document_id=source_document_id,
        text="\n".join(parts),
        language=settings.ocr_lang,
        spans=ocr_spans,
        stage="normalise.pdf",
        model="pypdfium2+paddleocr",
        model_version="scanned",
    )
