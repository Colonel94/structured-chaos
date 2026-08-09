#!/usr/bin/env python
"""Gate A #4b: PaddleOCR reads a test image (Arabic-capable).

CONTAINER ONLY (PREREQUISITES §3: PaddleOCR is painful to install natively on Windows —
GTK/build deps — run it inside Docker, never on the host).
    docker compose -f deploy/docker-compose.yml run --rm engine \
        python scripts/test_ocr.py path/to/image.png
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/test_ocr.py <image_path>")
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
    ocr = PaddleOCR(use_angle_cls=True, lang="arabic")
    result = ocr.ocr(str(img))
    lines = [ln[1][0] for page in result if page for ln in page]
    print(f"PASS: PaddleOCR read {len(lines)} line(s):")
    for ln in lines[:10]:
        print("   ", ln)
    return 0 if lines else 1


if __name__ == "__main__":
    sys.exit(main())
