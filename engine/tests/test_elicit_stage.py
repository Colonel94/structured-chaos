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

from app.elicit.policy import FAULT_OPTIONS
from app.elicit.stage import _fault_grounded, elicit_case
from app.resolve import ingest_object_collection
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _seed_case(
    session: Session,
    *,
    governed: dict[str, str],
    contact_ref: str | None = None,
    customer_text: str | None = None,
) -> UUID:
    """Create a case with the given governed fields already extracted (via the real append-only log
    + field_current projection), mimicking a post-extraction state the elicit stage reads.

    Also persists the customer's normalised text (``customer_text``, defaulting to the seeded ``fault``)
    so the closed-world fault-grounding check sees the words the fault was extracted from — matching
    production, where a real fault echoes the customer's own message."""
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
    api.save_normalised_content(
        session,
        case_id=case_id,
        source_document_id=doc,
        content_text=customer_text if customer_text is not None else governed.get("fault", ""),
        language="en",
        spans=[],
        stage="normalise",
        model="t",
        model_version="t",
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


# --- closed-world fault grounding (§4/§5) ---


def test_fault_grounding_distinguishes_stated_from_inferred() -> None:
    """The real cases from the portal: a customer-stated fault echoes their words and grounds; a fault
    the extractor inferred from the order record shares only the object noun and does not."""
    # Grounded: the fault repeats what the customer actually wrote.
    assert _fault_grounded(
        "the cake arrived completely melted and 2 hours late",
        "my cake showed up completely melted and 2 hours late, order BK-1001, I want my money back",
    )
    # Ungrounded: "i feel sad" + an order number → the extractor invented a delivery fault.
    assert not _fault_grounded(
        "the order was not delivered or was incorrect", "i feel sad my order was BK-1001 refund"
    )
    # The extractor's honest "no issue described" note is itself ungrounded → we ask what happened.
    assert not _fault_grounded(
        "The customer provided an order reference but did not describe any issue.", "i feel sad"
    )
    # Degenerate inputs never ground.
    assert not _fault_grounded(None, "anything") and not _fault_grounded("a fault", "")


def test_fault_that_narrates_the_customer_state_is_not_grounded() -> None:
    """Pure emotion with no concrete problem makes the extractor NARRATE THE CUSTOMER'S STATE ("the
    customer feels dismissed"). Even though "dismissed" lexically overlaps the message, that is not a
    fault we can act on or read back — so it must NOT ground (the portal would otherwise assert a
    fabricated category on pure emotion). A concrete problem describes the thing that went wrong."""
    # Emotion restated as a "fault", lexically overlapping the customer's words — must NOT ground.
    assert not _fault_grounded(
        "the customer feels dismissed and does not know how to explain it",
        "i am so upset, this whole experience has left me feeling completely dismissed",
    )
    assert not _fault_grounded(
        "The customer is expressing frustration and disappointment.",
        "i'm just really frustrated and disappointed by all of this",
    )
    # A concrete problem — describes the THING/EVENT, not the person — still grounds normally.
    assert _fault_grounded(
        "the wedding cake arrived three hours late and had collapsed",
        "the wedding cake arrived three hours late and had collapsed on one side",
    )


def test_stage_asks_what_happened_when_the_fault_is_not_grounded(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A case with an anchor and an extractor-inferred fault the customer never described: the stage
    must ask 'what happened' (a drill), not present the invented fault as fact or ask the outcome.
    """
    tenant = api.create_tenant(admin_session, "Ungrounded-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = _seed_case(
            s,
            governed={
                "category": "delivery_fulfilment",
                "fault": "the order was not delivered or was incorrect",
                "anchor_value": "BK-1",
            },
            customer_text="i feel sad",  # the customer never described the fault
        )

    asyncio.run(elicit_case(tenant, case, factory=app_factory))

    with tenant_session(tenant, factory=app_factory) as s:
        state, qcount, _a, _r = api.get_case_elicit_state(s, case)  # type: ignore[misc]
        meta = _elicit_meta(s, case)
    assert state == "incomplete" and qcount == 1 and meta["question_kind"] == "drill"
    assert meta["fault_grounded"] is False
    q = str(meta["next_question"])
    assert "What happened" in q and "put this right" not in q


def test_stage_analytical_drill_states_the_record_when_the_anchor_resolves(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """Moment 3: a sparse case whose anchor RESOLVES to an order → the fault drill STATES what the
    record shows and offers narrowed options, instead of the open "What happened?"."""
    tenant = api.create_tenant(admin_session, "Moment3-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        asyncio.run(
            ingest_object_collection(
                s,
                object_type="order",
                objects=[
                    {
                        "order_id": "BK-1",
                        "phone": "+441234",
                        "items": "cake",
                        "delivered_at": "18:42",
                    },
                    {
                        "order_id": "BK-2",
                        "phone": "+445678",
                        "items": "cake",
                        "delivered_at": "12:00",
                    },
                ],
            )
        )
        # Anchor stated + resolvable, but the customer described no fault (category=other, ungrounded).
        case = _seed_case(
            s,
            governed={"category": "other", "anchor_value": "BK-1"},
            customer_text="i feel sad",
        )

    asyncio.run(elicit_case(tenant, case, factory=app_factory))

    with tenant_session(tenant, factory=app_factory) as s:
        _state, _q, _a, _r = api.get_case_elicit_state(s, case)  # type: ignore[misc]
        meta = _elicit_meta(s, case)
    assert meta["question_kind"] == "drill"
    q = str(meta["next_question"])
    assert "found your order BK-1" in q  # STATES the record (Moment 3)
    assert "What happened" not in q
    assert meta["options"] == list(FAULT_OPTIONS)  # narrowed, tappable


def test_stage_asks_what_happened_for_emotional_venting_even_when_lexically_grounded(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """The subtle case: the customer only vented ("i feel let down"), and the extractor echoed that into
    a fault that IS lexically grounded ("feels let down…") but could not categorise it (category=other).
    Lexical grounding alone would accept it; the concrete-category signal catches it → ask what happened.
    """
    tenant = api.create_tenant(admin_session, "Venting-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = _seed_case(
            s,
            governed={
                "category": "other",  # the extractor saw no actionable complaint class
                "fault": "the customer feels let down after an unspecified event",
                "anchor_value": "BK-9",
            },
            customer_text="i feel really let down after everything today",  # grounds lexically
        )

    asyncio.run(elicit_case(tenant, case, factory=app_factory))

    with tenant_session(tenant, factory=app_factory) as s:
        state, _q, _a, _r = api.get_case_elicit_state(s, case)  # type: ignore[misc]
        meta = _elicit_meta(s, case)
    assert state == "incomplete" and meta["fault_grounded"] is False
    assert "What happened" in str(meta["next_question"])
