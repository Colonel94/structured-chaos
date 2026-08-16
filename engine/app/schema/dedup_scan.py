"""The dedup trigger — a periodic scan that runs qualifier-space synonym-merge across every tenant,
OFF the hot path and BEFORE promote_scan (remediation R1).

Why a scan, not inline in extract: embedding a qualifier with BGE-M3 + a possible LLM adjudication is
too heavy for the sub-60s intake path, and (like promotion) a merge mid-burst shouldn't cascade into
live intake. So dedup runs on the same debounced schedule as promotion, immediately BEFORE it, so
promotion counts the MERGED canonicals (two synonym qualifiers pool their support into one column
instead of both promoting as duplicates — the whole point of the moat's convergence claim).

The scan logic is factored out here (embedder/llm injected) so it is unit-testable without a running
Procrastinate worker or real models; ``queue.dedup_scan`` is the thin periodic task that injects the
real BGE-M3 + Ollama backends. Idempotent: ``dedup_registry`` only ever embeds variants not yet
embedded, so re-running merges only what is new since the last scan.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..backends.interfaces import EmbeddingBackend, LLMBackend
from ..obs.logging import get_logger
from ..store import api
from ..store.db import SessionFactory, admin_session, tenant_session
from .dedup import dedup_registry

log = get_logger(__name__)


async def scan_and_dedup(
    *,
    embedder: EmbeddingBackend,
    llm: LLMBackend,
    tenant_ids: list[UUID] | None = None,
    factory: sessionmaker[Session] | None = None,
) -> dict[UUID, dict[str, int]]:
    """Run head-scoped qualifier dedup across tenants (all by default). Returns the per-tenant method
    tally (seed/merge/admit_new/llm_merge/llm_admit) for observability/testing. ``tenant_ids`` may be
    supplied to scope the scan (tests); by default every tenant is scanned (admin session)."""
    factory = factory or SessionFactory
    if tenant_ids is None:
        with admin_session() as adm:
            tenant_ids = api.list_tenant_ids(adm)

    out: dict[UUID, dict[str, int]] = {}
    for tid in tenant_ids:
        with tenant_session(tid, factory=factory) as s:
            methods = await dedup_registry(s, embedder=embedder, llm=llm)
        out[tid] = methods
        if methods:
            log.info("dedup.scan", tenant=str(tid), **{f"m_{k}": v for k, v in methods.items()})
    return out
