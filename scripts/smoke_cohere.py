#!/usr/bin/env python
"""Gate A smoke test: Cohere key valid (returns 200).

Run:  uv run --project engine python scripts/smoke_cohere.py
Validates the key against /v1/models (cheap, model-agnostic). The Transcribe Arabic
request shape is exercised for real in Phase 2 / Phase 0.5 with actual audio.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    _load_env()
    key = os.environ.get("COHERE_API_KEY", "")
    if not key:
        print("FAIL: COHERE_API_KEY missing in .env (Gate A #2).")
        return 1
    try:
        r = httpx.get(
            "https://api.cohere.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
    except httpx.HTTPError as e:
        print(f"FAIL: network error calling Cohere: {e}")
        return 1
    if r.status_code == 200:
        print("PASS: Cohere 200; key valid.")
        return 0
    print(f"FAIL: Cohere returned {r.status_code}: {r.text[:300]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
