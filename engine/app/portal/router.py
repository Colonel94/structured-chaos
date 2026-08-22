"""The public portal router — a SEPARATE surface from ``/api`` (PORTAL.md §1–2, §6).

Never accepts ``X-Tenant-Id``: the tenant comes only from the embed key (submit) or the signed case
token (status/answer). Submit returns immediately; the case is created on first contact and processed by
the DURABLE Procrastinate pipeline (``ingest`` enqueues ``normalise`` transactionally, which chains
extract → elicit/rules on the worker), so a transient failure is retried automatically and an exhausted
one is stamped ``processing_failed`` — never silently dropped, never rendered as a finished-but-empty
case. The customer polls a status projection driven by real persisted state. The elicitation policy, the
anchor+2 budget, windowing, and the deadline are all reused — the portal renders, it never decides.

Requires a worker (``scripts/run_worker.py default``) — the same worker the rest of the pipeline uses.
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from ..api.routes import (
    FactoryDep,
    get_factory,
)  # reuse the agent API's factory dep (one test override)
from ..config import settings
from ..obs.logging import get_logger
from ..store.db import tenant_session
from . import store
from .tokens import sign_case_token, verify_case_token

router = APIRouter(prefix="/p")
log = get_logger(__name__)

__all__ = ["get_factory", "router"]

_STATIC = Path(__file__).resolve().parent / "static"

# The edge MIME allowlist — a stranger's phone photo, a screenshot, a voice note (webm/opus on
# Chrome/Android, mp4/aac on Safari/iOS), a PDF, or plain text. Anything else is rejected before work.
_ALLOWED_MIME_PREFIXES = ("image/",)
_ALLOWED_MIME = {
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/aac",
    "audio/x-m4a",
    "application/pdf",
    "text/plain",
}


def _mime_ok(mime: str) -> bool:
    mime = (mime or "").split(";")[0].strip().lower()
    return mime in _ALLOWED_MIME or any(
        mime.startswith(p) for p in _ALLOWED_MIME_PREFIXES
    )


# --------------------------------------------------------------------------- rate limiting (in-memory)


class _SlidingWindow:
    """A per-key sliding-window counter. In-memory ⇒ per-process (honest PoC scope; Redis is the
    multi-instance upgrade). Cost-bearing routes only (submit/answer), never the cheap status poll.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_s: float) -> bool:
        now = time.monotonic()
        dq = self._hits[key]
        cutoff = now - window_s
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


_rate = _SlidingWindow()


def _rate_limit(request: Request, tenant_id: UUID) -> None:
    ip = request.client.host if request.client else "unknown"
    if not _rate.allow(
        f"ip:{ip}", limit=settings.portal_rate_ip_per_10min, window_s=600
    ) or not _rate.allow(
        f"tenant:{tenant_id}", limit=settings.portal_rate_tenant_per_hour, window_s=3600
    ):
        raise HTTPException(
            status_code=429, detail="Too many submissions — please try again shortly."
        )


# --------------------------------------------------------------------------------------- CORS (per tenant)


def _same_origin(request: Request, origin: str) -> bool:
    host = request.headers.get("host", "")
    return origin.endswith("://" + host) if host else False


def _enforce_origin(request: Request, allowed: list[str]) -> str | None:
    """Return the Origin to echo (allowed), or raise 403. A missing Origin (non-browser / same-origin
    GET) is allowed; a browser Origin must be same-origin (the standalone pages) or in the tenant's list.
    """
    origin = request.headers.get("origin")
    if not origin:
        return None
    if _same_origin(request, origin) or origin in allowed:
        return origin
    raise HTTPException(
        status_code=403, detail="This site is not authorised to submit here."
    )


def _cors(resp: Response, origin: str | None) -> Response:
    if origin:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    return resp


# ------------------------------------------------------------------------------------- the pipeline runner


