"""LLM extraction backend — a quantized instruct model via Ollama on the 4070.

qwen3:14b is a *reasoning* model that emits ``<think>…`` blocks; for extraction we disable that
(``think: false``) so the output is the answer, not the monologue. ``temperature: 0`` for
determinism. When a JSON schema is supplied, Ollama constrains the output to it (structured
extraction). ``last_usage`` carries prompt/eval token counts + wall time for the cost meter.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ...config import Settings, settings


class OllamaLLM:
    def __init__(self, cfg: Settings = settings) -> None:
        self._host = cfg.ollama_host.rstrip("/")
        self._model = cfg.ollama_model
        self.last_usage: dict[str, float] = {}

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,  # qwen3 is a reasoning model — suppress the <think> block for extraction
            # temperature 0 = greedy (verified deterministic, R7 2026-08-17); the explicit seed hardens
            # that against any future Ollama batching/kv-cache change — determinism is a trust-gate
            # (idempotent replay must re-extract identically), not just a convenience.
            "options": {"temperature": 0, "seed": 0},
        }
        if schema is not None:
            payload["format"] = schema  # constrain output to the JSON schema
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self._host}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        self.last_usage = {
            "wall_ms": (time.perf_counter() - t0) * 1000.0,
            "tokens_in": float(data.get("prompt_eval_count", 0)),
            "tokens_out": float(data.get("eval_count", 0)),
        }
        content: str = data["message"]["content"]
        return content
