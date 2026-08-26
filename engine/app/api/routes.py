"""Review-view HTTP routes — the engine's first client reads the assembled case (Phase 4.7).

Every review request is scoped by an authenticated session whose membership supplies both tenant and
reviewer identity. RLS remains the database isolation boundary. A legacy ``X-Tenant-Id`` path is kept
only outside production so the established integration harness can exercise the API without accounts.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from threading import Lock
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .. import review_auth
from ..config import settings
from ..report import (
    NotCommittedError,
    ReportBackendUnavailable,
    html_to_pdf,
    render_case_html,
    render_register_csv,
)
from ..store import api
from ..store.db import SessionFactory, tenant_session

router = APIRouter(prefix="/api")

# The grace window during which a fresh approval can be undone (api.uncommit_case). Lets the review UI
# commit on a single keystroke — the fast path — with a brief, honest "undo" instead of the slower
# arm/confirm two-step. Server-authoritative: past this, the approval is durable (DESIGN.md §10).
UNDO_WINDOW_SECONDS = 15


class CorrectionIn(BaseModel):
    """A reviewer's edit to one field — appended to the correction log (never overwrites), then the
    projection is rebuilt and the deterministic decision recomputed off the corrected governed core.
    """

    field_path: str
    new_value: Any = None
    reviewer_id: str
    note: str | None = None


class CommitIn(BaseModel):
    """The human-approval act — who is approving. Turns on the commit gate (a report may then issue).

    ``review_ms``/``fields_edited`` are the CLIENT-measured cost of clearing this case (only the browser
    knows when a human actually started looking). Optional so a non-instrumented caller still commits; when
    present they are logged once (``review_event``) for the ≤30s review-time gate (winning-condition §4).
    """

    reviewer_id: str
    review_ms: int | None = None
    fields_edited: int = 0


class FeedbackIn(BaseModel):
    """A reviewer's verdict on the model's extraction — the feedback loop, independent of field edits and
    approval. ``verdict`` is accurate/inaccurate/partial; ``comment`` is the optional why (what the model
    missed/nailed) that guides the next prompt/policy fix."""

    reviewer_id: str
    verdict: str
    comment: str | None = None


class SignupIn(BaseModel):
    email: str
    password: str
    display_name: str
    workspace_name: str


class LoginIn(BaseModel):
    email: str
    password: str


def get_factory() -> sessionmaker[Session]:
    """The app-role session factory — overridden in tests to bind the per-test engine."""
    return SessionFactory


FactoryDep = Annotated[sessionmaker[Session], Depends(get_factory)]


def _production() -> bool:
    return settings.app_env.strip().lower() in ("prod", "production")


def get_request_identity(
    request: Request,
    factory: FactoryDep,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> review_auth.Identity | UUID:
    """Resolve a real session, or the explicit dev-only tenant compatibility path."""
    raw_session = request.cookies.get(review_auth.SESSION_COOKIE, "")
    if raw_session:
        identity = review_auth.resolve_session(factory, raw_session)
        if identity is None:
            raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            cookie_csrf = request.cookies.get(review_auth.CSRF_COOKIE, "")
            if (
                not cookie_csrf
                or not x_csrf_token
                or cookie_csrf != x_csrf_token
                or not review_auth.valid_csrf(factory, raw_session, x_csrf_token)
            ):
                raise HTTPException(
                    status_code=403, detail="Invalid request token. Refresh and retry."
                )
        return identity
    if x_tenant_id and not _production():
        try:
            return UUID(x_tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="X-Tenant-Id is not a valid UUID") from None
    raise HTTPException(status_code=401, detail="Sign in to open a review workspace.")


IdentityDep = Annotated[review_auth.Identity | UUID, Depends(get_request_identity)]


def get_request_tenant(identity: IdentityDep) -> str:
    return str(identity.tenant_id if isinstance(identity, review_auth.Identity) else identity)


def get_request_reviewer(identity: IdentityDep) -> str | None:
    return identity.display_name if isinstance(identity, review_auth.Identity) else None


TenantHeader = Annotated[str, Depends(get_request_tenant)]
ReviewerDep = Annotated[str | None, Depends(get_request_reviewer)]


def _auth_payload(identity: review_auth.Identity) -> dict[str, Any]:
    return {
        "authenticated": True,
        "user": {
            "id": str(identity.user_id),
            "email": identity.email,
            "display_name": identity.display_name,
        },
        "workspace": {
            "id": str(identity.tenant_id),
            "name": identity.workspace_name,
            "role": identity.role,
        },
    }


def _set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    secure = _production()
    response.set_cookie(
        review_auth.SESSION_COOKIE,
        session_token,
        max_age=12 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        review_auth.CSRF_COOKIE,
        csrf_token,
        max_age=12 * 60 * 60,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )


_auth_hits: dict[str, deque[float]] = defaultdict(deque)
_auth_hits_lock = Lock()


def _limit_auth(request: Request) -> None:
    """Bound password-hash work per process/IP. The deployment edge adds the global limit."""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _auth_hits_lock:
        hits = _auth_hits[ip]
        while hits and hits[0] < now - 600:
            hits.popleft()
        if len(hits) >= 20:
            raise HTTPException(
                status_code=429, detail="Too many sign-in attempts. Try again later."
            )
        hits.append(now)


@router.post("/auth/signup")
def signup(body: SignupIn, request: Request, factory: FactoryDep) -> Response:
    _limit_auth(request)
    if not settings.auth_allow_signup:
        raise HTTPException(status_code=403, detail="Account creation is disabled.")
    try:
        identity, session_token, csrf_token = review_auth.create_account(
            factory,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            workspace=body.workspace_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="An account already exists for this email."
        ) from None
    response = JSONResponse(_auth_payload(identity), status_code=201)
    _set_auth_cookies(response, session_token, csrf_token)
    return response


@router.post("/auth/login")
def auth_login(body: LoginIn, request: Request, factory: FactoryDep) -> Response:
    _limit_auth(request)
    try:
        result = review_auth.login(factory, email=body.email, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if result is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    identity, session_token, csrf_token = result
    response = JSONResponse(_auth_payload(identity))
    _set_auth_cookies(response, session_token, csrf_token)
    return response


@router.get("/auth/session")
def auth_session(identity: IdentityDep) -> dict[str, Any]:
    if not isinstance(identity, review_auth.Identity):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return _auth_payload(identity)


@router.post("/auth/logout")
def auth_logout(request: Request, factory: FactoryDep, identity: IdentityDep) -> Response:
    del identity  # authentication + CSRF are enforced by the dependency
    raw_session = request.cookies.get(review_auth.SESSION_COOKIE, "")
    if raw_session:
        review_auth.revoke_session(factory, raw_session)
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(review_auth.SESSION_COOKIE, path="/")
    response.delete_cookie(review_auth.CSRF_COOKIE, path="/")
    return response


def _tenant(x_tenant_id: str) -> UUID:
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Tenant-Id is not a valid UUID") from None


def _case_uuid(case_id: str) -> UUID:
    try:
        return UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="case_id is not a valid UUID") from None


async def _bounded_upload(file: UploadFile, remaining: int) -> bytes:
    if remaining <= 0:
        raise HTTPException(status_code=413, detail="Uploads exceed the 25 MB request limit.")
    data = await file.read(remaining + 1)
    if len(data) > remaining:
        raise HTTPException(status_code=413, detail="Uploads exceed the 25 MB request limit.")
    return data


def _supported_intake_mime(mime: str) -> bool:
    base = mime.split(";", 1)[0].strip().lower()
    return base.startswith(("image/", "audio/")) or base in {"application/pdf", "text/plain"}


@router.get("/cases")
def list_cases(x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """The register: recent cases for the tenant with a light summary."""
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        return {"cases": api.list_cases(s)}


@router.post("/ingest")
async def ingest_case(
    x_tenant_id: TenantHeader,
    factory: FactoryDep,
    text: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006 (FastAPI reads this marker)
) -> Response:
    """Self-serve intake: a stranger submits their messiest real case — pasted text and/or dropped files
    (a WhatsApp export, a photo, a PDF, a voice note) — and gets back a fully structured case, with no
    developer in the room (winning-condition §2/§8; closes the "no product surface" red flag §7).

    Persists the case and immutable sources, then returns as soon as the durable normalise job is committed.
    The worker owns the single production path from normalise → extract → rules + elicitation. Keeping GPU,
    ASR and OCR work out of the HTTP request prevents timeouts and avoids running a second copy of jobs that
    intake already enqueued transactionally. The review client polls the case until its decision is ready.
    Tenant-scoped by the authenticated workspace (RLS); first-contact time is recorded before this returns."""
    from ..backends.registry import get_blob
    from ..intake.ingest import ingest_messages
    from ..intake.models import InboundAttachment, InboundMessage, guess_mime

    tenant = _tenant(x_tenant_id)
    body = text.strip()
    attachments: list[InboundAttachment] = []
    total_bytes = len(body.encode("utf-8"))
    for f in files:
        data = await _bounded_upload(f, settings.api_max_request_bytes - total_bytes)
        if not data:
            continue
        name = f.filename or "upload"
        mime = f.content_type or guess_mime(name)
        if not _supported_intake_mime(mime):
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {mime}")
        total_bytes += len(data)
        attachments.append(InboundAttachment(filename=name, mime=mime, data=data))
    if not body and not attachments:
        raise HTTPException(status_code=400, detail="provide text or at least one file")

    blob = get_blob()
    msg = InboundMessage(
        channel="file_drop",
        sender="",  # a web drop has no anchor phone; resolution degrades to open questions (§5 fallback)
        sent_at=datetime.now(UTC),  # the clock starts at first contact — now (§3)
        text=body or None,
        attachments=tuple(attachments),
    )
    res = await ingest_messages(tenant, [msg], blob=blob, factory=factory)
    return JSONResponse(
        {
            "case_ids": [str(c) for c in res.case_ids],
            "status": "queued",
        },
        status_code=202,
    )


@router.post("/objects")
async def upload_objects(
    x_tenant_id: TenantHeader,
    factory: FactoryDep,
    file: Annotated[UploadFile, File()],
    object_type: Annotated[str, Form()] = "object",
) -> dict[str, Any]:
    """Self-serve object store: connect your orders/bookings/assets by dropping a CSV/JSON/JSONL export
    (winning-condition §2 — self-serve, inside the 10 minutes, by file upload). The profiler discovers
    the identifier columns itself; no schema is declared. Once loaded, the objects resolve the ANCHOR on
    a case so the drill looks facts up instead of asking (Moment 3). Idempotent — re-uploading the same
    export is a no-op (the object content-hash is unique per tenant)."""
    from ..backends.registry import get_embedding
    from ..resolve import ingest_object_collection
    from ..resolve.upload import ObjectFileError, parse_object_file

    data = await _bounded_upload(file, settings.api_max_request_bytes)
    if not data:
        raise HTTPException(status_code=400, detail="the uploaded file is empty")
    try:
        objects = parse_object_file(file.filename or "upload", data)
    except ObjectFileError as exc:
        raise HTTPException(status_code=400, detail=f"could not read the file: {exc}") from None
    otype = object_type.strip() or "object"
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        result = await ingest_object_collection(
            s, object_type=otype, objects=objects, embedder=get_embedding()
        )
        total = api.count_objects(s, object_type=otype)
    return {
        "object_type": result.object_type,
        "ingested": result.ingested,
        "duplicates": result.duplicates,
        "keys_indexed": result.keys_indexed,
        "embedded": result.embedded,
        "key_fields": result.key_fields,
        "total": total,
    }


@router.get("/cases/{case_id}")
def get_case(case_id: str, x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """One case's full review payload. 404 if the case is absent for this tenant (RLS fail-closed)."""
    cid = _case_uuid(case_id)
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        review = api.get_case_review(s, cid)
    if review is None:
        raise HTTPException(status_code=404, detail="case not found")
    return review


