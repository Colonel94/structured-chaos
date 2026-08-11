#!/usr/bin/env python
"""Gate A #4b: PaddleOCR (3.x) reads a test image. English-first (owner override 2026-08-12).

CONTAINER ONLY (PREREQUISITES §3: PaddleOCR is painful to install natively on Windows —
run it inside Docker, never on the host).
    docker compose -f deploy/docker-compose.yml run --rm -v "${PWD}/data:/app/data" \
        engine python /app/scripts/test_ocr.py /app/data/smoke/ocr_smoke.png

Default lang="en" → PP-OCRv5 (newer, more accurate). The Arabic path (kept for when the Gulf
moat is re-prioritised) adds ocr_version="PP-OCRv3" (the only version with an Arabic recogniser);
select via env OCR_LANG=ar. NOTE: oneDNN is disabled (FLAGS_use_mkldnn=0) for BOTH langs — the
paddle-3.x PIR/oneDNN inference bug hits every rec model on this build, not just Arabic.
"""

from __future__ import annotations

import os

# Verified live (2026-08-12): the paddle-3.x PIR/oneDNN inference bug
# (ConvertPirAttribute2RuntimeAttribute) hits ALL rec models on this build — English PP-OCRv5
# too, not just Arabic PP-OCRv3. So disable oneDNN unconditionally (must precede paddle import).
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

_OCR_LANG = os.environ.get("OCR_LANG", "en")

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: python scripts/test_ocr.py <image_path>  (env OCR_LANG=en|ar, default en)"
        )
        return 2
    img = Path(sys.argv[1])
    if not img.exists():
        print(f"FAIL: image not found: {img}")
        return 1
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("FAIL: paddleocr not installed. Run inside the container (§3 caution).")
        return 1

    kwargs: dict[str, object] = {"lang": _OCR_LANG, "enable_mkldnn": False}
    if _OCR_LANG != "en":  # Arabic recogniser only lives in PP-OCRv3.
        kwargs["ocr_version"] = "PP-OCRv3"
    ocr = PaddleOCR(**kwargs)
    result = ocr.predict(str(img))
    if not result:
        print("FAIL: PaddleOCR returned no result.")
        return 1
    r0 = result[0]
    texts = list(r0.get("rec_texts", []))
    scores = list(r0.get("rec_scores", []))
    print(f"PASS: PaddleOCR (lang={_OCR_LANG}) read {len(texts)} line(s):")
    for t, s in list(zip(texts, scores))[:10]:
        print(f"    ({s:.2f})  {t}")
    return 0 if texts else 1


if __name__ == "__main__":
    sys.exit(main())
