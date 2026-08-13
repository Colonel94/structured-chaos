"""Phase 3 — multimodal normalisation coverage: photo (OCR) + scanned PDF (GAP-2).

Container-only: PaddleOCR is not installed on the Windows host (PREREQUISITES §3), so these skip
there and run in the container CI where OCR exists — closing the exit-gate gap that the photo/PDF
paths had no automated coverage (they were previously proven by manual container runs only). The
audio path is covered by the fake-ASR unit test in test_normalise.py and proven live on the GPU.
"""

from __future__ import annotations

import io

import pytest

# Skip the whole module unless the OCR engine is installed (container). No DB needed — these exercise
# the normalise modules directly.
pytest.importorskip("paddleocr", reason="OCR is container-only (PaddleOCR)")

from app.normalise.ocr import normalise_image
from app.normalise.pdf import normalise_pdf


def _png(text: str) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (700, 160), "white")
    ImageDraw.Draw(img).text((40, 60), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _image_pdf(text: str) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (700, 200), "white")
    ImageDraw.Draw(img).text((40, 80), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, "PDF")  # image-only PDF → forces the rasterise→OCR path
    return buf.getvalue()


async def test_photo_normalises_to_image_region_spans() -> None:
    c = await normalise_image("img-1", _png("Order 12345 refund please"), "image/png")
    assert c.stage == "normalise.ocr"
    assert c.spans, "expected OCR to detect text"
    assert c.spans[0].kind == "image_region"
    assert "bbox" in c.spans[0].locator  # region-level provenance anchor
    assert c.interface == "ocr" and "wall_ms" in c.usage  # metered
    assert not c.degraded


async def test_scanned_pdf_normalises_via_rasterise_then_ocr() -> None:
    c = await normalise_pdf("pdf-1", _image_pdf("Scanned invoice total 250 AED"))
    assert not c.degraded  # OCR available → completed, not degraded
    assert c.spans and c.spans[0].kind == "image_region"
    assert c.interface == "ocr"
