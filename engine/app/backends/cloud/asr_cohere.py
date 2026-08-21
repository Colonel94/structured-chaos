"""Cloud ASR backend — NOT YET IMPLEMENTED (deferred cloud path).

The PoC runs the LOCAL ASR path (faster-whisper on the RTX 4070, $0). This module exists so that
selecting ``asr_backend=cloud`` fails with a CLEAR, ACTIONABLE message at startup instead of a cryptic
``ImportError`` on a missing module — a config switch that throws an import error is not a switch.

Implementing it (a hosted speech-to-text endpoint for a GPU-less cloud deploy) is metered-cloud work,
gated on the $0 rule + an explicit owner decision. Mirror ``cloud/llm_claude.py`` when the time comes.
"""

from __future__ import annotations

from ...config import Settings

_MSG = (
    "The CLOUD ASR backend is not implemented — the PoC runs local (faster-whisper on the 4070). "
    "Set ASR_BACKEND=local, or implement app/backends/cloud/asr_cohere.py (a hosted STT endpoint)."
)


class CohereASR:
    """Placeholder for the deferred cloud ASR path. Raises loudly on construction (see module docstring)."""

    def __init__(self, cfg: Settings) -> None:
        raise NotImplementedError(_MSG)
