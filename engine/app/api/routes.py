"""Review-view HTTP routes — the engine's first client reads the assembled case (Phase 4.7).

Two read-only endpoints under ``/api``: a case register and one case's full review payload (governed
core + emergent + provenance + corrections + the normalised text that backs it). Everything is
RLS-scoped: the tenant comes from the ``X-Tenant-Id`` header and is set as the transaction GUC, so a
query can only ever read that tenant's rows — a wrong id reads nothing (fail-closed), never a leak.

The tenant header is the **PoC** convention (operator-facing review tool, manual tenant onboarding —
CLAUDE.md §9); real auth mapping a session→tenant is later. RLS, not the header, is the isolation
boundary. The session factory is a FastAPI dependency so tests can bind it to their per-test engine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

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


class CorrectionIn(BaseModel):
    """A reviewer's edit to one field — appended to the correction log (never overwrites), then the
    projection is rebuilt and the deterministic decision recomputed off the corrected governed core.
    """

    field_path: str
    new_value: Any = None
    reviewer_id: str
    note: str | None = None


class CommitIn(BaseModel):
    """The human-approval act — who is approving. Turns on the commit gate (a report may then issue)."""

    reviewer_id: str


def get_factory() -> sessionmaker[Session]:
    """The app-role session factory — overridden in tests to bind the per-test engine."""
    return SessionFactory


# FastAPI dependency aliases via Annotated (the B008-safe idiom — the marker lives in the type, not
# a mutable default). ``TenantHeader`` is required, so a missing header is a 422 before any DB touch.
TenantHeader = Annotated[str, Header(alias="X-Tenant-Id")]
FactoryDep = Annotated[sessionmaker[Session], Depends(get_factory)]


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
) -> dict[str, Any]:
    """Self-serve intake: a stranger submits their messiest real case — pasted text and/or dropped files
    (a WhatsApp export, a photo, a PDF, a voice note) — and gets back a fully structured case, with no
    developer in the room (winning-condition §2/§8; closes the "no product surface" red flag §7).

    Runs the REAL pipeline inline so the result is immediate: ingest (immutable content-addressed source
    docs) → normalise (transcribe/OCR/text + provenance spans) → extract (governed core + emergent, with
    per-field provenance) → the deterministic priority/SLA decision → elicitation (records the anchor+2
    drill). Tenant-scoped via ``X-Tenant-Id`` (RLS); the case then appears in the review queue. p50 ≈ one
    extraction (~7-10s local), well inside the ≤60s gate."""
    from ..backends.registry import get_blob, get_llm
    from ..elicit.stage import elicit_case
    from ..extract.stage import extract_case
    from ..intake.ingest import ingest_messages
    from ..intake.models import InboundAttachment, InboundMessage, guess_mime
    from ..pipeline import normalise_source_document
    from ..rules.stage import decide_case

    tenant = _tenant(x_tenant_id)
    body = text.strip()
    attachments: list[InboundAttachment] = []
    for f in files:
        data = await f.read()
        if not data:
            continue
        name = f.filename or "upload"
        attachments.append(
            InboundAttachment(filename=name, mime=f.content_type or guess_mime(name), data=data)
        )
    if not body and not attachments:
        raise HTTPException(status_code=400, detail="provide text or at least one file")

    blob, llm = get_blob(), get_llm()
    msg = InboundMessage(
        channel="file_drop",
        sender="",  # a web drop has no anchor phone; resolution degrades to open questions (§5 fallback)
        sent_at=datetime.now(UTC),  # the clock starts at first contact — now (§3)
        text=body or None,
        attachments=tuple(attachments),
    )
    res = await ingest_messages(tenant, [msg], blob=blob, factory=factory)
    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob, factory=factory)
    for cid in res.case_ids:
        await extract_case(tenant, cid, llm=llm, factory=factory)
        decide_case(tenant, cid, factory=factory)
        await elicit_case(tenant, cid, llm=llm, blob=blob, factory=factory)
    return {"case_ids": [str(c) for c in res.case_ids]}


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
    case_id: str, body: CorrectionIn, x_tenant_id: TenantHeader, factory: FactoryDep
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
            reviewer_id=body.reviewer_id,
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
    case_id: str, body: CommitIn, x_tenant_id: TenantHeader, factory: FactoryDep
) -> dict[str, Any]:
    """Approve a case (the commit gate). One-way + idempotent: a re-commit returns the original stamp,
    never re-attributing it. After this, and only after this, a report may be issued (§3)."""
    cid = _case_uuid(case_id)
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        result = api.commit_case(s, cid, reviewer_id=body.reviewer_id)
    if result is None:
        raise HTTPException(status_code=404, detail="case not found")
    return {"commit": result}


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
