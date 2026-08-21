"""Honest processing failure — a ``processing_failed`` case_state (Phase: portal/trust)

The case must never LIE. When the pipeline dies mid-flight (an Ollama crash, an ASR blow-up, a worker
restart that drops an in-flight job), the case previously stayed in ``created`` and — once elicitation
had run on a partial/empty extraction — could render as a *finished-looking empty case* ("we read it and
found nothing"), the worst possible presentation for a system whose whole promise is that it refuses to
guess and shows its uncertainty (CLAUDE.md §2 Claim 2, §3 trust gates).

``processing_failed`` is the honest terminal state a durable pipeline stage stamps when its retries are
exhausted. It reaches the already-built stalled/handoff copy in the portal and an error state in the
review UI — the case still EXISTS (originals retained, §3), a human picks it up, nothing is silently
dropped or dressed up as done.

Adds one value to the ``case_record.case_state`` CHECK. Reversible (down-migration first parks any
failed case back to ``created`` so the old, narrower constraint still holds).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019_processing_failed"
down_revision: str | None = "0018_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES_NEW = "('created','incomplete','actionable','in_review','committed','processing_failed')"
_STATES_OLD = "('created','incomplete','actionable','in_review','committed')"


def upgrade() -> None:
    op.execute("ALTER TABLE case_record DROP CONSTRAINT case_record_case_state_check")
    op.execute(
        f"ALTER TABLE case_record ADD CONSTRAINT case_record_case_state_check "
        f"CHECK (case_state IN {_STATES_NEW})"
    )


def downgrade() -> None:
    # No case may violate the narrower constraint we're restoring — park any failed case back to
    # 'created' (the honest "still in flight" state) before re-adding the old CHECK.
    op.execute(
        "UPDATE case_record SET case_state = 'created' WHERE case_state = 'processing_failed'"
    )
    op.execute("ALTER TABLE case_record DROP CONSTRAINT case_record_case_state_check")
    op.execute(
        f"ALTER TABLE case_record ADD CONSTRAINT case_record_case_state_check "
        f"CHECK (case_state IN {_STATES_OLD})"
    )
