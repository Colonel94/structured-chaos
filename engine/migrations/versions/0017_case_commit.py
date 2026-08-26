"""case_record commit gate — the human-approval stamp (Phase 7, §3 trust gate + §16.4)

Revision ID: 0017_case_commit
Revises: 0016_case_decision
Create Date: 2026-08-19

"Nothing external happens without human approval" (CLAUDE.md §3). A report is issued, an external
record written, or a notification sent ONLY after a human has approved the assembled case. This adds
the approval stamp the gate reads: ``committed_at`` (when) + ``committed_by`` (which reviewer) on
``case_record``. The ``case_state = 'committed'`` value already exists (0001); these columns carry the
provenance the trust gate demands (reviewer + timestamp) and are what the report generator checks —
``committed_at IS NULL`` → no report, full stop.

Commit is ONE-WAY: the store's ``commit_case`` sets the stamp with ``COALESCE`` guards so a re-commit
is a no-op (first reviewer wins) and the approval can never be silently re-attributed. The paired
CHECK keeps the two columns consistent — either both set (committed) or both null (not yet). Only the
two new columns get an UPDATE grant; ``tenant_id`` remains ungrantable, so a compromised app role
still cannot re-point a case at another tenant (mirrors the 0001 case-lifecycle grant).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0017_case_commit"
down_revision: str | None = "0016_case_decision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user


def upgrade() -> None:
    op.execute("ALTER TABLE case_record ADD COLUMN committed_at timestamptz")
    op.execute("ALTER TABLE case_record ADD COLUMN committed_by text")
    # Both set (approved) or both null (not yet) — an approval always carries who + when.
    op.execute(
        "ALTER TABLE case_record ADD CONSTRAINT case_commit_pair "
        "CHECK ((committed_at IS NULL) = (committed_by IS NULL))"
    )
    # The reviewer stamps only these two columns; case_state's grant already exists (0001).
    op.execute(f"GRANT UPDATE (committed_at, committed_by) ON case_record TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("ALTER TABLE case_record DROP CONSTRAINT IF EXISTS case_commit_pair")
    op.execute("ALTER TABLE case_record DROP COLUMN IF EXISTS committed_by")
    op.execute("ALTER TABLE case_record DROP COLUMN IF EXISTS committed_at")
