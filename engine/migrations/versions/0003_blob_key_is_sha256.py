"""source_document.blob_key must equal sha256 (content-addressed) — remove the divergence footgun

Revision ID: 0003_blob_key_is_sha256
Revises: 0002_cost_meter
Create Date: 2026-08-12

The blob store (MinioBlob/FakeBlob) is content-addressed: the object key IS the sha256 of the
bytes, and get() can only retrieve by that. add_source_document takes sha256 and blob_key as
separate params; nothing stopped them diverging, which would write a row whose blob is
unretrievable. This CHECK makes the "blob_key == sha256" convention a hard constraint so a
Phase-3 ingest path cannot get it wrong. (A later ingest helper may drop blob_key entirely and
derive it; until then, the constraint removes the choice.)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_blob_key_is_sha256"
down_revision: str | None = "0002_cost_meter"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE source_document "
        "ADD CONSTRAINT ck_blob_key_is_sha256 CHECK (blob_key = sha256)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE source_document DROP CONSTRAINT IF EXISTS ck_blob_key_is_sha256")
