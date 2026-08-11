"""Make faster-whisper / CTranslate2 find the pip-installed CUDA 12 runtime on Windows.

Why this exists: CT2 loads cuBLAS/cuDNN lazily at inference via the standard Windows DLL
search, which does NOT honour `os.add_dll_directory` for its case — but it DOES find DLLs
sitting next to its own extension module (that is how it ships cudnn64_9.dll). So we both
register the nvidia `*/bin` dirs AND copy the cuBLAS/nvrtc DLLs next to the ctranslate2
module if missing. Idempotent; a no-op on non-Windows or when the wheels aren't installed.

Install the runtime once:  uv pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12>=9,<10"
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def enable_cuda_win() -> str:
    """Return 'ready' if the CUDA DLLs are in place (or not needed), else 'unavailable'."""
    if os.name != "nt":
        return "ready"  # Linux/container: rely on the image's CUDA libs / CPU.
    try:
        import nvidia  # namespace pkg from nvidia-cublas-cu12 / nvidia-cudnn-cu12
    except ImportError:
        return "unavailable"  # no runtime wheels → caller falls back to CPU.

    nvidia_bins: list[Path] = []
    for root in list(getattr(nvidia, "__path__", [])):
        rp = Path(root)
        if not rp.is_dir():
            continue
        for child in rp.iterdir():
            b = child / "bin"
            if b.is_dir():
                nvidia_bins.append(b)
                try:
                    os.add_dll_directory(str(b))
                except OSError:
                    pass  # dir vanished between listdir and add — harmless.

    # Colocate the DLLs next to the ct2 module (the search path CT2 actually honours).
    try:
        import ctranslate2
    except ImportError:
        return (
            "ready"  # ct2 absent → the add_dll_directory calls above are all we can do.
        )
    ct2_dir = Path(ctranslate2.__file__).parent
    for b in nvidia_bins:
        for dll in b.glob("*.dll"):
            dest = ct2_dir / dll.name
            if not dest.exists():
                try:
                    shutil.copy2(dll, dest)
                except OSError:
                    pass  # best-effort; add_dll_directory is the fallback.
    return "ready"
