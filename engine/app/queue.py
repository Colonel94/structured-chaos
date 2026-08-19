"""Procrastinate task queue — transactional enqueue on our psycopg3 stack (Phase 2).

The whole point is **transactional enqueue**: a job is deferred on the *same* psycopg3 connection
that carries the business write, so enqueue is atomic with it. If the transaction rolls back the job
is never queued (no phantom); if it commits the job is durably queued (no orphan). We use
Procrastinate's native ``SyncPsycopgConnector`` (psycopg3) — its ``defer_job(job, connection=…)``
runs the enqueue INSERT on the connection we hand it, which is our tenant transaction's raw
connection. (The psycopg2 SQLAlchemy connector was rejected: it double-escapes ``%`` for psycopg2's
paramstyle and errors against a psycopg3 connection.)

Procrastinate's own tables live in the same DB but are NOT tenant-scoped (queue infra). The runtime
``app_rw`` role is granted only on ``procrastinate_*`` objects — never broadening its scope on the
trust-spine tables. Real pipeline stages wire their bodies in Phase 3; the tasks here are the queue
contract (idempotent/retryable via the Phase-1 stage ledger) + a dedicated low-priority backfill queue.
"""

from __future__ import annotations

from typing import Any

import psycopg
from procrastinate import App, PsycopgConnector, SyncPsycopgConnector
from sqlalchemy.orm import Session

from .config import Settings, settings

DEFAULT_QUEUE = "default"
BACKFILL_QUEUE = "backfill"  # promotion backfill runs here — low priority, never blocks intake


def _conninfo(cfg: Settings = settings, *, admin: bool = False) -> str:
    user = cfg.postgres_admin_user if admin else cfg.postgres_user
    pw = cfg.postgres_admin_password if admin else cfg.postgres_password
    return (
        f"host={cfg.postgres_host} port={cfg.postgres_port} dbname={cfg.postgres_db} "
        f"user={user} password={pw}"
    )


# The runtime connects as the least-privilege app_rw (granted on procrastinate_* only).
#
# TWO connectors for one hard constraint. Deferring is SYNCHRONOUS everywhere it happens — inside a
# SQLAlchemy transaction in the engine, AND inside the worker's task bodies (which run
# `asyncio.run(...)` then defer the next stage). A native SyncPsycopgConnector is the only thing that
# works in BOTH: an async connector's sync bridge (get_sync_connector → AsyncToSync) deadlocks on the
# worker task's own running event loop. So ``app`` (the module default, used for every defer) is sync.
# But the worker PROCESS itself needs an async connector to listen/fetch, so ``worker_app`` is an async
# twin sharing the same task registry; the worker entrypoint (scripts/run_worker.py) runs it. The
# periodic promote-scan is deliberately NOT an @app.periodic (the twin can't run procrastinate's
# periodic deferrer) — the entrypoint's own scheduler loop defers it instead.
connector = SyncPsycopgConnector(conninfo=_conninfo())
app = App(connector=connector)


@app.task(name="pipeline.persist", queue=DEFAULT_QUEUE)
def persist(*, tenant_id: str, case_id: str) -> str:
    """Retained queue-contract placeholder (Phase 2). The first real stage body is
    :func:`normalise_document` below; this stays as the minimal enqueue-contract task the Phase-2
    transactional-enqueue tests exercise. Returns the case id it handled."""
    return case_id


@app.task(name="pipeline.normalise", queue=DEFAULT_QUEUE)
def normalise_document(*, tenant_id: str, source_document_id: str) -> str:
    """Real Phase-3 stage body: normalise one source document (transcript/OCR/text + provenance
    spans), guarded by the Phase-1 idempotency ledger. Sync task → runs in Procrastinate's worker
    thread; ``asyncio.run`` drives the async stage function (which awaits blob + ASR/OCR). Imported
    lazily so ``queue`` stays import-light. Returns the document id handled."""
    import asyncio
    from uuid import UUID

    from .pipeline import normalise_source_document

    asyncio.run(normalise_source_document(tenant_id, UUID(source_document_id)))
    return source_document_id


@app.task(name="pipeline.extract", queue=DEFAULT_QUEUE)
def extract_case_task(*, tenant_id: str, case_id: str) -> str:
    """Real Phase-4 stage body: extract the governed core + grounded emergent for one case from its
    normalised text, guarded by the Phase-1 idempotency ledger. Enqueued transactionally by the
    normalise stage the moment a document's normalisation completes, so extraction chains straight off
    intake with no manual trigger (4.7). Sync task → ``asyncio.run`` drives the async stage. Imported
    lazily to keep ``queue`` import-light. Returns the case id handled."""
    import asyncio
    from uuid import UUID

    from .extract.stage import extract_case

    asyncio.run(extract_case(tenant_id, UUID(case_id)))
    return case_id


