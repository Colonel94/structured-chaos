"""Phase 6 — the calibrated confidence model (pure, no DB). Reliability from gold, abstention → 0,
fail-safe when unfitted, and selective-prediction routing."""

from __future__ import annotations

from pathlib import Path

from app.confidence import FitRow, fit, load_calibration, save_calibration
from app.confidence.model import Calibration, FieldCalibration


def _rows() -> list[FitRow]:
    # product_fault: 10/10 right (reliable); service_fault: 4/10 right (unreliable residual). Cells are
    # n=10 so they clear _MIN_CELL_N and earn a per-class number; overall accuracy 14/20 = 0.7 (default).
    rows: list[FitRow] = []
    for _ in range(10):
        rows.append(FitRow("category", "product_fault", "product_fault"))
    for i in range(10):
        rows.append(
            FitRow("category", "service_fault", "service_fault" if i < 4 else "billing_charge")
        )
    return rows


def test_fit_measures_per_class_reliability() -> None:
    cal = fit(_rows(), version="t", fit_on="unit")
    assert cal.fields["category"].reliability["product_fault"] == 1.0
    assert cal.fields["category"].reliability["service_fault"] == 0.4


def test_reliable_class_scores_high_unreliable_low() -> None:
    cal = fit(_rows(), version="t", fit_on="unit")
    assert cal.confidence("category", "product_fault") == 1.0
    assert cal.confidence("category", "service_fault") == 0.4


def test_abstention_and_null_are_zero_confidence() -> None:
    cal = fit(_rows(), version="t", fit_on="unit")
    assert cal.confidence("category", "UNCLEAR") == 0.0
    assert cal.confidence("category", None) == 0.0


def test_uncalibrated_field_falls_back_to_grounding() -> None:
    cal = fit(_rows(), version="t", fit_on="unit")
    # An emergent attr / a field with no gold → grounding is the only honest signal.
    assert cal.confidence("delay_amount", "6 weeks", grounding=0.9) == 0.9
    assert cal.confidence("delay_amount", "6 weeks", grounding=1.0) == 1.0


def test_grounding_attenuates_a_calibrated_value() -> None:
    cal = fit(_rows(), version="t", fit_on="unit")
    assert cal.confidence("category", "product_fault", grounding=0.5) == 0.5


def test_unseen_value_uses_the_conservative_field_default() -> None:
    cal = fit(_rows(), version="t", fit_on="unit")
    # A class never seen at fit → the field's overall accuracy (7/10 here), not 0 and not 1.
    assert cal.confidence("category", "safety_health") == cal.fields["category"].default == 0.7


def test_thin_cell_is_floored_to_the_default() -> None:
    # A class with < _MIN_CELL_N gold observations must NOT emit a per-class number (noise wearing a
    # decimal — owner review): even 3/3 correct falls back to the field's conservative default, and only
    # cells that clear the floor keep a recorded support count.
    rows = [
        FitRow("category", "product_fault", "product_fault" if i < 8 else "x") for i in range(10)
    ]  # 8/10, n=10 → kept
    rows += [FitRow("category", "rare", "rare") for _ in range(3)]  # 3/3 but n=3 → dropped
    cal = fit(rows, version="t", fit_on="unit")
    assert "rare" not in cal.fields["category"].reliability  # not reported as 1.0
    assert cal.confidence("category", "rare") == cal.fields["category"].default
    assert cal.fields["category"].support == {"product_fault": 10}  # only the surviving cell


def test_route_uses_the_auto_threshold() -> None:
    cal = Calibration(
        version="t",
        fit_on="u",
        fields={"category": FieldCalibration({"a": 0.99, "b": 0.5}, 0.5)},
        tau_auto=0.9,
        gate_met=True,
    )
    assert cal.route(cal.confidence("category", "a")) == "auto"
    assert cal.route(cal.confidence("category", "b")) == "review"


def test_missing_artifact_fails_safe_everything_routes_to_review(tmp_path: Path) -> None:
    cal = load_calibration(tmp_path / "does_not_exist.json")
    assert cal.gate_met is False and cal.tau_auto > 1.0
    # No calibration → a LOW (not spuriously certain) confidence, and it routes to review (refuse to guess).
    conf = cal.confidence("category", "product_fault", grounding=1.0)
    assert conf <= 0.5 and cal.route(conf) == "review"


def test_save_load_round_trip(tmp_path: Path) -> None:
    cal = fit(_rows(), version="rt", fit_on="unit")
    path = tmp_path / "calibration.json"
    save_calibration(cal, path)
    back = load_calibration(path)
    assert back.version == "rt"
    assert back.confidence("category", "product_fault") == cal.confidence(
        "category", "product_fault"
    )
    assert back.tau_auto == cal.tau_auto


def test_gate_unreachable_is_reported_not_forced() -> None:
    # Every class is a coin-flip → no τ reaches 98% accepted accuracy → gate_met False, τ unreachable.
    rows = [FitRow("category", "x", "x" if i % 2 else "y") for i in range(20)]
    cal = fit(rows, version="t", fit_on="unit")
    assert cal.gate_met is False and cal.tau_auto > 1.0
