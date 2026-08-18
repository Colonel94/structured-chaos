"""Drill-down elicitation — the anchor + two-question drill (Phase 5).

The product's core claim: a case is created on first contact, extraction fills everything it can, and
elicitation closes only the genuine gaps — the anchor (a KEY that unlocks lookup, asked once) plus at
most TWO drills, then hand off to a human. The budget is enforced in CODE here, never left to the
model. An angry, incomplete case is handed off, not interrogated. The one fact that can never be
inferred — the desired outcome — is always asked when absent.
"""

from __future__ import annotations

from .policy import DRILL_BUDGET, ElicitationPlan, decide

__all__ = ["DRILL_BUDGET", "ElicitationPlan", "decide"]