def _log_voice(attachments: list[tuple[str, str, int]]) -> None:
    """Instrument voice submissions (owner directive): container/codec/size — the first real recordings
    through the portal ARE the eval set. No transcript text (no customer data in logs).
    """
    for filename, mime, size in attachments:
        base = (mime or "").split(";")[0].strip().lower()
        if base.startswith("audio/"):
            log.info(
                "voice.submission",
                container=base,
                filename_ext=Path(filename).suffix,
                bytes=size,
            )


# --------------------------------------------------------------------------------------------- routes


@router.post("/submit")
async def submit(
    request: Request,
    factory: FactoryDep,
    key: Annotated[str, Form()] = "",
    text: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006 (FastAPI marker)
) -> Response:
    """A stranger submits their mess. Resolves the tenant from the embed key (never a header), creates the
    case IMMEDIATELY (it exists on first contact), returns a signed token. Processing is durable: the
    ingest below enqueues the normalise→extract→elicit chain on the worker transactionally, so it retries
    on a transient failure and stamps ``processing_failed`` on an exhausted one — no fragile in-process
    task to lose on a restart."""
    resolved = store.resolve_embed_key(key, factory=factory)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Unknown or missing site key.")
    tenant_id, allowed_origins = resolved
    origin = _enforce_origin(request, allowed_origins)
    _rate_limit(request, tenant_id)

    from ..intake.models import InboundAttachment, InboundMessage, guess_mime

    body = text.strip()
    attachments: list[InboundAttachment] = []
    voice_meta: list[tuple[str, str, int]] = []
    total = 0
    for f in files:
        data = await f.read()
        if not data:
            continue
        name = f.filename or "upload"
        mime = f.content_type or guess_mime(name)
        if not _mime_ok(mime):
            raise HTTPException(
                status_code=415, detail=f"Unsupported file type: {mime}"
            )
        if len(data) > settings.portal_max_file_bytes:
            raise HTTPException(
                status_code=413, detail="A file is too large (max 10 MB)."
            )
        total += len(data)
        if total > settings.portal_max_request_bytes:
            raise HTTPException(
                status_code=413, detail="Too much attached (max 25 MB total)."
            )
        attachments.append(InboundAttachment(filename=name, mime=mime, data=data))
        voice_meta.append((name, mime, len(data)))
    if not body and not attachments:
        raise HTTPException(
            status_code=400, detail="Tell us what went wrong, or attach a file."
        )
    _log_voice(voice_meta)

    from ..backends.registry import get_blob
    from ..intake.ingest import ingest_messages

    session_anchor = "web-" + secrets.token_hex(
        8
    )  # stable per-case anchor → windowing links the reply
    msg = InboundMessage(
        channel="web",
        sender=session_anchor,
        sent_at=datetime.now(UTC),
        text=body or None,
        attachments=tuple(attachments),
    )
    # ingest_messages defers the durable normalise job transactionally (intake/ingest.py) — committing
    # the case and enqueuing its pipeline atomically. The worker then chains extract → elicit/rules with
    # retries; nothing to schedule here. If the transaction rolled back, no case and no orphan job exist.
    ing = await ingest_messages(tenant_id, [msg], blob=get_blob(), factory=factory)
    if not ing.case_ids:
        raise HTTPException(status_code=500, detail="Could not create the case.")
    case_id = ing.case_ids[0]
    token = sign_case_token(tenant_id, case_id)
    return _cors(
        JSONResponse({"ref": store._reference(case_id), "token": token}), origin
    )


def _token_or_404(token: str) -> tuple[UUID, UUID]:
    resolved = verify_case_token(token)
    if resolved is None:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    return resolved


