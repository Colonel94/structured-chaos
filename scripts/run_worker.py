"""Worker entrypoint — runs the Procrastinate worker that FIRES the queued pipeline stages.

Why a custom entrypoint instead of the bare `procrastinate worker` CLI: the worker needs an ASYNC
connector to listen/fetch, but the pipeline's defers are SYNCHRONOUS (transactional enqueue in the
engine, and the next-stage enqueue inside each worker task body). A native sync connector is the only
thing that works inside a worker task's own `asyncio.run(...)` loop — an async connector's sync bridge
deadlocks there. So this process:

  * opens the SYNC ``app`` (its pool serves every ``.defer()`` a task body makes — e.g. normalise→
    extract, and the backfill re-enqueue that defers with no explicit connection), and
  * runs the worker on the ASYNC ``worker_app`` twin (fetch/listen), and
  * on the intake worker only (``--schedule``), runs a scheduler loop that defers the promote-scan on
    an interval — replacing @app.periodic, which the async twin can't run.

Usage:
  python -m scripts.run_worker default --schedule   # intake: normalise + extract + promote-scan
  python -m scripts.run_worker backfill             # isolated low-priority backfill drain
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import sys
from typing import Any

from app.obs.logging import get_logger
from app.queue import _conninfo, app, dedup_scan, mint_scan, promote_scan, worker_app

log = get_logger(__name__)

# How often the intake worker defers the schema-maintenance scans (the old @app.periodic cron was */30).
PROMOTE_SCAN_INTERVAL_SECONDS = 30 * 60

# How often EVERY worker stamps its liveness heartbeat (R3). Short relative to the liveness threshold
# (settings.worker_liveness_seconds, default 60) so a live-but-busy worker never reads as dead.
HEARTBEAT_INTERVAL_SECONDS = 15


def _lock_key(queues: list[str]) -> int:
    """A STABLE 64-bit signed advisory-lock key for a queue-set. Sorted so ['a','b'] == ['b','a'];
    hashed (not Python ``hash()``, which is per-process randomised) so two processes agree. Different
    queue-sets → different keys, so the intake (``default``) and ``backfill`` workers never collide.
    """
    key_src = "adaptive-intake.worker:" + ",".join(sorted(queues))
    return int.from_bytes(
        hashlib.blake2b(key_src.encode(), digest_size=8).digest(), "big", signed=True
    )


def _singleton_lock(queues: list[str]) -> Any:
    """Refuse to start a SECOND worker on the same queue-set — the zombie-worker footgun.

    Two ``run_worker default`` processes (or a stale one on old code) race the same jobs and cause
    spurious stage failures / bogus ``processing_failed`` cases — a whole test session was lost to this
    (longterm_context.md §0). "Remember to check" is not a fix; this enforces it in code.

    Mechanism: a Postgres SESSION-level advisory lock, keyed by the sorted queue-set. It is the right
    tool here because it (a) auto-releases the instant the connection dies — no stale PID files to
    reap after a crash — and (b) is shared by the host AND the container against the same DB. The
    ``default`` (intake) and ``backfill`` workers take DIFFERENT keys, so compose runs both fine; only a
    second worker on the SAME queues collides and exits. Set ``WORKER_ALLOW_MULTIPLE=1`` to bypass (only
    ever legitimate for a deliberate multi-worker scale-out sharing one queue — not the PoC).

    Returns the held connection (the caller must keep the reference alive for the whole process so the
    lock is not released early), or exits the process with a clear message if the lock is already held.
    """
    if os.environ.get("WORKER_ALLOW_MULTIPLE") == "1":
        log.warning("worker.singleton_lock_bypassed", queues=queues)
        return None
    import psycopg

    key = _lock_key(queues)
    conn = psycopg.connect(_conninfo(), autocommit=True)
    got = conn.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()
    if not got or not got[0]:
        conn.close()
        log.error("worker.already_running", queues=queues)
        print(
            f"!! a worker on queues {queues} is ALREADY RUNNING (advisory lock held).\n"
            f"   Refusing to start a second one — two workers on the same queue race jobs and cause\n"
            f"   spurious stage failures. Stop the other worker first, or set WORKER_ALLOW_MULTIPLE=1\n"
            f"   to override (only for a deliberate multi-worker scale-out).",
            file=sys.stderr,
        )
        raise SystemExit(3)
    log.info("worker.singleton_lock_acquired", queues=queues, key=key)
    return conn


def reap_orphaned_jobs(conn: Any, queues: list[str]) -> list[int]:
    """Release jobs stuck in ``doing`` on THIS worker's queues back to ``todo`` so they re-run.

    Safe ONLY because the caller holds the queue-set's singleton advisory lock: no other worker is
    processing these queues, and this worker has not started fetching yet — so every ``doing`` job is
    orphaned by a predecessor that died mid-job (killed / crashed / OOM). Procrastinate does not re-queue
    those on its own (its ``worker_id``/stalled-worker pruning didn't catch it in the wild), so without this
    the job's CASE hangs at ``created`` FOREVER while the live worker still looks healthy — the exact
    failure a real iPhone voice test hit (longterm_context §0: worker killed mid-transcription → orphaned
    ``pipeline.normalise`` job → case stuck, portal shows "still processing" indefinitely).

    NEVER call this while the singleton lock is bypassed (``WORKER_ALLOW_MULTIPLE=1``): with a live sibling
    worker on the same queues, a ``doing`` job may be genuinely in flight and releasing it would double-run
    it. ``main`` only calls this when the lock was actually acquired.

    (Not handled here — a genuine *poison* job that crashes the worker every run would be reaped in a loop;
    that class is caught instead by each stage's ``RetryStrategy`` → ``processing_failed`` on repeated
    *exceptions*. This reaper is for a healthy job whose worker was killed, not a job that kills workers.)
    """
    rows = conn.execute(
        "UPDATE procrastinate_jobs SET status = 'todo', worker_id = NULL, abort_requested = false "
        "WHERE status = 'doing' AND queue_name = ANY(%s) RETURNING id",
        (queues,),
    ).fetchall()
    ids = [int(r[0]) for r in rows]
    if ids:
        # Loud on purpose (§10 no-silent-caps): a reaped job means a worker died mid-job — operationally
        # notable, and the reason a case that was hung is now moving again.
        log.warning(
            "worker.reaped_orphaned_jobs", count=len(ids), queues=queues, job_ids=ids
        )
    else:
        log.info("worker.no_orphaned_jobs", queues=queues)
    return ids


async def _scheduler() -> None:
    """Defer the schema-maintenance scans every interval, IN ORDER — the order is the moat's pipeline:
      1. dedup  — collapse synonym qualifiers to their canonical (so promotion counts pooled support
                  and never splits two synonyms into duplicate columns, R1);
      2. mint   — cluster the escape valve and mint NEW heads from recurring novelty (the R2 pivot:
                  emergent columns are born here), re-homing history against the extended vocabulary;
      3. promote— lift recurring heads/qualifiers into the governed layer.
    ``.defer()`` is a quick sync call on the already-open sync ``app`` — a few ms every 30 min.
    """
    while True:
        await asyncio.sleep(PROMOTE_SCAN_INTERVAL_SECONDS)
        dedup_scan.defer()
        mint_scan.defer()
        promote_scan.defer()
        log.info("scheduler.schema_maintenance_scans_deferred")


def _beat(conn: Any, queue: str) -> None:
    conn.execute(
        "INSERT INTO worker_heartbeat (queue, beat_at) VALUES (%s, now()) "
        "ON CONFLICT (queue) DO UPDATE SET beat_at = now()",
        (queue,),
    )


async def _heartbeat_loop(queues: list[str]) -> None:
    """Stamp this worker's liveness on a short interval so the portal/health can tell 'down' from 'busy'
    (R3). Its own dedicated connection (the procrastinate pool is busy fetching); a stale heartbeat means
    the worker is gone, and the portal switches to honest handoff copy. A heartbeat failure must NEVER
    take the worker down — the worker's JOB is to process jobs; log and keep beating."""
    import psycopg

    queue = ",".join(sorted(queues))
    conn = psycopg.connect(_conninfo(), autocommit=True)
    try:
        while True:
            try:
                await asyncio.to_thread(_beat, conn, queue)
            except Exception:
                log.exception("worker.heartbeat_failed", queue=queue)
                with contextlib.suppress(Exception):
                    conn.close()
                conn = psycopg.connect(
                    _conninfo(), autocommit=True
                )  # reconnect and carry on
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
    finally:
        with contextlib.suppress(Exception):
            conn.close()


async def _run(queues: list[str], schedule: bool) -> None:
    async with worker_app.open_async():
        # The heartbeat runs on EVERY worker (not gated on --schedule) — liveness is universal.
        coros = [
            worker_app.run_worker_async(queues=queues, wait=True),
            _heartbeat_loop(queues),
        ]
        if schedule:
            coros.append(_scheduler())
        await asyncio.gather(*coros)


def main() -> None:
    # psycopg's async pool cannot run on Windows' default ProactorEventLoop — force the selector loop.
    # No-op on Linux (the container), where the selector loop is already the default.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    schedule = "--schedule" in sys.argv[1:]
    queues = argv or ["default"]
    # Refuse a second worker on these queues BEFORE opening the pool (the zombie-worker footgun). The
    # returned connection is bound to a local so the advisory lock lives for the whole process.
    _lock_conn = _singleton_lock(queues)
    # We now hold the exclusive lock (unless bypassed) → any 'doing' job on these queues is orphaned by a
    # dead worker. Release them so they re-run. A reaper failure must NEVER stop the worker from starting
    # (its job is to process jobs — mirrors the heartbeat's fail-open discipline).
    if _lock_conn is not None:
        try:
            reap_orphaned_jobs(_lock_conn, queues)
        except Exception:
            log.exception("worker.reap_failed", queues=queues)
    log.info("worker.start", queues=queues, schedule=schedule)
    # Hold the sync connector pool open for the whole process so task-body defers have a live pool.
    with app.open():
        asyncio.run(_run(queues, schedule))


if __name__ == "__main__":
    main()
