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
import sys

from app.obs.logging import get_logger
from app.queue import app, dedup_scan, mint_scan, promote_scan, worker_app

log = get_logger(__name__)

# How often the intake worker defers the schema-maintenance scans (the old @app.periodic cron was */30).
PROMOTE_SCAN_INTERVAL_SECONDS = 30 * 60


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


async def _run(queues: list[str], schedule: bool) -> None:
    async with worker_app.open_async():
        coros = [worker_app.run_worker_async(queues=queues, wait=True)]
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
    log.info("worker.start", queues=queues, schedule=schedule)
    # Hold the sync connector pool open for the whole process so task-body defers have a live pool.
    with app.open():
        asyncio.run(_run(queues, schedule))


if __name__ == "__main__":
    main()
