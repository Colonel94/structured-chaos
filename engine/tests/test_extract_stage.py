"""Phase 4.1 — the extract pipeline stage, end-to-end (EDD §6, trust spine).

DB-backed (testcontainers). ingest → normalise → extract, with a scripted LLM so the assertions are
deterministic: governed core + grounded emergent persist through the append-only field_extraction log
with citations, the emergent-field registry is maintained, field_current projects, an ungrounded
candidate is dropped, and a replay is a no-op.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.backends.fake import FakeBlob
from app.extract.stage import extract_case
from app.intake.ingest import ingest_messages
from app.intake.models import InboundMessage
from app.store import api, meter
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

_CASE_TEXT = "chocolate cake order 4471 arrived crushed and late, I want a refund"


class _ScriptedLLM:
    def __init__(self) -> None:
        self.last_usage = {"wall_ms": 5.0, "tokens_in": 100.0, "tokens_out": 40.0}
        self._payload = json.dumps(
            {
                "category": "product_fault",
                "fault": "cake crushed and late",
                "desired_outcome": "refund",
                "emotion_signal": "frustrated",
                "severity_signal": "none",
                "anchor_value": "4471",
                "emergent_attributes": [
                    # Path A shape: head (closed vocab) + open qualifier + value.
                    {"head": "product", "qualifier": None, "value": "chocolate cake"},  # grounded
                    {"head": "condition", "qualifier": "crushed", "value": "crushed"},  # grounded
                    {"head": "description", "qualifier": None, "value": "bright green"},  # dropped
                ],
            }
        )

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._payload


async def test_extract_stage_persists_governed_and_grounded_emergent(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Extract-Co")
    admin_session.commit()
    blob = FakeBlob()
    msg = InboundMessage(
        channel="file_drop",
        sender="+9715",
        sent_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        text=_CASE_TEXT,
    )
    res = await ingest_messages(tenant, [msg], blob=blob, factory=app_factory)
    case_id = res.case_ids[0]
    for sdid in res.source_document_ids:
        from app.pipeline import normalise_source_document

        await normalise_source_document(tenant, sdid, blob=blob, factory=app_factory)

    llm = _ScriptedLLM()
    assert await extract_case(tenant, case_id, llm=llm, factory=app_factory) is True

    with tenant_session(tenant, factory=app_factory) as s:
        gov = s.execute(
            text(
                "SELECT count(*) FROM field_extraction WHERE case_id=:c AND layer='governed_core'"
            ),
            {"c": case_id},
        ).scalar_one()
        emg = (
            s.execute(
                text(
                    "SELECT field_path FROM field_extraction WHERE case_id=:c AND layer='emergent'"
                ),
                {"c": case_id},
            )
            .scalars()
            .all()
        )
        reg = s.execute(
            text("SELECT field_name, support_count FROM emergent_field ORDER BY field_name")
        ).all()
        fc = s.execute(
            text("SELECT count(*) FROM field_current WHERE case_id=:c"), {"c": case_id}
        ).scalar_one()
        cost = meter.case_cost(s, case_id)

    # 6 governed (category, fault, desired_outcome, emotion, severity, anchor) — all non-null here.
    assert gov == 6
    # 2 grounded emergent (composite names); the ungrounded "bright green" description was dropped.
    assert set(emg) == {"product", "crushed_condition"}
    assert {r[0]: r[1] for r in reg} == {"product": 1, "crushed_condition": 1}  # registry support
    assert fc == 8  # projection = 6 governed + 2 emergent
    assert cost["calls"] >= 1  # the extraction LLM call was metered

    # Replay is a no-op (idempotency ledger).
    assert await extract_case(tenant, case_id, llm=llm, factory=app_factory) is False


async def test_null_desired_outcome_is_not_recorded(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """Refuse-to-guess: a governed field the model returned null for is absent from the log (→ it
    will be elicited), not stored as a guess."""

    class _NullOutcomeLLM:
        last_usage: ClassVar[dict[str, float]] = {}

        async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
            return json.dumps(
                {
                    "category": "UNCLEAR",
                    "fault": "delivery was bad",
                    "desired_outcome": None,
                    "emotion_signal": "calm",
                    "severity_signal": "none",
                    "anchor_value": None,
                    "emergent_attributes": [],
                }
            )

    tenant = api.create_tenant(admin_session, "NullOutcome-Co")
    admin_session.commit()
    blob = FakeBlob()
    msg = InboundMessage(
        "file_drop", "+9715", datetime(2026, 8, 13, tzinfo=UTC), text="delivery was bad"
    )
    res = await ingest_messages(tenant, [msg], blob=blob, factory=app_factory)
    case_id = res.case_ids[0]
    from app.pipeline import normalise_source_document

    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob, factory=app_factory)
    await extract_case(tenant, case_id, llm=_NullOutcomeLLM(), factory=app_factory)

    with tenant_session(tenant, factory=app_factory) as s:
        paths = (
            s.execute(
                text("SELECT field_path FROM field_extraction WHERE case_id=:c"), {"c": case_id}
            )
            .scalars()
            .all()
        )
    assert "desired_outcome" not in paths  # null → not recorded
    assert "anchor_value" not in paths  # null → not recorded
    assert "category" in paths  # present values still recorded
