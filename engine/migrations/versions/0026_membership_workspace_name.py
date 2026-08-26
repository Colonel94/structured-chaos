"""membership workspace label — session-readable display name without bypassing tenant RLS"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026_membership_workspace_name"
down_revision: str | None = "0025_workspace_provisioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspace_membership ADD COLUMN workspace_name text")
    op.execute("""
        UPDATE workspace_membership m SET workspace_name = t.name
          FROM tenant t WHERE t.id = m.tenant_id
    """)
    op.execute("ALTER TABLE workspace_membership ALTER COLUMN workspace_name SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE workspace_membership DROP COLUMN workspace_name")
