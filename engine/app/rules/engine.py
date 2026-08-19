"""The deterministic priority / SLA / routing engine (Phase 6, EDD §8).

Service levels are a rules engine's output, never a model's (CLAUDE.md §3): the model supplies the
inputs (category, severity, emotion); this maps them — through a YAML policy — to a priority, an SLA
target and a routing team, purely and reproducibly. Same inputs + same policy version → the same
:class:`Decision`, every time, explainable in one sentence.

Evaluation is FIRST-MATCH-WINS over an ordered rule list, so exactly one rule decides a case and IS the
explanation. The policy is validated at load (fail loud): every rule is well-formed and the list ends in
an unconditional catch-all, so :func:`evaluate` is a total function — no case can fall through to an
undefined decision. The SLA deadline is computed by the stage from ``first_contact_at`` (the clock starts
at first contact); this module is pure and clock-free so it stays trivially deterministic and testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

_DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "policy_default.yaml"

# The governed-core keys the engine reads, and the `when` condition key each maps to.
_INPUT_KEYS: dict[str, str] = {
    "category": "category",
    "severity": "severity_signal",
    "emotion": "emotion_signal",
}
_PRIORITIES = frozenset({"P1", "P2", "P3", "P4"})


class PolicyError(ValueError):
    """A policy that cannot be trusted to produce a deterministic, total decision — raised at load so a
    malformed tenant override fails loud at onboarding, never silently mis-routes a live case."""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    when: Mapping[
        str, frozenset[str]
    ]  # condition-key -> allowed values (empty mapping = catch-all)
    priority: str
    routing: str
    sla_hours: float
    rationale: str

    def matches(self, inputs: Mapping[str, str | None]) -> bool:
        """True iff every condition holds. An omitted condition key is a wildcard; a listed key requires
        the case's value to be present AND in the allowed set (so a rule needing severity=financial_harm
        never fires on a case whose severity is None)."""
        for cond_key, allowed in self.when.items():
            if inputs.get(_INPUT_KEYS[cond_key]) not in allowed:
                return False
        return True


@dataclass(frozen=True)
class Policy:
    version: str
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class Decision:
    priority: str
    routing: str
    sla_target_hours: float
    matched_rule_id: str
    rationale: str
    policy_version: str


def _parse_rule(raw: object, idx: int) -> Rule:
    if not isinstance(raw, dict):
        raise PolicyError(f"rule #{idx} is not a mapping")
    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or not rule_id:
        raise PolicyError(f"rule #{idx} is missing a string id")
    when_raw = raw.get("when", {}) or {}
    if not isinstance(when_raw, dict):
        raise PolicyError(f"rule {rule_id!r}: `when` must be a mapping")
    when: dict[str, frozenset[str]] = {}
    for key, vals in when_raw.items():
        if key not in _INPUT_KEYS:
            raise PolicyError(f"rule {rule_id!r}: unknown condition key {key!r}")
        if not isinstance(vals, list) or not vals or not all(isinstance(v, str) for v in vals):
            raise PolicyError(
                f"rule {rule_id!r}: condition {key!r} must be a non-empty list of strings"
            )
        when[key] = frozenset(vals)
    priority = raw.get("priority")
    if priority not in _PRIORITIES:
        raise PolicyError(f"rule {rule_id!r}: priority must be one of {sorted(_PRIORITIES)}")
    routing = raw.get("routing")
    if not isinstance(routing, str) or not routing:
        raise PolicyError(f"rule {rule_id!r}: routing must be a non-empty string")
    sla_hours = raw.get("sla_hours")
    if not isinstance(sla_hours, (int, float)) or isinstance(sla_hours, bool) or sla_hours <= 0:
        raise PolicyError(f"rule {rule_id!r}: sla_hours must be a positive number")
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or not rationale:
        raise PolicyError(f"rule {rule_id!r}: rationale must be a non-empty string")
    return Rule(
        rule_id=rule_id,
        when=when,
        priority=priority,
        routing=routing,
        sla_hours=float(sla_hours),
        rationale=rationale,
    )


def parse_policy(text: str) -> Policy:
    """Parse + VALIDATE a policy from YAML text. Raises :class:`PolicyError` unless it is well-formed and
    ends in an unconditional catch-all (so :func:`evaluate` is total)."""
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise PolicyError("policy must be a mapping")
    version = doc.get("version")
    if not isinstance(version, str) or not version:
        raise PolicyError("policy is missing a string `version`")
    raw_rules = doc.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PolicyError("policy must have a non-empty `rules` list")
    rules = tuple(_parse_rule(r, i) for i, r in enumerate(raw_rules))
    if rules[-1].when:
        raise PolicyError("the last rule must be an unconditional catch-all (empty `when`)")
    seen: set[str] = set()
    for r in rules:
        if r.rule_id in seen:
            raise PolicyError(f"duplicate rule id {r.rule_id!r}")
        seen.add(r.rule_id)
    return Policy(version=version, rules=rules)


def load_default_policy() -> Policy:
    """The universal default policy shipped with the product (zero-config tenants run on this)."""
    return parse_policy(_DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))


def load_policy(tenant_yaml: str | None) -> Policy:
    """The policy in force for a tenant: its own override text if set, else the universal default. A
    tenant override REPLACES the default wholesale (it must be a complete, valid policy) — predictable
    precedence over a merge, and it fails loud at load if malformed rather than mis-routing later.
    """
    if tenant_yaml and tenant_yaml.strip():
        policy = parse_policy(tenant_yaml)
        return Policy(version=f"tenant:{policy.version}", rules=policy.rules)
    return load_default_policy()


def evaluate(inputs: Mapping[str, str | None], policy: Policy) -> Decision:
    """Map governed-core inputs to a :class:`Decision` by first-match-wins. Total by construction (the
    catch-all last rule always matches). ``inputs`` uses the governed-core keys (category, severity_signal,
    emotion_signal); missing/None values simply fail any rule that requires them."""
    for rule in policy.rules:
        if rule.matches(inputs):
            return Decision(
                priority=rule.priority,
                routing=rule.routing,
                sla_target_hours=rule.sla_hours,
                matched_rule_id=rule.rule_id,
                rationale=rule.rationale,
                policy_version=policy.version,
            )
    # Unreachable: parse_policy guarantees a catch-all. Guard so a future refactor fails loud, not silent.
    raise PolicyError("no rule matched and no catch-all present — policy invariant violated")


def evaluated_inputs(governed: Mapping[str, str | None]) -> dict[str, str | None]:
    """The exact input snapshot a decision is computed from — persisted with the decision so it can be
    replayed/audited (the three governed signals the policy reads)."""
    return {k: governed.get(k) for k in ("category", "severity_signal", "emotion_signal")}
