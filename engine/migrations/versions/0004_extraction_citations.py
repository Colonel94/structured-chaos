"""provenance is a bridge, not a column — extraction_citation (many sources per value, with roles)

Revision ID: 0004_extraction_citations
Revises: 0003_blob_key_is_sha256
Create Date: 2026-08-12

Owner decision (2026-08-12), settled: a value's provenance is many-to-many, not one-source-per-value.
A single value is derived from several sources — `delay = 102 min` comes from the order record AND
the complaint time; a looked-up field's source is an object-store row, not a message at all; the same
value can be corroborated by a photo and *contradicted* by the record. The one-source `source_document_id`
column (and its `source_span`) fudged this and would break under audit (click a value → a message that
doesn't contain it).

So: keep `source_document` as-is (one message / file / object-store snapshot — immutable, content-
addressed), drop the single-source columns off `field_extraction`, and hang provenance off a join:

    field_extraction  ──<  extraction_citation  >──  source_document
                             locator (span/offset/timestamp-range/bbox), role, weight

`role` earns its keep: primary | corroborating | derived_from | contradicts. `contradicts` makes
contradiction detection *storable* (complaint says late, record says on time — both citations hang off
the same value with opposing roles) rather than recomputed on the fly.

Three decisions baked in with it:
- **Object-store rows are source_documents too** — `source_document.doc_kind` gains `object_snapshot`;
  Phase 5 snapshots the row at extraction time and content-hashes it, so "where did promised=17:00 come
  from?" still answers after the order record changes (and it will). (Snapshot channel-nullability is a
  cheap ALTER deferred to Phase 5 when the object store lands; the expensive part — the bridge — is here.)
- **Citations are versioned with the extraction, not the value** — re-extraction after a promotion writes
  new `field_extraction` rows with new citations; `field_current` projects the latest; history is intact.
- **A human correction is the human citation** — `field_correction.reviewer_id` is provenance with role
  "human" pointing at the reviewer; the review UI unifies it with these machine citations so it stays
  honest about which values a machine produced. (Kept in `field_correction`, matching the diagram, which
  connects the bridge to `field_extraction` only.)

Caveat honoured: `weight` is stored, never yet aggregated into a confidence score (three citations ≠ 3×
trust; that's a separate, separately-calibrated mechanism — EDD, later). Citations are provenance →
append-only + immutable + RLS'd, exactly like the logs they cite.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0004_extraction_citations"
down_revision: str | None = "0003_blob_key_is_sha256"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    # --- 1. Object-store snapshots become first-class source documents ---------------------
    op.execute(
        "ALTER TABLE source_document ADD COLUMN doc_kind text NOT NULL DEFAULT 'message' "
        "CHECK (doc_kind IN ('message','file','object_snapshot'))"
    )

    # --- 2. Retire the single-source columns (no real extraction rows exist yet) -----------
    # DROP CASCADE also removes the (tenant_id, source_document_id) composite FK.
    op.execute("ALTER TABLE field_extraction DROP COLUMN source_document_id CASCADE")
    op.execute("ALTER TABLE field_extraction DROP COLUMN source_span")

    # --- 3. The provenance bridge ----------------------------------------------------------
    op.execute("""
        CREATE TABLE extraction_citation (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq           bigint GENERATED ALWAYS AS IDENTITY,
            tenant_id     uuid NOT NULL,
            extraction_id uuid NOT NULL,
            source_document_id uuid NOT NULL,
            role          text NOT NULL
                          CHECK (role IN ('primary','corroborating','derived_from','contradicts')),
            locator       jsonb,   -- {char_start,char_end} | {t_start,t_end} | {page,bbox}; null = whole source
            weight        double precision CHECK (weight IS NULL OR weight >= 0),  -- stored, not yet computed
            created_at    timestamptz NOT NULL DEFAULT now(),
            UNIQUE (extraction_id, source_document_id, role),
            FOREIGN KEY (tenant_id, extraction_id) REFERENCES field_extraction (tenant_id, id),
            FOREIGN KEY (tenant_id, source_document_id) REFERENCES source_document (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_citation_tenant ON extraction_citation (tenant_id)")
    op.execute("CREATE INDEX ix_citation_extraction ON extraction_citation (tenant_id, extraction_id)")

    # Citations are provenance → append-only + immutable, like the logs they cite.
    op.execute("""
        CREATE TRIGGER trg_extraction_citation_immutable
        BEFORE UPDATE OR DELETE ON extraction_citation
        FOR EACH ROW EXECUTE FUNCTION block_mutation()
        """)
    op.execute("""
        CREATE TRIGGER trg_extraction_citation_no_truncate
        BEFORE TRUNCATE ON extraction_citation
        FOR EACH STATEMENT EXECUTE FUNCTION block_mutation()
        """)

    # Fail-closed RLS, identical to the trust spine.
    op.execute("ALTER TABLE extraction_citation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE extraction_citation FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON extraction_citation TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    op.execute(f"GRANT SELECT, INSERT ON extraction_citation TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS extraction_citation CASCADE")
    op.execute("ALTER TABLE field_extraction ADD COLUMN source_span jsonb")
    op.execute("ALTER TABLE field_extraction ADD COLUMN source_document_id uuid")
    op.execute("ALTER TABLE source_document DROP COLUMN IF EXISTS doc_kind")
