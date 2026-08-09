"""Deterministic fake backends for tests and the Phase-0 "config loads a fake backend"
exit gate. No network, no keys, no containers — pure and reproducible.
"""

from __future__ import annotations

import hashlib

from .interfaces import Transcript, TranscriptSegment


class FakeASR:
    async def transcribe(self, audio: bytes, *, mime: str) -> Transcript:
        return Transcript(
            language="ar",
            segments=[TranscriptSegment(text="fake transcript", t_start=0.0, t_end=1.0)],
        )


class FakeLLM:
    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return "{}" if schema else "fake completion"


class FakeEmbedding:
    DIM = 1024

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Deterministic pseudo-vector from a hash so dedup tests are reproducible.
        out: list[list[float]] = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            vec = [((h[i % len(h)] / 255.0) * 2 - 1) for i in range(self.DIM)]
            out.append(vec)
        return out


class FakeBlob:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, *, content_type: str) -> str:
        self._store[key] = data
        return key

    async def get(self, key: str) -> bytes:
        return self._store[key]