@router.post("/cases/{case_id}/corrections")
def post_correction(
    case_id: str,
    body: CorrectionIn,
    x_tenant_id: TenantHeader,
    reviewer: ReviewerDep,
    factory: FactoryDep,
) -> dict[str, Any]:
    """Record a reviewer's correction to one field, rebuild the projection, and recompute the
    deterministic decision (a governed-signal change re-derives priority/SLA — §16.2). Returns the
    refreshed review. Rejected (409) once a case is committed: approval is final (§3)."""
    cid = _case_uuid(case_id)
    tid = _tenant(x_tenant_id)
    with tenant_session(tid, factory=factory) as s:
        if api.get_case_channel(s, cid) is None:  # None ⇒ absent for this tenant (RLS fail-closed)
            raise HTTPException(status_code=404, detail="case not found")
        if api.commit_status(s, cid) is not None:
            raise HTTPException(
                status_code=409, detail="case is committed — corrections are closed"
            )
        prev = api.get_field_values(s, cid, [body.field_path]).get(body.field_path)
        based_on = api.get_latest_extraction_id(s, cid, body.field_path)
        api.record_correction(
            s,
            case_id=cid,
            field_path=body.field_path,
            prev_value=prev,
            new_value=body.new_value,
            based_on_extraction_id=based_on,
            reviewer_id=reviewer or body.reviewer_id,
            note=body.note,
        )
        api.rebuild_field_current(s, cid)
    # Recompute off the corrected governed core (own transaction; idempotent — a no-op if the decision
    # inputs did not move). Same inputs+policy → identical decision (§3 determinism).
    from ..rules.stage import decide_case

    decide_case(tid, cid, factory=factory)
    with tenant_session(tid, factory=factory) as s:
        review = api.get_case_review(s, cid)
    if review is None:
        raise HTTPException(status_code=404, detail="case not found")
    return review


