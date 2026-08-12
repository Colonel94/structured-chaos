"""ASR backend — faster-whisper (CTranslate2) on the 4070, CPU fallback.

The model is loaded lazily and cached at class scope (loading large-v3 is expensive; do it once).
Segment-level timestamps come free from faster-whisper and become the audio provenance span. On the
Windows host, GPU use needs the CUDA-12/cuDNN-9 DLLs colocated next to the ct2 module — see
``scripts/cuda_win.py`` (CT2 ignores ``add_dll_directory`` for its lazy cuBLAS load).
"""

from __future__ import annotations

import asyncio
import io
import time
from typing import Any

from ...config import Settings, settings
from ..interfaces import Transcript, TranscriptSegment


class WhisperASR:
    _model: Any = None  # class-scope cache — load large-v3 once

    def __init__(self, cfg: Settings = settings) -> None:
        self._model_name = cfg.whisper_model
        self._device = cfg.whisper_device
        self.last_usage: dict[str, float] = {}

    def _load(self) -> Any:
        if WhisperASR._model is None:
            from faster_whisper import WhisperModel

            if self._device == "cpu":
                device, compute_type = "cpu", "int8"
            else:  # auto / cuda → GPU with int8_float16 to fit 12 GB
                device, compute_type = "cuda", "int8_float16"
            WhisperASR._model = WhisperModel(
                self._model_name, device=device, compute_type=compute_type
            )
        return WhisperASR._model

    def _transcribe_sync(self, audio: bytes) -> Transcript:
        model = self._load()
        t0 = time.perf_counter()
        segments, info = model.transcribe(io.BytesIO(audio), beam_size=5)
        segs = [
            TranscriptSegment(text=s.text.strip(), t_start=float(s.start), t_end=float(s.end))
            for s in segments
        ]
        self.last_usage = {
            "wall_ms": (time.perf_counter() - t0) * 1000.0,
            "audio_seconds": float(info.duration),
        }
        return Transcript(language=info.language, segments=segs)

    async def transcribe(self, audio: bytes, *, mime: str) -> Transcript:
        # faster-whisper is synchronous/CPU-GPU bound → offload so we never block the event loop.
        return await asyncio.to_thread(self._transcribe_sync, audio)
