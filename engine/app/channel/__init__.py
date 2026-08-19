"""Egress — send the elicitation question and close the conversational loop (Phase 5).

The engine decides the next question (deterministic, budgeted) and records it; this dispatches it over
the customer's channel, once, with a durable audit. The reply re-enters intake (windowed onto the same
case) → re-extract → re-elicit, so the drill advances turn by turn until the case is actionable or the
anchor+2 budget hands it to a human.
"""

from __future__ import annotations

from .dispatch import dispatch_case_question

__all__ = ["dispatch_case_question"]