@router.post("/cases/{case_id}/commit")
def post_commit(
    case_id: str,
    body: CommitIn,
    x_tenant_id: TenantHeader,
    reviewer: ReviewerDep,
    factory: FactoryDep,
) -> dict[str, Any]:
    """Approve a case (the commit gate). One-way + idempotent: a re-commit returns the original stamp,
    never re-attributing it. After this, and only after this, a report may be issued (§3). The measured
    review time is logged once (for the ≤30s gate). Returns the undo window so the UI can offer a brief,
    honest undo of a fresh, accidental approval."""
    cid = _case_uuid(case_id)
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        reviewer_id = reviewer or body.reviewer_id
        if api.get_case_channel(s, cid) is None:
            raise HTTPException(status_code=404, detail="case not found")
        if api.get_case_decision(s, cid) is None:
            raise HTTPException(
                status_code=409,
                detail="case processing is not complete — approval is not available yet",
            )
        result = api.commit_case(s, cid, reviewer_id=reviewer_id)
        if result is None:  # defensive: the existence check above and commit share this transaction
            raise HTTPException(status_code=409, detail="case cannot be approved")
        api.record_review_event(
            s,
            case_id=cid,
            reviewer_id=reviewer_id,
            review_ms=body.review_ms,
            fields_edited=body.fields_edited,
        )
    return {"commit": result, "undo_window_seconds": UNDO_WINDOW_SECONDS}


