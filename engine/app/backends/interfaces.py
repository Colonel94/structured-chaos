"""The four backend interfaces (Protocols).

The engine depends only on these shapes; cloud/local/fake impls are selected by config
(registry.py). This is the seam that makes the same engine run in-region on a 4070 with
no external call, or in cloud/metered mode, with zero code change (CLAUDE.md §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    t_start: float  # seconds — segment-level provenance (cloud ASR has no word timestamps)
    t_end: float


@dataclass(frozen=True)
class Transcript:
    language: str
    segments: list[TranscriptSegment]

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)


@runtime_checkable
class ASRBackend(Protocol):
    """Audio bytes -> transcript with segment timestamps."""

    async def transcribe(self, audio: bytes, *, mime: str) -> Transcript: ...


@runtime_checkable
class LLMBackend(Protocol):
    """Prompt (+ optional JSON schema) -> model output. Extraction/semantic discovery only."""

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str: ...


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Text -> dense vector (BGE-M3: 1024-d). Drives schema dedup/convergence."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class BlobStore(Protocol):
    """Content-addressed immutable blob storage (originals retained forever)."""

    async def put(self, key: str, data: bytes, *, content_type: str) -> str: ...
    async def get(self, key: str) -> bytes: ...


@runtime_checkable
class Channel(Protocol):
    """Egress — send a message back to a customer, returning the channel's message ref. The local
    PoC records-and-relays ($0, no live transport); the cloud impl (WhatsApp Cloud API) is the
    deferred path, same interface. Only the elicitation drill (deterministic, budgeted) is sent this
    way; resolutions/reports still gate on human approval (Phase 7)."""

    async def send(self, *, recipient: str, text: str) -> str: ...
