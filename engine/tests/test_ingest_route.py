"""Phase 7 (sellability) — the self-serve intake route, end-to-end (the product surface).

DB-backed. A stranger POSTs their messy case to ``/api/ingest`` (no developer, no script) and it comes
back a fully structured case in the review register: governed core + a deterministic decision + per-field
provenance, tenant-scoped (RLS). Closes the audit's "no product surface" red flag (winning-condition §7)
and the "intake never exercised over HTTP" gap. The real Ollama/whisper are swapped for a scripted LLM +
fake blob here (deterministic, host/CI-safe); the live model path is proven separately on the GPU.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import get_factory
from app.backends.fake import FakeBlob
from app.main import app
from app.store import api

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
                    {"head": "condition", "qualifier": "crushed", "value": "crushed"}
                ],
            }
        )

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._payload


async def test_ingest_route_structures_a_pasted_case_end_to_end(
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = api.create_tenant(admin_session, "Ingest-Co")
    admin_session.commit()
    # Swap the heavy live backends for deterministic ones (the route resolves them from the registry).
    monkeypatch.setattr("app.backends.registry.get_llm", lambda *a, **k: _ScriptedLLM())
    monkeypatch.setattr("app.backends.registry.get_blob", lambda *a, **k: FakeBlob())
    app.dependency_overrides[get_factory] = lambda: app_factory
    try:
        client = TestClient(app)
        headers = {"X-Tenant-Id": str(tenant)}

        # A stranger submits pasted text — no form, no developer.
        r = client.post("/api/ingest", headers=headers, files={"text": (None, _CASE_TEXT)})
        assert r.status_code == 200
        case_ids = r.json()["case_ids"]
        assert len(case_ids) == 1

        # It comes back structured: governed core + a deterministic decision, in the register.
        review = client.get(f"/api/cases/{case_ids[0]}", headers=headers).json()
        fields = {f["field_path"]: f for f in review["fields"]}
        assert fields["category"]["value"] == "product_fault"
        assert fields["category"]["provenance"]  # per-field provenance attached
        assert review["decision"] is not None  # priority/SLA computed with no manual trigger
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