@router.post("/cases/{case_id}/uncommit")
def post_uncommit(
    case_id: str, body: CommitIn, x_tenant_id: TenantHeader, factory: FactoryDep
) -> dict[str, Any]:
    """Undo a just-approved case within the grace window (``UNDO_WINDOW_SECONDS``). 409 if the case is not
    committed or the window has passed (the approval is durable); 404 if absent for this tenant. This is
    what makes single-keystroke commit safe — an accidental approval is reversible for a few seconds, and
    permanent after (DESIGN.md §10)."""
    cid = _case_uuid(case_id)
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        if api.get_case_channel(s, cid) is None:  # None ⇒ absent for this tenant (RLS fail-closed)
            raise HTTPException(status_code=404, detail="case not found")
        result = api.uncommit_case(s, cid, window_seconds=UNDO_WINDOW_SECONDS)
    if result is None:
        raise HTTPException(
            status_code=409, detail="approval is final — the undo window has passed"
        )
    return {"uncommitted": result}


_FEEDBACK_VERDICTS = frozenset({"accurate", "inaccurate", "partial"})


@router.post("/cases/{case_id}/feedback")
def post_feedback(
    case_id: str,
    body: FeedbackIn,
    x_tenant_id: TenantHeader,
    reviewer: ReviewerDep,
    factory: FactoryDep,
) -> dict[str, Any]:
    """Record a reviewer's verdict on the model's extraction for this case — the feedback loop. Distinct
    from a field correction (which fixes a value) and from approval: it's the qualitative signal ("what did
    the model get right/wrong and why") that a human uses to tune prompts/policies ($0). Append-only;
    allowed on any case (even committed — feedback on the model is not the same as re-opening the record).
    404 if the case is absent for this tenant (RLS fail-closed); 400 on an unknown verdict."""
    cid = _case_uuid(case_id)
    verdict = body.verdict.strip().lower()
    if verdict not in _FEEDBACK_VERDICTS:
        raise HTTPException(
            status_code=400, detail=f"verdict must be one of {sorted(_FEEDBACK_VERDICTS)}"
        )
    comment = (body.comment or "").strip() or None
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        if api.get_case_channel(s, cid) is None:  # None ⇒ absent for this tenant (RLS fail-closed)
            raise HTTPException(status_code=404, detail="case not found")
        entry = api.record_case_feedback(
            s,
            case_id=cid,
            reviewer_id=reviewer or body.reviewer_id,
            verdict=verdict,
            comment=comment,
        )
    return {"feedback": entry}


