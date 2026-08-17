"""sensitivity flags — the PII gate's audit trail on emergent/minted concepts (remediation R5)

Revision ID: 0013_sensitivity_flag
Revises: 0012_minted_head_gloss
Create Date: 2026-08-17

A concept the PII gate classifies as protected (health / government_id / payment_card / biometric /
credentials) is BARRED from the durable governed schema — it is not promoted and not minted into the
extraction vocabulary. But it is not dropped: the raw data already lives immutably in the append-only
log, and we record WHY it was barred so a reviewer can see it. These nullable columns carry that flag on
the three registries where a concept can try to become a column: minted heads, emergent heads (dim-1
promotion), emergent field variants (dim-2 promotion). NULL / 'none' = not sensitive (the default).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_sensitivity_flag"
down_revision: str | None = "0012_minted_head_gloss"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE minted_head ADD COLUMN sensitivity text")
    op.execute("ALTER TABLE emergent_head ADD COLUMN sensitivity text")
    op.execute("ALTER TABLE emergent_field ADD COLUMN sensitivity text")


def downgrade() -> None:
    op.execute("ALTER TABLE minted_head DROP COLUMN IF EXISTS sensitivity")
    op.execute("ALTER TABLE emergent_head DROP COLUMN IF EXISTS sensitivity")
    op.execute("ALTER TABLE emergent_field DROP COLUMN IF EXISTS sensitivity")
