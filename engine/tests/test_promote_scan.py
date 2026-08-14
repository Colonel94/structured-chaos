"""Phase 4 STAGE 6 — the promotion TRIGGER (periodic scan), the debounced enqueuer.

DB-backed. Attests a head across enough distinct cases to promote, then runs ``scan_and_enqueue`` with
a fake defer and asserts: the newly-promoted concept is enqueued for backfill with its attested
categories; a second scan enqueues NOTHING (already promoted → is_new False → no re-backfill).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.extract.head_nouns import compose_name
from app.schema.promote import PROMOTE_HEAD_N, PromotedConcept
from app.schema.promote_scan import scan_and_enqueue
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

_DT = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _h(s: object) -> str:
    return hashlib.sha256(str(s).encode()).hexdigest()


def _attest(session: Session, *, head: str, case_id: object, category: str) -> None:
    """Attest a bare head in a case AND set the case's governed category (backfill scoping reads it)."""
    name = compose_name(head, None)
    doc = api.add_source_document(
        session,
        case_id=case_id,
        sha256=_h(case_id),
        blob_key=_h(case_id),  # type: ignore[arg-type]
        mime="text/plain",
        channel="file_drop",
        byte_size=1,
        received_at=_DT,
    )
    cite = [api.Citation(source_document_id=doc, role="primary")]
    for path, value, layer in ((name, "v", "emergent"), ("category", category, "governed_core")):
        api.record_extraction(
            session,
            case_id=case_id,
            field_path=path,
            value=value,
            model="m",
            model_version="m",  # type: ignore[arg-type]
            prompt_version="p",
            run_id=uuid4(),
            confidence=0.5,
            citations=cite,
            layer=layer,
        )
    api.register_emergent_field(session, field_name=name, field_name_hash=_h(name), head=head)
    api.register_emergent_head(session, head=head)
    api.rebuild_field_current(session, case_id)


def test_scan_promotes_and_enqueues_backfill_once(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Scan-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        for _ in range(PROMOTE_HEAD_N):
            case = api.create_case(s, channel="file_drop", first_contact_at=_DT)
            _attest(s, head="amount", case_id=case, category="billing_charge")

    calls: list[tuple[PromotedConcept, list[str]]] = []

    def _fake_defer(
        session: Session, tid: object, concept: PromotedConcept, cats: list[str], bs: int
    ) -> None:
        calls.append((concept, cats))

    enqueued = scan_and_enqueue(_fake_defer, tenant_ids=[tenant], factory=app_factory)

    assert len(enqueued) == 1
    concept, cats = calls[0]
    assert concept.concept_key == "amount" and concept.is_new is True
    assert cats == ["billing_charge"]  # backfill scoped to the concept's attested category

    # Second scan: already promoted → nothing new → no backfill re-enqueued.
    calls.clear()
    again = scan_and_enqueue(_fake_defer, tenant_ids=[tenant], factory=app_factory)
    assert again == [] and calls == []
