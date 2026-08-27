"""Fit the confidence calibration artifact and write it to ``app/confidence/calibration.json`` (the
runtime-loaded artifact, EDD §10).

This is the OFFLINE step. The runtime never re-fits — it just loads the JSON — so there is NO
sklearn/scipy dependency in the engine; fitting is a few deterministic counts here.

WHAT IT FITS ON (owner directive, 2026-08-27 — the fix the calibration was waiting for). Calibration
turns a predicted class into P(correct | the model predicted this class). "Correct" only means what the
GOLD says, so the gold choice is everything:

  * ``--spike`` (legacy) fits on ``spike_calibration_*.jsonl`` — SELF-AUTHORED cfpb/multidomain gold. On
    that gold "correct" meant "agrees with the labeller I (Claude) wrote", i.e. confidence was really
    P(agrees-with-my-labels), a label-consistency number, not a reliability estimate ([[calibration-label-ceiling-per-class]]).
  * default (calib-v3) fits on the INDEPENDENT TWO-EXPERT CONSENSUS: the held-out cases where the two
    independent domain-expert labellers (Osman, Catleen) AGREE. That agreed label is the closest thing to
    ground truth we have, so confidence becomes a genuine reliability estimate for the first time. Rows
    where the two experts DISAGREE have no trustworthy gold and are excluded (that is what "consensus"
    means — we only calibrate where independent truth is unambiguous).

Thin cells are floored the same way in both modes: a class with < _MIN_CELL_N (=10) gold observations
emits NO per-class number and falls back to the field's conservative default (its overall accuracy), so
the artifact never reports precision it does not have (owner directive; already enforced in
``app/confidence/model.py``).

Run:
    ./.venv/Scripts/python.exe eval/fit_calibration.py            # independent consensus (calib-v3)
    ./.venv/Scripts/python.exe eval/fit_calibration.py --spike    # legacy self-authored spike gold
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.confidence import FitRow, fit, save_calibration

_FIX = Path(__file__).resolve().parent / "fixtures"
GOV = ("category", "desired_outcome", "severity_signal", "emotion_signal")
_LABEL_COL = {
    "gold_category": "category",
    "gold_desired_outcome": "desired_outcome",
    "gold_severity_signal": "severity_signal",
    "gold_emotion_signal": "emotion_signal",
}


def _norm(v: object) -> str:
    s = str(v or "").strip().lower()
    return "" if s in ("", "null") else s


def _load_spike_rows() -> tuple[list[FitRow], list[str]]:
    """LEGACY: build rows from the self-authored spike gold (cfpb/multidomain, pooled)."""
    rows: list[FitRow] = []
    sources: list[str] = []
    for spike in sorted(_FIX.glob("spike_calibration_*.jsonl")):
        cases = [json.loads(x) for x in spike.read_text(encoding="utf-8").splitlines() if x]
        if not cases:
            continue
        sources.append(f"{spike.stem.replace('spike_calibration_', '')}(n={len(cases)})")
        for c in cases:
            grounding = float(c.get("grounding", 1.0))
            for f in GOV:
                rows.append(
                    FitRow(
                        field_path=f,
                        predicted=c["pred"].get(f),
                        gold=c["gold"].get(f),
                        grounding=grounding,
                    )
                )
    return rows, [f"gold: {' + '.join(sources)}"] if sources else []


def _load_label_csv(path: Path) -> dict[str, dict[str, str]]:
    return {
        str(r["id"]): {f: _norm(r.get(col, "")) for col, f in _LABEL_COL.items()}
        for r in csv.DictReader(path.open(encoding="utf-8"))
    }


def _load_consensus_rows() -> tuple[list[FitRow], list[str]]:
    """Build rows from the INDEPENDENT two-expert consensus: model prediction vs the label the two
    independent experts AGREE on, for the held-out cases. Rows where they disagree (no consensus gold)
    are skipped. Grounding comes from the extraction's ``field_validity``.
    """
    cat_p, osm_p = _FIX / "holdout_labels_catleen.csv", _FIX / "holdout_labels_osman.csv"
    model_p = _FIX / "holdout_extractions.jsonl"
    if not (cat_p.exists() and osm_p.exists() and model_p.exists()):
        return [], []
    cat, osm = _load_label_csv(cat_p), _load_label_csv(osm_p)

    model: dict[str, dict[str, str]] = {}
    grounding: dict[str, float] = {}
    for line in model_p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        cid = str(r["id"])
        gov = r.get("governed") or {}
        model[cid] = {f: _norm(gov.get(f)) for f in GOV}
        try:
            grounding[cid] = float(r.get("field_validity", 1.0))
        except (TypeError, ValueError):
            grounding[cid] = 1.0

    rows: list[FitRow] = []
    per_field_n = dict.fromkeys(GOV, 0)
    disagreed = dict.fromkeys(GOV, 0)
    for cid in (c for c in cat if c in osm and c in model):
        g = grounding.get(cid, 1.0)
        for f in GOV:
            gv_c, gv_o = cat[cid][f], osm[cid][f]
            if gv_c != gv_o:  # the two experts disagree → no consensus gold on this field
                disagreed[f] += 1
                continue
            # An abstention prediction (model emitted null) is hardwired to confidence 0 at runtime, so it
            # gets no calibrated cell (predicted=None → skipped by the fitter). A real null GOLD (only
            # desired_outcome) is kept as "" so a non-null prediction there counts as a miss, not a skip.
            predicted = model[cid][f] or None
            rows.append(FitRow(field_path=f, predicted=predicted, gold=gv_c, grounding=g))
            per_field_n[f] += 1
    src = "independent 2-expert consensus (catleen∩osman, holdout) — agreeing rows: " + ", ".join(
        f"{f}={per_field_n[f]}/{per_field_n[f] + disagreed[f]}" for f in GOV
    )
    return rows, [src]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    use_spike = "--spike" in sys.argv[1:]
    if use_spike:
        rows, sources = _load_spike_rows()
        version = "calib-spike"
        if not rows:
            print("no spike_calibration_*.jsonl found — run eval/spike_calibration.py first")
            return 1
    else:
        rows, sources = _load_consensus_rows()
        version = "calib-v3"
        if not rows:
            print(
                "no independent consensus found — need holdout_labels_catleen.csv + "
                "holdout_labels_osman.csv + holdout_extractions.jsonl in eval/fixtures/.\n"
                "(Use --spike to fit on the legacy self-authored spike gold instead.)"
            )
            return 1

    fit_on = sources[0]
    cal = fit(rows, version=version, fit_on=fit_on)
    save_calibration(cal)
    print(f"fitted {version} on {fit_on}")
    print(f"  tau_auto={cal.tau_auto:.3f}  gate_met={cal.gate_met}")
    for name, fc in sorted(cal.fields.items()):
        n_trusted = len(fc.reliability)
        print(f"  [{name}] default={fc.default:.3f}  ({n_trusted} trusted classes, n>=10)")
        for val, rel in sorted(fc.reliability.items()):
            print(f"      {val:<22} {rel:.3f}  (n={fc.support.get(val, 0)})")
    print("wrote app/confidence/calibration.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
