"""trust spine — tenancy (RLS), provenance/immutability, correction log, idempotency

Revision ID: 0001_trust_spine
Revises:
Create Date: 2026-08-12

Builds the Phase-1 trust layer (EDD §7). Everything a value's trustworthiness depends on lives
here: fail-closed RLS tenant isolation, append-only immutable originals + provenance logs, the
rebuildable ``field_current`` projection, and the idempotency ledger. Hand-authored SQL — the
security objects (policies, triggers, grants, the least-privilege role) cannot be expressed by
autogenerate, and this is not code to let a diff tool guess at.

Cross-tenant integrity is **structural**, not probabilistic: every child row's parent must share
its ``tenant_id`` (composite FKs), so a compromised app role cannot even reference another tenant's
case/document. The known residual (accepted, EDD §7.1): the ``app.tenant_id`` GUC is set by the
caller, so the *credential* is the tenant boundary — isolation is provable per well-behaved request,
not per physical connection. Anyone able to run arbitrary SQL as ``app_rw`` can reset the GUC.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0001_trust_spine"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The runtime app role — its NOSUPERUSER/NOBYPASSRLS attributes are *converged* below (asserted
# unconditionally), because the entire RLS guarantee is void if this role can bypass RLS.
_APP_ROLE = settings.postgres_user
_APP_PW = settings.postgres_password

# Tenant tables keyed on `tenant_id` (all get the same fail-closed isolation policy).
_TENANT_TABLES = (
    "case_record",
    "source_document",
    "field_extraction",
    "field_correction",
    "field_current",
    "stage_execution",
)

_TENANT_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_APP_ROLE_GRANTS = {
    # append-only + read; NO update/delete (also enforced by trigger — defence in depth)
    "source_document": "SELECT, INSERT",
    "field_extraction": "SELECT, INSERT",
    "field_correction": "SELECT, INSERT",
    # lifecycle updates allowed on specific columns only — never tenant_id
    "case_record": "SELECT, INSERT",
    # disposable projection — fully mutable (rebuilt from the logs)
    "field_current": "SELECT, INSERT, UPDATE, DELETE",
    # idempotency ledger — claim + status transitions
    "stage_execution": "SELECT, INSERT, UPDATE",
}

# Append-only tables: UPDATE/DELETE *and* TRUNCATE are blocked, so even the owner/superuser
# cannot mutate or wipe originals & provenance.
_APPEND_ONLY = ("source_document", "field_extraction", "field_correction")


def _assert_identifier(name: str) -> None:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(f"unsafe SQL identifier for the app role: {name!r}")


def upgrade() -> None:
    _assert_identifier(_APP_ROLE)
    pw_literal = _APP_PW.replace("'", "''")

    # --- 1. Least-privilege runtime role -----------------------------------------------------
    # CREATE only if missing (no password inside the DO block → no dollar-quote breakout), then
    # CONVERGE its attributes + password with an unconditional top-level ALTER. Idempotent-by-
    # convergence, not idempotent-by-skip: a pre-existing app_rw that was SUPERUSER/BYPASSRLS is
    # forced back to safe attributes here, so the RLS guarantee cannot silently degrade.
    op.execute(f"""
        DO $sc_role_bootstrap$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_APP_ROLE}') THEN
            EXECUTE format('CREATE ROLE %I LOGIN', '{_APP_ROLE}');
          END IF;
        END $sc_role_bootstrap$;
        """)
    op.execute(
        f"ALTER ROLE {_APP_ROLE} WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
        f"PASSWORD '{pw_literal}'"
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}")

    # --- 2. Tenant registry (root; not tenant_id-keyed) ------------------------------------
    op.execute("""
        CREATE TABLE tenant (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name       text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """)

    # --- 3. Case (Block D lifecycle; governed-core VALUES live in field_current) -----------
    op.execute("""
        CREATE TABLE case_record (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id         uuid NOT NULL REFERENCES tenant(id),
            case_state        text NOT NULL DEFAULT 'created'
                              CHECK (case_state IN
                                ('created','incomplete','actionable','in_review','committed')),
            channel           text NOT NULL
                              CHECK (channel IN ('whatsapp','email','file_drop')),
            first_contact_at  timestamptz NOT NULL,       -- SLA clock start (not completeness)
            question_count    int  NOT NULL DEFAULT 0 CHECK (question_count >= 0),  -- anchor+2 budget
            external_mappings jsonb NOT NULL DEFAULT '{}'::jsonb,  -- day-one, empty; prevents a P2 rewrite
            created_at        timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, id)   -- composite-FK target: children reference (tenant_id, case_id)
        )
        """)
    op.execute("CREATE INDEX ix_case_tenant ON case_record (tenant_id)")

    # --- 4. Immutable, content-addressed originals -----------------------------------------
    op.execute("""
        CREATE TABLE source_document (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   uuid NOT NULL,
            case_id     uuid NOT NULL,
            sha256      text NOT NULL,
            blob_key    text NOT NULL,      -- object-store key (== sha256)
            mime        text NOT NULL,
            channel     text NOT NULL CHECK (channel IN ('whatsapp','email','file_drop')),
            byte_size   bigint NOT NULL CHECK (byte_size >= 0),
            received_at timestamptz NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, sha256),     -- idempotent ingest: same bytes never duplicate
            UNIQUE (tenant_id, id),         -- composite-FK target for field_extraction
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_srcdoc_tenant ON source_document (tenant_id)")
    op.execute("CREATE INDEX ix_srcdoc_case ON source_document (case_id)")

    # --- 5. Append-only provenance log (one row per extracted value) -----------------------
    # Provenance is COMPLETE by construction: source_document_id, source_span and confidence are
    # all NOT NULL, so no extracted value can exist without a traceable source + a confidence
    # (CLAUDE.md §3 "no value exists without it"). model/version/prompt are NOT NULL too.
    op.execute("""
        CREATE TABLE field_extraction (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                bigint GENERATED ALWAYS AS IDENTITY,  -- monotonic append order
            tenant_id          uuid NOT NULL,
            case_id            uuid NOT NULL,
            field_path         text NOT NULL,
            value              jsonb,
            layer              text NOT NULL DEFAULT 'governed_core'
                               CHECK (layer IN ('governed_core','emergent')),
            model              text NOT NULL,
            model_version      text NOT NULL,
            prompt_version     text NOT NULL,
            confidence         double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            run_id             uuid NOT NULL,
            source_document_id uuid NOT NULL,
            source_span        jsonb NOT NULL,  -- {t_start,t_end} | {page,bbox} | {char_start,char_end}
            extracted_at       timestamptz NOT NULL DEFAULT now(),
            created_at         timestamptz NOT NULL DEFAULT now(),
            UNIQUE (run_id, field_path),  -- re-run of the same extraction is a no-op, not a dupe
            UNIQUE (tenant_id, id),       -- composite-FK target for field_correction
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id),
            FOREIGN KEY (tenant_id, source_document_id) REFERENCES source_document (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_fe_tenant ON field_extraction (tenant_id)")
    op.execute("CREATE INDEX ix_fe_case_field ON field_extraction (tenant_id, case_id, field_path)")

    # --- 6. Append-only correction log (the moat asset + eval set) --------------------------
    op.execute("""
        CREATE TABLE field_correction (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                   bigint GENERATED ALWAYS AS IDENTITY,  -- monotonic append order
            tenant_id             uuid NOT NULL,
            case_id               uuid NOT NULL,
            field_path            text NOT NULL,
            prev_value            jsonb,
            new_value             jsonb,
            based_on_extraction_id uuid,
            reviewer_id           text NOT NULL,
            note                  text,
            corrected_at          timestamptz NOT NULL DEFAULT now(),
            created_at            timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id),
            FOREIGN KEY (tenant_id, based_on_extraction_id)
                REFERENCES field_extraction (tenant_id, id)  -- MATCH SIMPLE: skipped when NULL
        )
        """)
    op.execute("CREATE INDEX ix_fc_tenant ON field_correction (tenant_id)")
    op.execute("CREATE INDEX ix_fc_case_field ON field_correction (tenant_id, case_id, field_path)")

    # --- 7. Disposable projection: latest correction else latest extraction ----------------
    op.execute("""
        CREATE TABLE field_current (
            tenant_id   uuid NOT NULL,
            case_id     uuid NOT NULL,
            field_path  text NOT NULL,
            value       jsonb,
            source_kind text NOT NULL CHECK (source_kind IN ('extraction','correction')),
            source_id   uuid NOT NULL,
            confidence  double precision,
            updated_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, case_id, field_path),
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)

    # --- 8. Idempotency ledger --------------------------------------------------------------
    # Claimed as 'running'; the caller transitions to 'done' on success. A crash between claim
    # and completion leaves the row 'running', which a replay is allowed to re-claim — so work is
    # never permanently lost (CLAUDE.md §3 "replay any stage → no lost data / retryable").
    op.execute("""
        CREATE TABLE stage_execution (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       uuid NOT NULL,
            case_id         uuid,
            stage           text NOT NULL,
            idempotency_key text NOT NULL,
            status          text NOT NULL DEFAULT 'running'
                            CHECK (status IN ('done','running','failed')),
            created_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, idempotency_key),
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_stage_tenant ON stage_execution (tenant_id)")

    # --- 9. Immutability: block UPDATE/DELETE/TRUNCATE on the append-only tables (fail loud) -
    op.execute("""
        CREATE OR REPLACE FUNCTION block_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'append-only: % on % is blocked (originals & provenance are immutable)',
                TG_OP, TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
        END $$;
        """)
    for tbl in _APPEND_ONLY:
        op.execute(f"""
            CREATE TRIGGER trg_{tbl}_immutable
            BEFORE UPDATE OR DELETE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION block_mutation()
            """)
        # TRUNCATE fires no row triggers → needs a separate statement-level guard, else a
        # superuser could wipe the table wholesale despite the row trigger.
        op.execute(f"""
            CREATE TRIGGER trg_{tbl}_no_truncate
            BEFORE TRUNCATE ON {tbl}
            FOR EACH STATEMENT EXECUTE FUNCTION block_mutation()
            """)

    # --- 10. RLS: fail-closed tenant isolation ---------------------------------------------
    # tenant registry — a tenant sees only its own row.
    op.execute("ALTER TABLE tenant ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_self ON tenant TO {_APP_ROLE}
          USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)
    op.execute(f"GRANT SELECT ON tenant TO {_APP_ROLE}")

    # tenant_id-keyed tables — separate USING (read) from WITH CHECK (write) so a tenant can't
    # write into one it can't read. An unset GUC → NULL → predicate false → zero rows.
    for tbl in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {tbl} TO {_APP_ROLE}
              USING ({_TENANT_PREDICATE})
              WITH CHECK ({_TENANT_PREDICATE})
            """)

    # --- 11. Least-privilege grants ---------------------------------------------------------
    for tbl, privs in _APP_ROLE_GRANTS.items():
        op.execute(f"GRANT {privs} ON {tbl} TO {_APP_ROLE}")
    # case lifecycle updates: specific columns only — tenant_id is not grantable, so it cannot
    # be re-pointed at another tenant even with a compromised app role.
    op.execute(
        f"GRANT UPDATE (case_state, question_count, external_mappings) ON case_record TO {_APP_ROLE}"
    )


def downgrade() -> None:
    for tbl in (
        "stage_execution",
        "field_current",
        "field_correction",
        "field_extraction",
        "source_document",
        "case_record",
        "tenant",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS block_mutation()")
    # The app role is cluster-global and may be reused; leave it in place.
