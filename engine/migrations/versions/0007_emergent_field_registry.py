"""emergent_field registry — the self-converging schema's working set (Phase 4, EDD §6)

Revision ID: 0007_emergent_field_registry
Revises: 0006_case_contact_ref
Create Date: 2026-08-13

Emergent attribute *values* already have a home: the append-only ``field_extraction`` log carries them
with ``layer='emergent'`` and full provenance (citations, immutability, RLS) — no new value table
needed. What the moat needs on top is a **registry of distinct emergent field names per tenant**: the
BGE-M3 embedding used for dedup/canonicalisation (STAGE 3), the recurrence ``support_count`` that
drives promotion (STAGE 4), and the alias link when one field is merged into another. That is this
table — a derived, maintained working set (rebuildable from the logs), not an append-only provenance
log, so it is mutable (upsert on each attestation) and RLS'd like the rest of the tenant data.

``embedding`` is ``vector(1024)`` (BGE-M3) and nullable — a field is registered at extraction time and
embedded when the dedup unit runs (kept out of the hot extract path). pgvector's extension is created
here (idempotent) so the column type resolves.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0007_emergent_field_registry"
down_revision: str | None = "0006_case_contact_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE emergent_field (
            tenant_id       uuid NOT NULL,
            field_name_hash text NOT NULL,   -- stable id of the normalised name (dedup/promotion key)
            field_name      text NOT NULL,   -- canonical snake_case display name
            embedding       vector(1024),    -- BGE-M3; null until the dedup unit embeds it
            support_count   int  NOT NULL DEFAULT 0,   -- distinct cases attesting this field (promotion)
            canonical_hash  text,            -- if merged into another field, that field's hash (alias)
            promoted        boolean NOT NULL DEFAULT false,
            first_seen_at   timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, field_name_hash),
            FOREIGN KEY (tenant_id) REFERENCES tenant (id)
        )
        """)
    op.execute("CREATE INDEX ix_emergent_field_tenant ON emergent_field (tenant_id)")

    op.execute("ALTER TABLE emergent_field ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE emergent_field FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON emergent_field TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    # Maintained working set → mutable (upsert on each attestation, embed/merge on dedup).
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON emergent_field TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS emergent_field CASCADE")
