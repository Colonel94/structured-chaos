"""Fit the confidence calibration artifact from the spike output(s) and write it to
``app/confidence/calibration.json`` (the runtime-loaded artifact, EDD §10).

This is the OFFLINE step: it reads the per-case predictions vs human gold captured by
``eval/spike_calibration.py`` (for whichever datasets exist — cfpb and/or multidomain, pooled), turns
them into labeled rows, and fits per-value reliability + the auto-route threshold τ (leave-one-out
selective prediction to a ≥98% accepted-accuracy target). The runtime never re-fits — it just loads the
JSON — so there is NO sklearn/scipy dependency in the engine; fitting is a few deterministic counts here.

Run (after the spike jsonl(s) exist):
    uv run python eval/fit_calibration.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.confidence import FitRow, fit, save_calibration

_FIX = Path(__file__).resolve().parent / "fixtures"
GOV = ("category", "desired_outcome", "severity_signal", "emotion_signal")


def _load_rows() -> tuple[list[FitRow], list[str]]:
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
    return rows, sources


def main() -> int:
    rows, sources = _load_rows()
    if not rows:
        print("no spike_calibration_*.jsonl found — run eval/spike_calibration.py first")
        return 1
    fit_on = "gold: " + " + ".join(sources)
    cal = fit(rows, version="calib-v1", fit_on=fit_on)
    save_calibration(cal)
    print(f"fitted calibration on {fit_on}")
    print(f"  tau_auto={cal.tau_auto:.3f}  gate_met={cal.gate_met}")
    for name, fc in sorted(cal.fields.items()):
        n_classes = len(fc.reliability)
        print(f"  [{name}] {n_classes} calibrated classes, default={fc.default}")
    print("wrote app/confidence/calibration.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
