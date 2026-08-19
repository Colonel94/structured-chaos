"""Phase 5 — the channel loop: dispatch the pending elicitation question, once (§5). DB-backed.

The engine records the next question; dispatch transmits it over the customer's channel with a durable
audit and never twice. A case with nothing pending, or no one to reply to, is a no-op. The elicit stage
enqueues dispatch when it asks — so the drill's question is sent with no manual trigger, and the reply
re-enters intake to advance the loop.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.backends.fake import FakeChannel
from app.channel import dispatch_case_question
from app.elicit.stage import elicit_case
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _seed_case(session: Session, *, governed: dict[str, str], contact_ref: str | None) -> UUID:
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


def _outbound(session: Session, case_id: UUID) -> list[tuple[str, str | None]]:
    return [
        (str(r[0]), None if r[1] is None else str(r[1]))
        for r in session.execute(
            text("SELECT body, external_ref FROM outbound_message WHERE case_id = :c"),
            {"c": case_id},
        ).all()
    ]


def _elicit_then_case(tenant: object, factory: sessionmaker[Session], **seed: object) -> UUID:
    with tenant_session(tenant, factory=factory) as s:  # type: ignore[arg-type]
        case = _seed_case(s, **seed)  # type: ignore[arg-type]
    asyncio.run(elicit_case(tenant, case, factory=factory))  # records the pending question
    return case


def test_dispatch_sends_the_pending_question_once(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Dispatch-Co")
    admin_session.commit()
    case = _elicit_then_case(
        tenant, app_factory, governed={"category": "delivery_fulfilment"}, contact_ref="+44999"
    )
    channel = FakeChannel()
    assert (
        asyncio.run(dispatch_case_question(tenant, case, channel=channel, factory=app_factory))
        is True
    )
    assert len(channel.sent) == 1
    recipient, text_sent = channel.sent[0]
    assert recipient == "+44999" and "order number" in text_sent  # the anchor question

    with tenant_session(tenant, factory=app_factory) as s:
        out = _outbound(s, case)
    assert len(out) == 1 and out[0][1] is not None  # recorded + external ref stamped


def test_dispatch_is_idempotent(admin_session: Session, app_factory: sessionmaker[Session]) -> None:
    tenant = api.create_tenant(admin_session, "DispatchIdem-Co")
    admin_session.commit()
    case = _elicit_then_case(
        tenant, app_factory, governed={"category": "service_fault"}, contact_ref="+44999"
    )
    channel = FakeChannel()
    assert (
        asyncio.run(dispatch_case_question(tenant, case, channel=channel, factory=app_factory))
        is True
    )
    # Re-dispatch the same pending question → no second send.
    assert (
        asyncio.run(dispatch_case_question(tenant, case, channel=channel, factory=app_factory))
        is False
    )
    assert len(channel.sent) == 1
    with tenant_session(tenant, factory=app_factory) as s:
        assert len(_outbound(s, case)) == 1


def test_dispatch_noop_when_nothing_pending(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "DispatchActionable-Co")
    admin_session.commit()
    # Actionable case (category + fault + desired_outcome) → elicit asks nothing → nothing to dispatch.
    case = _elicit_then_case(
        tenant,
        app_factory,
        governed={"category": "product_fault", "fault": "broken", "desired_outcome": "refund"},
        contact_ref="+44999",
    )
    channel = FakeChannel()
    assert (
        asyncio.run(dispatch_case_question(tenant, case, channel=channel, factory=app_factory))
        is False
    )
    assert channel.sent == []


def test_dispatch_noop_when_no_recipient(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "DispatchNoRecip-Co")
    admin_session.commit()
    # A pending question but no contact_ref to reply to (e.g. a file drop) → not sent (operator relays).
    case = _elicit_then_case(
        tenant, app_factory, governed={"category": "delivery_fulfilment"}, contact_ref=None
    )
    channel = FakeChannel()
    assert (
        asyncio.run(dispatch_case_question(tenant, case, channel=channel, factory=app_factory))
        is False
    )
    assert channel.sent == []


def test_elicit_chains_dispatch_when_it_asks(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "DispatchChain-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = _seed_case(s, governed={"category": "delivery_fulfilment"}, contact_ref="+44999")
    asyncio.run(elicit_case(tenant, case, factory=app_factory))  # asks the anchor → chains dispatch
    with tenant_session(tenant, factory=app_factory) as s:
        jobs = s.execute(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE task_name='pipeline.dispatch' AND args->>'case_id' = :c"
            ),
            {"c": str(case)},
        ).scalar_one()
    assert jobs == 1