@app.task(name="pipeline.elicit", queue=DEFAULT_QUEUE)
def elicit_case_task(*, tenant_id: str, case_id: str) -> str:
    """Phase-5 stage body: decide the next elicitation move (the anchor + two-drill budget, enforced in
    code) for one case. Enqueued transactionally by the extract stage the moment a case's governed core
    is (re-)extracted, so each customer reply → re-extraction → the drill advances with no manual
    trigger. Sync task → ``asyncio.run`` drives the async stage. Imported lazily to keep ``queue``
    import-light. Returns the case id handled."""
    import asyncio
    from uuid import UUID

    from .backends.registry import get_blob, get_llm
    from .elicit.stage import elicit_case

    # blob → object-snapshot-on-bind (provenance); llm → complaint-vs-record contradiction check.
    asyncio.run(elicit_case(tenant_id, UUID(case_id), llm=get_llm(), blob=get_blob()))
    return case_id


@app.task(name="pipeline.dispatch", queue=DEFAULT_QUEUE)
def dispatch_case_task(*, tenant_id: str, case_id: str) -> str:
    """Phase-5 egress: transmit a case's pending elicitation question over its channel, once. Enqueued
    transactionally by the elicit stage whenever it issues a question, so the drill's question is sent
    with no manual trigger; the customer's reply re-enters intake and advances the loop. Idempotent (the
    outbound ledger's UNIQUE key). Sync task → ``asyncio.run``. Returns the case id handled."""
    import asyncio
    from uuid import UUID

    from .backends.registry import get_channel
    from .channel.dispatch import dispatch_case_question

    asyncio.run(dispatch_case_question(tenant_id, UUID(case_id), channel=get_channel()))
    return case_id


@app.task(name="pipeline.rules", queue=DEFAULT_QUEUE)
def rules_case_task(*, tenant_id: str, case_id: str) -> str:
    """Phase-6 stage body: compute the deterministic priority/SLA/routing decision for one case.
    Enqueued transactionally by the extract stage (parallel to elicit) the moment a case's governed core
    is (re-)extracted, so the SLA clock + routing are set with no manual trigger and recompute whenever a
    signal changes. Sync stage (no model call) → called directly, no ``asyncio.run``. Imported lazily to
    keep ``queue`` import-light. Returns the case id handled."""
    from uuid import UUID

    from .rules.stage import decide_case

    decide_case(tenant_id, UUID(case_id))
    return case_id


@app.task(name="pipeline.backfill", queue=BACKFILL_QUEUE)
def backfill(
    *,
    tenant_id: str,
    concept_key: str,
    head: str,
    qualifier: str | None,
    categories: list[str],
    batch_size: int,
) -> str:
    """Retroactive backfill of a promoted concept: re-EXTRACT it across a bounded batch of the
    concept's historical cases (STAGE 6, the moat — NOT a re-projection). Runs one batch, then
    re-enqueues itself on the low-priority backfill queue while cases remain, so a promotion that fans
    out to a whole category drains in bounded steps and never blocks intake. Imported lazily to keep
    ``queue`` import-light. Returns the concept handled."""
    import asyncio

    from .schema.backfill import backfill_concept_batch

    result = asyncio.run(
        backfill_concept_batch(
            tenant_id,
            concept_key=concept_key,
            head=head,
            qualifier=qualifier,
            categories=categories,
            batch_size=batch_size,
        )
    )
    if result.more:  # a full batch came back → more cases remain → next batch
        backfill.defer(
            tenant_id=tenant_id,
            concept_key=concept_key,
            head=head,
            qualifier=qualifier,
            categories=categories,
            batch_size=batch_size,
        )
    return concept_key


@app.task(name="pipeline.dedup_scan", queue=DEFAULT_QUEUE)
def dedup_scan() -> str:
    """Off-hot-path qualifier-space dedup (remediation R1) — head-scoped synonym-merge over every
    tenant's emergent registry, so synonym qualifiers collapse to ONE canonical BEFORE promote_scan can
    split them into duplicate columns. Deferred on an interval by the worker scheduler loop, immediately
    BEFORE promote_scan. Sync task → ``asyncio.run`` drives the async embed/adjudicate. Lazy imports
    keep ``queue`` import-light."""
    import asyncio

    from .backends.registry import get_embedding, get_llm
    from .schema.dedup_scan import scan_and_dedup

    asyncio.run(scan_and_dedup(embedder=get_embedding(), llm=get_llm()))
    return "ok"


