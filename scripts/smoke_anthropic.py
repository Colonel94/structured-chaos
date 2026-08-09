#!/usr/bin/env python
"""Gate A smoke test: Anthropic key valid + Claude Haiku reachable (returns 200).

Run:  uv run --project engine python scripts/smoke_anthropic.py
Reads ANTHROPIC_API_KEY / ANTHROPIC_MODEL from the repo-root .env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

# Load .env from repo root without a hard dependency on where it's invoked from.
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
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
    if not key:
        print("FAIL: ANTHROPIC_API_KEY missing in .env (Gate A #1).")
        return 1
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "ping"}],
            },
            timeout=30,
        )
    except httpx.HTTPError as e:
        print(f"FAIL: network error calling Anthropic: {e}")
        return 1
    if r.status_code == 200:
        print(f"PASS: Anthropic 200; model '{model}' reachable.")
        return 0
    print(f"FAIL: Anthropic returned {r.status_code}: {r.text[:300]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
