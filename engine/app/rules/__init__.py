"""Deterministic priority/SLA/routing engine, YAML-driven (Phase 6, EDD §8). Never model output.

The model supplies inputs (category, severity, emotion); :func:`evaluate` maps them — through a validated
policy, first-match-wins — to a priority, an SLA target and a routing team, purely and reproducibly. The
:func:`app.rules.stage.decide_case` stage persists the decision with the SLA deadline computed from
``first_contact_at`` (the clock starts at first contact).
"""

from __future__ import annotations

from .engine import (
    Decision,
    Policy,
    PolicyError,
    Rule,
    evaluate,
    evaluated_inputs,
    load_default_policy,
    load_policy,
    parse_policy,
)

__all__ = [
    "Decision",
    "Policy",
    "PolicyError",
    "Rule",
    "evaluate",
    "evaluated_inputs",
    "load_default_policy",
    "load_policy",
    "parse_policy",
]
