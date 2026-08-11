#!/usr/bin/env python
"""Gate A #4c: the local extraction LLM (Ollama) returns a completion on the 4070.

Replaces the old cloud `smoke_anthropic.py` (owner override 2026-08-10: LLM path is
local, no API keys). Talks to the Ollama server on the HOST (not the container) — the
GPU-bound model runs on Windows where the CUDA driver lives.

    uv run --project engine python scripts/test_ollama.py
    # or plain:  python scripts/test_ollama.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

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
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
    # A tiny extraction-shaped prompt: force a one-word answer so we can assert on it.
    payload = {
        "model": model,
        "prompt": "Reply with exactly one word: what object does a bakery complaint concern? Answer:",
        "stream": False,
        "options": {"temperature": 0, "num_predict": 16},
    }
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"FAIL(ollama): cannot reach {host} — is `ollama serve` running? {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"FAIL(ollama): {e}")
        return 1

    text = (body.get("response") or "").strip()
    if not text:
        print(f"FAIL(ollama): empty completion from model '{model}'. Raw: {body}")
        return 1
    print(f"PASS(ollama): model '{model}' responded on the 4070.")
    print(f"    prompt→ completion: {text!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
