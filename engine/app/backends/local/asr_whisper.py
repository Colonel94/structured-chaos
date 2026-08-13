"""ASR backend — faster-whisper (CTranslate2) on the 4070, CPU fallback.

The model is loaded lazily and cached at class scope (loading large-v3 is expensive; do it once).
Segment-level timestamps come free from faster-whisper and become the audio provenance span. On the
Windows host, GPU use needs the CUDA-12/cuDNN-9 DLLs colocated next to the ct2 module — see
``scripts/cuda_win.py`` (CT2 ignores ``add_dll_directory`` for its lazy cuBLAS load).
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from pathlib import Path
from typing import Any

from ...config import Settings, settings
from ..interfaces import Transcript, TranscriptSegment


def _enable_cuda_win() -> None:
    """Colocate the pip-installed CUDA-12/cuDNN-9 DLLs so CT2 finds them on the Windows host (CT2
    ignores ``add_dll_directory`` for its lazy cuBLAS load — see ``scripts/cuda_win.py``). No-op off
    Windows or when the runtime wheels aren't present. Best-effort: never let this block a CPU run.
    """
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    if scripts.is_dir() and str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        from cuda_win import enable_cuda_win

        enable_cuda_win()
    except Exception:  # noqa: BLE001, S110 — GPU accel is an optimisation; CPU fallback is fine
        pass


class WhisperASR:
    _model: Any = None  # class-scope cache — load large-v3 once
    _device: str = ""  # the device the cached model actually loaded on

    def __init__(self, cfg: Settings = settings) -> None:
        self._model_name = cfg.whisper_model
        self._want_device = cfg.whisper_device  # 'auto' | 'cuda' | 'cpu'
        self.last_usage: dict[str, float] = {}

    def _load(self) -> Any:
        """Load once, cached at class scope. Tries GPU (int8_float16 to fit 12 GB) when asked, then
        falls back to CPU/int8 — a host without the CUDA runtime still transcribes, just slower."""
        if WhisperASR._model is not None:
            return WhisperASR._model
        from faster_whisper import WhisperModel

        attempts = (
            [("cuda", "int8_float16"), ("cpu", "int8")]
            if self._want_device in ("auto", "cuda")
            else [("cpu", "int8")]
        )
        if self._want_device in ("auto", "cuda"):
            _enable_cuda_win()
        last: Exception | None = None
        for device, compute_type in attempts:
            try:
                WhisperASR._model = WhisperModel(
                    self._model_name, device=device, compute_type=compute_type
                )
                WhisperASR._device = device
                return WhisperASR._model
            except Exception as e:  # noqa: BLE001 — try the next device before giving up
                last = e
        raise RuntimeError(f"faster-whisper failed to load on any device: {last}")

    def _transcribe_sync(self, audio: bytes) -> Transcript:
        model = self._load()
        t0 = time.perf_counter()
        # vad_filter=True runs faster-whisper's bundled silero VAD (onnxruntime) — the §4 VAD
        # front-end, without a separate torch dependency: it drops silence and yields cleaner
        # utterance-level segments, which become the audio provenance spans.
        segments, info = model.transcribe(io.BytesIO(audio), beam_size=5, vad_filter=True)
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
