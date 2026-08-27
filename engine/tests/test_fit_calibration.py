"""Regression guard for the consensus calibration loader (``fit_calibration._load_consensus_rows``).

The loader turns the two independent reviewers + the model extractions into the ``FitRow``s that
``fit()`` calibrates on, so confidence is a real reliability estimate only if this loader is right. Its
four load-bearing behaviours had no other protection:

  1. a case counts for a field ONLY where the two reviewers AGREE — disagreements are excluded, never
     adjudicated (no majority vote with two reviewers);
  2. a blank ``desired_outcome`` is a REAL null gold — a non-null model prediction there is a miss (kept
     with ``gold=""``), while a null model prediction is dropped (``predicted=None`` → the fitter skips it);
  3. only ids present in BOTH reviewers AND the model are used (source coverage = the triple intersection);
  4. grounding is the extraction's ``field_validity`` (default 1.0 when absent).

A golden test also reproduces the committed calib-v3 artifact from the real fixtures — the numbers the
owner verified (721 rows, gate_met=False, tau_auto=1.01) — so any future change to the loader that alters
the shipped calibration fails here.

Lives in eval/, not on the test path, so we add it to sys.path (like test_score_holdout / test_worker_lock).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

_EVAL = Path(__file__).resolve().parents[1] / "eval"
if str(_EVAL) not in sys.path:
    sys.path.insert(0, str(_EVAL))

import fit_calibration as fc

from app.confidence import fit, load_calibration

_COLS = [
    "id",
    "gold_category",
    "gold_desired_outcome",
    "gold_severity_signal",
    "gold_emotion_signal",
]
# A fully-agreed, non-blank baseline row the tests vary one field at a time from.
_BASE = {
    "gold_category": "product_fault",
    "gold_desired_outcome": "refund",
    "gold_severity_signal": "financial_harm",
    "gold_emotion_signal": "frustrated",
}
_GOV = {
    "category": "product_fault",
    "desired_outcome": "refund",
    "severity_signal": "financial_harm",
    "emotion_signal": "frustrated",
}


def _write_labels(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in _COLS})


def _write_model(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _load(tmp_path, labels_a, labels_b, model):
    a, b, m = tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "m.jsonl"
    _write_labels(a, labels_a)
    _write_labels(b, labels_b)
    _write_model(m, model)
    return fc._load_consensus_rows(a, b, m)[0]


def _by_field(rows) -> dict[str, list]:
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r.field_path, []).append(r)
    return out


def test_disagreement_is_excluded_not_adjudicated(tmp_path) -> None:
    a = [{"id": "1", **_BASE, "gold_severity_signal": "safety_health"}]
    b = [
        {"id": "1", **_BASE, "gold_severity_signal": "none"}
    ]  # reviewers disagree on severity only
    model = [{"id": "1", "governed": _GOV}]
    byf = _by_field(_load(tmp_path, a, b, model))
    assert "severity_signal" not in byf  # the disagreed field is dropped, not majority-voted
    assert set(byf) == {"category", "desired_outcome", "emotion_signal"}  # the agreed fields remain


def test_blank_outcome_is_a_real_null_gold(tmp_path) -> None:
    common = {**_BASE, "gold_desired_outcome": ""}  # both reviewers agree: no remedy stated (null)
    a = [{"id": "1", **common}, {"id": "2", **common}]
    b = [{"id": "1", **common}, {"id": "2", **common}]
    model = [
        {
            "id": "1",
            "governed": {**_GOV, "desired_outcome": "refund"},
        },  # non-null pred vs null gold
        {"id": "2", "governed": {**_GOV, "desired_outcome": None}},  # null pred vs null gold
    ]
    pairs = {
        (r.predicted, r.gold) for r in _by_field(_load(tmp_path, a, b, model))["desired_outcome"]
    }
    assert (
        "refund",
        "",
    ) in pairs  # a predicted remedy over a null gold is a MISS, kept (not skipped)
    assert (None, "") in pairs  # a null prediction is kept as predicted=None → the fitter skips it


def test_only_ids_in_all_three_sources_are_used(tmp_path) -> None:
    a = [{"id": "1", **_BASE}, {"id": "2", **_BASE}, {"id": "3", **_BASE}]  # 3 reviewer-A cases
    b = [{"id": "1", **_BASE}, {"id": "2", **_BASE}]  # id 3 missing from reviewer B
    model = [{"id": "1", "governed": _GOV}]  # only id 1 has a model extraction
    rows = _load(tmp_path, a, b, model)  # A ∩ B ∩ model = {id 1}
    assert len(rows) == 4  # exactly the four governed fields for the one covered id
    assert {r.field_path for r in rows} == {
        "category",
        "desired_outcome",
        "severity_signal",
        "emotion_signal",
    }


def test_grounding_comes_from_field_validity(tmp_path) -> None:
    a = [{"id": "1", **_BASE}, {"id": "2", **_BASE}]
    b = [{"id": "1", **_BASE}, {"id": "2", **_BASE}]
    model = [
        {"id": "1", "governed": _GOV, "field_validity": 0.5},  # explicit grounding
        {"id": "2", "governed": _GOV},  # no field_validity → defaults to 1.0
    ]
    counts = Counter(r.grounding for r in _load(tmp_path, a, b, model))
    assert (
        counts[0.5] == 4 and counts[1.0] == 4
    )  # each id contributes its grounding across all 4 fields


def test_real_fixtures_reproduce_calib_v3() -> None:
    """Golden guard: the real fixtures reproduce the committed calib-v3 artifact the owner verified."""
    rows, src = fc._load_consensus_rows()
    assert len(rows) == 721
    assert Counter(r.field_path for r in rows) == {
        "severity_signal": 188,
        "category": 185,
        "desired_outcome": 182,
        "emotion_signal": 166,
    }
    cal = fit(rows, version="calib-v3", fit_on=src[0])
    committed = load_calibration()  # app/confidence/calibration.json (the shipped artifact)
    assert cal.version == committed.version == "calib-v3"
    assert cal.gate_met is False and cal.tau_auto == committed.tau_auto == 1.01
    assert cal.fit_on == committed.fit_on
    assert set(cal.fields) == set(committed.fields)
    for name, fcal in cal.fields.items():
        cc = committed.fields[name]
        assert fcal.support == cc.support
        assert fcal.default == cc.default
        assert fcal.reliability == pytest.approx(cc.reliability)
