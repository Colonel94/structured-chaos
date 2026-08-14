"""Path A — two-dimensional promotion: head column + head-promotion registry (Phase 4, 2026-08-14)

Revision ID: 0009_path_a_head_promotion
Revises: 0008_emergent_field_hnsw
Create Date: 2026-08-14

Path A makes an emergent attribute ``{head, qualifier, value}``: the HEAD (closed vocabulary) is the
column, the QUALIFIER is open data. The ``field_extraction`` log is unchanged — it still records the
composite ``qualifier_head`` name as ``field_path`` (preserving within-case multiplicity: a case with a
charged amount AND a refunded amount stays two rows). This migration adds the head dimension the
registry needs for **two-dimensional promotion** (owner constraint #2, 2026-08-14):

1. ``emergent_field.head`` — each composite (registry row) now carries its head, so support can be
   rolled up to the head (column) level for the convergence gate and head promotion.
2. ``emergent_head`` — the head-level registry: distinct-case support + a ``promoted`` flag. Promoting
   a HEAD creates a governed column. This is the *first* promotion dimension.

The *second* dimension — promoting a QUALIFIER (splitting a promoted column into variant columns) — is
recorded on the existing ``emergent_field.promoted`` flag (the composite row IS the head+qualifier). It
is STRICTLY HARDER than head promotion and REQUIRES the head promoted first (enforced in promote.py),
so there is never an orphan-qualifier column whose parent head doesn't exist.

Both tables are derived, maintained working sets (rebuildable from the append-only logs), so they are
mutable + RLS'd like ``emergent_field`` (migration 0007).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0009_path_a_head_promotion"
down_revision: str | None = "0008_emergent_field_hnsw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    # 1. The head each composite belongs to (nullable: pre-Path-A rows have none; prod has none).
    op.execute("ALTER TABLE emergent_field ADD COLUMN head text")
    op.execute("CREATE INDEX ix_emergent_field_head ON emergent_field (tenant_id, head)")

    # 2. The head-level registry (the emergent COLUMN space — the convergence unit + promotion dim 1).
    op.execute("""
        CREATE TABLE emergent_head (
            tenant_id      uuid NOT NULL,
            head           text NOT NULL,           -- a value from the closed head vocabulary
            support_count  int  NOT NULL DEFAULT 0, -- distinct cases attesting ANY qualifier of this head
            promoted       boolean NOT NULL DEFAULT false,  -- head lifted to a governed column
            first_seen_at  timestamptz NOT NULL DEFAULT now(),
            updated_at     timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, head),
            FOREIGN KEY (tenant_id) REFERENCES tenant (id)
        )
        """)
    op.execute("CREATE INDEX ix_emergent_head_tenant ON emergent_head (tenant_id)")

    op.execute("ALTER TABLE emergent_head ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE emergent_head FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON emergent_head TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON emergent_head TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS emergent_head CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_emergent_field_head")
    op.execute("ALTER TABLE emergent_field DROP COLUMN IF EXISTS head")
