"""The customer portal public surface (/p) — security first (PORTAL.md §6, §13). DB-backed.

The two named guarantees: a client-supplied tenant header is IGNORED (tenant comes only from the embed
key / signed token), and a case token cannot read another tenant's case. Plus: no internal state leaks in
the status projection, edge file limits, and the shared-policy option render. The heavy pipeline uses a
scripted LLM + fake blob (deterministic, host/CI-safe). Processing is now DURABLE (the worker runs the
normalise→extract→elicit chain that ingest enqueues); there is no worker in a unit test, so ``_process``
drives the same stages synchronously — standing in for the worker — before we poll the status.
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
from app.portal.tokens import sign_case_token, verify_case_token
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
    monkeypatch: pytest.MonkeyPatch,
    app_factory: sessionmaker[Session],
    llm: _ScriptedLLM,
) -> TestClient:
    blob = (
        FakeBlob()
    )  # ONE instance — submit puts, the background pipeline gets; they share the store
    monkeypatch.setattr("app.backends.registry.get_llm", lambda *a, **k: llm)
    monkeypatch.setattr("app.backends.registry.get_blob", lambda *a, **k: blob)
    app.dependency_overrides[get_factory] = lambda: app_factory
    return TestClient(app)


def _process(app_factory: sessionmaker[Session], token: str) -> None:
    """Stand in for the worker: run the durable normalise→extract→decide→elicit chain for the case behind
    a signed token, synchronously, so a poll sees the processed state. Uses the same registry-overridden
    scripted LLM + shared FakeBlob, and the test factory (the stages' default global factory is not
    repointed at the test DB — the caller must pass it, exactly as the worker/portal did).
    """
    import asyncio

    from app.backends.registry import get_blob, get_llm
    from app.elicit.stage import elicit_case
    from app.extract.stage import extract_case
    from app.pipeline import normalise_source_document
    from app.rules.stage import decide_case

    resolved = verify_case_token(token)
    assert resolved is not None
    tenant_id, case_id = resolved
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
        sdids = api.list_case_source_documents(s, case_id)
    blob, llm = get_blob(), get_llm()

    async def _go() -> None:
        for sdid in sdids:
            await normalise_source_document(str(tenant_id), sdid, blob=blob, factory=app_factory)
        await extract_case(str(tenant_id), case_id, llm=llm, factory=app_factory)
        decide_case(str(tenant_id), case_id, factory=app_factory)
        await elicit_case(str(tenant_id), case_id, llm=llm, blob=blob, factory=app_factory)

    asyncio.run(_go())


# ---------------------------------------------------------------- the two named security guarantees


def test_submit_ignores_client_tenant_header(
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
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


def test_case_token_does_not_grant_cross_origin_read_access(
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mint_tenant(admin_session, "Portal-CORS", "EK_cors")
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        created = client.post(
            "/p/submit", data={"key": "EK_cors", "text": "my parcel arrived smashed"}
        )
        token = created.json()["token"]
        blocked = client.get(f"/p/case/{token}", headers={"Origin": "https://malicious.example"})
        assert blocked.status_code == 403
        assert "Access-Control-Allow-Origin" not in blocked.headers
    finally:
        app.dependency_overrides.clear()


def test_case_token_cannot_read_another_tenants_case(
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
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
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mint_tenant(admin_session, "Leak-Co", "EK_leak")
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        token = client.post("/p/submit", data={"key": "EK_leak", "text": "late parcel"}).json()[
            "token"
        ]
        _process(app_factory, token)
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
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        assert client.post("/p/submit", data={"key": "nope", "text": "hi"}).status_code == 404
        assert client.post("/p/submit", data={"key": "", "text": "hi"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_file_type_and_size_limits(
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
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
        monkeypatch.setattr(config_mod.settings, "portal_max_file_bytes", 100)
        monkeypatch.setattr(config_mod.settings, "portal_max_request_bytes", 50)
        r = client.post(
            "/p/submit",
            data={"key": "EK_lim", "text": "x" * 40},
            files={"files": ("total.txt", b"y" * 20, "text/plain")},
        )
        assert r.status_code == 413
    finally:
        app.dependency_overrides.clear()


def test_status_surfaces_shared_options_when_policy_asks_outcome(
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
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
        _process(app_factory, token)
        body = client.get(f"/p/case/{token}").json()
        assert body["question"] and "put this right" in body["question"].lower()
        # the options come from the SHARED policy (OUTCOME_OPTIONS), rendered, not invented by the widget.
        assert body["options"] == [
            "Refund",
            "Replacement",
            "Fix it",
            "An answer",
            "Escalate",
        ]
    finally:
        app.dependency_overrides.clear()


def test_status_shows_honest_failure_not_empty_case(
    admin_session: Session,
    app_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A case whose processing died (retries exhausted → ``processing_failed``) must NOT render as a
    finished-but-empty case. The status shows the honest stalled/handoff copy, and still leaks nothing.
    """
    tenant = _mint_tenant(admin_session, "Fail-Co", "EK_fail")
    client = _wire(monkeypatch, app_factory, _ScriptedLLM())
    try:
        token = client.post("/p/submit", data={"key": "EK_fail", "text": "late parcel"}).json()[
            "token"
        ]
        # Simulate the worker stamping the case failed after its retries were exhausted.
        resolved = verify_case_token(token)
        assert resolved is not None
        _, case_id = resolved
        with app_factory() as s:
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
            assert api.fail_case_processing(s, case_id) is True
            s.commit()
        body = client.get(f"/p/case/{token}").json()
        # Honest handoff, not a completed-looking empty case.
        assert body["stalled"] is True and body["processing"] is True
        assert "snag" in body["headline"].lower()
        assert "resend" in body["detail"].lower()
        # Still no internal state leak in the failure projection.
        blob = json.dumps(body).lower()
        for leak in (
            "processing_failed",
            "case_state",
            "confidence",
            "priority",
            "routing",
        ):
            assert leak not in blob, f"failure status leaked {leak!r}: {body}"
    finally:
        app.dependency_overrides.clear()


