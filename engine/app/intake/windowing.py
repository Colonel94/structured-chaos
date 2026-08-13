"""Conversation windowing — new case vs follow-up (EDD §11, TECH-SPEC §2.4).

Complaints span many messages over time, so the single hardest intake question is: does this message
*start a new case* or *continue an existing one*? The design (concept §13 — "budget more effort here
than extraction") is a **hybrid**, not a single heuristic:

1. **Idle gap** — a message within 24h of the last activity on an *open* case continues it (Freshdesk's
   threading interval). This resolves the overwhelming majority deterministically, no model call.
2. **Resolve/close state** — a case in a terminal state (``committed``) is closed; a later message is
   presumed new unless it lands inside a short reopen window.
3. **LLM classifier** — only for the genuinely ambiguous middle (a message long after an open case's
   last activity, or shortly after a close): "new issue, or follow-up to *that* case?" This is the
   only branch that costs a model call, and it is behind the ``LLMBackend`` interface (fake in tests).

Bias when uncertain: **default to a new case**. Wrongly merging two distinct complaints destroys a
case boundary (and its SLA clock); wrongly splitting is cheaply re-linked by a human later. So the
classifier must be *confident* to fold a message into a prior case; anything else opens a new one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from ..backends.interfaces import LLMBackend
from .models import InboundMessage

# Within this gap, a message on an OPEN case is the same conversation — no model call.
OPEN_IDLE = timedelta(hours=24)
# After a case is committed/closed, a message inside this window *might* be a follow-up (else new).
TERMINAL_REOPEN = timedelta(days=4)

_TERMINAL_STATES = frozenset({"committed"})

# Grammar-constrained classifier verdict — guaranteed-valid JSON (never prose-parsed).
_CLASSIFIER_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["new", "follow_up"]},
        "reason": {"type": "string"},
    },
    "required": ["decision", "reason"],
}


@dataclass(frozen=True)
class PriorCase:
    """The most recent case for this sender within the tenant — the only context windowing needs.
    ``prior_text`` is a short recent slice of that case (its last message(s)), for the classifier.
    """

    case_id: UUID
    case_state: str
    last_activity_at: datetime
    prior_text: str = ""


@dataclass(frozen=True)
class WindowDecision:
    """Where the message goes. ``action='new'`` → open a fresh case; ``action='follow_up'`` → append
    to ``case_id``. ``method`` records *how* it was decided (for the questions-per-case/audit trail).
    """

    action: str  # 'new' | 'follow_up'
    case_id: UUID | None
    reason: str
    method: str  # 'no_prior' | 'idle_gap' | 'terminal_state' | 'classifier'


def _new(reason: str, method: str) -> WindowDecision:
    return WindowDecision(action="new", case_id=None, reason=reason, method=method)


def _follow(case_id: UUID, reason: str, method: str) -> WindowDecision:
    return WindowDecision(action="follow_up", case_id=case_id, reason=reason, method=method)


async def _classify(message: InboundMessage, prior: PriorCase, llm: LLMBackend) -> WindowDecision:
    """Ask the model whether ``message`` continues ``prior`` or opens a new issue. Fails safe to a
    new case on any malformed/empty verdict — never merge on a guess."""
    prompt = (
        "You are triaging a customer service inbox. Decide whether the NEW MESSAGE continues the "
        "EXISTING CASE (a follow-up about the same issue) or raises a genuinely NEW issue.\n"
        "Answer 'follow_up' ONLY if it is clearly about the same issue; when unsure, answer 'new'.\n\n"
        f"EXISTING CASE (recent messages):\n{prior.prior_text or '(no text)'}\n\n"
        f"NEW MESSAGE:\n{message.text or '(no text — media only)'}\n\n"
        'Respond as JSON: {"decision": "new"|"follow_up", "reason": "..."}'
    )
    try:
        raw = await llm.complete(prompt, schema=_CLASSIFIER_SCHEMA)
        verdict = json.loads(raw)
        decision = verdict.get("decision")
        reason = str(verdict.get("reason", ""))[:300]
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        return _new("classifier returned no usable verdict → default new", "classifier")
    if decision == "follow_up":
        return _follow(prior.case_id, reason or "classifier: same issue", "classifier")
    return _new(reason or "classifier: new issue", "classifier")


async def decide_window(
    message: InboundMessage,
    prior: PriorCase | None,
    *,
    llm: LLMBackend | None = None,
) -> WindowDecision:
    """Decide whether ``message`` opens a new case or follows ``prior`` (the sender's latest case).

    Deterministic for the clear cases (no prior, within the open-idle window, long after a close);
    the ``LLMBackend`` classifier is consulted only for the ambiguous middle. ``llm`` may be injected
    (tests use a fake); a missing backend on an ambiguous message fails safe to a new case.
    """
    if prior is None:
        return _new("no prior case for this sender", "no_prior")

    gap = message.sent_at - prior.last_activity_at

    if prior.case_state in _TERMINAL_STATES:
        if gap > TERMINAL_REOPEN:
            return _new("prior case closed long ago", "terminal_state")
        # Shortly after a close → could be a reopen/follow-up. Ambiguous → classify.
        if llm is None:
            return _new("closed case, no classifier available → default new", "terminal_state")
        return await _classify(message, prior, llm)

    # Open case.
    if gap <= OPEN_IDLE:
        return _follow(prior.case_id, "within 24h of open-case activity", "idle_gap")
    # Long silence on an open case → new issue or resumed thread? Ambiguous → classify.
    if llm is None:
        return _new("open case idle >24h, no classifier → default new", "idle_gap")
    return await _classify(message, prior, llm)
