"""Review-usability surface — the endpoints that make the review UI fast and measurable.

τ=1.01 → nothing auto-routes → every case is cleared by a human, so review TIME is the load-bearing
gate (winning-condition §4). This suite covers the backend that serves it:

- **review-time instrumentation** — a committed case logs one ``review_event``; ``/api/review-stats``
  aggregates median/p90; re-commit never double-counts.
- **batch approve** — one act clears several cases (still a per-case human approval, §3); the batch time
  is split evenly; a cross-tenant id is reported as failed, never leaked.
- **undo window** — a fresh approval is reversible within the grace window and durable after; the report
  gate re-closes on undo.
- **field-options** — the one-key correction vocabulary matches the extraction schema exactly.
- **tenant isolation** holds on every new route (review-stats never sums across tenants).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import UNDO_WINDOW_SECONDS, get_factory
from app.backends.fake import FakeBlob
from app.extract.schema import DESIRED_OUTCOMES, EMOTIONS, SEVERITIES, TAXONOMY
from app.extract.stage import extract_case
from app.intake.ingest import ingest_messages
from app.intake.models import InboundMessage
from app.main import app
from app.pipeline import normalise_source_document
from app.store import api

pytestmark = pytest.mark.usefixtures("pg")


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
                "emergent_attributes": [],
            }
        )

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._payload


async def _seed_case(
    tenant: object, app_factory: sessionmaker[Session], marker: str = "4471", sender: str = "+9715"
) -> object:
    # Each distinct case needs UNIQUE text AND a distinct sender: identical content hits content-addressed
    # idempotency, and the same sender within the idle gap gets windowed into one case as a follow-up (§0).
    blob = FakeBlob()
    msg = InboundMessage(
        channel="file_drop",
        sender=sender,
        sent_at=datetime(2026, 8, 23, 10, 0, tzinfo=UTC),
        text=f"chocolate cake order {marker} arrived crushed and late, I want a refund",
    )
    res = await ingest_messages(tenant, [msg], blob=blob, factory=app_factory)
    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob, factory=app_factory)
    await extract_case(tenant, res.case_ids[0], llm=_ScriptedLLM(), factory=app_factory)
    return res.case_ids[0]


def _client(app_factory: sessionmaker[Session]) -> TestClient:
    app.dependency_overrides[get_factory] = lambda: app_factory
    return TestClient(app)


async def test_commit_logs_review_time_and_stats_aggregate(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A committed case logs its measured review time; the stats endpoint reports the median; a re-commit
    does not double-count (idempotent measurement)."""
    tenant = api.create_tenant(admin_session, "Time-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory)
    headers = {"X-Tenant-Id": str(tenant)}
    try:
        client = _client(app_factory)
        r = client.post(
            f"/api/cases/{case_id}/commit",
            headers=headers,
            json={"reviewer_id": "r1", "review_ms": 24000, "fields_edited": 1},
        )
        assert r.status_code == 200
        assert r.json()["undo_window_seconds"] == UNDO_WINDOW_SECONDS

        # Re-commit (idempotent) must not add a second measurement.
        client.post(
            f"/api/cases/{case_id}/commit",
            headers=headers,
            json={"reviewer_id": "r2", "review_ms": 99000},
        )
        stats = client.get("/api/review-stats", headers=headers).json()
        assert stats["count"] == 1
        assert stats["median_ms"] == 24000.0
        assert stats["avg_fields_edited"] == 1.0
    finally:
        app.dependency_overrides.clear()


async def test_review_stats_are_tenant_isolated(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """One tenant's review times never appear in another's stats (RLS)."""
    tenant_a = api.create_tenant(admin_session, "Stats-A")
    tenant_b = api.create_tenant(admin_session, "Stats-B")
    admin_session.commit()
    case_a = await _seed_case(tenant_a, app_factory)
    try:
        client = _client(app_factory)
        client.post(
            f"/api/cases/{case_a}/commit",
            headers={"X-Tenant-Id": str(tenant_a)},
            json={"reviewer_id": "r1", "review_ms": 12000},
        )
        stats_b = client.get("/api/review-stats", headers={"X-Tenant-Id": str(tenant_b)}).json()
        assert stats_b["count"] == 0
        assert stats_b["median_ms"] is None
    finally:
        app.dependency_overrides.clear()


async def test_batch_approve_commits_all_and_reports_cross_tenant_as_failed(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A batch approve commits every in-tenant case (splitting the time evenly) and reports an
    out-of-tenant id as failed — never a leak."""
    tenant_a = api.create_tenant(admin_session, "Batch-A")
    tenant_b = api.create_tenant(admin_session, "Batch-B")
    admin_session.commit()
    a1 = await _seed_case(tenant_a, app_factory, marker="A1", sender="+97150001")
    a2 = await _seed_case(tenant_a, app_factory, marker="A2", sender="+97150002")
    b1 = await _seed_case(tenant_b, app_factory, marker="B1")  # belongs to another tenant
    try:
        client = _client(app_factory)
        r = client.post(
            "/api/cases/commit-batch",
            headers={"X-Tenant-Id": str(tenant_a)},
            json={"reviewer_id": "r1", "case_ids": [str(a1), str(a2), str(b1)], "review_ms": 20000},
        )
        assert r.status_code == 200
        body = r.json()
        assert set(body["committed"]) == {str(a1), str(a2)}
        assert body["failed"] == [str(b1)]  # cross-tenant → fail-closed, not committed

        # Both a-cases are approved and each carries an even share of the batch time (20000/3 ids).
        for cid in (a1, a2):
            assert (
                client.get(f"/api/cases/{cid}", headers={"X-Tenant-Id": str(tenant_a)}).json()[
                    "commit"
                ]
                is not None
            )
        stats = client.get("/api/review-stats", headers={"X-Tenant-Id": str(tenant_a)}).json()
        assert stats["count"] == 2
        assert stats["median_ms"] == round(20000 / 3)
    finally:
        app.dependency_overrides.clear()


async def test_undo_within_window_reverts_then_report_gate_recloses(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A fresh approval can be undone: the stamp clears, the case returns to review, and corrections open
    again (they 409 while committed)."""
    tenant = api.create_tenant(admin_session, "Undo-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory)
    headers = {"X-Tenant-Id": str(tenant)}
    try:
        client = _client(app_factory)
        client.post(f"/api/cases/{case_id}/commit", headers=headers, json={"reviewer_id": "r1"})
        assert client.get(f"/api/cases/{case_id}", headers=headers).json()["commit"] is not None

        r = client.post(
            f"/api/cases/{case_id}/uncommit", headers=headers, json={"reviewer_id": "r1"}
        )
        assert r.status_code == 200
        review = client.get(f"/api/cases/{case_id}", headers=headers).json()
        assert review["commit"] is None
        assert review["case_state"] == "in_review"

        # Corrections are open again after the undo (they are refused only while committed).
        corr = client.post(
            f"/api/cases/{case_id}/corrections",
            headers=headers,
            json={"field_path": "fault", "new_value": "crushed", "reviewer_id": "r1"},
        )
        assert corr.status_code == 200
    finally:
        app.dependency_overrides.clear()


async def test_undo_after_window_is_refused(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """Past the grace window the approval is durable — undo is a 409, the stamp stands."""
    tenant = api.create_tenant(admin_session, "Durable-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory)
    headers = {"X-Tenant-Id": str(tenant)}
    try:
        client = _client(app_factory)
        client.post(f"/api/cases/{case_id}/commit", headers=headers, json={"reviewer_id": "r1"})
        # Age the commit past the window (admin, out-of-band) so no real sleep is needed.
        admin_session.execute(
            text(
                "UPDATE case_record SET committed_at = now() - make_interval(secs => :s) "
                "WHERE id = :cid"
            ),
            {"s": UNDO_WINDOW_SECONDS + 60, "cid": case_id},
        )
        admin_session.commit()

        r = client.post(
            f"/api/cases/{case_id}/uncommit", headers=headers, json={"reviewer_id": "r1"}
        )
        assert r.status_code == 409
        assert client.get(f"/api/cases/{case_id}", headers=headers).json()["commit"] is not None
    finally:
        app.dependency_overrides.clear()


async def test_uncommit_absent_case_is_404(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """Undoing a case that doesn't exist for this tenant is a fail-closed 404, not a 409."""
    tenant = api.create_tenant(admin_session, "Missing-Co")
    admin_session.commit()
    try:
        client = _client(app_factory)
        r = client.post(
            f"/api/cases/{tenant}/uncommit",  # a valid UUID that is not a case
            headers={"X-Tenant-Id": str(tenant)},
            json={"reviewer_id": "r1"},
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_review_breakdown_ties_corrections_to_case_time(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """The breakdown attributes a case's measured review time to the fields corrected in it — so a high
    median has a per-field culprit list. A field never corrected does not appear."""
    tenant = api.create_tenant(admin_session, "Breakdown-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory)
    headers = {"X-Tenant-Id": str(tenant)}
    try:
        client = _client(app_factory)
        # Correct one field, then approve with a measured time.
        client.post(
            f"/api/cases/{case_id}/corrections",
            headers=headers,
            json={"field_path": "desired_outcome", "new_value": "replacement", "reviewer_id": "r1"},
        )
        client.post(
            f"/api/cases/{case_id}/commit",
            headers=headers,
            json={"reviewer_id": "r1", "review_ms": 30000, "fields_edited": 1},
        )
        fields = client.get("/api/review-breakdown", headers=headers).json()["fields"]
        by_path = {f["field_path"]: f for f in fields}
        assert by_path["desired_outcome"]["cases"] == 1
        assert by_path["desired_outcome"]["median_ms"] == 30000.0
        # A field the reviewer never touched is not attributed any time.
        assert "category" not in by_path
    finally:
        app.dependency_overrides.clear()


def test_field_options_match_the_extraction_schema(
    app_factory: sessionmaker[Session],
) -> None:
    """The one-key correction vocabulary is sourced from the extraction schema, so picks can never drift
    from what the model is constrained to emit."""
    try:
        client = _client(app_factory)
        opts = client.get("/api/field-options").json()
        assert opts["category"] == list(TAXONOMY)
        assert opts["desired_outcome"] == list(DESIRED_OUTCOMES)
        assert opts["emotion_signal"] == list(EMOTIONS)
        assert opts["severity_signal"] == list(SEVERITIES)
    finally:
        app.dependency_overrides.clear()
