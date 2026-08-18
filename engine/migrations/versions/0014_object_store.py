"""object_record + object_key — the self-serve object store for entity resolution (Phase 5, EDD §16.1)

Revision ID: 0014_object_store
Revises: 0013_sensitivity_flag
Create Date: 2026-08-18

The anchor (order #, booking ref, the phone used to order) is a KEY, not a field: everything
downstream is LOOKED UP, not asked. That lookup needs a per-tenant store of the tenant's own objects —
orders, bookings, jobs, assets, customers — ingested self-serve from an upload, with NO fixed schema
(a bakery's ``order`` and a plumber's ``job`` share no columns). So, like the emergent layer, the
payload is a schema-agnostic ``jsonb`` blob; what makes it resolvable is a deterministic profiling pass
that picks the identifier fields and writes them to ``object_key`` as hashed exact-match keys.

Two tables, both RLS'd per tenant (an object is tenant data; a cross-tenant object lookup must read
zero rows — the same isolation the trust spine proves for cases):

- ``object_record`` — one row per object. ``attributes`` is the arbitrary payload; ``content_hash``
  (sha256 of the canonical payload) makes re-ingest idempotent (replay a batch → no duplicates);
  ``embedding`` (BGE-M3, nullable until embedded) backs the pgvector FUZZY fallback (match a name when
  no exact key was quoted). Composite PK ``(tenant_id, id)`` so ``object_key`` can carry a composite FK
  — structural cross-tenant integrity, not just a shared id.
- ``object_key`` — the hashed exact-key index. One row per ``(object, identifier_field)``: the
  normalised value's sha256 (``key_value_hash``) is what the resolver looks up; the raw ``key_value`` is
  kept for the confirmation prompt. A silent match fires only when a key resolves to exactly ONE object
  (winning-condition §4: acting on the wrong order is worse than asking).

Originals are never mutated in place; a resolved object is snapshotted at extraction time as a
``source_document`` with ``doc_kind='object_snapshot'`` (already reserved, migration 0004), so
provenance survives the live object later changing.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0014_object_store"
down_revision: str | None = "0013_sensitivity_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    # object_record — the schema-agnostic object payload (pgvector extension already created in 0007).
    op.execute("""
        CREATE TABLE object_record (
            tenant_id     uuid NOT NULL,
            id            uuid NOT NULL DEFAULT gen_random_uuid(),
            object_type   text NOT NULL,            -- the tenant's collection: 'order' | 'booking' | 'job'
            external_id   text,                     -- the tenant's own id for the object (may be null)
            content_hash  text NOT NULL,            -- sha256 of the canonical attributes → idempotent re-ingest
            attributes    jsonb NOT NULL,           -- the arbitrary object payload (no fixed schema)
            key_fields    jsonb NOT NULL DEFAULT '[]'::jsonb,  -- fields profiled as identifiers (transparency)
            embedding     vector(1024),             -- BGE-M3 of a text rendering; null until embedded
            ingested_at   timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, id),
            UNIQUE (tenant_id, content_hash),       -- re-ingesting the same object is a no-op
            FOREIGN KEY (tenant_id) REFERENCES tenant (id)
        )
        """)
    op.execute("CREATE INDEX ix_object_record_tenant ON object_record (tenant_id)")
    op.execute("CREATE INDEX ix_object_record_type ON object_record (tenant_id, object_type)")
    op.execute(
        "CREATE INDEX ix_object_record_embedding ON object_record "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200)"
    )

    # object_key — the hashed exact-match index the resolver looks up the anchor against.
    op.execute("""
        CREATE TABLE object_key (
            tenant_id      uuid NOT NULL,
            object_id      uuid NOT NULL,
            key_field      text NOT NULL,           -- 'order_id' | 'phone' | 'email' | ...
            key_value_hash text NOT NULL,           -- sha256 of the NORMALISED value (the lookup key)
            key_value      text NOT NULL,           -- the raw value (for the confirmation prompt)
            PRIMARY KEY (tenant_id, object_id, key_field),
            FOREIGN KEY (tenant_id, object_id)
                REFERENCES object_record (tenant_id, id) ON DELETE CASCADE,
            FOREIGN KEY (tenant_id) REFERENCES tenant (id)
        )
        """)
    # the resolver's hot path: given a hashed anchor value, find the object(s) it keys.
    op.execute(
        "CREATE INDEX ix_object_key_lookup ON object_key (tenant_id, key_field, key_value_hash)"
    )

    for table in ("object_record", "object_key"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table} TO {_APP_ROLE}
              USING ({_PREDICATE})
              WITH CHECK ({_PREDICATE})
            """)
        # The object store is a maintained working set (re-ingest / re-embed), so it is mutable.
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS object_key CASCADE")
    op.execute("DROP TABLE IF EXISTS object_record CASCADE")
