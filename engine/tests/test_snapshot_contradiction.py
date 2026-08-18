"""Phase 5 — object-snapshot-on-bind + the contradicts role (§5). DB-backed.

When a case binds to an object we freeze the record as an immutable object_snapshot (provenance survives
the live object changing), and any discrepancy between the complaint and the record is stored as a
``contradicts`` citation — surfaced to the agent, never argued with the customer, never silently lost.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.backends.fake import FakeBlob
from app.elicit.stage import elicit_case
from app.resolve import ingest_object_collection
from app.resolve.snapshot import snapshot_object
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _seed_case(
    session: Session, *, governed: dict[str, str], contact_ref: str | None = None
) -> UUID:
    case_id = api.create_case(
        session, channel="whatsapp", first_contact_at=datetime.now(UTC), contact_ref=contact_ref
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


def _snapshots(session: Session, case_id: UUID) -> int:
    return session.execute(
        text(
            "SELECT count(*) FROM source_document WHERE case_id=:c AND doc_kind='object_snapshot'"
        ),
        {"c": case_id},
    ).scalar_one()


def _contradicts(session: Session) -> int:
    return session.execute(
        text("SELECT count(*) FROM extraction_citation WHERE role='contradicts'")
    ).scalar_one()


_ORDERS = [
    {
        "order_id": "BK-1",
        "phone": "+44111",
        "customer_name": "X",
        "items": "y",
        "delivered_at": "15:30",
    },
    {
        "order_id": "BK-2",
        "phone": "+44222",
        "customer_name": "X",
        "items": "y",
        "delivered_at": "12:00",
    },
]


def test_snapshot_object_is_idempotent(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Snap-Co")
    admin_session.commit()
    blob = FakeBlob()
    with tenant_session(tenant, factory=app_factory) as s:
        asyncio.run(ingest_object_collection(s, object_type="order", objects=_ORDERS))
        oid = api.resolve_object_by_key(s, key_value_hash=hashlib.sha256(b"bk-1").hexdigest())[
            0
        ].object_id
        case = _seed_case(s, governed={"category": "x"})
        a = asyncio.run(snapshot_object(s, case_id=case, object_id=oid, blob=blob))
        b = asyncio.run(snapshot_object(s, case_id=case, object_id=oid, blob=blob))
    assert a is not None and a == b  # same object state → one snapshot, not two
    with tenant_session(tenant, factory=app_factory) as s:
        assert _snapshots(s, case) == 1


def test_silent_bind_snapshots_the_record(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Bind-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        asyncio.run(ingest_object_collection(s, object_type="order", objects=_ORDERS))
        case = _seed_case(
            s, governed={"category": "delivery_fulfilment", "fault": "late", "anchor_value": "BK-1"}
        )
    # No llm → no contradiction check, but the bind still snapshots the record (provenance).
    asyncio.run(elicit_case(tenant, case, blob=FakeBlob(), factory=app_factory))
    with tenant_session(tenant, factory=app_factory) as s:
        assert _snapshots(s, case) == 1
        assert _contradicts(s) == 0


def test_anchor_contradiction_records_a_contradicts_citation(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Contra-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        asyncio.run(ingest_object_collection(s, object_type="order", objects=_ORDERS))
        # sender is BK-2's phone, but they quote BK-1 → the anchors disagree (a record contradiction).
        case = _seed_case(
            s,
            governed={"category": "delivery_fulfilment", "anchor_value": "BK-1"},
            contact_ref="+44222",
        )
    asyncio.run(elicit_case(tenant, case, blob=FakeBlob(), factory=app_factory))
    with tenant_session(tenant, factory=app_factory) as s:
        assert _snapshots(s, case) == 1  # the mismatched record was frozen
        assert _contradicts(s) == 1  # anchor_value cited as contradicting it
        meta = s.execute(
            text(
                "SELECT external_mappings->'elicit'->>'contradictions' FROM case_record WHERE id=:c"
            ),
            {"c": case},
        ).scalar_one()
    assert meta == "1"


class _ContraLLM:
    """A scripted LLM: the complaint 'never arrived' contradicts the record's delivered_at."""

    last_usage: ClassVar[dict[str, float]] = {}

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return json.dumps(
            {
                "contradictions": [
                    {
                        "record_field": "delivered_at",
                        "record_value": "15:30",
                        "claim": "never arrived",
                    }
                ]
            }
        )


class _NoContraLLM:
    last_usage: ClassVar[dict[str, float]] = {}

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return json.dumps({"contradictions": []})


def test_llm_contradiction_between_complaint_and_record_is_cited(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "LLMContra-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        asyncio.run(ingest_object_collection(s, object_type="order", objects=_ORDERS))
        case = _seed_case(
            s,
            governed={
                "category": "delivery_fulfilment",
                "fault": "the order never arrived",
                "anchor_value": "BK-1",
            },
        )
    asyncio.run(elicit_case(tenant, case, llm=_ContraLLM(), blob=FakeBlob(), factory=app_factory))
    with tenant_session(tenant, factory=app_factory) as s:
        assert _snapshots(s, case) == 1
        assert _contradicts(s) == 1  # fault cited as contradicting delivered_at


def test_no_contradiction_snapshots_without_a_contradicts_citation(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Clean-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        asyncio.run(ingest_object_collection(s, object_type="order", objects=_ORDERS))
        case = _seed_case(
            s,
            governed={"category": "delivery_fulfilment", "fault": "late", "anchor_value": "BK-1"},
        )
    asyncio.run(elicit_case(tenant, case, llm=_NoContraLLM(), blob=FakeBlob(), factory=app_factory))
    with tenant_session(tenant, factory=app_factory) as s:
        assert _snapshots(s, case) == 1
        assert _contradicts(s) == 0  # no discrepancy → snapshot only, no false flag
