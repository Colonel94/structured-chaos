"""Backend selection by config.

LOCAL impls are the PoC's primary path (owner override 2026-08-10): faster-whisper (ASR),
Ollama (LLM), BGE-M3 (embeddings), MinIO (blob). CLOUD impls stay behind the same interfaces as
the deferred path (some not built yet → their lazy import raises loudly if `cloud` is selected).
`fake` impls power tests and the Phase-0 gate.
"""

from __future__ import annotations

from typing import cast

from ..config import Backend, Settings, settings
from . import fake
from .interfaces import ASRBackend, BlobStore, EmbeddingBackend, LLMBackend


def get_asr(cfg: Settings = settings) -> ASRBackend:
    match cfg.asr_backend:
        case Backend.fake:
            return fake.FakeASR()
        case Backend.local:
            from .local.asr_whisper import WhisperASR

            return cast(ASRBackend, WhisperASR(cfg))
        case Backend.cloud:
            from .cloud.asr_cohere import CohereASR  # deferred cloud path

            return cast(ASRBackend, CohereASR(cfg))


def get_llm(cfg: Settings = settings) -> LLMBackend:
    match cfg.llm_backend:
        case Backend.fake:
            return fake.FakeLLM()
        case Backend.local:
            from .local.llm_ollama import OllamaLLM

            return cast(LLMBackend, OllamaLLM(cfg))
        case Backend.cloud:
            from .cloud.llm_claude import ClaudeLLM  # deferred cloud path

            return cast(LLMBackend, ClaudeLLM(cfg))


def get_embedding(cfg: Settings = settings) -> EmbeddingBackend:
    match cfg.embedding_backend:
        case Backend.fake:
            return fake.FakeEmbedding()
        case Backend.local:
            from .local.embed_bge import BGEEmbedding

            return cast(EmbeddingBackend, BGEEmbedding(cfg))
        case Backend.cloud:
            from .cloud.embed_bge import BGEEmbedding as CloudBGE  # deferred cloud path

            return cast(EmbeddingBackend, CloudBGE(cfg))


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
