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


def test_local_backend_is_a_loud_stub() -> None:
    cfg = _fake_cfg()
    cfg.asr_backend = Backend.local
    with pytest.raises(NotImplementedError):
        registry.get_asr(cfg)


@pytest.mark.asyncio
async def test_fake_embedding_is_1024d() -> None:
    vecs = await FakeEmbedding().embed(["hello", "world"])
    assert len(vecs) == 2
    assert all(len(v) == 1024 for v in vecs)  # BGE-M3 dimensionality
