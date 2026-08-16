"""minted_head — emergent heads born from `other` clusters (Phase 4 moat, remediation head-minting)

Revision ID: 0011_minted_head
Revises: 0010_backfill_attempt
Create Date: 2026-08-17

The R2 finding: convergence is a COLUMN-level property, and the column space must GROW by emergence,
not stay a hand-seeded closed list. The escape valve (`other`) collects genuinely-new concepts; when a
cluster of them recurs across enough distinct cases, a NEW head is minted — a column that did not exist
in the seed vocabulary (``HEAD_NOUNS``). This table is the per-tenant registry of those minted heads.

The minted heads EXTEND a tenant's extraction vocabulary: the effective head enum handed to the model
is ``HEAD_NOUNS`` (universal seed) + this tenant's minted heads. That is what makes "domain
specialisation is emergent, never seeded" literally true — a ``regulation`` column emerging from CFPB
data, a ``symptom`` column from vehicle complaints, with zero configuration. Like ``emergent_field`` it
is a derived, maintained working set (rebuildable from the logs), mutable, and RLS'd per tenant.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0011_minted_head"
down_revision: str | None = "0010_backfill_attempt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE minted_head (
            tenant_id     uuid NOT NULL,
            head          text NOT NULL,   -- the new column name (snake_case), NOT in the seed HEAD_NOUNS
            support_count int  NOT NULL DEFAULT 0,   -- distinct cases in the founding cluster
            source        text,            -- provenance note (e.g. 'other_cluster' + example values)
            first_seen_at timestamptz NOT NULL DEFAULT now(),
            updated_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, head),
            FOREIGN KEY (tenant_id) REFERENCES tenant (id)
        )
        """)
    op.execute("CREATE INDEX ix_minted_head_tenant ON minted_head (tenant_id)")

    op.execute("ALTER TABLE minted_head ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE minted_head FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON minted_head TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON minted_head TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS minted_head CASCADE")
