"""Cloud embedding backend — NOT YET IMPLEMENTED (deferred cloud path).

The PoC runs the LOCAL embedding path (BGE-M3 on the RTX 4070, $0). This module exists so that
selecting ``embedding_backend=cloud`` fails with a CLEAR, ACTIONABLE message at startup instead of a
cryptic ``ImportError`` on a missing module — a config switch that throws an import error is not a switch.

Implementing it (a hosted BGE / embedding endpoint for a GPU-less cloud deploy) is metered-cloud work,
gated on the $0 rule + an explicit owner decision. Mirror ``cloud/llm_claude.py`` when the time comes.
"""

from __future__ import annotations

from ...config import Settings

_MSG = (
    "The CLOUD embedding backend is not implemented — the PoC runs local (BGE-M3 on the 4070). "
    "Set EMBEDDING_BACKEND=local, or implement app/backends/cloud/embed_bge.py (a hosted embed endpoint)."
)


class BGEEmbedding:
    """Placeholder for the deferred cloud embedding path. Raises loudly on construction (see module docstring)."""

    def __init__(self, cfg: Settings) -> None:
        raise NotImplementedError(_MSG)
