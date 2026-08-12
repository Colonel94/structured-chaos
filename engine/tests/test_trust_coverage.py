"""Coverage gaps closed after the Phases 0-1-2 adversarial review — invariants that were enforced
but untested, or claimed but unproven. Each test names the review finding it closes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.store import api, meter
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _now() -> datetime:
    return datetime.now(UTC)


def _case_with_doc(s: Session) -> tuple:
    case = api.create_case(s, channel="file_drop", first_contact_at=_now())
    doc = api.add_source_document(
        s,
        case_id=case,
        sha256="e" * 64,
        blob_key="e" * 64,
        mime="text/plain",
        channel="file_drop",
        byte_size=1,
        received_at=_now(),
    )
    return case, doc


# ---- H1: idempotent conflict-return paths (the "replay is a no-op / no dupe" invariant) --------


def test_reingesting_same_bytes_returns_same_document(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Idem-Doc")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        kw = {
            "case_id": case,
            "sha256": "f" * 64,
            "blob_key": "f" * 64,
            "mime": "image/png",
            "channel": "file_drop",
            "byte_size": 9,
            "received_at": _now(),
        }
        first = api.add_source_document(s, **kw)
        second = api.add_source_document(s, **kw)  # same sha256 → ON CONFLICT DO NOTHING branch
        count = s.execute(text("SELECT count(*) FROM source_document")).scalar_one()
    assert first == second
    assert count == 1


def test_rerunning_same_extraction_returns_same_row(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Idem-Extract")
    admin_session.commit()
    run_id = uuid4()
    with tenant_session(tenant, factory=app_factory) as s:
        case, doc = _case_with_doc(s)
        kw = {
            "case_id": case,
            "field_path": "fault",
            "value": "x",
            "model": "m",
            "model_version": "v",
            "prompt_version": "p",
            "run_id": run_id,
            "confidence": 0.5,
            "citations": [
                api.Citation(
                    source_document_id=doc, role="primary", locator={"char_start": 0, "char_end": 1}
                )
            ],
        }
        first = api.record_extraction(s, **kw)
        second = api.record_extraction(s, **kw)  # same (run_id, field_path) → no dupe
        count = s.execute(
            text("SELECT count(*) FROM field_extraction WHERE run_id = :r"), {"r": run_id}
        ).scalar_one()
    assert first == second
    assert count == 1


# ---- H2: composite FK makes cross-tenant references structurally impossible -------------------


def test_child_cannot_reference_another_tenants_case(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant_a = api.create_tenant(admin_session, "FK-A")
    tenant_b = api.create_tenant(admin_session, "FK-B")
    admin_session.commit()
    with tenant_session(tenant_a, factory=app_factory) as s:
        case_a = api.create_case(s, channel="file_drop", first_contact_at=_now())
    # As tenant B, try to attach a source_document to tenant A's case → composite FK
    # (tenant_id=B, case_id=A's case) has no matching parent → rejected.
    with pytest.raises(DBAPIError), tenant_session(tenant_b, factory=app_factory) as s:
        api.add_source_document(
            s,
            case_id=case_a,
            sha256="0" * 64,
            blob_key="0" * 64,
            mime="text/plain",
            channel="file_drop",
            byte_size=1,
            received_at=_now(),
        )


# ---- H4: a handled failure is re-claimable (fail_stage → re-claim) ----------------------------


def test_failed_stage_is_reclaimable(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Fail-Reclaim")
    admin_session.commit()
    key = api.compute_idempotency_key(
        source_sha256="s", stage="extract", model_version="m", prompt_version="p", code_version="c"
    )
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        assert api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case) is True
        api.fail_stage(s, idempotency_key=key)  # handled failure
    with tenant_session(tenant, factory=app_factory) as s:
        assert (
            api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case) is True
        )  # retry
        api.complete_stage(s, idempotency_key=key)
    with tenant_session(tenant, factory=app_factory) as s:
        assert api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case) is False


# ---- M2: CHECK constraints are enforced ------------------------------------------------------


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        (
            (
                "INSERT INTO case_record (tenant_id, channel, first_contact_at) VALUES "
                "(NULLIF(current_setting('app.tenant_id',true),'')::uuid, 'carrier_pigeon', now())"
            ),
            {},
        ),
        ("UPDATE case_record SET question_count = -1 WHERE id = :c", {"__case__": True}),
    ],
)
def test_check_constraints_reject_bad_values(
    admin_session: Session, app_factory: sessionmaker[Session], sql: str, params: dict
) -> None:
    tenant = api.create_tenant(admin_session, "Check-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
    with pytest.raises(DBAPIError), tenant_session(tenant, factory=app_factory) as s:
        s.execute(text(sql), {"c": case} if params.get("__case__") else {})


def test_confidence_out_of_range_rejected(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Conf-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
    with pytest.raises(DBAPIError), tenant_session(tenant, factory=app_factory) as s:
        s.execute(
            text(
                "INSERT INTO field_extraction (tenant_id, case_id, field_path, value, model, "
                "model_version, prompt_version, confidence, run_id) "
                "VALUES (NULLIF(current_setting('app.tenant_id',true),'')::uuid, :c, 'f', '\"x\"'::jsonb, "
                "'m','v','p', 1.5, gen_random_uuid())"
            ),
            {"c": case},
        )


# ---- M4: a case exists in 'created' state before questions; clock at first_contact ------------


def test_case_created_immediately_in_created_state(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Created-Co")
    admin_session.commit()
    fc = _now()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="whatsapp", first_contact_at=fc)
        state, qc, first_contact = s.execute(
            text(
                "SELECT case_state, question_count, first_contact_at FROM case_record WHERE id=:c"
            ),
            {"c": case},
        ).one()
    assert state == "created"  # exists before the questions do
    assert qc == 0  # anchor+2 budget starts at zero
    assert first_contact == fc  # SLA clock starts at first contact


# ---- M5: field_current projects a correction for a field with no extraction -------------------


def test_projection_handles_correction_only_field(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "CorrOnly-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        api.record_correction(
            s,
            case_id=case,
            field_path="desired_outcome",
            prev_value=None,
            new_value="refund",
            based_on_extraction_id=None,
            reviewer_id="rev-1",
        )
        api.rebuild_field_current(s, case)
        value, kind = s.execute(
            text(
                "SELECT value, source_kind FROM field_current "
                "WHERE case_id=:c AND field_path='desired_outcome'"
            ),
            {"c": case},
        ).one()
    assert value == "refund"
    assert kind == "correction"


# ---- Meter wiring: a backend's last_usage flows into the meter (closes the open loop) ---------


def test_meter_records_from_backend_last_usage(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    class _StubBackend:
        last_usage: ClassVar[dict[str, float]] = {
            "tokens_in": 40,
            "tokens_out": 15,
            "wall_ms": 250.0,
        }

    tenant = api.create_tenant(admin_session, "MeterWire-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        meter.meter_backend(
            s,
            backend=_StubBackend(),
            interface="llm",
            backend_name="local",
            model="qwen3:14b",
            case_id=case,
        )
        cost = meter.case_cost(s, case)
    assert cost["calls"] == 1
    assert cost["tokens_in"] == 40
    assert cost["wall_ms"] == pytest.approx(250.0)


# ---- 0004: provenance is a bridge — many sources per value, with roles ------------------------


def test_extraction_requires_at_least_one_citation(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """No value exists without provenance — an empty citation list is refused at the boundary."""
    tenant = api.create_tenant(admin_session, "NoCite-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        with pytest.raises(ValueError, match="at least one source"):
            api.record_extraction(
                s,
                case_id=case,
                field_path="fault",
                value="x",
                model="m",
                model_version="v",
                prompt_version="p",
                run_id=uuid4(),
                confidence=0.5,
                citations=[],
            )


def test_value_cites_many_sources_incl_a_contradiction(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """delay = 102 min is derived from the order snapshot AND the complaint message; a record that
    disagrees is cited with role 'contradicts' — the conflict is stored, not recomputed later."""
    tenant = api.create_tenant(admin_session, "MultiCite-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="whatsapp", first_contact_at=_now())
        complaint = api.add_source_document(
            s,
            case_id=case,
            sha256="1" * 64,
            blob_key="1" * 64,
            mime="text/plain",
            channel="whatsapp",
            byte_size=20,
            received_at=_now(),
            doc_kind="message",
        )
        order = api.add_source_document(  # an object-store row, snapshotted + content-hashed
            s,
            case_id=case,
            sha256="2" * 64,
            blob_key="2" * 64,
            mime="application/json",
            channel="file_drop",
            byte_size=64,
            received_at=_now(),
            doc_kind="object_snapshot",
        )
        ext = api.record_extraction(
            s,
            case_id=case,
            field_path="delay_minutes",
            value=102,
            model="m",
            model_version="v",
            prompt_version="p",
            run_id=uuid4(),
            confidence=0.8,
            citations=[
                api.Citation(order, "derived_from", {"field": "promised_time"}, 0.6),
                api.Citation(complaint, "primary", {"char_start": 0, "char_end": 20}, 0.9),
                api.Citation(order, "contradicts", {"field": "actual_time"}, None),
            ],
        )
        roles = (
            s.execute(
                text("SELECT role FROM extraction_citation WHERE extraction_id = :e ORDER BY role"),
                {"e": ext},
            )
            .scalars()
            .all()
        )
        kinds = (
            s.execute(
                text(
                    "SELECT DISTINCT sd.doc_kind FROM extraction_citation c "
                    "JOIN source_document sd ON sd.id = c.source_document_id "
                    "WHERE c.extraction_id = :e"
                ),
                {"e": ext},
            )
            .scalars()
            .all()
        )
    assert set(roles) == {"contradicts", "derived_from", "primary"}
    assert "object_snapshot" in kinds  # a looked-up value cites a snapshot, not a message


def test_citations_are_immutable(
    admin_session: Session, app_factory: sessionmaker[Session], admin_engine: Engine
) -> None:
    tenant = api.create_tenant(admin_session, "CiteImmut-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case, doc = _case_with_doc(s)
        ext = api.record_extraction(
            s,
            case_id=case,
            field_path="fault",
            value="x",
            model="m",
            model_version="v",
            prompt_version="p",
            run_id=uuid4(),
            confidence=0.5,
            citations=[api.Citation(doc, "primary", {"char_start": 0, "char_end": 1})],
        )
        cid = s.execute(
            text("SELECT id FROM extraction_citation WHERE extraction_id = :e"), {"e": ext}
        ).scalar_one()
    # even the superuser can't rewrite provenance
    with pytest.raises(DBAPIError), admin_engine.begin() as conn:
        conn.execute(text("UPDATE extraction_citation SET role='primary' WHERE id=:i"), {"i": cid})


def test_citations_are_tenant_isolated(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant_a = api.create_tenant(admin_session, "CiteA")
    tenant_b = api.create_tenant(admin_session, "CiteB")
    admin_session.commit()
    with tenant_session(tenant_a, factory=app_factory) as s:
        case, doc = _case_with_doc(s)
        api.record_extraction(
            s,
            case_id=case,
            field_path="fault",
            value="x",
            model="m",
            model_version="v",
            prompt_version="p",
            run_id=uuid4(),
            confidence=0.5,
            citations=[api.Citation(doc, "primary")],
        )
    with tenant_session(tenant_b, factory=app_factory) as s:
        seen = s.execute(text("SELECT count(*) FROM extraction_citation")).scalar_one()
    assert seen == 0
