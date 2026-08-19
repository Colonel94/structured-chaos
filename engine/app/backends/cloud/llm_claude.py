"""Cloud LLM extraction backend — Claude Haiku 4.5 via the Anthropic API (the deferred cloud path).

Same ``LLMBackend`` interface as the local Ollama backend (``complete(prompt, *, schema) -> str``), so
the extractor is unchanged — only the config-switched backend differs (CLAUDE.md §4, dual-deployment). The
PoC runs LOCAL on the 4070 by default; this path is stood up to TEST whether a more accurate extractor
lifts the Phase-6 confidence ceiling (the local qwen3 caps category accuracy at ~81%, which blocks the
≥98% auto-route gate). Metered API spend across the ~200 eval cases is the one sanctioned cost (§Directive 2).

Structured output: Anthropic's ``output_config.format`` (json_schema) constrains the response to valid JSON,
the cloud analogue of Ollama's grammar-constrained ``format``. The incoming schema (built for llama.cpp) is
adapted here — Anthropic requires ``additionalProperties: false`` on every object — so callers pass the same
schema to either backend. temperature 0 for determinism (Haiku 4.5 still accepts sampling params). Model id
+ pricing verified against the claude-api skill (``claude-haiku-4-5``, $1/$5 per MTok, 2026-06-24).
"""

from __future__ import annotations

import time
from typing import Any

from ...config import Settings, settings


def _strict_objects(node: object) -> object:
    """Recursively set ``additionalProperties: false`` on every object schema — Anthropic structured
    outputs require it (the local/llama.cpp path does not). Pure transform; the original is untouched.
    """
    if isinstance(node, dict):
        out: dict[str, object] = {k: _strict_objects(v) for k, v in node.items()}
        if out.get("type") == "object" or "properties" in out:
            out.setdefault("additionalProperties", False)
        return out
    if isinstance(node, list):
        return [_strict_objects(x) for x in node]
    return node


class ClaudeLLM:
    """Anthropic Messages API backend. Lazy-imports the SDK so a local-only checkout never needs it."""

    def __init__(self, cfg: Settings = settings) -> None:
        import anthropic

        # api_key="" → the SDK resolves ANTHROPIC_API_KEY / an `ant` profile from the environment.
        self._client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key or None)
        self._model = cfg.anthropic_model
        self.last_usage: dict[str, float] = {}

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 2048,
            "temperature": 0,  # deterministic extraction, mirroring the local greedy path
            "messages": [{"role": "user", "content": prompt}],
        }
        if schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": _strict_objects(schema)}
            }
        t0 = time.perf_counter()
        resp = await self._client.messages.create(**kwargs)
        self.last_usage = {
            "wall_ms": (time.perf_counter() - t0) * 1000.0,
            "tokens_in": float(getattr(resp.usage, "input_tokens", 0) or 0),
            "tokens_out": float(getattr(resp.usage, "output_tokens", 0) or 0),
        }
        # With output_config.format the first block is text carrying valid JSON. Be defensive: return the
        # first text block's text, else an empty string (the extractor already handles non-JSON as a
        # fully-flagged empty result).
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                return str(block.text)
        return ""
