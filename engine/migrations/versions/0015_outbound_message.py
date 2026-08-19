"""outbound_message — the audit + idempotency ledger for messages the system sends (Phase 5, §5)

Revision ID: 0015_outbound_message
Revises: 0014_object_store
Create Date: 2026-08-19

Closing the conversational loop means the system SENDS the elicitation question, then the customer's
reply re-enters intake and advances the drill. An egress that writes to the outside world needs the
same discipline as the rest of the spine: a durable record of what was sent (nothing external happens
without a record), and idempotency so the same question is never sent twice (the pipeline replays).

One row per dispatched question, RLS'd per tenant. ``question_hash`` (sha256 of case + body) is UNIQUE
per case, so a redundant dispatch is a no-op — the drill's anchor+2 budget already caps how many
distinct questions exist, and this guarantees each is transmitted once. ``external_ref`` is the
channel's own message id (a WhatsApp message id, or a local ref for the PoC sink).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0015_outbound_message"
down_revision: str | None = "0014_object_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE outbound_message (
            tenant_id     uuid NOT NULL,
            id            uuid NOT NULL DEFAULT gen_random_uuid(),
            case_id       uuid NOT NULL,
            channel       text NOT NULL,     -- inherits the case channel (whatsapp | email | file_drop)
            recipient     text NOT NULL,     -- the contact_ref we send back to
            body          text NOT NULL,     -- the question sent (deterministic policy text, not model)
            question_hash text NOT NULL,     -- sha256(case_id + body) → idempotent: send each once
            external_ref  text,              -- the channel's message id (or a local ref for the PoC)
            status        text NOT NULL DEFAULT 'sent'
                          CHECK (status IN ('sending','sent','failed')),
            created_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, id),
            UNIQUE (tenant_id, case_id, question_hash),   -- the same question is transmitted once
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_outbound_message_case ON outbound_message (tenant_id, case_id)")

    op.execute("ALTER TABLE outbound_message ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE outbound_message FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON outbound_message TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    # Claim (INSERT) then mark sent (UPDATE the external_ref/status) — an audit trail, not a log we
    # rewrite, so UPDATE is allowed but DELETE is not.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON outbound_message TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS outbound_message CASCADE")
