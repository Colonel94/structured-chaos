"""Calibrated per-field confidence + selective-prediction routing (Phase 6, EDD §10).

The trust metric is "refuse to guess": a field the system is not sure of is FLAGGED and routed to review,
never confidently filled wrong. The spike (eval/spike_calibration.py, §10 first) established the honest
signal on the committed local stack: the model's own introspection is degenerate (it self-reports ~0.95
even when wrong), so confidence is NOT the model's verbalized number. It is CALIBRATION on the human gold
— the empirically-measured reliability of a predicted value, P(correct | the model predicted this class),
attenuated by grounding, and forced to zero on explicit abstention (UNCLEAR / a null the model refused to
guess). Clean classes the model predicts reliably earn high confidence; the low-precision residual and the
confusable cluster earn low confidence → review.

Two honesty caveats the artifact carries (owner review 2026-08-19c): (a) "correct" means "agrees with the
HUMAN GOLD used to fit" — the gold I authored — so confidence measures agreement-with-the-labeller, not
agreement-with-reality; the ceiling is label consistency, and the fix is an INDEPENDENT human-labelled
held-out slice, not a bigger extractor. (b) This is a per-CLASS prior: two cases in the same predicted
class score identically except for grounding, so it drives class-level review TRIAGE, never a per-case
difficulty ranking. Thin cells (n < _MIN_CELL_N) emit no number — they fall to the field default.

This module is the RUNTIME: it loads a calibration artifact (fit offline on the labeled dev set by
:func:`fit`, persisted to ``calibration.json``) and scores a field value. If no artifact is present it
fails SAFE — every value reads low-confidence and routes to review (refuse to guess), never the reverse.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

_ARTIFACT_PATH = Path(__file__).resolve().parent / "calibration.json"

# The abstention sentinels: a value the extractor refused to guess. Confidence 0 → always routed to review.
_ABSTENTIONS = frozenset({"UNCLEAR"})

# Fail-safe defaults when no calibration artifact exists yet (fresh checkout / before the first fit):
# everything is low-confidence and routes to review. Safe direction (refuse to guess), never auto-route.
_SAFE_DEFAULT_CONFIDENCE = 0.4

# Minimum gold observations before a per-class reliability is TRUSTED as a number. Below this a cell is
# noise wearing a decimal (owner review, 2026-08-19): a 1.00 from n=2, or a 0.33 from n=5, is not a
# measurement. A thin cell is DROPPED from the reliability map so the value falls back to the field's
# conservative default (its overall accuracy) — the artifact never reports precision it does not have.
# Rule of three: at n<10 the 95% error bound is ≥~30%, so a small-n cell can't support a high-τ claim.
_MIN_CELL_N = 10


@dataclass(frozen=True)
class FieldCalibration:
    """Per-value reliability for one governed field, plus the fallback for a value unseen at fit time.

    Only cells with ``support[value] >= _MIN_CELL_N`` appear in ``reliability``; thinner cells are
    omitted so :meth:`Calibration.confidence` uses ``default`` for them (no invented precision). The
    surviving ``support`` counts are carried so the artifact shows exactly how much gold backs each number.
    """

    reliability: dict[str, float]
    default: float  # reliability of a value not seen (or too thinly seen) at fit — conservative
    support: dict[str, int] = field(
        default_factory=dict
    )  # gold n behind each surviving reliability


@dataclass(frozen=True)
class Calibration:
    """The fitted calibration: per-field value reliabilities + the auto-route threshold τ. ``tau_auto`` is
    the lowest confidence whose accepted set still meets the accuracy gate on the dev set; ``gate_met``
    records whether that gate (≥98%) was actually reachable — reported honestly, never forced (§10).
    """

    version: str
    fit_on: str
    fields: dict[str, FieldCalibration] = field(default_factory=dict)
    tau_auto: float = 0.8
    gate_met: bool = False

    def confidence(self, field_path: str, value: object, *, grounding: float = 1.0) -> float:
        """Calibrated confidence for a field value in [0, 1]. An abstention (UNCLEAR / None) → 0. A
        calibrated governed value → its reliability × grounding. An uncalibrated field (e.g. emergent) →
        grounding alone (the only honest signal we have for it). When NO calibration is loaded at all
        (unfitted / missing artifact) → a low bootstrap confidence so a missing artifact reads as
        uncertain and routes to review — never spuriously certain."""
        if value is None or (isinstance(value, str) and value.strip() in _ABSTENTIONS):
            return 0.0
        if (
            not self.fields
        ):  # unfitted: no gold to lean on → conservative for everything (fail safe)
            return round(max(0.0, min(1.0, _SAFE_DEFAULT_CONFIDENCE * grounding)), 4)
        fc = self.fields.get(field_path)
        if fc is None:
            return round(
                max(0.0, min(1.0, grounding)), 4
            )  # calibrated elsewhere; this field is uncalibrated (emergent) → grounding is all we have
        # A value with a thin/absent cell falls to the field default — no per-class number is emitted
        # unless ≥_MIN_CELL_N gold cases back it (thin cells were dropped at fit time).
        reliability = fc.reliability.get(str(value), fc.default)
        return round(max(0.0, min(1.0, reliability * grounding)), 4)

    def route(self, confidence: float) -> str:
        """Selective prediction: ``auto`` if confidence clears the auto-route threshold, else ``review``.
        Below τ the field is flagged and routed to a human — never auto-filled as if correct."""
        return "auto" if confidence >= self.tau_auto else "review"


def _blank(version: str = "unfitted", reason: str = "no calibration artifact") -> Calibration:
    return Calibration(version=version, fit_on=reason, fields={}, tau_auto=1.01, gate_met=False)


def load_calibration(path: Path = _ARTIFACT_PATH) -> Calibration:
    """Load the fitted artifact, or a fail-safe blank (τ unreachable → everything routes to review) if it
    is absent/unreadable. Fail-safe means a missing calibration can only ever be MORE cautious."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _blank()
    fields = {
        name: FieldCalibration(
            reliability=dict(fc["reliability"]),
            default=float(fc["default"]),
            support={k: int(v) for k, v in fc.get("support", {}).items()},
        )
        for name, fc in doc.get("fields", {}).items()
    }
    return Calibration(
        version=str(doc.get("version", "unknown")),
        fit_on=str(doc.get("fit_on", "")),
        fields=fields,
        tau_auto=float(doc.get("tau_auto", 1.01)),
        gate_met=bool(doc.get("gate_met", False)),
    )


