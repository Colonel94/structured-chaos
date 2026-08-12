"""Phase-0 exit gate: config loads a fake backend; local backends refuse to run (loud stub)."""

import pytest

from app.backends import registry
from app.backends.fake import FakeASR, FakeBlob, FakeEmbedding, FakeLLM
from app.config import Backend, Settings


def _fake_cfg() -> Settings:
    return Settings(
        asr_backend=Backend.fake,
        llm_backend=Backend.fake,
        embedding_backend=Backend.fake,
        blob_backend=Backend.fake,
    )


def test_fake_backends_selected() -> None:
    cfg = _fake_cfg()
    assert isinstance(registry.get_asr(cfg), FakeASR)
    assert isinstance(registry.get_llm(cfg), FakeLLM)
    assert isinstance(registry.get_embedding(cfg), FakeEmbedding)
    assert isinstance(registry.get_blob(cfg), FakeBlob)


def test_local_backends_are_wired() -> None:
    """LOCAL is the PoC's built path now (owner override) — the interfaces resolve to the real
    local impls. Instantiation is cheap: the heavy models load lazily on first call, not here.
    """
    from app.backends.cloud.blob_minio import MinioBlob
    from app.backends.local.asr_whisper import WhisperASR
    from app.backends.local.embed_bge import BGEEmbedding
    from app.backends.local.llm_ollama import OllamaLLM

    cfg = Settings(
        asr_backend=Backend.local,
        llm_backend=Backend.local,
        embedding_backend=Backend.local,
        blob_backend=Backend.local,
    )
    assert isinstance(registry.get_asr(cfg), WhisperASR)
    assert isinstance(registry.get_llm(cfg), OllamaLLM)
    assert isinstance(registry.get_embedding(cfg), BGEEmbedding)
    assert isinstance(registry.get_blob(cfg), MinioBlob)


@pytest.mark.parametrize("getter", ["get_asr", "get_llm", "get_embedding"])
def test_cloud_inference_backends_are_not_built_yet(getter: str) -> None:
    """Selecting `cloud` for ASR/LLM/embed fails loudly — those impls are the deferred path and
    their modules don't exist. This guards against a half-built cloud module silently resolving.
    (Blob's cloud path IS built — MinIO — so it's excluded.)"""
    cfg = Settings(
        asr_backend=Backend.cloud,
        llm_backend=Backend.cloud,
        embedding_backend=Backend.cloud,
        blob_backend=Backend.cloud,
    )
    with pytest.raises(ImportError):
        getattr(registry, getter)(cfg)


@pytest.mark.asyncio
async def test_fake_embedding_is_1024d() -> None:
    vecs = await FakeEmbedding().embed(["hello", "world"])
    assert len(vecs) == 2
    assert all(len(v) == 1024 for v in vecs)  # BGE-M3 dimensionality
