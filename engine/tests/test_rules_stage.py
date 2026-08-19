"""Phase 6 — the rules stage wired to the store: writes the deterministic decision, the SLA clock runs
from first_contact_at, idempotent replay, recompute on a changed signal, and tenant isolation. DB-backed.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.rules.stage import decide_case
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _seed_case(
    session: Session, *, governed: dict[str, str], first_contact_at: datetime | None = None
) -> tuple[UUID, datetime]:
    """A case with the given governed fields already extracted (append-only log + projection), mimicking
    the post-extraction state the rules stage reads. Returns (case_id, first_contact_at)."""
    fca = first_contact_at or datetime.now(UTC)
    case_id = api.create_case(session, channel="file_drop", first_contact_at=fca, contact_ref=None)
    sha = hashlib.sha256(uuid4().bytes).hexdigest()
    doc = api.add_source_document(
        session,
        case_id=case_id,
        sha256=sha,
        blob_key=sha,
        mime="text/plain",
        channel="file_drop",
        byte_size=10,
        received_at=fca,
    )
    run = uuid4()
    cites = [api.Citation(source_document_id=doc, role="primary")]
    for k, v in governed.items():
        api.record_extraction(
            session,
            case_id=case_id,
            field_path=k,
            value=v,
            model="t",
            model_version="t",
            prompt_version="t",
            run_id=run,
            confidence=0.5,
            citations=cites,
            layer="governed_core",
        )
    api.rebuild_field_current(session, case_id)
    return case_id, fca


def test_stage_writes_the_decision_and_clock_runs_from_first_contact(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Rules-Co")
    admin_session.commit()
    fca = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    with tenant_session(tenant, factory=app_factory) as s:
        case, _ = _seed_case(
            s,
            governed={
                "category": "billing_charge",
                "severity_signal": "financial_harm",
                "emotion_signal": "calm",
            },
            first_contact_at=fca,
        )

    assert decide_case(tenant, case, factory=app_factory) is True

    with tenant_session(tenant, factory=app_factory) as s:
        d = api.get_case_decision(s, case)
    assert d is not None
    assert d["priority"] == "P2" and d["routing"] == "finance_billing"
    assert d["matched_rule_id"] == "financial-harm"
    # The SLA deadline is first_contact_at + the target — the clock starts at first contact, not now.
    due = datetime.fromisoformat(str(d["sla_response_due_at"]))
    assert due == fca + timedelta(hours=float(d["sla_target_hours"]))  # type: ignore[arg-type]
    assert d["inputs"] == {
        "category": "billing_charge",
        "severity_signal": "financial_harm",
        "emotion_signal": "calm",
    }


def test_stage_is_idempotent_on_unchanged_inputs(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Rules-Idem-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case, _ = _seed_case(s, governed={"category": "product_fault", "emotion_signal": "calm"})

    assert decide_case(tenant, case, factory=app_factory) is True
    # Same governed inputs + policy → the replay is a no-op (recompute is skipped by the ledger).
    assert decide_case(tenant, case, factory=app_factory) is False

    with tenant_session(tenant, factory=app_factory) as s:
        d = api.get_case_decision(s, case)
    assert d is not None and d["matched_rule_id"] == "default"


def test_stage_recomputes_when_a_signal_changes(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Rules-Recompute-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case, fca = _seed_case(s, governed={"category": "service_fault", "emotion_signal": "calm"})
    assert decide_case(tenant, case, factory=app_factory) is True
    with tenant_session(tenant, factory=app_factory) as s:
        assert api.get_case_decision(s, case)["matched_rule_id"] == "default"  # type: ignore[index]

    # A re-extraction flips emotion to angry → the projection changes → the decision recomputes.
    with tenant_session(tenant, factory=app_factory) as s:
        sha = hashlib.sha256(uuid4().bytes).hexdigest()
        doc = api.add_source_document(
            s,
            case_id=case,
            sha256=sha,
            blob_key=sha,
            mime="text/plain",
            channel="file_drop",
            byte_size=10,
            received_at=fca,
        )
        api.record_extraction(
            s,
            case_id=case,
            field_path="emotion_signal",
            value="angry",
            model="t",
            model_version="t",
            prompt_version="t2",
            run_id=uuid4(),
            confidence=0.5,
            citations=[api.Citation(source_document_id=doc, role="primary")],
            layer="governed_core",
        )
        api.rebuild_field_current(s, case)

    assert decide_case(tenant, case, factory=app_factory) is True
    with tenant_session(tenant, factory=app_factory) as s:
        d = api.get_case_decision(s, case)
    assert d is not None and d["matched_rule_id"] == "angry-any" and d["routing"] == "human_review"


def test_decision_is_tenant_isolated(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    a = api.create_tenant(admin_session, "Rules-A")
    b = api.create_tenant(admin_session, "Rules-B")
    admin_session.commit()
    with tenant_session(a, factory=app_factory) as s:
        case, _ = _seed_case(
            s, governed={"category": "safety_health", "severity_signal": "safety_health"}
        )
    assert decide_case(a, case, factory=app_factory) is True

    # Tenant B cannot read tenant A's decision (RLS) — the same trust gate as every tenant table.
    with tenant_session(b, factory=app_factory) as s:
        assert api.get_case_decision(s, case) is None