@router.get("/feedback")
def get_feedback(x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """The feedback loop's OUTPUT for this tenant — a verdict tally + recent entries (newest first), the
    queue an engineer works from to pick the next prompt/policy fix. This is 'where the feedback goes'.
    """
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        return api.recent_feedback(s)


@router.get("/tuning-digest")
def get_tuning_digest(x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """The feedback loop's ACTIONABLE end — recurring correction transitions (which boundary reviewers keep
    re-drawing), per-field edit pressure + time, the feedback tally/notes, and the headline review median,
    in one view. Turns the accumulated signal into 'what to fix next' so the next prompt fix picks itself
    (surfaced for a human — never auto-applied). See ``api.tuning_digest`` for the honest caveats.
    """
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        return api.tuning_digest(s)


@router.post("/tuning-digest/draft")
async def post_tuning_draft(x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """Pre-draft a reviewable prompt-delta from the tuning digest, using the LOCAL model ($0). The digest
    is read in-transaction; the (slow) model call runs outside it. Always returns the honest caveats; the
    ``draft`` is None when there is no signal yet or the model output was unusable. NEVER applies anything —
    shipping a prompt change is a human editing prompt.py + re-running the eval (CLAUDE.md §10)."""
    from ..backends.registry import get_llm
    from ..extract.prompt_tuning import draft_prompt_delta

    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        digest = api.tuning_digest(s)
    return await draft_prompt_delta(digest, llm=get_llm())


@router.get("/review-stats")
def get_review_stats(x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """The tenant's review-time aggregates — count, median/p90 ms, avg fields edited. The load-bearing
    ≤30s gate lives here (winning-condition §4)."""
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        return api.review_stats(s)


@router.get("/review-breakdown")
def get_review_breakdown(x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """WHICH corrections are costing the review time — per field, how many approved cases corrected it and
    the median review time of those cases (slowest first). The diagnostic that turns the single median into
    an actionable "where is it going" when it comes back high. Correlational (see ``api.review_breakdown``).
    """
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        return {"fields": api.review_breakdown(s)}


@router.get("/field-options")
def get_field_options() -> dict[str, list[str]]:
    """The allowed values for each closed-vocabulary governed field — the source of the review UI's one-key
    correction picks. Sourced from the extraction schema so the picks can never drift from what the model
    is constrained to emit. Not tenant data (a fixed universal vocabulary), so no header needed."""
    from ..extract.schema import DESIRED_OUTCOMES, EMOTIONS, SEVERITIES, TAXONOMY

    return {
        "category": list(TAXONOMY),
        "desired_outcome": list(DESIRED_OUTCOMES),
        "emotion_signal": list(EMOTIONS),
        "severity_signal": list(SEVERITIES),
    }


@router.get("/cases/{case_id}/report.pdf")
def get_case_report(case_id: str, x_tenant_id: TenantHeader, factory: FactoryDep) -> Response:
    """The per-case PDF report — issued ONLY for an approved case (409 otherwise). The HTML is assembled
    in-transaction (RLS); the PDF is rendered outside it. 503 when the container-only backend is absent.
    """
    cid = _case_uuid(case_id)
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        try:
            html = render_case_html(s, cid)
        except NotCommittedError:
            raise HTTPException(status_code=409, detail="case is not approved") from None
        except LookupError:
            raise HTTPException(status_code=404, detail="case not found") from None
    try:
        pdf = html_to_pdf(html)
    except ReportBackendUnavailable:
        raise HTTPException(
            status_code=503, detail="PDF backend unavailable (report is container-only)"
        ) from None
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="case-{cid}.pdf"'},
    )


@router.get("/cases.csv")
def get_register_csv(x_tenant_id: TenantHeader, factory: FactoryDep) -> Response:
    """The universal manager register as CSV (internal operator list; not gated on approval)."""
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        csv_text = render_register_csv(s)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="register.csv"'},
    )


@router.get("/docs/{doc_id}")
async def get_source_doc(doc_id: str, x_tenant_id: TenantHeader, factory: FactoryDep) -> Response:
    """Stream an original source document (audio/image) so a reviewer can click a value through to its
    exact source. RLS-scoped: a doc outside the tenant reads as 404, never a cross-tenant blob leak.
    """
    try:
        did = UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="doc_id is not a valid UUID") from None
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        ref = api.get_source_blob_ref(s, did)
    if ref is None:
        raise HTTPException(status_code=404, detail="source document not found")
    blob_key, mime = ref
    from ..backends.registry import get_blob

    data = await get_blob().get(blob_key)
    return Response(content=data, media_type=mime)
