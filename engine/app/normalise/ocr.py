"""OCR normalisation — photographed/scanned images → text with region provenance (EDD §2.3, §11).

**Container-only** (PaddleOCR, PREREQUISITES §3 — never installed on the Windows host). English-first
(§0, 2026-08-12): default ``lang="en"`` selects PP-OCRv5 (newer/better); ``OCR_LANG=ar`` selects the
Arabic ``PP-OCRv3`` path. Either way ``FLAGS_use_mkldnn=0`` is required to dodge the paddle-3.x
PIR/oneDNN inference bug (verified 2026-08-12: the bug is *not* Arabic-specific).

Each detected line becomes an ``image_region`` span with a pixel ``bbox`` — the OCR region is the
provenance anchor the review screen highlights when a value is clicked (TECH-SPEC §12). Returns
``(text, bbox, confidence)`` triples so callers (image + rasterised-PDF paths) share one shape.
"""

from __future__ import annotations

import os

# Must precede the paddle import (dodges the paddle-3.x PIR/oneDNN bug). Set at import time.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import io
from typing import Any

from ..config import settings
from .models import NormalisedContent, NormalisedSpan

_OCR: Any = None  # cached engine — building a PaddleOCR is expensive


def _engine() -> Any:
    global _OCR
    if _OCR is None:
        from paddleocr import PaddleOCR

        if settings.ocr_lang == "ar":
            # Arabic recogniser ships under PP-OCRv3 only (arabic_PP-OCRv3_mobile_rec).
            _OCR = PaddleOCR(lang="ar", ocr_version="PP-OCRv3", enable_mkldnn=False)
        else:
            _OCR = PaddleOCR(lang=settings.ocr_lang, enable_mkldnn=False)
    return _OCR


def _bbox_of(poly: Any) -> list[float]:
    """Axis-aligned ``[x0, y0, x1, y1]`` enclosing a PaddleOCR quad polygon."""
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return [min(xs), min(ys), max(xs), max(ys)]


def ocr_image_bytes(data: bytes) -> list[tuple[str, list[float], float]]:
    """Run OCR on one image; return ``(text, bbox, confidence)`` per detected line."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    result = _engine().predict(np.asarray(img))
    r0 = result[0] if result else {}
    texts = list(r0.get("rec_texts", []))
    scores = list(r0.get("rec_scores", []))
    polys = list(r0.get("rec_polys", []))
    out: list[tuple[str, list[float], float]] = []
    for i, txt in enumerate(texts):
        t = str(txt).strip()
        if not t:
            continue
        bbox = _bbox_of(polys[i]) if i < len(polys) and len(polys[i]) else [0.0, 0.0, 0.0, 0.0]
        conf = float(scores[i]) if i < len(scores) else float("nan")
        out.append((t, bbox, conf))
    return out


async def normalise_image(source_document_id: str, data: bytes, mime: str) -> NormalisedContent:
    """Normalise one photographed/scanned image into anchored text via OCR."""
    lines = ocr_image_bytes(data)
    spans = [
        NormalisedSpan(text=t, kind="image_region", locator={"bbox": bbox}, confidence=conf)
        for (t, bbox, conf) in lines
    ]
    return NormalisedContent(
        source_document_id=source_document_id,
        text="\n".join(s.text for s in spans),
        language=settings.ocr_lang,
        spans=spans,
        stage="normalise.ocr",
        model="paddleocr",
        model_version="PP-OCRv3" if settings.ocr_lang == "ar" else "PP-OCRv5",
    )
