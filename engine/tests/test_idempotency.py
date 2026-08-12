"""Trust gate — idempotent stages + a rebuildable projection (CLAUDE.md §3, EDD §7.3).

Replaying a stage is a no-op; ``field_current`` recomputes from the append-only logs (latest
correction, else latest extraction) and is stable under repeated rebuilds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _now() -> datetime:
    return datetime.now(UTC)


def test_idempotency_key_is_deterministic_and_version_sensitive() -> None:
    base = {
        "source_sha256": "abc",
        "stage": "extract",
        "model_version": "m1",
        "prompt_version": "p1",
        "code_version": "c1",
    }
    assert api.compute_idempotency_key(**base) == api.compute_idempotency_key(**base)
    bumped = {**base, "prompt_version": "p2"}
    assert api.compute_idempotency_key(**base) != api.compute_idempotency_key(**bumped)


def test_completed_stage_blocks_replay(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A stage that ran to completion is skipped on replay (idempotent success)."""
    tenant = api.create_tenant(admin_session, "Idem-Co")
    admin_session.commit()
    key = api.compute_idempotency_key(
        source_sha256="s", stage="extract", model_version="m", prompt_version="p", code_version="c"
    )
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        first = api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case)
        api.complete_stage(s, idempotency_key=key)  # work finished successfully
    # Genuine replay in a new transaction → already done → skip.
    with tenant_session(tenant, factory=app_factory) as s:
        second = api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case)
    assert first is True
    assert second is False


def test_crashed_stage_is_reclaimable(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """A stage claimed but never completed (crash) must be re-claimable on replay — work is
    retried, not lost (CLAUDE.md §3)."""
    tenant = api.create_tenant(admin_session, "Crash-Co")
    admin_session.commit()
    key = api.compute_idempotency_key(
        source_sha256="s", stage="extract", model_version="m", prompt_version="p", code_version="c"
    )
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        first = api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case)
        # ...process "crashes" here — complete_stage is never called; row stays 'running'.
    with tenant_session(tenant, factory=app_factory) as s:
        retry = api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case)
        api.complete_stage(s, idempotency_key=key)
    with tenant_session(tenant, factory=app_factory) as s:
        after_done = api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case)
    assert first is True
    assert retry is True  # re-claimed, not skipped
    assert after_done is False  # now genuinely done


def test_field_current_rebuilds_from_logs(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Projection-Co")
    admin_session.commit()

    span = {"char_start": 0, "char_end": 5}
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        doc = api.add_source_document(
            s,
            case_id=case,
            sha256="c" * 64,
            blob_key="c" * 64,
            mime="text/plain",
            channel="file_drop",
            byte_size=5,
            received_at=_now(),
        )
        # Two extractions of the same field in one transaction (identical timestamps) —
        # the monotonic seq must still pick the later one deterministically.
        api.record_extraction(
            s,
            case_id=case,
            field_path="category",
            value="product_fault",
            model="fake",
            model_version="v1",
            prompt_version="p1",
            run_id=uuid4(),
            confidence=0.7,
            citations=[api.Citation(source_document_id=doc, role="primary", locator=span)],
        )
        ext2 = api.record_extraction(
            s,
            case_id=case,
            field_path="category",
            value="delivery_fulfilment",
            model="fake",
            model_version="v1",
            prompt_version="p1",
            run_id=uuid4(),
            confidence=0.9,
            citations=[api.Citation(source_document_id=doc, role="primary", locator=span)],
        )
        n = api.rebuild_field_current(s, case)
        row = s.execute(
            text(
                "SELECT value, source_kind, source_id, confidence FROM field_current "
                "WHERE case_id=:c AND field_path='category'"
            ),
            {"c": case},
        ).one()

    assert n == 1
    assert row[0] == "delivery_fulfilment"  # latest extraction wins
    assert row[1] == "extraction"
    assert str(row[2]) == str(ext2)
    assert row[3] == pytest.approx(0.9)

    # A correction supersedes the extraction; rebuild is idempotent.
    with tenant_session(tenant, factory=app_factory) as s:
        api.record_correction(
            s,
            case_id=case,
            field_path="category",
            prev_value="delivery_fulfilment",
            new_value="billing_charge",
            based_on_extraction_id=ext2,
            reviewer_id="rev-1",
        )
        api.rebuild_field_current(s, case)
        api.rebuild_field_current(s, case)  # twice → stable
        row2 = s.execute(
            text(
                "SELECT value, source_kind, confidence FROM field_current "
                "WHERE case_id=:c AND field_path='category'"
            ),
            {"c": case},
        ).one()
        count = s.execute(
            text("SELECT count(*) FROM field_current WHERE case_id=:c"), {"c": case}
        ).scalar_one()

    assert row2[0] == "billing_charge"  # correction wins over extraction
    assert row2[1] == "correction"
    assert row2[2] is None  # corrections carry no model confidence
    assert count == 1  # idempotent: no duplicate projection rows