def save_calibration(cal: Calibration, path: Path = _ARTIFACT_PATH) -> None:
    doc = {
        "version": cal.version,
        "fit_on": cal.fit_on,
        "tau_auto": cal.tau_auto,
        "gate_met": cal.gate_met,
        "fields": {
            name: {"reliability": fc.reliability, "default": fc.default, "support": fc.support}
            for name, fc in cal.fields.items()
        },
    }
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------- offline fitting


@dataclass(frozen=True)
class FitRow:
    """One labeled observation for fitting: what the model predicted for a field, and the gold truth."""

    field_path: str
    predicted: str | None
    gold: str | None
    grounding: float = 1.0


def _fit_reliability(rows: Sequence[FitRow]) -> dict[str, FieldCalibration]:
    correct: dict[tuple[str, str], int] = defaultdict(int)
    total: dict[tuple[str, str], int] = defaultdict(int)
    field_correct: dict[str, int] = defaultdict(int)
    field_total: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.predicted is None or r.gold is None:
            continue
        total[(r.field_path, r.predicted)] += 1
        field_total[r.field_path] += 1
        if r.predicted == r.gold:
            correct[(r.field_path, r.predicted)] += 1
            field_correct[r.field_path] += 1
    out: dict[str, FieldCalibration] = {}
    fields = {fp for fp, _ in total}
    for fp in fields:
        # Only cells with enough gold behind them earn a per-class number; thinner cells are DROPPED
        # (they fall back to the default) rather than emitting a decimal from 1-5 observations.
        rel = {
            val: correct[(f, val)] / total[(f, val)]
            for (f, val) in total
            if f == fp and total[(f, val)] >= _MIN_CELL_N
        }
        support = {
            val: total[(f, val)] for (f, val) in total if f == fp and total[(f, val)] >= _MIN_CELL_N
        }
        # A value unseen (or too thinly seen) at fit time defaults to the field's overall accuracy — a
        # conservative, non-zero prior so a genuinely novel-but-plausible class isn't auto-failed, yet
        # still lands below a high τ (so it routes to review until it has its own track record).
        default = (
            field_correct[fp] / field_total[fp] if field_total[fp] else _SAFE_DEFAULT_CONFIDENCE
        )
        out[fp] = FieldCalibration(reliability=rel, default=round(default, 4), support=support)
    return out


def _select_tau(
    rows: Sequence[FitRow], fields: dict[str, FieldCalibration], target: float
) -> tuple[float, bool]:
    """Leave-one-out selective prediction on the driver field (category): the lowest τ whose accepted-set
    accuracy still meets ``target``. LOO so a case never grades itself. Returns (τ, gate_met)."""
    cat = [
        r
        for r in rows
        if r.field_path == "category" and r.predicted is not None and r.gold is not None
    ]
    if not cat:
        return 1.01, False
    scored: list[tuple[float, bool]] = []
    for i, r in enumerate(cat):
        c = sum(
            1
            for j, o in enumerate(cat)
            if j != i and o.predicted == r.predicted and o.predicted == o.gold
        )
        t = sum(1 for j, o in enumerate(cat) if j != i and o.predicted == r.predicted)
        conf = (c / t if t else 0.0) * r.grounding
        scored.append((conf, r.predicted == r.gold))
    best: float | None = None
    for tau in sorted({c for c, _ in scored}, reverse=True):
        acc_set = [ok for c, ok in scored if c >= tau]
        if acc_set and sum(acc_set) / len(acc_set) >= target:
            best = tau
    return (best, True) if best is not None else (1.01, False)


def fit(rows: Sequence[FitRow], *, version: str, fit_on: str, target: float = 0.98) -> Calibration:
    """Fit a calibration from labeled rows: per-value reliability per field + the auto-route τ chosen by
    leave-one-out selective prediction to meet ``target`` accepted-set accuracy. If the gate can't be met
    at any τ, ``gate_met=False`` and τ is set unreachable (route everything to review) — honest, not forced.
    """
    fields = _fit_reliability(rows)
    tau, gate_met = _select_tau(rows, fields, target)
    return Calibration(
        version=version, fit_on=fit_on, fields=fields, tau_auto=tau, gate_met=gate_met
    )
