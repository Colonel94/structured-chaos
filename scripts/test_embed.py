#!/usr/bin/env python
"""Gate A #4a: BGE-M3 embeds a test string (1024-d). Run in the container (or a box with
the `embed` group installed): `uv run --project engine --group embed python scripts/test_embed.py`.
BGE-M3 is CPU-capable; no GPU required for the PoC.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError:
        print("FAIL: FlagEmbedding not installed. Install the `embed` group or run in-container.")
        return 1
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
    out = model.encode(["مرحبا، طلبي وصل متأخر", "the cake arrived melted"])
    dense = out["dense_vecs"]
    dim = len(dense[0])
    print(f"PASS: BGE-M3 embedded 2 strings; dim={dim} (expected 1024).")
    return 0 if dim == 1024 else 1


if __name__ == "__main__":
    sys.exit(main())
