"""The customer portal public surface (/p) — security first (PORTAL.md §6, §13). DB-backed.

The two named guarantees: a client-supplied tenant header is IGNORED (tenant comes only from the embed
key / signed token), and a case token cannot read another tenant's case. Plus: no internal state leaks in
the status projection, edge file limits, and the shared-policy option render. The heavy pipeline uses a
scripted LLM + fake blob (deterministic, host/CI-safe); TestClient runs the BackgroundTask synchronously,
so a submit is fully processed by the time we poll.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import get_factory
from app.backends.fake import FakeBlob
from app.main import app
from app.portal.router import router as portal_router
from app.portal.tokens import sign_case_token
from app.store import api

pytestmark = pytest.mark.usefixtures("pg")

# Mount the public router onto the shared app once (main.py only mounts it when portal_enabled at import).
if not any(getattr(r, "path", "").startswith("/p/") for r in app.routes):
    app.include_router(portal_router)


@pytest.fixture(autouse=True)
def _portal_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.config as config_mod

    monkeypatch.setattr(config_mod.settings, "portal_secret", "test-portal-secret")
    # The rate limiter is a module-global; clear it between tests (TestClient shares one client IP, so
    # the per-IP window would otherwise carry across tests and 429 the later ones).
    from app.portal.router import _rate

    _rate._hits.clear()


class _ScriptedLLM:
    """Returns a fixed extraction. ``outcome`` toggles whether desired_outcome is present (→ actionable)
    or null (→ the elicit stage asks the outcome drill, with options)."""

    def __init__(self, *, outcome: str | None = "refund", anchor: str | None = None) -> None:
        self.last_usage = {"wall_ms": 5.0, "tokens_in": 100.0, "tokens_out": 40.0}
        self._payload = json.dumps(
            {
                "category": "delivery_fulfilment",
                "fault": "parcel arrived late and damaged",
                "desired_outcome": outcome,
                "emotion_signal": "frustrated",
                "severity_signal": "none",
                "anchor_value": anchor,
                "emergent_attributes": [],
            }
        )

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._payload


def _mint_tenant(admin_session: Session, name: str, key: str) -> str:
    tenant = api.create_tenant(admin_session, name)
    admin_session.execute(
        text("UPDATE tenant SET embed_key = :k WHERE id = :t"), {"k": key, "t": tenant}
    )
    admin_session.commit()
    return str(tenant)


def _wire(
    monkeypatch: pytest.MonkeyPatch, app_factory: sessionmaker[Session], llm: _ScriptedLLM
) -> TestClient:
    blob = (
        FakeBlob()
    )  # ONE instance — submit puts, the background pipeline gets; they share the store
    monkeypatch.setattr("app.backends.registry.get_llm", lambda *a, **k: llm)
    monkeypatch.setattr("app.backends.registry.get_blob", lambda *a, **k: blob)
    app.dependency_overrides[get_factory] = lambda: app_factory
    return TestClient(app)


# ---------------------------------------------------------------- the two named security guarantees


def test_submit_ignores_client_tenant_header(
    admin_session: Session, app_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_a = _mint_tenant(admin_session, "Portal-A", "EK_aaa")
    tenant_b = _mint_tenant(admin_session, "Portal-B", "EK_bbb")
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        # Submit with A's key but a spoofed X-Tenant-Id pointing at B. The header must have NO effect.
        r = client.post(
            "/p/submit",
            data={"key": "EK_aaa", "text": "my parcel arrived smashed"},
            headers={"X-Tenant-Id": tenant_b},
        )
        assert r.status_code == 200
        # The case must belong to A (the key's tenant), never B (the header's).
        with app_factory() as s:
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
            in_a = s.execute(text("SELECT count(*) FROM case_record")).scalar()
        with app_factory() as s:
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_b})
            in_b = s.execute(text("SELECT count(*) FROM case_record")).scalar()
        assert in_a == 1 and in_b == 0
    finally:
        app.dependency_overrides.clear()


def test_case_token_cannot_read_another_tenants_case(
    admin_session: Session, app_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_a = _mint_tenant(admin_session, "Tok-A", "EK_ta")
    tenant_b = _mint_tenant(admin_session, "Tok-B", "EK_tb")
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        # A real case in tenant B.
        rb = client.post("/p/submit", data={"key": "EK_tb", "text": "B's private complaint"})
        token_b = rb.json()["token"]
        case_b = token_b  # opaque; we need B's case_id to forge an A-scoped token
        # Recover B's case id (admin) and forge a token binding it to tenant A.
        with app_factory() as s:
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_b})
            case_b_id = s.execute(text("SELECT id FROM case_record LIMIT 1")).scalar()
        forged = sign_case_token(tenant_a, case_b_id)  # signed, but points A's GUC at B's case
        # RLS: A cannot see B's case → 404, never a leak.
        assert client.get(f"/p/case/{forged}").status_code == 404
        # A tampered signature is rejected outright.
        assert client.get(f"/p/case/{token_b[:-3]}xxx").status_code == 404
        # B's own token still works.
        assert client.get(f"/p/case/{token_b}").status_code == 200
        assert case_b  # (silence unused)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------- no internal leaks + limits + options


def test_status_leaks_no_internal_state(
    admin_session: Session, app_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _mint_tenant(admin_session, "Leak-Co", "EK_leak")
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        token = client.post("/p/submit", data={"key": "EK_leak", "text": "late parcel"}).json()[
            "token"
        ]
        body = client.get(f"/p/case/{token}").json()
        blob = json.dumps(body).lower()
        for leak in (
            "confidence",
            "priority",
            "routing",
            "case_state",
            "delivery_fulfilment",  # the raw enum
            "emergent",
            "severity",
            "reviewer",
        ):
            assert leak not in blob, f"status leaked {leak!r}: {body}"
        # It DOES carry the safe, customer-facing read-back in plain words.
        assert "delivery problem" in blob
    finally:
        app.dependency_overrides.clear()


def test_unknown_key_is_404(
    admin_session: Session, app_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        assert client.post("/p/submit", data={"key": "nope", "text": "hi"}).status_code == 404
        assert client.post("/p/submit", data={"key": "", "text": "hi"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_file_type_and_size_limits(
    admin_session: Session, app_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _mint_tenant(admin_session, "Lim-Co", "EK_lim")
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        # a disallowed MIME → 415
        r = client.post(
            "/p/submit",
            data={"key": "EK_lim"},
            files={"files": ("x.exe", b"MZ....", "application/x-msdownload")},
        )
        assert r.status_code == 415
        # an oversized allowed file → 413
        import app.config as config_mod

        monkeypatch.setattr(config_mod.settings, "portal_max_file_bytes", 10)
        r = client.post(
            "/p/submit",
            data={"key": "EK_lim"},
            files={"files": ("big.txt", b"x" * 100, "text/plain")},
        )
        assert r.status_code == 413
    finally:
        app.dependency_overrides.clear()


def test_status_surfaces_shared_options_when_policy_asks_outcome(
    admin_session: Session, app_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _mint_tenant(admin_session, "Opt-Co", "EK_opt")
    # outcome=None + an anchor present → has_anchor is True, so the drill skips the anchor and asks the
    # OUTCOME drill, which carries the shared options.
    client = _wire(monkeypatch, app_factory, _ScriptedLLM(outcome=None, anchor="ORD-99"))
    try:
        # the anchor must appear in the text (closed-world grounding drops ungrounded values)
        token = client.post(
            "/p/submit", data={"key": "EK_opt", "text": "late parcel, order ORD-99"}
        ).json()["token"]
        body = client.get(f"/p/case/{token}").json()
        assert body["question"] and "put this right" in body["question"].lower()
        # the options come from the SHARED policy (OUTCOME_OPTIONS), rendered, not invented by the widget.
        assert body["options"] == ["Refund", "Replacement", "Fix it", "An answer", "Escalate"]
    finally:
        app.dependency_overrides.clear()


def test_rate_limiter_unit() -> None:
    from app.portal.router import _SlidingWindow

    w = _SlidingWindow()
    assert all(w.allow("k", limit=3, window_s=100) for _ in range(3))
    assert not w.allow("k", limit=3, window_s=100)  # 4th in the window → blocked
    assert w.allow("other", limit=3, window_s=100)  # a different key is independent
