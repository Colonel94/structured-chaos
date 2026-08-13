"""Phase 3 — ingest + normalise integration, the exit-gate proof (BUILD-PLAN Phase 3).

DB-backed (testcontainers Postgres + FakeBlob + fake ASR). Proves the spine end-to-end: a messy
multi-message thread becomes case(s) with immutable originals and provenance-anchored normalised
text; windowing splits a new case from a follow-up; the normalise stage is transactionally enqueued
and idempotent; re-ingesting the same content creates no duplicate case or document.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.backends.fake import FakeBlob
from app.config import Backend, settings
from app.intake.ingest import ingest_messages
from app.intake.models import InboundAttachment, InboundMessage
from app.intake.whatsapp_export import parse_export_text
from app.pipeline import normalise_source_document
from app.store import api, meter
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

# Three birthday-cake messages within minutes, then a delivery complaint 7 days later → two cases.
_EXPORT = (
    "13/08/2026, 14:05 - Messages and calls are end-to-end encrypted.\n"
    "13/08/2026, 14:06 - +9715: The cake arrived crushed\n"
    "13/08/2026, 14:07 - +9715: it was for a birthday\n"
    "13/08/2026, 14:08 - +9715: I want a replacement or refund\n"
    "20/08/2026, 09:00 - +9715: also my last delivery was late again"
)


async def test_ingest_windows_stores_normalises_and_is_idempotent(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Ingest-Co")
    admin_session.commit()
    blob = FakeBlob()  # one instance so normalise reads back what ingest stored
    msgs = parse_export_text(_EXPORT)
    assert len(msgs) == 4  # the encryption system line is dropped

    res = await ingest_messages(tenant, msgs, blob=blob, factory=app_factory)

    # Windowing split the 7-day gap into two cases; four message documents stored.
    assert len(res.case_ids) == 2
    assert len(res.source_document_ids) == 4
    assert res.missing_attachments == 0

    # Every document's normalise stage was transactionally enqueued.
    njobs = admin_session.execute(
        text("SELECT count(*) FROM procrastinate_jobs WHERE task_name='pipeline.normalise'")
    ).scalar_one()
    assert njobs >= 4

    # Drive the normalise stage as the worker would; idempotent replay skips.
    for sdid in res.source_document_ids:
        assert await normalise_source_document(tenant, sdid, blob=blob, factory=app_factory)
    assert (
        await normalise_source_document(
            tenant, res.source_document_ids[0], blob=blob, factory=app_factory
        )
        is None
    )  # already done → skipped

    # The projection assembles each case's text from its normalised documents.
    with tenant_session(tenant, factory=app_factory) as s:
        first, second = res.case_ids
        t1 = api.get_case_normalised_text(s, first)
        t2 = api.get_case_normalised_text(s, second)
        rows = s.execute(text("SELECT count(*) FROM normalised_content")).scalar_one()
    assert "crushed" in t1 and "birthday" in t1 and "refund" in t1
    assert "delivery was late" in t2
    assert rows == 4

    # Re-ingesting the exact same content is a no-op — no new case, no new document.
    res2 = await ingest_messages(tenant, msgs, blob=blob, factory=app_factory)
    assert res2.case_ids == []
    assert res2.source_document_ids == []
    with tenant_session(tenant, factory=app_factory) as s:
        ncases = s.execute(text("SELECT count(*) FROM case_record")).scalar_one()
        ndocs = s.execute(text("SELECT count(*) FROM source_document")).scalar_one()
    assert ncases == 2
    assert ndocs == 4


async def test_normalise_records_cost_per_case_on_the_meter(
    admin_session: Session, app_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """GAP-1: a normalise stage that runs a backend (ASR) must record a per-case backend_call, or
    case_cost() silently measures zero. Uses the fake ASR backend (deterministic last_usage)."""
    monkeypatch.setattr(settings, "asr_backend", Backend.fake)
    tenant = api.create_tenant(admin_session, "Meter-Co")
    admin_session.commit()
    blob = FakeBlob()
    voice = InboundMessage(
        channel="file_drop",
        sender="+9715",
        sent_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        attachments=(InboundAttachment("note.ogg", "audio/ogg", b"AUDIOBYTES"),),
    )
    res = await ingest_messages(tenant, [voice], blob=blob, factory=app_factory)
    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob, factory=app_factory)

    with tenant_session(tenant, factory=app_factory) as s:
        cost = meter.case_cost(s, res.case_ids[0])
    assert cost["calls"] >= 1  # the ASR call was metered against the case (was 0 before the fix)
    assert cost["audio_seconds"] > 0


async def test_repeated_message_is_not_dropped_by_dedup(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """H1: content-only dedup wrongly dropped a legitimately repeated message. A customer sending the
    same short text at a different time must still be ingested (a fresh idempotency key)."""
    tenant = api.create_tenant(admin_session, "Repeat-Co")
    admin_session.commit()
    blob = FakeBlob()
    m1 = InboundMessage("file_drop", "+9715", datetime(2026, 8, 13, 10, 0, tzinfo=UTC), text="ok")
    m2 = InboundMessage("file_drop", "+9715", datetime(2026, 8, 20, 10, 0, tzinfo=UTC), text="ok")
    r1 = await ingest_messages(tenant, [m1], blob=blob, factory=app_factory)
    r2 = await ingest_messages(tenant, [m2], blob=blob, factory=app_factory)
    assert len(r1.source_document_ids) == 1
    assert len(r2.source_document_ids) == 1  # the second "ok" is NOT dropped
    # But re-ingesting the exact same message (same time+content) is still a no-op.
    r3 = await ingest_messages(tenant, [m1], blob=blob, factory=app_factory)
    assert r3.source_document_ids == []


async def test_scanned_pdf_without_ocr_stays_reclaimable(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """H3: an image-only PDF normalised where OCR is unavailable (this host has no paddle) must leave
    the normalise stage re-claimable ('failed'), not commit an empty 'done' that a container re-run
    would skip forever."""
    from io import BytesIO

    pytest.importorskip("PIL", reason="Pillow (pdf group) needed to synthesize the test PDF")
    pytest.importorskip("pypdfium2", reason="pdf group needed to exercise the rasterise path")
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (500, 200), "white")
    ImageDraw.Draw(img).text((40, 80), "scanned invoice content", fill="black")
    buf = BytesIO()
    img.save(buf, "PDF")  # an image-only PDF (no digital text layer)

    tenant = api.create_tenant(admin_session, "ScanPDF-Co")
    admin_session.commit()
    blob = FakeBlob()
    msg = InboundMessage(
        channel="file_drop",
        sender="+9715",
        sent_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        attachments=(InboundAttachment("invoice.pdf", "application/pdf", buf.getvalue()),),
    )
    res = await ingest_messages(tenant, [msg], blob=blob, factory=app_factory)
    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob, factory=app_factory)

    with tenant_session(tenant, factory=app_factory) as s:
        status = s.execute(
            text("SELECT status FROM stage_execution WHERE stage = 'normalise'")
        ).scalar_one()
    assert status == "failed"  # re-claimable in a capable (container) environment, not 'done'


async def test_normalised_content_is_tenant_isolated(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """normalised_content holds customer text (transcripts/OCR) — a new tenant-scoped trust-gate
    table. Prove RLS isolates it: tenant B cannot read tenant A's normalised content."""
    a = api.create_tenant(admin_session, "Norm-A")
    b = api.create_tenant(admin_session, "Norm-B")
    admin_session.commit()
    blob = FakeBlob()
    msgs = parse_export_text("13/08/2026, 10:00 - +9990: secret complaint text")
    res = await ingest_messages(a, msgs, blob=blob, factory=app_factory)
    for sdid in res.source_document_ids:
        await normalise_source_document(a, sdid, blob=blob, factory=app_factory)

    # Tenant A sees its normalised content; tenant B sees none of it (cross-tenant read = 0).
    with tenant_session(a, factory=app_factory) as s:
        seen_a = s.execute(text("SELECT count(*) FROM normalised_content")).scalar_one()
    with tenant_session(b, factory=app_factory) as s:
        seen_b = s.execute(text("SELECT count(*) FROM normalised_content")).scalar_one()
    assert seen_a >= 1
    assert seen_b == 0


async def test_ingest_sets_contact_ref_for_windowing(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Contact-Co")
    admin_session.commit()
    blob = FakeBlob()
    msgs = parse_export_text("13/08/2026, 14:06 - +97150000: hello there")
    res = await ingest_messages(tenant, msgs, blob=blob, factory=app_factory)
    with tenant_session(tenant, factory=app_factory) as s:
        ref = s.execute(
            text("SELECT contact_ref FROM case_record WHERE id = :c"),
            {"c": res.case_ids[0]},
        ).scalar_one()
    assert ref == "+97150000"
