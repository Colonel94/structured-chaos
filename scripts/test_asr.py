#!/usr/bin/env python
"""Gate A #4d: faster-whisper loads and transcribes a test clip.

This is a LOAD smoke — proof the product ASR model (WHISPER_MODEL, default large-v3)
initialises and emits a transcript with segment timestamps (the provenance granularity
the trust gate needs). It is NOT the Gulf-Arabic quality proof — that is Phase 0.5, on
real noisy owner recordings (`spike/spike1_asr.py`).

GPU (CUDA 12 + cuDNN 9) is the product path; this script falls back to CPU/int8 if the
CUDA runtime libs are absent, so the smoke still passes on a bare host.

    uv run --project engine --group asr python scripts/test_asr.py <clip.wav|.opus|.m4a>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from cuda_win import enable_cuda_win  # scripts/ is sys.path[0] when run as a script

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _load_model(model_name: str, want_device: str):  # type: ignore[no-untyped-def]
    """Try the requested device; fall back to CPU/int8 so a bare host still smokes."""
    from faster_whisper import WhisperModel

    attempts = []
    if want_device in ("auto", "cuda"):
        attempts.append(("cuda", "float16"))
    attempts.append(("cpu", "int8"))
    last_err: Exception | None = None
    for device, compute in attempts:
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute)
            return model, device, compute
        except Exception as e:  # noqa: BLE001 - CUDA libs missing etc. → try next
            last_err = e
            print(f"    (device={device}/{compute} unavailable: {str(e)[:120]})")
    raise RuntimeError(f"no usable device for faster-whisper: {last_err}")


def main() -> int:
    _load_env()
    if len(sys.argv) < 2:
        print("usage: python scripts/test_asr.py <audio_path>")
        return 2
    clip = Path(sys.argv[1])
    if not clip.exists():
        print(f"FAIL: clip not found: {clip}")
        return 1
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        print(
            "FAIL: faster-whisper not installed. `uv sync --group asr` (or run in-container)."
        )
        return 1

    model_name = os.environ.get("WHISPER_MODEL", "large-v3")
    want_device = os.environ.get("WHISPER_DEVICE", "auto")
    enable_cuda_win()
    print(f"Loading faster-whisper '{model_name}' (requested device={want_device})…")
    model, device, compute = _load_model(model_name, want_device)
    print(f"    loaded on device={device}/{compute}.")

    # CT2 defers cuBLAS/cuDNN loading to inference — so a GPU failure surfaces HERE, not
    # at construction. Force evaluation and fall back to CPU if the CUDA runtime is absent.
    try:
        segments, info = model.transcribe(str(clip), beam_size=5)
        seg_list = list(segments)
    except RuntimeError as e:
        if device == "cuda":
            from faster_whisper import WhisperModel

            print(
                f"    (GPU inference failed: {str(e)[:120]} — falling back to CPU/int8)"
            )
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            device = "cpu"
            segments, info = model.transcribe(str(clip), beam_size=5)
            seg_list = list(segments)
        else:
            raise
    text = " ".join(s.text.strip() for s in seg_list).strip()
    if not text:
        print(f"FAIL: empty transcript (lang={info.language}).")
        return 1
    print(
        f"PASS(asr): {len(seg_list)} segment(s), detected lang={info.language} "
        f"(p={info.language_probability:.2f}), device={device}."
    )
    for s in seg_list[:8]:
        print(f"    [{s.start:6.2f}→{s.end:6.2f}]  {s.text.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
