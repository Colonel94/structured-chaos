"""case_record.contact_ref — the anchor a case belongs to, so windowing can find a sender's case

Revision ID: 0006_case_contact_ref
Revises: 0005_normalised_content
Create Date: 2026-08-13

Conversation windowing (EDD §11) must answer "does this message continue an existing case for this
sender, or start a new one?" — which requires knowing *which contact* a case belongs to. That is the
**anchor** (the phone/email/handle the customer used): a key, not a field (concept §4.3). We add it
to ``case_record`` as ``contact_ref``.

It is set once at case creation and never changes (a case's originating contact is immutable), so the
existing INSERT grant covers it and no column-scoped UPDATE grant is added — ``contact_ref`` is
deliberately *not* in the updatable column set, matching how ``tenant_id`` is locked. Nullable, since
a channel that can't determine the sender still creates a case (never block on completeness, §3).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_case_contact_ref"
down_revision: str | None = "0005_normalised_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE case_record ADD COLUMN contact_ref text")
    # Lookup path for windowing: the sender's most recent case within the tenant.
    op.execute("CREATE INDEX ix_case_contact ON case_record (tenant_id, contact_ref)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_case_contact")
    op.execute("ALTER TABLE case_record DROP COLUMN IF EXISTS contact_ref")
