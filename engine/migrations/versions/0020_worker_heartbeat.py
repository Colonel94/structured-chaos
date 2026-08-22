"""Worker liveness heartbeat — an honest 'the worker is down' signal (Phase: ops/trust, R3)

A dead worker used to be indistinguishable from a slow one: the portal showed a case as
"still working…" indefinitely (or, after ``portal_stall_seconds``, "taking a little longer" — copy that
still implies someone will get to it soon). If the worker process is actually DOWN, that is a lie of
omission — nothing is going to advance the case until a human intervenes.

This table is the liveness signal. Every worker upserts its queue-set's ``beat_at`` on a short interval
(``scripts/run_worker.py``); the portal and ``/health`` read it. When the intake worker's heartbeat is
stale AND a case is still processing, the portal switches immediately to the honest handoff copy — the
same "we've hit a snag, a person is taking over" the ``processing_failed`` path uses — instead of an
open-ended spinner.

Operational, tenant-agnostic: NO RLS (it is not tenant data — it is process health), a plain grant to
``app_rw`` so both the worker (write) and the engine (read) can use it. One row per queue-set.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_worker_heartbeat"
down_revision: str | None = "0019_processing_failed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE worker_heartbeat (
            queue    text        PRIMARY KEY,
            beat_at  timestamptz NOT NULL DEFAULT now()
        )
        """)
    # The worker (app_rw) writes; the engine (app_rw) reads. Not a tenant table → no RLS.
    op.execute("GRANT SELECT, INSERT, UPDATE ON worker_heartbeat TO app_rw")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS worker_heartbeat")
