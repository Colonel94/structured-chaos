"""Backend selection by config.

Cloud impls are built in Phase 2; local impls are stubs that raise `NotImplementedError`
(the PoC never runs local — TECH-SPEC §0.1); fake impls power tests and the Phase-0 gate.
Selecting `local` today is intentionally loud, so nobody ships a half-built local path.
"""

from __future__ import annotations

from typing import NoReturn, cast

from ..config import Backend, Settings, settings
from . import fake
from .interfaces import ASRBackend, BlobStore, EmbeddingBackend, LLMBackend


def _stub(name: str) -> NoReturn:
    raise NotImplementedError(
        f"{name} local backend is deferred to clinic customer #1 (TECH-SPEC §0.1). "
        f"Set the *_BACKEND to 'cloud' or 'fake'."
    )


def get_asr(cfg: Settings = settings) -> ASRBackend:
    match cfg.asr_backend:
        case Backend.fake:
            return fake.FakeASR()
        case Backend.cloud:
            from .cloud.asr_cohere import CohereASR  # Phase 2

            return cast(ASRBackend, CohereASR(cfg))
        case Backend.local:
            _stub("ASR")


def get_llm(cfg: Settings = settings) -> LLMBackend:
    match cfg.llm_backend:
        case Backend.fake:
            return fake.FakeLLM()
        case Backend.cloud:
            from .cloud.llm_claude import ClaudeLLM  # Phase 2

            return cast(LLMBackend, ClaudeLLM(cfg))
        case Backend.local:
            _stub("LLM")


def get_embedding(cfg: Settings = settings) -> EmbeddingBackend:
    match cfg.embedding_backend:
        case Backend.fake:
            return fake.FakeEmbedding()
        case Backend.cloud:
            from .cloud.embed_bge import BGEEmbedding  # Phase 2

            return cast(EmbeddingBackend, BGEEmbedding(cfg))
        case Backend.local:
            _stub("Embedding")


def get_blob(cfg: Settings = settings) -> BlobStore:
    # Blob storage is infra (S3 API), not an inference model — MinIO serves both the local
    # (on-prem MinIO) and cloud (S3) deployments; only the endpoint differs. So there is no
    # "half-built local path" to guard against here: local and cloud both use MinioBlob.
    match cfg.blob_backend:
        case Backend.fake:
            return fake.FakeBlob()
        case Backend.cloud | Backend.local:
            from .cloud.blob_minio import MinioBlob

            return cast(BlobStore, MinioBlob(cfg))
