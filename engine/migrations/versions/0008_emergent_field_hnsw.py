"""HNSW cosine index on emergent_field.embedding — fast dedup nearest-neighbour (Phase 4.3)

Revision ID: 0008_emergent_field_hnsw
Revises: 0007_emergent_field_registry
Create Date: 2026-08-14

The dedup lookup (STAGE 3) finds the nearest canonical field by cosine each time a new emergent field
is registered. A pgvector HNSW index with the EDD's parameters (``m=16, ef_construction=200``,
``vector_cosine_ops``) keeps that sub-linear as the schema grows. Nullable embeddings are simply
skipped by the index.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_emergent_field_hnsw"
down_revision: str | None = "0007_emergent_field_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_emergent_field_embedding ON emergent_field "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_emergent_field_embedding")
