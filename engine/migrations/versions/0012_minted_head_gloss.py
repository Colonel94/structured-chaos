"""minted_head.gloss — a one-line definition so the model actually USES a minted head

Revision ID: 0012_minted_head_gloss
Revises: 0011_minted_head
Create Date: 2026-08-17

Live finding (2026-08-17c): extending the grammar enum with a minted head is necessary but NOT
sufficient — the model won't route a fact to ``regulation`` if the prompt never says what ``regulation``
means; it defaults to ``other``. So minting must also produce a short GLOSS (definition), stored here and
injected into the extraction prompt alongside the minted head name. Without it a minted column is dead.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_minted_head_gloss"
down_revision: str | None = "0011_minted_head"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE minted_head ADD COLUMN gloss text")


def downgrade() -> None:
    op.execute("ALTER TABLE minted_head DROP COLUMN IF EXISTS gloss")
