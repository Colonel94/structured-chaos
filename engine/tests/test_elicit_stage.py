"""Phase 5 — the elicit stage wired to the store: budget spent in code, emotion handoff, idempotent
replay, and object-resolved confirmation. DB-backed."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.elicit.stage import elicit_case
from app.resolve import ingest_object_collection
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _seed_case(
    session: Session, *, governed: dict[str, str], contact_ref: str | None = None
) -> UUID:
    """Create a case with the given governed fields already extracted (via the real append-only log
    + field_current projection), mimicking a post-extraction state the elicit stage reads."""
    case_id = api.create_case(
        session,
        channel="whatsapp",
        first_contact_at=datetime.now(UTC),
        contact_ref=contact_ref,
    )
    sha = hashlib.sha256(uuid4().bytes).hexdigest()
    doc = api.add_source_document(
        session,
        case_id=case_id,
        sha256=sha,
        blob_key=sha,
        mime="text/plain",
        channel="whatsapp",
        byte_size=10,
        received_at=datetime.now(UTC),
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
    return case_id


def _elicit_meta(session: Session, case_id: UUID) -> dict[str, object]:
    row = session.execute(
        text("SELECT external_mappings->'elicit' FROM case_record WHERE id = :cid"),
        {"cid": case_id},
    ).scalar_one()
    return dict(row) if row else {}


def test_stage_asks_anchor_first_and_spends_one_budget(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Elicit-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = _seed_case(s, governed={"category": "delivery_fulfilment", "fault": "arrived late"})

    assert asyncio.run(elicit_case(tenant, case, factory=app_factory)) is True

    with tenant_session(tenant, factory=app_factory) as s:
        state, qcount, anchor_asked, _ref = api.get_case_elicit_state(s, case)  # type: ignore[misc]
        meta = _elicit_meta(s, case)
    assert state == "incomplete" and qcount == 1 and anchor_asked is True
    assert meta["question_kind"] == "anchor"


def test_stage_hands_off_angry_incomplete_without_asking(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Angry-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = _seed_case(s, governed={"category": "service_fault", "emotion_signal": "angry"})

    asyncio.run(elicit_case(tenant, case, factory=app_factory))

    with tenant_session(tenant, factory=app_factory) as s:
        state, qcount, _a, _r = api.get_case_elicit_state(s, case)  # type: ignore[misc]
    assert state == "in_review" and qcount == 0  # never interrogated


def test_stage_is_idempotent_on_the_extracted_state(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Replay-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = _seed_case(s, governed={"category": "product_fault", "fault": "broken"})

    assert asyncio.run(elicit_case(tenant, case, factory=app_factory)) is True
    # Same governed state → the replay is a no-op (budget not double-spent).
    assert asyncio.run(elicit_case(tenant, case, factory=app_factory)) is False

    with tenant_session(tenant, factory=app_factory) as s:
        _state, qcount, _a, _r = api.get_case_elicit_state(s, case)  # type: ignore[misc]
    assert qcount == 1


def test_stage_confirms_the_resolved_object_then_asks_the_outcome(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Confirm-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        asyncio.run(
            ingest_object_collection(
                s,
                object_type="order",
                # two orders so cardinality profiling keeps order_id/phone as keys but treats the
                # repeating name/items as descriptive (a single-object batch makes everything "unique")
                objects=[
                    {
                        "order_id": "BK-1",
                        "phone": "+441234",
                        "customer_name": "Ada",
                        "items": "cake",
                    },
                    {
                        "order_id": "BK-2",
                        "phone": "+445678",
                        "customer_name": "Ada",
                        "items": "cake",
                    },
                ],
            )
        )
        # anchor stated + category/fault present, but the desired outcome is missing.
        case = _seed_case(
            s,
            governed={
                "category": "delivery_fulfilment",
                "fault": "arrived late",
                "anchor_value": "BK-1",
            },
        )

    asyncio.run(elicit_case(tenant, case, factory=app_factory))

    with tenant_session(tenant, factory=app_factory) as s:
        _state, qcount, _a, _r = api.get_case_elicit_state(s, case)  # type: ignore[misc]
        meta = _elicit_meta(s, case)
    assert qcount == 1 and meta["question_kind"] == "drill"
    q = str(meta["next_question"])
    assert "found your order BK-1" in q and "put this right" in q  # confirm, then ask
