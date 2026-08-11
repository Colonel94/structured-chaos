#!/usr/bin/env python
"""Phase 0.5 — Spike 2: photographed, stamped, bilingual document -> readable fields.

THROWAWAY. The vision path's riskiest proof. Takes a REAL angled/stamped Arabic-English
photo (or PDF), renders if needed (pypdfium2), runs PaddleOCR (arabic), and prints the
detected text + bounding boxes (region-level provenance). Eyeball: does the overlap +
skew + glare defeat it, or does it read? (BUILD-PLAN Phase 0.5, proof #2.)

CONTAINER ONLY (PaddleOCR — PREREQUISITES §3). Mount data/ so the photo is reachable:
    docker compose --env-file .env -f deploy/docker-compose.yml run --rm \
      -v "${PWD}/data:/app/data" engine python spike/spike2_doc.py data/spike/docs/doc_01.jpg
"""

from __future__ import annotations

import os

# Must precede the paddle import (dodges the paddle-3.x PIR/oneDNN bug on PP-OCRv3 rec).
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _render_pdf_to_image(pdf: Path) -> Path:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    page = doc[0]
    bitmap = page.render(scale=200 / 72)  # ~200 DPI
    img = bitmap.to_pil()
    out = pdf.with_suffix(".page1.png")
    img.save(out)
    print(f"  (rendered {pdf.name} page 1 -> {out.name} @200dpi)")
    return out


def main() -> int:
    default = ROOT / "data" / "spike" / "docs" / "doc_01.jpg"
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not target.exists():
        print(f"STAGED (not proven): no document at {target}.")
        print(
            "  Gate-A5 owner task — photograph 1 stamped bilingual doc (angled, glare,"
        )
        print(
            "  stamp overlapping text) per docs/recording-guide.md. Do NOT mark green."
        )
        return 2
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("FAIL: paddleocr not installed. Run inside the container (§3).")
        return 1

    img = _render_pdf_to_image(target) if target.suffix.lower() == ".pdf" else target
    # paddleocr 3.x: Arabic = arabic_PP-OCRv3_mobile_rec via lang="ar"+ocr_version="PP-OCRv3".
    ocr = PaddleOCR(lang="ar", ocr_version="PP-OCRv3", enable_mkldnn=False)
    result = ocr.predict(str(img))
    r0 = result[0] if result else {}
    texts = list(r0.get("rec_texts", []))
    scores = list(r0.get("rec_scores", []))
    polys = list(r0.get("rec_polys", []))
    if not texts:
        print(
            "RED: PaddleOCR returned 0 lines — the vision path does NOT read this doc as-is."
        )
        print(
            "  Plan change candidate: try a vision-LLM (llama3.2-vision) fallback. Record in §0."
        )
        return 1
    print(
        f"PASS(read {len(texts)} line(s)) — text + confidence + bbox (region provenance):"
    )
    for i, text in enumerate(texts[:25]):
        conf = scores[i] if i < len(scores) else float("nan")
        xy = polys[i][0] if i < len(polys) and len(polys[i]) else (0, 0)
        print(f"  ({conf:.2f}) @[{int(xy[0])},{int(xy[1])}]  {text}")
    print(
        "\nEYEBALL: are the bilingual fields legible despite stamp/skew/glare? Record verdict in §0."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
