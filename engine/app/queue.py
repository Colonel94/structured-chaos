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
from procrastinate import App, SyncPsycopgConnector
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


# The worker connects as the least-privilege app_rw (granted on procrastinate_* only). For
# transactional defer the connector's own conninfo is irrelevant — the enqueue uses the caller's
# connection — so this is safe to build at import time.
connector = SyncPsycopgConnector(conninfo=_conninfo())
app = App(connector=connector)


@app.task(name="pipeline.persist", queue=DEFAULT_QUEUE)
def persist(*, tenant_id: str, case_id: str) -> str:
    """Placeholder pipeline stage — the queue contract, body wired in Phase 3. Real stages will
    reopen a tenant session and run one idempotent stage (guarded by the Phase-1 claim_stage
    ledger). Returns the case id it handled."""
    return case_id


@app.task(name="pipeline.backfill", queue=BACKFILL_QUEUE)
def backfill(*, tenant_id: str, field_path: str) -> str:
    """Placeholder low-priority backfill stage (own queue so it never blocks intake). Body in
    Phase 4 (re-extract history after a field promotes)."""
    return field_path


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
