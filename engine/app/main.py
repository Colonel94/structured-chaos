"""FastAPI headless engine entrypoint.

`/health` is the Phase-0 exit gate; the `/api` review routes (Phase 4.7) are the review UI's read
model. The engine stays headless — these routes are a thin client of the store layer, not app logic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

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


@app.middleware("http")
async def release_headers_and_size_limit(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.api_max_request_bytes:
                return JSONResponse({"detail": "Request is too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length header."}, status_code=400)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; connect-src 'self'; font-src 'self'; "
        "img-src 'self' blob: data:; media-src 'self' blob:; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'",
    )
    if settings.app_env.strip().lower() in ("prod", "production"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


def _worker_health() -> dict[str, object]:
    """Best-effort worker liveness for /health (R3): the newest intake-worker heartbeat and whether it is
    within the liveness window. Never raises — a DB hiccup reports 'unknown', it must not 500 /health.
    """
    from datetime import UTC, datetime

    from sqlalchemy import text

    from .store.db import engine

    try:
        with engine.connect() as conn:
            beat = conn.execute(
                text("SELECT max(beat_at) FROM worker_heartbeat WHERE queue LIKE '%default%'")
            ).scalar()
        if beat is None:
            return {"status": "unknown", "detail": "no heartbeat recorded yet"}
        age = (datetime.now(UTC) - beat).total_seconds()
        alive = age <= settings.worker_liveness_seconds
        return {
            "status": "alive" if alive else "down",
            "last_beat_age_seconds": round(age, 1),
            "liveness_seconds": settings.worker_liveness_seconds,
        }
    except Exception as exc:  # noqa: BLE001 — health must never crash on a DB blip
        return {
            "status": "unknown",
            "detail": f"heartbeat read failed: {type(exc).__name__}",
        }


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness + a readout of which backend impl each interface is wired to + intake-worker liveness."""
    return {
        "status": "ok",
        "env": settings.app_env,
        "backends": {
            "asr": settings.asr_backend,
            "llm": settings.llm_backend,
            "embedding": settings.embedding_backend,
            "blob": settings.blob_backend,
        },
        "worker": _worker_health(),
    }


# Register last so explicit API, health, webhook, and portal routes always win. Local development leaves
# UI_DIST_DIR empty and uses Vite; the release image sets it to the built SPA directory.
if settings.ui_dist_dir:
    ui_dist = Path(settings.ui_dist_dir)
    if not ui_dist.is_dir():
        raise RuntimeError(f"UI_DIST_DIR does not exist: {ui_dist}")
    app.mount("/", StaticFiles(directory=ui_dist, html=True), name="review-ui")
