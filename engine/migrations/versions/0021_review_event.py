"""review_event — the measured cost of clearing a case in the review UI (Phase: review-usability)

τ=1.01 means nothing auto-routes: every case lands in the review UI and a human approves it. That makes
the review screen the product and the **time to approve a case** the load-bearing metric — "we fill your
forms, you approve" is a product at ≤30s/case and dead at 90s (winning-condition §4, the review-time
gate). You cannot optimise a number you do not measure, so this table records it.

One row per case: how long the approving reviewer had the case open (``review_ms``, measured client-side
— only the client knows when a human actually started looking) and how many fields they had to correct
(``fields_edited``). Written once, at approval, via ``ON CONFLICT DO NOTHING`` so an idempotent re-commit
(or an undo→re-approve) never double-counts or overwrites the first honest measurement.

A DISPOSABLE MEASUREMENT log, not provenance — it carries no customer data (only a duration + a count),
so "no customer data in logs" (CLAUDE.md §3) holds by construction. Tenant isolation is the same
fail-closed RLS as every tenant table; stats are aggregated per-tenant.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0021_review_event"
down_revision: str | None = "0020_worker_heartbeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE review_event (
            tenant_id     uuid NOT NULL,
            case_id       uuid NOT NULL,
            reviewer_id   text NOT NULL,
            review_ms     integer CHECK (review_ms IS NULL OR review_ms >= 0),  -- wall time the case was open
            fields_edited integer NOT NULL DEFAULT 0 CHECK (fields_edited >= 0),
            recorded_at   timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, case_id),
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)

    op.execute("ALTER TABLE review_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE review_event FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON review_event TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    # Written once at approval (ON CONFLICT DO NOTHING); read for aggregates. No UPDATE/DELETE grant —
    # a measurement, once taken, is not rewritten (keeps the review-time number honest across replays).
    op.execute(f"GRANT SELECT, INSERT ON review_event TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_event CASCADE")
