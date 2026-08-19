"""Phase 7 — the commit gate + reviewer corrections + the report/register export (trust spine).

DB-backed (testcontainers). Seeds one case (ingest → normalise → extract with a scripted LLM), then
exercises the Phase-7 surface end-to-end through the store and the ``/api`` routes:

- **The gate (§3):** no report is issued before a human approves — ``render_case_html`` refuses, and
  ``GET /report.pdf`` returns 409. Only after ``commit`` may a report be built.
- **Commit is one-way + idempotent:** a re-commit by a different reviewer never re-attributes the
  original approval (first writer wins).
- **Corrections** append (never overwrite), rebuild the projection, recompute the deterministic
  decision, and are refused once a case is committed (approval is final).
- **Tenant isolation** holds on every new route (register CSV, provenance blob) — a cross-tenant read
  is fail-closed, never a leak.

The PDF *bytes* are container-only (WeasyPrint/GTK) and proven in the container, not here; this suite
covers the gate + HTML + CSV, all host-safe.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import get_factory
from app.backends.fake import FakeBlob
from app.extract.stage import extract_case
from app.intake.ingest import ingest_messages
from app.intake.models import InboundMessage
from app.main import app
from app.pipeline import normalise_source_document
from app.report import NotCommittedError, build_case_html, render_case_html
from app.rules.stage import decide_case
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

_CASE_TEXT = "chocolate cake order 4471 arrived crushed and late, I want a refund"


class _ScriptedLLM:
    def __init__(self) -> None:
        self.last_usage = {"wall_ms": 5.0, "tokens_in": 100.0, "tokens_out": 40.0}
        self._payload = json.dumps(
            {
                "category": "product_fault",
                "fault": "cake crushed and late",
                "desired_outcome": "refund",
                "emotion_signal": "frustrated",
                "severity_signal": "none",
                "anchor_value": "4471",
                "emergent_attributes": [
                    {"head": "condition", "qualifier": "crushed", "value": "crushed"},
                ],
            }
        )

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._payload


async def _seed_case(tenant: object, app_factory: sessionmaker[Session]) -> object:
    blob = FakeBlob()
    msg = InboundMessage(
        channel="file_drop",
        sender="+9715",
        sent_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        text=_CASE_TEXT,
    )
    res = await ingest_messages(tenant, [msg], blob=blob, factory=app_factory)
    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob, factory=app_factory)
    await extract_case(tenant, res.case_ids[0], llm=_ScriptedLLM(), factory=app_factory)
    return res.case_ids[0]


async def test_report_refused_before_commit_issued_after(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """The commit gate: an unapproved case yields no report; the approved case does (§3)."""
    tenant = api.create_tenant(admin_session, "Gate-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory)

    # Before approval: the payload shows no stamp and the report is refused outright.
    with tenant_session(tenant, factory=app_factory) as s:
        assert api.get_case_review(s, case_id)["commit"] is None  # type: ignore[index]
        with pytest.raises(NotCommittedError):
            render_case_html(s, case_id)

    # Approve, then the report builds and carries the approval line.
    with tenant_session(tenant, factory=app_factory) as s:
        stamp = api.commit_case(s, case_id, reviewer_id="reviewer-1")
    assert stamp is not None and stamp["committed_by"] == "reviewer-1"

    with tenant_session(tenant, factory=app_factory) as s:
        review = api.get_case_review(s, case_id)
        assert review["commit"]["committed_by"] == "reviewer-1"  # type: ignore[index]
        html = render_case_html(s, case_id)
    assert "reviewer-1" in html and "product_fault" in html


async def test_commit_is_one_way_and_idempotent(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A re-commit never re-attributes or re-times the approval — first writer wins."""
    tenant = api.create_tenant(admin_session, "OneWay-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory)

    with tenant_session(tenant, factory=app_factory) as s:
        first = api.commit_case(s, case_id, reviewer_id="reviewer-1")
    with tenant_session(tenant, factory=app_factory) as s:
        second = api.commit_case(s, case_id, reviewer_id="reviewer-2")

    assert first is not None and second is not None
    assert second["committed_by"] == "reviewer-1"  # not re-attributed to reviewer-2
    assert second["committed_at"] == first["committed_at"]  # not re-timed


def test_build_case_html_renders_absence_and_escapes() -> None:
    """The template renders a refuse-to-guess absence explicitly and escapes injected markup."""
    review = {
        "case_id": "abcd1234-0000-0000-0000-000000000000",
        "channel": "file_drop",
        "case_state": "in_review",
        "first_contact_at": "2026-08-19T10:00:00+00:00",
        "decision": None,
        "commit": None,
        "fields": [
            {
                "field_path": "fault",
                "value": "<script>alert(1)</script>",
                "layer": "governed_core",
            }
        ],
    }
    html = build_case_html(review)
    assert "not stated" in html  # governed fields with no value shown explicitly
    assert "<script>alert(1)</script>" not in html  # escaped, not injected
    assert "&lt;script&gt;" in html


async def test_correction_appends_recomputes_and_locks_after_commit(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A reviewer edit appends to the log, rebuilds the projection, recomputes the decision, and is
    refused once the case is committed (approval is final)."""
    tenant = api.create_tenant(admin_session, "Correct-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory)
    decide_case(tenant, case_id, factory=app_factory)  # an initial deterministic decision exists

    app.dependency_overrides[get_factory] = lambda: app_factory
    try:
        client = TestClient(app)
        headers = {"X-Tenant-Id": str(tenant)}

        # Correct a governed field → the projection now sources from the correction, not the extraction.
        r = client.post(
            f"/api/cases/{case_id}/corrections",
            headers=headers,
            json={"field_path": "desired_outcome", "new_value": "replacement", "reviewer_id": "r1"},
        )
        assert r.status_code == 200
        fields = {f["field_path"]: f for f in r.json()["fields"]}
        assert fields["desired_outcome"]["value"] == "replacement"
        assert fields["desired_outcome"]["source_kind"] == "correction"
        assert fields["desired_outcome"]["correction"]["prev_value"] == "refund"
        assert r.json()["decision"] is not None  # recomputed, still deterministic

        # Approve, then a further correction is refused — the record is closed.
        assert (
            client.post(
                f"/api/cases/{case_id}/commit", headers=headers, json={"reviewer_id": "r1"}
            ).status_code
            == 200
        )
        locked = client.post(
            f"/api/cases/{case_id}/corrections",
            headers=headers,
            json={"field_path": "fault", "new_value": "x", "reviewer_id": "r1"},
        )
        assert locked.status_code == 409
    finally:
        app.dependency_overrides.clear()


async def test_report_route_gate_and_register_csv_isolation(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """``GET /report.pdf`` is 409 before approval; the register CSV lists the case and is tenant-scoped."""
    tenant_a = api.create_tenant(admin_session, "Rep-A")
    tenant_b = api.create_tenant(admin_session, "Rep-B")
    admin_session.commit()
    case_id = await _seed_case(tenant_a, app_factory)

    app.dependency_overrides[get_factory] = lambda: app_factory
    try:
        client = TestClient(app)
        a = {"X-Tenant-Id": str(tenant_a)}
        b = {"X-Tenant-Id": str(tenant_b)}

        # Gate: no report before approval (409), regardless of the PDF backend's availability.
        assert client.get(f"/api/cases/{case_id}/report.pdf", headers=a).status_code == 409

        # Register CSV: tenant A sees its case row; tenant B sees only the header (RLS fail-closed).
        csv_a = client.get("/api/cases.csv", headers=a)
        assert csv_a.status_code == 200
        assert str(case_id) in csv_a.text and "priority" in csv_a.text.splitlines()[0]
        csv_b = client.get("/api/cases.csv", headers=b)
        assert csv_b.status_code == 200
        assert str(case_id) not in csv_b.text  # no cross-tenant row

        # Provenance blob route: a bogus/foreign doc id is a fail-closed 404, never a leak.
        assert (
            client.get("/api/docs/00000000-0000-0000-0000-000000000000", headers=a).status_code
            == 404
        )
    finally:
        app.dependency_overrides.clear()
