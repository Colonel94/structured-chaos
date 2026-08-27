"""Guard test for the held-out scorer's agreement math (W1 support).

The scorer produces the four numbers the whole accuracy story is blocked on, so its co-label filtering and
null handling must be right: a blank desired_outcome counts as the real label 'null' ONLY when the source
used the column, and a field one side didn't label is skipped (never scored as a disagreement). Lives in
eval/, not on the test path, so we add it (like test_worker_lock).
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL = Path(__file__).resolve().parents[1] / "eval"
if str(_EVAL) not in sys.path:
    sys.path.insert(0, str(_EVAL))

from score_holdout import Source, _agreement, _consensus_agreement


def _src(name: str, data: dict[str, dict[str, str]], null_ok: set[str] | None = None) -> Source:
    return Source(name, data, null_ok or set())


def test_agreement_counts_only_co_labelled_rows() -> None:
    model = _src("model", {"1": {"category": "billing_charge"}, "2": {"category": "service_fault"}})
    human = _src(
        "owner", {"1": {"category": "billing_charge"}, "2": {"category": "access_availability"}}
    )
    assert _agreement(model, human, "category") == (1, 2)  # id1 agree, id2 disagree


def test_blank_outcome_is_null_when_column_used_but_skip_when_not() -> None:
    # Source A USED the column (has null_ok) → its blank is the real label 'null'.
    a = _src(
        "a", {"1": {"desired_outcome": ""}, "2": {"desired_outcome": "refund"}}, {"desired_outcome"}
    )
    b = _src(
        "b", {"1": {"desired_outcome": ""}, "2": {"desired_outcome": "refund"}}, {"desired_outcome"}
    )
    assert _agreement(a, b, "desired_outcome") == (2, 2)  # null==null and refund==refund

    # Source C did NOT use the column (no null_ok) → its blank is an unlabelled skip, not scored.
    c = _src("c", {"1": {"desired_outcome": ""}}, set())
    assert _agreement(c, b, "desired_outcome") == (0, 0)


def test_disagreement_on_present_labels_is_counted() -> None:
    a = _src("a", {"1": {"desired_outcome": "information"}}, {"desired_outcome"})
    b = _src("b", {"1": {"desired_outcome": "repair_redo"}}, {"desired_outcome"})
    assert _agreement(a, b, "desired_outcome") == (0, 1)  # both present, disagree


def test_consensus_scores_only_rows_where_both_humans_agree() -> None:
    model = _src(
        "model",
        {
            "1": {"category": "billing_charge"},
            "2": {"category": "service_fault"},
            "3": {"category": "privacy_data"},
        },
    )
    first = _src(
        "first",
        {
            "1": {"category": "billing_charge"},
            "2": {"category": "service_fault"},
            "3": {"category": "privacy_data"},
        },
    )
    second = _src(
        "second",
        {
            "1": {"category": "billing_charge"},
            "2": {"category": "product_fault"},  # human disagreement: excluded
            "3": {"category": "fraud_security"},  # human disagreement: excluded
        },
    )
    assert _consensus_agreement(model, first, second, "category") == (1, 1)


def test_consensus_counts_model_error_against_agreed_humans() -> None:
    model = _src("model", {"1": {"severity_signal": "none"}})
    first = _src("first", {"1": {"severity_signal": "financial_harm"}})
    second = _src("second", {"1": {"severity_signal": "financial_harm"}})
    assert _consensus_agreement(model, first, second, "severity_signal") == (0, 1)
