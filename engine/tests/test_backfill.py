"""Phase 4 STAGE 6 — retroactive backfill re-extracts a promoted concept across history (the moat).

DB-backed (testcontainers). Seeds cases through the real ingest→normalise path (so there are retained
originals + normalised text), then runs the backfill batch with a scripted concept-LLM and asserts:
re-extraction writes a NEW field_extraction row with fresh provenance where the concept is found; an
``absent`` marker where it isn't; category scoping excludes out-of-scope cases; every call is metered;
and a second run is a no-op (the attempt markers make it idempotent — no re-extracting forever).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.backends.fake import FakeBlob
from app.intake.ingest import ingest_messages
from app.intake.models import InboundMessage
from app.pipeline import normalise_source_document
from app.schema.backfill import backfill_concept_batch
from app.store import api, meter
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


class _ConceptLLM:
    """Says a case HAS the amount iff its text contains "$45.00" (the seeded amount) — otherwise
    absent. Lets us seed found/absent cases deterministically by their text."""

    def __init__(self) -> None:
        self.last_usage = {"wall_ms": 5.0, "tokens_in": 10.0, "tokens_out": 5.0}

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        if "$45.00" in prompt:
            return json.dumps({"present": True, "value": "$45.00", "qualifier": "late"})
        return json.dumps({"present": False, "value": None, "qualifier": None})


async def _seed_case(
    tenant: object,
    factory: sessionmaker[Session],
    *,
    sender: str,
    body: str,
    category: str,
    when: datetime,
) -> object:
    """A case with a retained original + normalised text + a governed category — but NO prior
    extraction of the backfill concept (exactly the historical case backfill must reach). A distinct
    ``sender`` per call so windowing makes each its own case (same sender would merge them)."""
    blob = FakeBlob()
    msg = InboundMessage(channel="file_drop", sender=sender, sent_at=when, text=body)
    res = await ingest_messages(tenant, [msg], blob=blob, factory=factory)
    case_id = res.case_ids[0]
    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob, factory=factory)
    sd = res.source_document_ids[0]
    with tenant_session(tenant, factory=factory) as s:
        api.record_extraction(
            s,
            case_id=case_id,
            field_path="category",
            value=category,
            model="m",
            model_version="m",
            prompt_version="p",
            run_id=uuid4(),
            confidence=0.5,
            citations=[api.Citation(source_document_id=sd, role="primary")],
            layer="governed_core",
        )
        api.rebuild_field_current(s, case_id)
    return case_id


async def test_backfill_reextracts_history_and_is_idempotent(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Backfill-Co")
    admin_session.commit()

    # Two in-scope cases: A states an amount, B does not. C is a different category → out of scope.
    case_a = await _seed_case(
        tenant,
        app_factory,
        sender="+97150000001",
        body="the late fee was $45.00 on my account",
        category="billing_charge",
        when=datetime(2026, 1, 1, tzinfo=UTC),
    )
    case_b = await _seed_case(
        tenant,
        app_factory,
        sender="+97150000002",
        body="I am unhappy with the service quality",
        category="billing_charge",
        when=datetime(2026, 1, 2, tzinfo=UTC),
    )
    case_c = await _seed_case(
        tenant,
        app_factory,
        sender="+97150000003",
        body="there was a $45.00 charge here too",
        category="other",
        when=datetime(2026, 1, 3, tzinfo=UTC),
    )

    llm = _ConceptLLM()
    result = await backfill_concept_batch(
        tenant,
        concept_key="amount",
        head="amount",
        qualifier=None,
        categories=["billing_charge"],
        batch_size=10,
        llm=llm,
        factory=app_factory,
    )

    assert (result.scanned, result.found, result.absent, result.more) == (2, 1, 1, False)

    with tenant_session(tenant, factory=app_factory) as s:
        a_emergent = s.execute(
            text(
                "SELECT field_path, value #>> '{}' FROM field_extraction "
                "WHERE case_id=:c AND layer='emergent'"
            ),
            {"c": case_a},
        ).all()
        a_current = s.execute(
            text(
                "SELECT value #>> '{}' FROM field_current WHERE case_id=:c AND field_path='late_amount'"
            ),
            {"c": case_a},
        ).scalar_one_or_none()
        attempts = dict(
            s.execute(
                text(
                    "SELECT case_id::text, outcome FROM backfill_attempt WHERE concept_key='amount'"
                )
            ).all()
        )
        a_cost = meter.case_cost(s, case_a)  # metered per case

    # A: re-extraction wrote a NEW emergent row (with provenance — record_extraction requires a
    # citation) and projected it; the concept was populated retroactively.
    assert ("late_amount", "$45.00") in a_emergent
    assert a_current == "$45.00"
    assert a_cost["calls"] >= 1  # the re-extraction was metered against the case
    # A found, B absent, C never scanned (category scoping).
    assert attempts.get(str(case_a)) == "found"
    assert attempts.get(str(case_b)) == "absent"
    assert str(case_c) not in attempts

    # Idempotent: everything in scope was attempted → a second run scans nothing (no re-extract-forever).
    again = await backfill_concept_batch(
        tenant,
        concept_key="amount",
        head="amount",
        qualifier=None,
        categories=["billing_charge"],
        batch_size=10,
        llm=llm,
        factory=app_factory,
    )
    assert (again.scanned, again.found, again.absent) == (0, 0, 0)
