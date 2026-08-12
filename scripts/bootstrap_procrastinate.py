"""Apply Procrastinate's schema + the app_rw grants to the live DB (idempotent). Run once after
`alembic upgrade head`, before starting a worker:

    uv run --project engine python scripts/bootstrap_procrastinate.py

Procrastinate owns/versions its own schema, so it is applied here (admin connection) rather than
via Alembic. Grants are scoped to procrastinate_* objects only — app_rw gains nothing on the
trust-spine tables.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "engine")

from app.queue import admin_conninfo, apply_procrastinate_schema


def main() -> int:
    apply_procrastinate_schema(admin_conninfo())
    print("procrastinate schema + app_rw grants applied to the live DB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
