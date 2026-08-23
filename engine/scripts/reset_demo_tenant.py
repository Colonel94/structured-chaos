"""Wipe ALL data for a demo tenant back to a clean slate (dev/demo ONLY) — keeps the tenant row + its
embed/portal config, deletes every case, object, extraction, and learned emergent-schema row it owns.

Why: a demo tenant accumulates test cases, half-processed cases, and stale objects across sessions. Before
the external gate (3 strangers, clean register) you want it EMPTY except for a freshly-seeded order book.
This clears the per-tenant data tables, scoped strictly to the one tenant, then you re-run
seed_portal_orders.py for the clean orders.

Safety: refuses to run unless APP_ENV is a non-prod env (this is a demo reset, never a prod tool). Scoped
to a single tenant_id — never touches another tenant's rows or the tenant row itself. Runs as the admin
(superuser) with FK triggers deferred for the duration, so the delete order across the 18 inter-referencing
tables doesn't matter; re-enabled before commit.

Run:
    POSTGRES_ADMIN_PASSWORD=change_me_admin_local uv run python scripts/reset_demo_tenant.py "Portal Demo Co"
Then reseed:
    POSTGRES_ADMIN_PASSWORD=change_me_admin_local uv run --group asr python scripts/seed_portal_orders.py "Portal Demo Co"
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from app.config import settings
from app.store.db import admin_session

# Every table carrying a tenant_id (information_schema-verified). Order is irrelevant because FK triggers
# are disabled for the transaction; listed alphabetically for auditability. The `tenant` row itself is
# NOT here — the tenant, its embed_key, allowed_origins, and portal config all survive the wipe.
_TENANT_DATA_TABLES = [
    "backend_call",
    "backfill_attempt",
    "case_decision",
    "extraction_citation",
    "field_correction",
    "field_current",
    "field_extraction",
    "normalised_content",
    "outbound_message",
    "review_event",
    "source_document",
    "stage_execution",
    "emergent_field",
    "emergent_head",
    "minted_head",
    "object_key",
    "object_record",
    "case_record",
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if settings.app_env.strip().lower() in ("prod", "production"):
        print("REFUSING: reset_demo_tenant is a dev/demo tool; APP_ENV is prod.", file=sys.stderr)
        return 2
    name = sys.argv[1] if len(sys.argv) > 1 else "Portal Demo Co"

    with admin_session() as s:
        tid = s.execute(
            text("SELECT id FROM tenant WHERE name = :n ORDER BY id LIMIT 1"), {"n": name}
        ).scalar()
        if tid is None:
            print(f'tenant "{name}" not found', file=sys.stderr)
            return 1

        # Disable FK triggers for this session (superuser) so the 18 inter-referencing tables can be
        # cleared without a hand-maintained child→parent order. Re-enabled implicitly at commit/close.
        s.execute(text("SET session_replication_role = replica"))
        cleared: dict[str, int] = {}
        for tbl in _TENANT_DATA_TABLES:
            res = s.execute(text(f"DELETE FROM {tbl} WHERE tenant_id = :t"), {"t": str(tid)})
            cleared[tbl] = res.rowcount or 0
        s.execute(text("SET session_replication_role = DEFAULT"))
        s.commit()

    total = sum(cleared.values())
    print(f'reset tenant "{name}"  ({tid})')
    for tbl, n in cleared.items():
        if n:
            print(f"  cleared {tbl:<20}: {n}")
    print(f"  total rows deleted     : {total}")
    print("tenant row + embed_key + portal config PRESERVED. Now reseed the order book:")
    print(f'  uv run --group asr python scripts/seed_portal_orders.py "{name}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
