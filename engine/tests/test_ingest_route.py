"""Phase 7 (sellability) — the self-serve intake route (the product surface).

DB-backed. A stranger POSTs their messy case to ``/api/ingest`` (no developer, no script), receives a
durably queued case immediately, and can open it in the tenant-scoped review register while the worker
processes it. Stage behavior and the full queue chain are covered independently; this test guards the HTTP
boundary against regressing to fragile/duplicate inline execution.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import get_factory
from app.backends.fake import FakeBlob
from app.main import app
from app.store import api

pytestmark = pytest.mark.usefixtures("pg")

_CASE_TEXT = "chocolate cake order 4471 arrived crushed and late, I want a refund"


async def test_ingest_route_durably_queues_a_pasted_case(
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = api.create_tenant(admin_session, "Ingest-Co")
    admin_session.commit()
    monkeypatch.setattr("app.backends.registry.get_blob", lambda *a, **k: FakeBlob())
    app.dependency_overrides[get_factory] = lambda: app_factory
    try:
        client = TestClient(app)
        headers = {"X-Tenant-Id": str(tenant)}

        # A stranger submits pasted text — no form, no developer.
        r = client.post("/api/ingest", headers=headers, files={"text": (None, _CASE_TEXT)})
        assert r.status_code == 202
        assert r.json()["status"] == "queued"
        case_ids = r.json()["case_ids"]
        assert len(case_ids) == 1

        # The case exists before extraction/questions and is visible immediately. The durable worker is
        # now the only component allowed to advance it; no inline extraction or decision is fabricated.
        review = client.get(f"/api/cases/{case_ids[0]}", headers=headers).json()
        assert review["case_state"] == "created"
        assert review["fields"] == []
        assert review["decision"] is None
        not_ready = client.post(
            f"/api/cases/{case_ids[0]}/commit",
            headers=headers,
            json={"reviewer_id": "r1"},
        )
        assert not_ready.status_code == 409
        assert any(
            c["case_id"] == case_ids[0]
            for c in client.get("/api/cases", headers=headers).json()["cases"]
        )
    finally:
        app.dependency_overrides.clear()


async def test_ingest_requires_text_or_a_file(
    admin_session: Session,
    app_factory: sessionmaker[Session],
) -> None:
    tenant = api.create_tenant(admin_session, "Empty-Co")
    admin_session.commit()
    app.dependency_overrides[get_factory] = lambda: app_factory
    try:
        client = TestClient(app)
        r = client.post(
            "/api/ingest", headers={"X-Tenant-Id": str(tenant)}, files={"text": (None, "   ")}
        )
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