def test_fail_case_processing_only_marks_inflight_cases(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """``fail_case_processing`` can only ever RECORD a failure — never un-finish a done case. It
    transitions from created/incomplete, is idempotent, and never clobbers actionable/committed.
    """
    from datetime import UTC, datetime

    tenant = _mint_tenant(admin_session, "Guard-Co", "EK_guard")
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        case_id = api.create_case(s, channel="web", first_contact_at=datetime.now(UTC))
        s.commit()

    def _state() -> str:
        with app_factory() as s:
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
            return str(
                s.execute(
                    text("SELECT case_state FROM case_record WHERE id = :c"),
                    {"c": case_id},
                ).scalar()
            )

    def _set(state: str) -> None:
        with app_factory() as s:
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
            s.execute(
                text("UPDATE case_record SET case_state = :st WHERE id = :c"),
                {"st": state, "c": case_id},
            )
            s.commit()

    # created → marks failed (returns True).
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        assert api.fail_case_processing(s, case_id) is True
        s.commit()
    assert _state() == "processing_failed"

    # already failed → idempotent no-op (returns False).
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        assert api.fail_case_processing(s, case_id) is False
        s.commit()

    # a finished case is NEVER un-finished by a late stage failure.
    for done in ("actionable", "in_review", "committed"):
        _set(done)
        with app_factory() as s:
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
            assert api.fail_case_processing(s, case_id) is False
            s.commit()
        assert _state() == done


def test_status_shows_processing_while_a_reply_is_in_flight(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A customer reply re-enters intake; until elicit re-runs on it, the case still carries the PRIOR
    turn's question. The status must read as 'we're working on it', never serve the stale question as
    ready (the chat would freeze). Reprocessing = the newest inbound message is newer than the last
    elicit decision (processed_at)."""
    from datetime import UTC, datetime, timedelta

    from app.portal.store import public_status

    tenant = _mint_tenant(admin_session, "Reproc-Co", "EK_reproc")
    t0 = datetime.now(UTC) - timedelta(minutes=5)
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        cid = api.create_case(s, channel="web", first_contact_at=t0)
        # Turn 1 settled: a standing question + processed_at just after first contact.
        s.execute(
            text("""
                UPDATE case_record SET case_state='incomplete',
                  external_mappings = jsonb_build_object('elicit', jsonb_build_object(
                    'next_question', 'What is your order number?',
                    'processed_at', to_jsonb(CAST(:pa AS text))))
                WHERE id = :c
            """),
            {"c": cid, "pa": (t0 + timedelta(seconds=1)).isoformat()},
        )
        # A reply arrives AFTER that decision — the pipeline hasn't re-run yet.
        sha = (
            secrets_hex() + secrets_hex() + secrets_hex() + secrets_hex()
        )  # 64-char hex (== blob key)
        api.add_source_document(
            s,
            case_id=cid,
            sha256=sha,
            blob_key=sha,
            mime="text/plain",
            channel="web",
            byte_size=10,
            received_at=t0 + timedelta(minutes=1),
            doc_kind="message",
        )
        s.commit()

    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        st = public_status(s, cid, stall_seconds=3600)
        assert st is not None and st["processing"] is True  # reply in flight → working on it
        # The stale question is NOT served while reprocessing.
        assert st.get("question") is None

        # Elicit re-runs and stamps processed_at past the reply → the case is ready again. (Same
        # transaction — no commit, which would reset the transaction-local tenant GUC and blind RLS.)
        api.touch_elicit_processed(s, cid, at_iso=(t0 + timedelta(minutes=2)).isoformat())
        st2 = public_status(s, cid, stall_seconds=3600)
        assert st2 is not None and st2.get("processing") is False


def test_worker_down_switches_to_honest_handoff(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """R3: a DEAD intake worker (stale heartbeat) must switch a still-processing case to honest handoff
    copy immediately — nothing will advance it until a human steps in, so an open-ended spinner is a lie.
    A cold start (no heartbeat row yet) must NOT cry 'snag' — it falls back to the gentler time-based
    stall so a just-provisioned stack doesn't alarm before the worker's first beat."""
    from datetime import UTC, datetime

    from app.portal.store import public_status, worker_down

    tenant = _mint_tenant(admin_session, "WorkerDown-Co", "EK_wdown")
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        cid = api.create_case(s, channel="web", first_contact_at=datetime.now(UTC))  # 'created'
        s.commit()

    # (1) No heartbeat row at all → NOT down (cold-start fallback) → normal processing copy.
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        assert worker_down(s, liveness_seconds=60) is False
        st = public_status(s, cid, stall_seconds=3600, worker_liveness_seconds=60)
        assert st is not None and st["processing"] is True
        assert "snag" not in st["headline"].lower()

    # (2) A STALE heartbeat → down → honest handoff copy, immediately (not after stall_seconds).
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        s.execute(
            text(
                "INSERT INTO worker_heartbeat (queue, beat_at) VALUES "
                "('default', now() - interval '5 minutes') "
                "ON CONFLICT (queue) DO UPDATE SET beat_at = EXCLUDED.beat_at"
            )
        )
        s.commit()
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        assert worker_down(s, liveness_seconds=60) is True
        st = public_status(s, cid, stall_seconds=3600, worker_liveness_seconds=60)
        assert st is not None and "snag" in st["headline"].lower() and st["stalled"] is True

    # (3) A FRESH heartbeat → recovered → back to normal processing copy.
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        s.execute(text("UPDATE worker_heartbeat SET beat_at = now() WHERE queue='default'"))
        s.commit()
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        assert worker_down(s, liveness_seconds=60) is False
        st = public_status(s, cid, stall_seconds=3600, worker_liveness_seconds=60)
        assert st is not None and "snag" not in st["headline"].lower()


def secrets_hex() -> str:
    import secrets

    return secrets.token_hex(8)


def test_rate_limiter_unit() -> None:
    from app.portal.router import _SlidingWindow

    w = _SlidingWindow()
    assert all(w.allow("k", limit=3, window_s=100) for _ in range(3))
    assert not w.allow("k", limit=3, window_s=100)  # 4th in the window → blocked
    assert w.allow("other", limit=3, window_s=100)  # a different key is independent


def test_standalone_page_authorises_its_inline_config_with_a_csp_nonce() -> None:
    """The widget's config is set by an INLINE <script>; the app CSP is script-src 'self' (no
    'unsafe-inline'), so the standalone page must authorise that one script with a per-response nonce —
    otherwise every real browser blocks it and the widget loads with NO embed key (a customer cannot
    submit). Guard: the nonce on the tag matches the CSP header, and it is fresh per response."""
    import re

    client = TestClient(app)
    r = client.get("/p/s/EK_nonce_demo")
    assert r.status_code == 200
    m = re.search(r'<script nonce="([^"]+)">', r.text)
    assert m, "the inline config <script> must carry a nonce"
    nonce = m.group(1)
    assert nonce and nonce != "__NONCE__"  # the placeholder was substituted with a real value
    assert "window.__ADAPTIVE_PORTAL__" in r.text  # the config the widget reads is present
    csp = r.headers["content-security-policy"]
    assert f"script-src 'self' 'nonce-{nonce}'" in csp  # the CSP authorises exactly this script
    # a fresh nonce per response (never a fixed/reused value that would defeat the point)
    r2 = client.get("/p/s/EK_nonce_demo")
    n2 = re.search(r'<script nonce="([^"]+)">', r2.text)
    assert n2 and n2.group(1) != nonce
