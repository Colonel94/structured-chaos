"""case_feedback — the reviewer's verdict ON the model's extraction (the feedback loop, made explicit)

A field CORRECTION fixes a wrong value → the append-only ``field_correction`` log, which is the eval set
and the tuning signal (CLAUDE.md §3). But that only captures *what the right value was*, and only when a
reviewer edits a field. It has no room for the judgement a reviewer forms while reading a case — "the
category is right but the fault summary missed the point", "this whole thing is hallucinated", "good catch
on the contradiction" — the qualitative signal that tells a human engineer WHICH prompt/policy to tune next.

This table is that channel: a per-case verdict (``accurate`` / ``inaccurate`` / ``partial``) + an optional
free-text note, written by the reviewer, independent of any field edit and independent of approval. It is
the visible end of the loop: reviewer feedback + corrections → collected here + in the correction log →
prompt/policy fixes ($0, human-driven — never online fine-tuning, per Directive 2) → a better extractor.

Append-only, like the correction log (feedback is evidence, never overwritten): GRANT SELECT, INSERT only.
Carries a verdict + a note the reviewer chose to write — no customer PII by construction. Tenant isolation
is the same fail-closed RLS as every tenant table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import settings

revision: str = "0022_case_feedback"
down_revision: str | None = "0021_review_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = settings.postgres_user
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE case_feedback (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq         bigint GENERATED ALWAYS AS IDENTITY,  -- monotonic append order
            tenant_id   uuid NOT NULL,
            case_id     uuid NOT NULL,
            reviewer_id text NOT NULL,
            verdict     text NOT NULL CHECK (verdict IN ('accurate','inaccurate','partial')),
            comment     text,
            created_at  timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (tenant_id, case_id) REFERENCES case_record (tenant_id, id)
        )
        """)
    op.execute("CREATE INDEX ix_case_feedback_case ON case_feedback (tenant_id, case_id, seq)")

    op.execute("ALTER TABLE case_feedback ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE case_feedback FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON case_feedback TO {_APP_ROLE}
          USING ({_PREDICATE})
          WITH CHECK ({_PREDICATE})
        """)
    # Append-only evidence (mirrors field_correction): written + read, never overwritten or deleted.
    op.execute(f"GRANT SELECT, INSERT ON case_feedback TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS case_feedback CASCADE")
