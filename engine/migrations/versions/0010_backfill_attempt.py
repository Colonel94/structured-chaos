"""Backfill attempt marker — retroactive re-extraction after promotion, STAGE 6 (Phase 4, 2026-08-14)

Revision ID: 0010_backfill_attempt
Revises: 0009_path_a_head_promotion
Create Date: 2026-08-14

When a head/qualifier is PROMOTED, the moat re-extracts the concept RETROACTIVELY against every
retained original in the concept's category — populating history the extractor never captured because
at the time it wasn't looking for that concept (CLAUDE.md §4: "promote… then backfill history 100%
correct"; this is re-EXTRACTION against the immutable originals, NOT a re-projection of what was already
extracted). New values land as fresh ``field_extraction`` rows with fresh citations; the log stays
append-only and immutable.

This table is the **idempotency marker**: one row per ``(case, concept)`` recording that backfill was
attempted and its outcome — ``found`` (a value was extracted + written) or ``absent`` (re-extraction
legitimately found nothing). Without the ``absent`` marker a case that truly lacks the concept would be
re-extracted forever (never idempotent, unbounded cost). ``cases_needing_backfill`` excludes any case
that already has a marker for the concept. Derived working set → mutable, RLS'd like the registries.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0010_backfill_attempt"
down_revision: str | None = "0009_path_a_head_promotion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE backfill_attempt (
            tenant_id    uuid NOT NULL,
            case_id      uuid NOT NULL,
            concept_key  text NOT NULL,   -- the promoted head, or the composite qualifier_head variant
            outcome      text NOT NULL CHECK (outcome IN ('found', 'absent')),
            attempted_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, case_id, concept_key),
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)
    op.execute(
        "CREATE INDEX ix_backfill_attempt_concept ON backfill_attempt (tenant_id, concept_key)"
    )

    op.execute("ALTER TABLE backfill_attempt ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE backfill_attempt FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON backfill_attempt TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    # A marker is written once and never mutated (an attempt is a historical fact); SELECT/INSERT only.
    op.execute(f"GRANT SELECT, INSERT ON backfill_attempt TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backfill_attempt CASCADE")