@app.task(name="pipeline.mint_scan", queue=DEFAULT_QUEUE)
def mint_scan() -> str:
    """Head-minting scan (remediation, the R2 pivot) — cluster each tenant's escape-valve facts and mint
    a NEW head for every cluster recurring across >= PROMOTE_HEAD_N distinct cases, then re-extract the
    affected cases so the minted column RE-HOMES history (the vocab-aware idempotency key makes that
    re-extraction fire instead of skipping). Runs AFTER dedup, BEFORE promote. Sync task → asyncio.run
    drives the async embed/name. Lazy imports keep ``queue`` light."""
    import asyncio

    from .backends.registry import get_embedding, get_llm
    from .schema.mint_scan import scan_and_mint

    minted = asyncio.run(scan_and_mint(embedder=get_embedding(), llm=get_llm()))
    for tid, heads in minted.items():
        for _head, _support, cases in heads:
            for cid in cases:
                extract_case_task.defer(tenant_id=str(tid), case_id=str(cid))
    return "ok"


@app.task(name="pipeline.promote_scan", queue=DEFAULT_QUEUE)
def promote_scan() -> str:
    """DEBOUNCED promotion trigger — never per case (a promotion mid-burst must not cascade backfill
    into live intake). Deferred on an interval by the worker entrypoint's scheduler loop
    (scripts/run_worker.py), NOT via @app.periodic (the async worker twin can't run procrastinate's
    periodic deferrer — see the connector note above). Promotes across all tenants and transactionally
    enqueues a backfill job for each concept newly promoted this scan. Lazy import keeps queue light.
    """
    from .schema.promote_scan import scan_and_enqueue

    def _defer(
        session: Session,
        tenant_id: Any,
        concept: Any,
        categories: list[str],
        batch_size: int,
    ) -> None:
        # Enqueue on the SAME transaction that marks the promotion → promote + enqueue commit together.
        defer_in_transaction(
            session,
            backfill,
            queue=BACKFILL_QUEUE,
            tenant_id=str(tenant_id),
            concept_key=concept.concept_key,
            head=concept.head,
            qualifier=concept.qualifier,
            categories=categories,
            batch_size=batch_size,
        )

    scan_and_enqueue(_defer)
    return "ok"


# The async twin the WORKER process runs (scripts/run_worker.py). Defined after every @app.task above
# so it shares the full task registry. with_connector keeps each task's `.app` pointing at the SYNC
# `app`, which is exactly what we want: a task body's `.defer()` / defer_in_transaction stays
# native-sync even while the worker's fetch/listen runs async. (with_connector is deprecated for the
# general case precisely because of that task→app link; here that link is the feature, not a bug.)
# There are no @app.periodic tasks, so the twin's periodic deferrer is a no-op and never crashes.
worker_app = app.with_connector(PsycopgConnector(conninfo=_conninfo()))


def raw_psycopg_connection(session: Session) -> psycopg.Connection[Any]:
    """The raw psycopg3 Connection under a SQLAlchemy session's current transaction — the seam
    that makes the enqueue share the caller's transaction."""
    return session.connection().connection.driver_connection  # type: ignore[return-value]


def defer_in_transaction(
    session: Session, task: Any, *, queue: str = DEFAULT_QUEUE, **task_kwargs: Any
) -> Any:
    """Enqueue ``task`` atomically inside the caller's DB transaction. Commit → job durably queued;
    rollback → job never existed. Returns the deferred Job."""
    job = task.configure(queue=queue).make_new_job(**task_kwargs)
    app.job_manager.defer_job(job, connection=raw_psycopg_connection(session))
    return job


# Grants scoped to procrastinate_* objects only — the app_rw role can enqueue/work jobs without
# gaining any privilege on the trust-spine tables.
PROCRASTINATE_GRANTS = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables
           WHERE schemaname='public' AND tablename LIKE 'procrastinate%' LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO app_rw', r.tablename);
  END LOOP;
  FOR r IN SELECT sequencename FROM pg_sequences
           WHERE schemaname='public' AND sequencename LIKE 'procrastinate%' LOOP
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I TO app_rw', r.sequencename);
  END LOOP;
  FOR r IN SELECT p.proname, pg_get_function_identity_arguments(p.oid) AS args
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public' AND p.proname LIKE 'procrastinate%' LOOP
    EXECUTE format('GRANT EXECUTE ON FUNCTION %I(%s) TO app_rw', r.proname, r.args);
  END LOOP;
END $$;
"""


def apply_procrastinate_schema(admin_conninfo: str) -> None:
    """Idempotently apply Procrastinate's schema + the app_rw grants (admin connection). Kept out
    of Alembic because Procrastinate owns/versions its own schema; run once per DB (bootstrap
    script for the live stack, test fixture for CI)."""
    schema_sql = app.schema_manager.get_schema()
    with psycopg.connect(admin_conninfo, autocommit=True) as pc:
        already = pc.execute("SELECT to_regclass('public.procrastinate_jobs')").fetchone()
        if already is None or already[0] is None:
            pc.execute(schema_sql)
        pc.execute(PROCRASTINATE_GRANTS)


def admin_conninfo(cfg: Settings = settings) -> str:
    return _conninfo(cfg, admin=True)
