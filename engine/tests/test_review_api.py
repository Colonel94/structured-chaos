"""Phase 4.7 — the review read model + its HTTP routes, end-to-end (trust spine, tenant isolation).

DB-backed (testcontainers). ingest → normalise → extract with a scripted LLM, then read the case back
through ``get_case_review`` and the ``/api`` routes: the governed core + emergent attributes surface
with their provenance, the register lists the case, a cross-tenant read is refused (RLS fail-closed),
and normalise transactionally enqueues the extract stage (the 4.7 chain).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import get_factory
from app.backends.fake import FakeBlob
from app.extract.stage import extract_case
from app.intake.ingest import ingest_messages
from app.intake.models import InboundMessage
from app.main import app
from app.pipeline import normalise_source_document
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


async def _seed_case(
    tenant: object, app_factory: sessionmaker[Session], *, blob: FakeBlob
) -> object:
    """ingest → normalise → extract one case, returning its id."""
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


async def test_get_case_review_assembles_governed_emergent_and_provenance(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Review-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory, blob=FakeBlob())

    with tenant_session(tenant, factory=app_factory) as s:
        review = api.get_case_review(s, case_id)

    assert review is not None
    assert review["case_id"] == str(case_id)
    assert review["channel"] == "file_drop"
    assert _CASE_TEXT.split(",")[0] in review["normalised_text"]
    assert len(review["source_documents"]) == 1

    fields = {f["field_path"]: f for f in review["fields"]}
    # governed core present, layered, and each value carries provenance (no value without a source).
    assert fields["category"]["value"] == "product_fault"
    assert fields["category"]["layer"] == "governed_core"
    assert fields["category"]["provenance"], "a governed value must cite its source"
    assert fields["category"]["prompt_version"]  # provenance metadata surfaced
    # emergent attribute is split into its Path-A head/qualifier for a clean column render.
    assert fields["crushed_condition"]["layer"] == "emergent"
    assert fields["crushed_condition"]["head"] == "condition"
    assert fields["crushed_condition"]["qualifier"] == "crushed"
    assert fields["crushed_condition"]["value"] == "crushed"
    # refuse-to-guess: nothing null was recorded (all six governed here are non-null).
    assert "desired_outcome" in fields


async def test_list_cases_registers_the_case_with_summary(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Register-Co")
    admin_session.commit()
    case_id = await _seed_case(tenant, app_factory, blob=FakeBlob())

    with tenant_session(tenant, factory=app_factory) as s:
        cases = api.list_cases(s)

    assert len(cases) == 1
    assert cases[0]["case_id"] == str(case_id)
    assert cases[0]["category"] == "product_fault"
    assert cases[0]["field_count"] == 7  # 6 governed + 1 emergent


async def test_normalise_enqueues_the_extract_stage(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """The 4.7 chain: a completed normalise transactionally enqueues pipeline.extract for its case."""
    tenant = api.create_tenant(admin_session, "Chain-Co")
    admin_session.commit()
    blob = FakeBlob()
    msg = InboundMessage(
        channel="file_drop",
        sender="+9716",
        sent_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        text=_CASE_TEXT,
    )
    res = await ingest_messages(tenant, [msg], blob=blob, factory=app_factory)
    case_id = res.case_ids[0]
    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob, factory=app_factory)

    njobs = admin_session.execute(
        text(
            "SELECT count(*) FROM procrastinate_jobs "
            "WHERE task_name='pipeline.extract' AND args->>'case_id' = :c"
        ),
        {"c": str(case_id)},
    ).scalar_one()
    assert njobs >= 1


async def test_routes_read_case_and_enforce_tenant_isolation(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant_a = api.create_tenant(admin_session, "Route-A")
    tenant_b = api.create_tenant(admin_session, "Route-B")
    admin_session.commit()
    case_id = await _seed_case(tenant_a, app_factory, blob=FakeBlob())

    app.dependency_overrides[get_factory] = lambda: app_factory
    try:
        client = TestClient(app)
        # tenant A reads its own case + register.
        r = client.get(f"/api/cases/{case_id}", headers={"X-Tenant-Id": str(tenant_a)})
        assert r.status_code == 200
        body = r.json()
        assert body["case_id"] == str(case_id)
        assert any(f["field_path"] == "category" for f in body["fields"])

        reg = client.get("/api/cases", headers={"X-Tenant-Id": str(tenant_a)})
        assert reg.status_code == 200
        assert len(reg.json()["cases"]) == 1

        # tenant B cannot read tenant A's case — RLS fail-closed → 404, never a cross-tenant leak.
        leak = client.get(f"/api/cases/{case_id}", headers={"X-Tenant-Id": str(tenant_b)})
        assert leak.status_code == 404
        assert (
            client.get("/api/cases", headers={"X-Tenant-Id": str(tenant_b)}).json()["cases"] == []
        )
    finally:
        app.dependency_overrides.clear()
