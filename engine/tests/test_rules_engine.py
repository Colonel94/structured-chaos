"""Phase 6 — the deterministic rules engine (pure, no DB). Same inputs + same policy → the same
decision, first-match precedence, a total function (catch-all), and fail-loud policy validation."""

from __future__ import annotations

import pytest

from app.rules import (
    PolicyError,
    evaluate,
    evaluated_inputs,
    load_default_policy,
    load_policy,
    parse_policy,
)

DEFAULT = load_default_policy()


def _decide(**governed: str | None):  # type: ignore[no-untyped-def]
    return evaluate(governed, DEFAULT)


# --------------------------------------------------------------------------- determinism (the gate)


def test_same_inputs_same_policy_give_identical_decision() -> None:
    inputs = {
        "category": "billing_charge",
        "severity_signal": "financial_harm",
        "emotion_signal": "calm",
    }
    first = evaluate(inputs, DEFAULT)
    for _ in range(20):
        assert evaluate(inputs, DEFAULT) == first  # bit-identical every time


def test_decision_is_explainable_in_one_sentence() -> None:
    d = _decide(category="service_fault", severity_signal="none", emotion_signal="frustrated")
    assert d.rationale.endswith(".") and d.rationale.count(".") == 1  # one sentence
    assert d.matched_rule_id  # and it names the rule that fired


# ------------------------------------------------------------------- first-match precedence / routing


def test_safety_severity_dominates_everything() -> None:
    # Even a calm billing complaint is urgent when severity flags a safety/health risk.
    d = _decide(category="billing_charge", severity_signal="safety_health", emotion_signal="calm")
    assert (d.priority, d.routing, d.matched_rule_id) == (
        "P1",
        "safety_escalation",
        "safety-critical",
    )


def test_angry_escalates_above_the_plain_category_path() -> None:
    calm = _decide(category="billing_charge", severity_signal="none", emotion_signal="calm")
    angry = _decide(category="billing_charge", severity_signal="none", emotion_signal="angry")
    assert calm.matched_rule_id == "billing-or-record" and calm.priority == "P2"
    assert angry.matched_rule_id == "angry-any" and angry.routing == "human_review"


def test_angry_plus_financial_harm_is_the_most_urgent() -> None:
    d = _decide(category="billing_charge", severity_signal="financial_harm", emotion_signal="angry")
    assert d.priority == "P1" and d.matched_rule_id == "angry-financial-harm"


def test_financial_harm_routes_to_finance() -> None:
    d = _decide(category="service_fault", severity_signal="financial_harm", emotion_signal="calm")
    assert d.priority == "P2" and d.routing == "finance_billing"


def test_record_accuracy_takes_the_billing_path() -> None:
    d = _decide(category="record_accuracy", severity_signal="none", emotion_signal="calm")
    assert d.matched_rule_id == "billing-or-record" and d.routing == "finance_billing"


def test_unclear_routes_to_triage_not_a_wrong_deadline() -> None:
    d = _decide(category="UNCLEAR", severity_signal="none", emotion_signal="calm")
    assert d.routing == "triage" and d.matched_rule_id == "unclear"


def test_known_category_routes_to_its_owning_team_not_the_general_queue() -> None:
    # A calm delivery complaint no longer falls to "general queue" — it routes to the team that owns it,
    # with a reason that names the issue (the weak-analysis fix; priority stays standard).
    d = _decide(category="delivery_fulfilment", severity_signal="none", emotion_signal="frustrated")
    assert d.routing == "fulfilment" and d.matched_rule_id == "delivery"
    assert "delivery" in d.rationale.lower() and d.priority == "P3"
    # a product fault takes the returns/quality path; 'other' still falls to the general queue.
    assert _decide(category="product_fault").routing == "returns_quality"
    assert _decide(category="other").matched_rule_id == "default"


# ------------------------------------------------------------------------ totality (catch-all) / None


def test_catch_all_matches_when_nothing_is_known() -> None:
    # A case with no governed signals still gets a decision (the case exists before the answers do).
    d = evaluate({}, DEFAULT)
    assert d.matched_rule_id == "default" and d.priority == "P3" and d.routing == "general_queue"


def test_none_signals_do_not_fire_conditional_rules() -> None:
    d = _decide(category=None, severity_signal=None, emotion_signal=None)
    assert d.matched_rule_id == "default"


def test_evaluated_inputs_snapshots_exactly_the_three_signals() -> None:
    snap = evaluated_inputs(
        {
            "category": "product_fault",
            "severity_signal": "none",
            "emotion_signal": "calm",
            "fault": "x",
        }
    )
    assert snap == {
        "category": "product_fault",
        "severity_signal": "none",
        "emotion_signal": "calm",
    }


# --------------------------------------------------------------------------- policy validation (loud)


def test_missing_catch_all_is_rejected() -> None:
    with pytest.raises(PolicyError, match="catch-all"):
        parse_policy(
            "version: x\nrules:\n  - {id: a, when: {category: [other]}, priority: P3, "
            "routing: q, sla_hours: 1, rationale: r.}\n"
        )


def test_bad_priority_is_rejected() -> None:
    with pytest.raises(PolicyError, match="priority"):
        parse_policy(
            "version: x\nrules:\n  - {id: a, when: {}, priority: URGENT, routing: q, "
            "sla_hours: 1, rationale: r.}\n"
        )


def test_unknown_condition_key_is_rejected() -> None:
    with pytest.raises(PolicyError, match="unknown condition key"):
        parse_policy(
            "version: x\nrules:\n  - {id: a, when: {colour: [red]}, priority: P3, "
            "routing: q, sla_hours: 1, rationale: r.}\n"
        )


def test_non_positive_sla_is_rejected() -> None:
    with pytest.raises(PolicyError, match="sla_hours"):
        parse_policy(
            "version: x\nrules:\n  - {id: a, when: {}, priority: P3, routing: q, "
            "sla_hours: 0, rationale: r.}\n"
        )


def test_duplicate_rule_id_is_rejected() -> None:
    with pytest.raises(PolicyError, match="duplicate"):
        parse_policy(
            "version: x\nrules:\n"
            "  - {id: a, when: {category: [other]}, priority: P3, routing: q, sla_hours: 1, rationale: r.}\n"
            "  - {id: a, when: {}, priority: P3, routing: q, sla_hours: 1, rationale: r.}\n"
        )


# ------------------------------------------------------------------------ tenant override replaces default


def test_tenant_override_replaces_the_default_and_is_version_tagged() -> None:
    override = (
        "version: acme-1\nrules:\n"
        "  - {id: everything-urgent, when: {}, priority: P1, routing: acme_desk, "
        "sla_hours: 2, rationale: Acme treats every case as urgent.}\n"
    )
    policy = load_policy(override)
    assert policy.version == "tenant:acme-1"
    d = evaluate({"category": "product_fault", "severity_signal": "none"}, policy)
    assert d.priority == "P1" and d.routing == "acme_desk"


def test_no_override_falls_back_to_default() -> None:
    assert load_policy(None).version == DEFAULT.version
    assert load_policy("   ").version == DEFAULT.version
