"""Guard test for the orphaned-job reaper — the fix for a worker killed mid-job leaving a case stuck.

A real iPhone voice test hit this: a worker was killed mid-transcription, its ``pipeline.normalise`` job
sat in ``doing`` forever (Procrastinate did not re-queue it), and the case hung at ``created`` while the
live worker still looked healthy. On startup, holding the queue-set's exclusive singleton lock, the worker
releases every ``doing`` job on its queues back to ``todo`` so it re-runs.

This proves the SQL contract against a real Postgres: only ``doing`` jobs, only on the worker's queues,
are released (and their ``worker_id`` cleared so they are re-fetchable); a ``doing`` job on another
queue-set (a live sibling worker's) and any already-finished job are left untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest

from app.queue import _conninfo

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_worker import reap_orphaned_jobs

pytestmark = pytest.mark.usefixtures("pg")


def _insert_job(conn: psycopg.Connection, *, queue: str, status: str) -> int:
    row = conn.execute(
        "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status, priority, attempts) "
        "VALUES (%s, 'pipeline.normalise', '{}'::jsonb, %s::procrastinate_job_status, 0, 0) "
        "RETURNING id",
        (queue, status),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_reaper_releases_only_orphaned_doing_jobs_on_its_queues() -> None:
    """Only a ``doing`` job on the worker's own queue-set is released; other queues and finished jobs are
    left alone."""
    conn = psycopg.connect(_conninfo(), autocommit=True)
    try:
        doing_default = _insert_job(conn, queue="default", status="doing")
        doing_backfill = _insert_job(
            conn, queue="backfill", status="doing"
        )  # a sibling worker's queue
        todo_default = _insert_job(conn, queue="default", status="todo")
        done_default = _insert_job(conn, queue="default", status="succeeded")

        reaped = reap_orphaned_jobs(conn, ["default"])
        assert reaped == [
            doing_default
        ]  # exactly the orphaned doing job on THIS queue-set

        def state(jid: int) -> tuple[str, object]:
            r = conn.execute(
                "SELECT status::text, worker_id FROM procrastinate_jobs WHERE id = %s",
                (jid,),
            ).fetchone()
            assert r is not None
            return (str(r[0]), r[1])

        assert state(doing_default) == (
            "todo",
            None,
        )  # released + owner cleared → re-fetchable
        assert (
            state(doing_backfill)[0] == "doing"
        )  # another queue-set (a live sibling) is untouched
        assert state(todo_default)[0] == "todo"  # a waiting job is untouched
        assert (
            state(done_default)[0] == "succeeded"
        )  # a finished job is never resurrected
    finally:
        conn.close()


def test_reaper_is_a_noop_when_nothing_is_orphaned() -> None:
    """No ``doing`` jobs → nothing released (and no crash)."""
    conn = psycopg.connect(_conninfo(), autocommit=True)
    try:
        _insert_job(conn, queue="default", status="todo")
        assert reap_orphaned_jobs(conn, ["default"]) == []
    finally:
        conn.close()
