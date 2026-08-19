"""case_decision — the deterministic priority/SLA/routing projection (Phase 6, EDD §8 + §16.2)

Revision ID: 0016_case_decision
Revises: 0015_outbound_message
Create Date: 2026-08-19

Service levels are a RULES ENGINE's output, never a model's (CLAUDE.md §3). The model supplies the
inputs (category, severity, emotion); a deterministic, YAML-driven policy turns them into a priority,
an SLA deadline (clock from ``first_contact_at``, not completeness) and a routing target. Same inputs +
same policy version → the same row, every time, explainable in one sentence (``rationale`` + the
``matched_rule_id`` that fired).

Like ``field_current``, this is a DISPOSABLE PROJECTION: it is fully derived from (the governed core ×
the policy), so it is rebuilt, not logged — hence UPDATE/DELETE are granted (unlike the append-only
provenance tables). ``inputs`` snapshots exactly what the decision was computed from, so an auditor can
replay it. Tenant isolation is the same fail-closed RLS as every tenant table.

Also adds ``tenant.policy_yaml`` — the OPTIONAL per-tenant policy override text. NULL → the case runs on
the universal default policy shipped in ``app/rules/policy_default.yaml`` (zero-config: a tenant gets a
correct SLA with no input; written policy is refinement, never a setup gate — §16.2). It is admin-set at
onboarding, so the runtime app role gets no write grant on it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0016_case_decision"
down_revision: str | None = "0015_outbound_message"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    # Optional per-tenant policy override (admin-set; NULL → universal default). No app-role write grant.
    op.execute("ALTER TABLE tenant ADD COLUMN policy_yaml text")

    op.execute("""
        CREATE TABLE case_decision (
            tenant_id            uuid NOT NULL,
            case_id              uuid NOT NULL,
            priority             text NOT NULL CHECK (priority IN ('P1','P2','P3','P4')),
            routing              text NOT NULL,          -- the team/queue the policy routes to
            sla_target_hours     numeric NOT NULL CHECK (sla_target_hours > 0),
            sla_response_due_at  timestamptz NOT NULL,   -- first_contact_at + target (clock from contact)
            matched_rule_id      text NOT NULL,          -- which policy rule fired (explainability)
            rationale            text NOT NULL,          -- the one-sentence explanation
            policy_version       text NOT NULL,          -- default-policy version + tenant-override tag
            inputs               jsonb NOT NULL,         -- {category,severity,emotion} snapshot (replay)
            computed_at          timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, case_id),
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_case_decision_due ON case_decision (tenant_id, sla_response_due_at)")

    op.execute("ALTER TABLE case_decision ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE case_decision FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON case_decision TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    # Disposable projection — rebuilt from (governed core × policy), so fully mutable (mirrors field_current).
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON case_decision TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS case_decision CASCADE")
    op.execute("ALTER TABLE tenant DROP COLUMN IF EXISTS policy_yaml")
