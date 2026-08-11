#!/usr/bin/env python
"""Phase 0.5 — Spike 1: real noisy Gulf voice note -> usable transcript.

THROWAWAY. The ASR moat's riskiest proof. Runs faster-whisper (large-v3) over the
owner-recorded Gulf-Arabic notes in data/spike/audio/ and prints the transcript with
segment timestamps so a human can eyeball: is it usable on REAL noisy code-switched
audio, or unusable? (BUILD-PLAN Phase 0.5, proof #1.)

Runs on the HOST (GPU if CUDA 12 + cuDNN 9 present, else CPU fallback).
    uv run --project engine --group asr python spike/spike1_asr.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT / "data" / "spike" / "audio"
EXTS = (".opus", ".ogg", ".m4a", ".wav", ".mp3")


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
    from faster_whisper import WhisperModel

    attempts = [("cuda", "float16")] if want_device in ("auto", "cuda") else []
    attempts.append(("cpu", "int8"))
    last: Exception | None = None
    for device, compute in attempts:
        try:
            return WhisperModel(model_name, device=device, compute_type=compute), device
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"    (device={device}/{compute} unavailable: {str(e)[:100]})")
    raise RuntimeError(f"no usable device: {last}")


def main() -> int:
    _load_env()
    clips = (
        sorted(p for p in AUDIO_DIR.glob("*") if p.suffix.lower() in EXTS)
        if AUDIO_DIR.exists()
        else []
    )
    if not clips:
        print(f"STAGED (not proven): no recordings in {AUDIO_DIR}.")
        print("  This is the Gate-A5 owner task — record 3–5 noisy Gulf voice notes")
        print(
            "  per docs/recording-guide.md, drop them here, then re-run. Do NOT mark green."
        )
        return 2
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        print("FAIL: faster-whisper not installed. `uv sync --group asr`.")
        return 1

    sys.path.insert(0, str(ROOT / "scripts"))
    from cuda_win import enable_cuda_win

    enable_cuda_win()
    model_name = os.environ.get("WHISPER_MODEL", "large-v3")
    print(f"Loading faster-whisper '{model_name}'…")
    model, device = _load_model(model_name, os.environ.get("WHISPER_DEVICE", "auto"))
    print(f"    device={device}. {len(clips)} clip(s) to transcribe.\n")

    for clip in clips:
        try:
            segments, info = model.transcribe(str(clip), beam_size=5)
            seg_list = list(segments)
        except RuntimeError as e:
            if device == "cuda":
                from faster_whisper import WhisperModel

                print(
                    f"  (GPU inference failed: {str(e)[:100]} — reloading on CPU/int8)"
                )
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                device = "cpu"
                segments, info = model.transcribe(str(clip), beam_size=5)
                seg_list = list(segments)
            else:
                raise
        print(
            f"=== {clip.name}  (lang={info.language} p={info.language_probability:.2f}) ==="
        )
        for s in seg_list:
            print(f"  [{s.start:6.2f}→{s.end:6.2f}]  {s.text.strip()}")
        print()
    print(
        "EYEBALL THE ABOVE: usable on real noisy Gulf/code-switched audio? Record verdict in §0."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
