"""FastAPI headless engine entrypoint.

`/health` is the Phase-0 exit gate; the `/api` review routes (Phase 4.7) are the review UI's read
model. The engine stays headless — these routes are a thin client of the store layer, not app logic.
"""

from __future__ import annotations

from fastapi import FastAPI

from .api.routes import router as api_router
from .api.whatsapp import router as whatsapp_router
from .config import settings

app = FastAPI(title="Adaptive Intake Engine", version="0.0.0")
app.include_router(api_router)
app.include_router(whatsapp_router)  # WhatsApp Cloud API webhook (verify + inbound)

# The customer-facing portal is a SEPARATE public surface, mounted ONLY when explicitly enabled
# (fail-closed) — so the unauthenticated /p routes never exist by accident on an agent-only deployment.
if settings.portal_enabled:
    from .portal.router import router as portal_router

    app.include_router(portal_router)


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
