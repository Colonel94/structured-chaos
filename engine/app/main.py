"""FastAPI headless engine entrypoint.

Phase 0 ships only `/health` (Phase-0 exit gate). Real routes/webhooks arrive in Phase 3.
"""

from __future__ import annotations

from fastapi import FastAPI

from .config import settings

app = FastAPI(title="Adaptive Intake Engine", version="0.0.0")


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness + a readout of which backend impl each interface is wired to."""
    return {
        "status": "ok",
        "env": settings.app_env,
        "backends": {
            "asr": settings.asr_backend,
            "llm": settings.llm_backend,
            "embedding": settings.embedding_backend,
            "blob": settings.blob_backend,
        },
    }