@router.get("/case/{token}")
def case_status(token: str, request: Request, factory: FactoryDep) -> Response:
    """Poll the redacted status — read-only, no internal state. RLS-scoped to the token's tenant."""
    tenant_id, case_id = _token_or_404(token)
    with tenant_session(tenant_id, factory=factory) as s:
        status = store.public_status(
            s,
            case_id,
            stall_seconds=settings.portal_stall_seconds,
            worker_liveness_seconds=settings.worker_liveness_seconds,
        )
    if status is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return _cors(JSONResponse(status), request.headers.get("origin"))


@router.post("/case/{token}/answer")
async def answer(
    token: str,
    request: Request,
    factory: FactoryDep,
    answer: Annotated[str, Form()] = "",
) -> Response:
    """The single pending drill answer. Re-ingested as a continuation of the SAME case (windowing on the
    case's contact_ref), then re-extracted on the DURABLE worker chain — the policy issues the next move.
    No portal question logic, no in-process task."""
    tenant_id, case_id = _token_or_404(token)
    _rate_limit(request, tenant_id)
    body = answer.strip()
    if not body:
        raise HTTPException(
            status_code=400, detail="Type your answer, or tap one of the options."
        )

    from ..backends.registry import get_blob
    from ..intake.ingest import ingest_messages
    from ..intake.models import InboundMessage
    from ..store import api

    with tenant_session(tenant_id, factory=factory) as s:
        elicit_state = api.get_case_elicit_state(s, case_id)
    if elicit_state is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    contact_ref = elicit_state[3] or ("web-" + secrets.token_hex(8))

    msg = InboundMessage(
        channel="web",
        sender=contact_ref,  # same anchor → windowing attaches this reply to the open case
        sent_at=datetime.now(UTC),
        text=body,
        attachments=(),
    )
    # Durable again: the re-ingest enqueues normalise→extract→elicit transactionally; the worker advances
    # the drill. The customer's poll picks up the next question (or completion) from persisted state.
    await ingest_messages(tenant_id, [msg], blob=get_blob(), factory=factory)
    return _cors(JSONResponse({"ok": True}), request.headers.get("origin"))


# --------------------------------------------------------------------------- static widget + standalone pages


@router.options("/submit")
@router.options("/case/{token}/answer")
def preflight(request: Request) -> Response:
    """CORS preflight — the tenant isn't known yet (the key is in the body), so reflect the Origin; the
    actual POST enforces the per-tenant allowlist (§6, defence in depth)."""
    origin = request.headers.get("origin")
    resp = Response(status_code=204)
    if origin:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Vary"] = "Origin"
    return resp


@router.get("/embed.js")
def embed_js() -> Response:
    """The widget script — one <script> tag drops it on a host site (served self-contained, cached)."""
    path = _STATIC / "embed.js"
    if not path.exists():
        raise HTTPException(status_code=404, detail="widget not built")
    return FileResponse(path, media_type="application/javascript")


def _standalone_page(mode: str, value: str) -> HTMLResponse:
    """A full-page host for businesses with no website to embed on — same widget, mounted standalone."""
    esc = value.replace('"', "").replace("<", "").replace(">", "")
    # The outer page header reflects the mode: a "check on it" link must not read "Tell us what went wrong".
    head_title, head_sub = (
        ("Your case", "Here's where things stand.")
        if mode == "status"
        else (
            "Tell us what went wrong",
            "No account, no forms. We'll give you a link to check on it.",
        )
    )
    html = (_STATIC / "standalone.html").read_text(encoding="utf-8")
    html = (
        html.replace("__MODE__", mode)
        .replace("__VALUE__", esc)
        .replace("__HEAD_TITLE__", head_title)
        .replace("__HEAD_SUB__", head_sub)
    )
    return HTMLResponse(html)


@router.get("/s/{key}")
def standalone_submit(key: str) -> HTMLResponse:
    """Shareable submit link (a bakery with only an Instagram profile still needs a link)."""
    return _standalone_page("submit", key)


@router.get("/c/{token}")
def standalone_status(token: str) -> HTMLResponse:
    """Shareable 'check on it later' link."""
    return _standalone_page("status", token)
