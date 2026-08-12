"""cost-per-case meter — per-backend-call usage, attributable to a case

Revision ID: 0002_cost_meter
Revises: 0001_trust_spine
Create Date: 2026-08-12

Every inference call (ASR/LLM/Embedding/Blob) logs its usage — tokens, audio-seconds, wall/GPU
time, and $ (zero on the local path; the meaningful figure there is GPU-time/throughput) — against a
``case_id``, so the real per-case cost is *measured* as features land (BUILD-PLAN Phase 2), not
estimated at Phase 8. Tenant-scoped under the same fail-closed RLS as the trust spine; case_id is a
composite FK so a call can never be attributed to another tenant's case.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0002_cost_meter"
down_revision: str | None = "0001_trust_spine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE backend_call (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     uuid NOT NULL,
            case_id       uuid,                       -- nullable: not every call is case-bound
            interface     text NOT NULL CHECK (interface IN ('asr','llm','embedding','blob')),
            backend       text NOT NULL CHECK (backend IN ('local','cloud','fake')),
            model         text NOT NULL,
            tokens_in     bigint NOT NULL DEFAULT 0,
            tokens_out    bigint NOT NULL DEFAULT 0,
            audio_seconds double precision NOT NULL DEFAULT 0,
            wall_ms       double precision NOT NULL DEFAULT 0,   -- GPU/wall time (the local "cost")
            cost_usd      numeric(12,6) NOT NULL DEFAULT 0,      -- 0 on the local path
            created_at    timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_backend_call_case ON backend_call (tenant_id, case_id)")
    op.execute("ALTER TABLE backend_call ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE backend_call FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON backend_call TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    op.execute(f"GRANT SELECT, INSERT ON backend_call TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backend_call CASCADE")
