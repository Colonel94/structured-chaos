"""normalised_content — the derived transcript/OCR/text layer, with provenance spans (Phase 3)

Revision ID: 0005_normalised_content
Revises: 0004_extraction_citations
Create Date: 2026-08-13

Normalisation (EDD §2/§2.3) turns one immutable ``source_document`` (voice note / photo / PDF /
text) into readable ``text`` plus the ``spans`` that anchor every fragment back to the original
(audio ``{t_start,t_end}`` / image ``{bbox}`` / pdf ``{page,bbox}`` / ``{char_start,char_end}``).
Those spans are the exact ``locator`` shape an ``extraction_citation`` carries, so Phase-4 extraction
cites the span it read with no translation — this is what keeps "click a value → its source in the
audio/image" answerable (CLAUDE.md §3).

Unlike the append-only provenance logs, this layer is **derived and rebuildable**: it is fully
reconstructable from the immutable original by re-running the (versioned) normaliser, so it is
mutable (upsert on re-run) and carries no immutability trigger. Re-normalising the same document +
stage replaces the row; a model-version bump makes a new idempotency key upstream (§7.3), so a genuine
re-run is intentional, not accidental. RLS tenant isolation is identical to the trust spine — a
derived table is still tenant data.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0005_normalised_content"
down_revision: str | None = "0004_extraction_citations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE normalised_content (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id          uuid NOT NULL,
            case_id            uuid NOT NULL,
            source_document_id uuid NOT NULL,
            text               text NOT NULL,
            language           text NOT NULL,
            spans              jsonb NOT NULL,   -- [{text, kind, locator, confidence}] — provenance anchors
            stage              text NOT NULL,    -- normalise.audio|ocr|pdf|text|raw
            model              text NOT NULL,
            model_version      text NOT NULL,
            meta               jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, source_document_id, stage),   -- one normalisation per (doc, stage); re-run upserts
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id),
            FOREIGN KEY (tenant_id, source_document_id) REFERENCES source_document (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_norm_tenant ON normalised_content (tenant_id)")
    op.execute("CREATE INDEX ix_norm_case ON normalised_content (tenant_id, case_id)")

    # Fail-closed RLS, identical to the trust spine — a derived table is still tenant data.
    op.execute("ALTER TABLE normalised_content ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE normalised_content FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON normalised_content TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    # Rebuildable projection → fully mutable (upsert on re-normalise); no append-only trigger.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON normalised_content TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS normalised_content CASCADE")
