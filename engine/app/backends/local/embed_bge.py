"""Embedding backend — BGE-M3 (1024-d) via FlagEmbedding, local on the 4070.

Drives the schema dedup/convergence moat (cosine similarity in pgvector). The model is loaded
lazily and cached at class scope. fp16 to fit VRAM; CPU-capable if no GPU.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ...config import Settings, settings

_DIM = 1024  # BGE-M3 dense dimensionality


class BGEEmbedding:
    _model: Any = None  # class-scope cache — load once

    def __init__(self, cfg: Settings = settings) -> None:
        self._name = cfg.bge_model
        self.last_usage: dict[str, float] = {}

    def _load(self) -> Any:
        if BGEEmbedding._model is None:
            from FlagEmbedding import BGEM3FlagModel

            BGEEmbedding._model = BGEM3FlagModel(self._name, use_fp16=True)
        return BGEEmbedding._model

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        t0 = time.perf_counter()
        out = model.encode(texts, batch_size=12, max_length=512)["dense_vecs"]
        self.last_usage = {
            "wall_ms": (time.perf_counter() - t0) * 1000.0,
            "n_texts": float(len(texts)),
        }
        return [[float(x) for x in vec] for vec in out]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_sync, texts)
