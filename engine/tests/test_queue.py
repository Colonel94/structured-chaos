"""Phase-2 exit gate — transactional enqueue: a job is atomic with its business write, so a
rollback leaves no phantom job and no orphan case, and a commit durably queues both. Plus the
dedicated low-priority backfill queue.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.queue import (
    BACKFILL_QUEUE,
    _fail_case_if_terminal,
    backfill,
    defer_in_transaction,
    persist,
)
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _now() -> datetime:
    return datetime.now(UTC)


def _jobs_for(session: Session, case_id: str) -> int:
    return session.execute(
        text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'case_id' = :c"),
        {"c": case_id},
    ).scalar_one()


def test_enqueue_commits_atomically_with_the_write(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Queue-Commit")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        defer_in_transaction(s, persist, tenant_id=str(tenant), case_id=str(case))
    # After commit: both the case and its job are durably present (no orphan).
    with tenant_session(tenant, factory=app_factory) as s:
        cases = s.execute(text("SELECT count(*) FROM case_record")).scalar_one()
        jobs = _jobs_for(s, str(case))
    assert cases == 1
    assert jobs == 1


def test_rollback_leaves_no_phantom_job_or_orphan_case(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Queue-Rollback")
    admin_session.commit()
    marker = uuid4().hex
    with (
        pytest.raises(RuntimeError),
        tenant_session(tenant, factory=app_factory) as s,
    ):
        api.create_case(s, channel="file_drop", first_contact_at=_now())
        defer_in_transaction(s, persist, tenant_id=str(tenant), case_id=marker)
        raise RuntimeError("force rollback")
    # After rollback: neither the job nor the case exists.
    with tenant_session(tenant, factory=app_factory) as s:
        cases = s.execute(text("SELECT count(*) FROM case_record")).scalar_one()
        jobs = _jobs_for(s, marker)
    assert cases == 0  # no orphan case
    assert jobs == 0  # no phantom job


def test_backfill_uses_its_own_low_priority_queue(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Queue-Backfill")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        api.create_case(s, channel="file_drop", first_contact_at=_now())
        defer_in_transaction(
            s,
            backfill,
            queue=BACKFILL_QUEUE,
            tenant_id=str(tenant),
            concept_key="amount",
            head="amount",
            qualifier=None,
            categories=["billing_charge"],
            batch_size=25,
        )
    with tenant_session(tenant, factory=app_factory) as s:
        queue_name = s.execute(
            text(
                "SELECT queue_name FROM procrastinate_jobs "
                "WHERE task_name='pipeline.backfill' ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()
    assert queue_name == BACKFILL_QUEUE


def test_job_args_carry_ids_only_never_content(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """The queue is un-RLS'd, un-redacted infra — job args must carry only IDs, never customer
    content, or a job row becomes a cross-tenant / PII leak channel (bypasses the isolation +
    no-PII-in-logs gates at once). Establish + enforce the invariant now, before Phase-3 stages
    are tempted to stuff normalised text into args."""
    tenant = api.create_tenant(admin_session, "Queue-Args")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        defer_in_transaction(s, persist, tenant_id=str(tenant), case_id=str(case))
        defer_in_transaction(
            s,
            backfill,
            queue=BACKFILL_QUEUE,
            tenant_id=str(tenant),
            concept_key="amount",
            head="amount",
            qualifier=None,
            categories=["billing_charge"],
            batch_size=25,
        )
    # All id-typed keys — never content. source_document_id (the Phase-3 normalise stage's arg) is a
    # UUID id, in keeping with the invariant; adding it here as new id-args land is not a weakening.
    allowed = {
        "tenant_id",
        "case_id",
        "field_path",
        "idempotency_key",
        "stage",
        "source_document_id",
        # Backfill args (Path A STAGE 6): all schema-metadata, never customer content — the concept
        # key / head / qualifier are column-name tokens (like field_path), categories are closed
        # governed-taxonomy values, batch_size is an int.
        "concept_key",
        "head",
        "qualifier",
        "categories",
        "batch_size",
    }
    with tenant_session(tenant, factory=app_factory) as s:
        all_args = s.execute(text("SELECT args FROM procrastinate_jobs")).scalars().all()
    for args in all_args:
        stray = set(args.keys()) - allowed
        assert not stray, f"job args carry non-id keys (leak risk): {stray}"


# ------------------------------------------------------------ honest terminal-failure marking (Fix 1)


class _FakeTask:
    """Stands in for a Procrastinate Task: ``get_retry_exception`` returns None when no retry remains
    (terminal), or a truthy sentinel while a retry is still pending — the exact signal the real strategy
    emits, so the marking helper's decision is tested without a live worker."""

    def __init__(self, *, terminal: bool) -> None:
        self._terminal = terminal

    def get_retry_exception(self, *, exception: BaseException, job: object) -> object | None:
        return None if self._terminal else object()


class _FakeCtx:
    def __init__(self, *, terminal: bool) -> None:
        self.task = _FakeTask(terminal=terminal)
        self.job = object()


def _case_state(app_factory: sessionmaker[Session], tenant: str, case_id: str) -> str:
    with tenant_session(tenant, factory=app_factory) as s:
        return str(
            s.execute(
                text("SELECT case_state FROM case_record WHERE id = :c"), {"c": case_id}
            ).scalar()
        )


def test_terminal_failure_marks_case_processing_failed(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """When a stage's retries are EXHAUSTED, the case is stamped ``processing_failed`` (it must surface
    honestly, never as a done-but-empty case)."""
    tenant = api.create_tenant(admin_session, "Terminal-Fail")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="web", first_contact_at=_now())
    _fail_case_if_terminal(
        _FakeCtx(terminal=True),  # type: ignore[arg-type]
        RuntimeError("ollama crashed"),
        tenant_id=str(tenant),
        case_id=str(case),
        stage="extract",
        factory=app_factory,
    )
    assert _case_state(app_factory, str(tenant), str(case)) == "processing_failed"


def test_retryable_failure_leaves_case_in_flight(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """While a retry is still pending, the case is NOT marked failed — the customer keeps seeing
    "still working", and a successful retry recovers it normally (no false failure flicker)."""
    tenant = api.create_tenant(admin_session, "Retryable")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="web", first_contact_at=_now())
    _fail_case_if_terminal(
        _FakeCtx(terminal=False),  # type: ignore[arg-type]
        RuntimeError("transient blip"),
        tenant_id=str(tenant),
        case_id=str(case),
        stage="extract",
        factory=app_factory,
    )
    assert _case_state(app_factory, str(tenant), str(case)) == "created"
