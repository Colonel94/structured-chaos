"""deletion ledger — durable blob cleanup after an approved tenant erasure"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024_deletion_ledger"
down_revision: str | None = "0023_review_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Admin-only by omission: app_rw receives no grant. A row contains only a content hash and deletion
    # operation UUID, so an interrupted erasure can safely resume after tenant rows are already gone.
    op.execute("""
        CREATE TABLE deletion_blob_pending (
            deletion_id uuid NOT NULL,
            blob_key text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (deletion_id, blob_key)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deletion_blob_pending")
