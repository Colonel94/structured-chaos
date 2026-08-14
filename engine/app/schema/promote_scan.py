"""The promotion trigger — a DEBOUNCED periodic scan, never a per-case call (2026-08-14).

Checking thresholds per case is cheap, but firing `promote()` at the tail of every extraction means a
promotion can trip mid-burst and cascade a backfill (re-extraction over history) straight into live
intake. So promotion runs on a schedule instead: this scans every tenant, promotes what has earned it,
and for each NEWLY-promoted concept enqueues a backfill job (on the low-priority queue). The
promotion-marking and the backfill enqueue commit together (transactional defer), so a promotion can't
be recorded without its backfill being queued, nor vice-versa.

The scan logic is factored out here (defer is injected) so it is unit-testable without a running
Procrastinate worker; `queue.promote_scan` is the thin periodic task that injects the real defer.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..obs.logging import get_logger
from ..store import api
from ..store.db import SessionFactory, admin_session, tenant_session
from .promote import PromotedConcept, promote

log = get_logger(__name__)

DEFAULT_BATCH_SIZE = 25

# defer(session, tenant_id, concept, categories, batch_size) — enqueue one backfill job. Given the
# tenant session so production can defer transactionally with the promotion commit.
DeferBackfill = Callable[[Session, UUID, PromotedConcept, list[str], int], None]


def scan_and_enqueue(
    defer_backfill: DeferBackfill,
    *,
    tenant_ids: list[UUID] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    factory: sessionmaker[Session] | None = None,
) -> list[tuple[UUID, PromotedConcept]]:
    """Promote across all tenants and enqueue backfill for the concepts promoted THIS scan. Returns
    the ``(tenant_id, concept)`` pairs enqueued — for observability/testing. Idempotent across scans:
    an already-promoted concept is not re-enqueued (its ``is_new`` is False). ``tenant_ids`` may be
    supplied to scope the scan (tests); by default every tenant is scanned (admin session)."""
    factory = factory or SessionFactory
    if tenant_ids is None:
        with admin_session() as adm:
            tenant_ids = api.list_tenant_ids(adm)

    enqueued: list[tuple[UUID, PromotedConcept]] = []
    for tid in tenant_ids:
        with tenant_session(tid, factory=factory) as s:
            for concept in promote(s):
                if not concept.is_new:
                    continue  # promoted on an earlier scan → already backfilled
                categories = api.concept_attested_categories(
                    s,
                    head=concept.head,
                    qualifier_composite=concept.concept_key if concept.kind == "variant" else None,
                )
                if not categories:
                    continue  # nothing to scope a backfill to (shouldn't happen for a promoted concept)
                defer_backfill(s, tid, concept, categories, batch_size)
                enqueued.append((tid, concept))
                log.info(
                    "promote.enqueue_backfill",
                    tenant=str(tid),
                    concept=concept.concept_key,
                    categories=len(categories),
                )
    return enqueued
