"""Idempotent DB init for the container entrypoint (F7 — closes the setup-gate gap).

``docker compose up`` must not start the engine against an unmigrated database (the ``app_rw`` role
and the trust-spine tables wouldn't even exist). This runs, as the ``intake_admin`` superuser, the
two setup steps that were previously manual (``alembic upgrade head`` + Procrastinate schema/grants)
before the engine serves — driven by the compose ``migrate`` one-shot service the engine depends on.

Both steps are idempotent: ``alembic upgrade`` is a no-op at head, and ``apply_procrastinate_schema``
only creates what's missing. Safe to run on every boot.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import settings
from .queue import admin_conninfo, apply_procrastinate_schema


def main() -> int:
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations))
    cfg.set_main_option("sqlalchemy.url", settings.admin_database_url)
    command.upgrade(cfg, "head")
    apply_procrastinate_schema(admin_conninfo())
    print("db init: migrations at head + procrastinate schema/grants ensured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
