"""SPIKE #2 (throwaway, §10) — CALIBRATION on the human gold: does the empirically-measured reliability
of a predicted value (attenuated by grounding, zeroed on explicit abstention) give an HONEST confidence
that separates correct from wrong under the selective-prediction dual gate — where the model's own
introspection (spike #1) and an LLM cross-check both failed?

Spike #1 proved the model's introspective signals are degenerate (it commits hard, self-reports ~0.95
even when wrong). A reframed LLM cross-check also failed (an incompetent second classifier disagrees
everywhere). The main prompt already encodes the best category discrimination, and its residual errors
sit at the owner-authored gold-ambiguity ceiling — so there is NO magic separator. The honest signal is
CALIBRATION: confidence(predicted value) = P(correct | the model predicted this class), estimated on the
gold correction set (the project's asset, §3). Clean classes the model predicts reliably (product_fault,
safety_health) earn high confidence; the low-precision residual (service_fault) and the confusable
cluster earn low confidence — routed to review. Explicit abstention (UNCLEAR/null) → confidence 0.

We report the selective-prediction PAIR (accepted accuracy AND coverage) at the τ that first reaches
≥98% accepted accuracy, plus the fraction of wrong cases flagged, with rule-of-three bounds. Leave-one-out
so the reliability of a case's class is NOT estimated including that case (no self-grading). If no τ holds
both, we say so and do NOT force the knob (§10).

Run (Ollama up):  EVAL_DATASET=cfpb uv run --group embed python eval/spike_calibration.py --limit 120
Resumable: writes eval/fixtures/spike_calibration_<dataset>.jsonl per case; --reuse re-analyses.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset import DATASET, LABELS, SAMPLE

from app.backends.local.llm_ollama import OllamaLLM
from app.extract.extractor import extract

_RAW = Path(__file__).resolve().parent / "fixtures" / f"spike_calibration_{DATASET}.jsonl"

# Every governed field with clean human gold — all calibrated in one run (category is the driver of the
# SLA/routing decision, so it anchors the headline + τ selection, but the artifact covers all four).
GOV = ("category", "desired_outcome", "severity_signal", "emotion_signal")
_GOLD_COL = {f: f"gold_{f}" for f in GOV}


def _norm(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _load_gold() -> dict[str, dict[str, str | None]]:
    gold: dict[str, dict[str, str | None]] = {}
    with LABELS.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            gold[row["id"]] = {f: _norm(row.get(_GOLD_COL[f])) for f in GOV}
    return gold


async def _collect(limit: int | None) -> list[dict[str, Any]]:
    gold = _load_gold()
    rows = [json.loads(x) for x in SAMPLE.read_text(encoding="utf-8").splitlines() if x]
    if limit:
        rows = rows[:limit]
    llm = OllamaLLM()
    out: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for i, row in enumerate(rows):
        cid = str(row["id"])
        if cid not in gold:
            continue
        r = await extract(row["narrative"], llm=llm)
        out.append(
            {
                "id": cid,
                "gold": gold[cid],
                "pred": {f: _norm(r.governed.get(f)) for f in GOV},
                "grounding": round(r.field_validity, 3),
            }
        )
        if (i + 1) % 10 == 0:
            print(
                f"  {i + 1}/{len(rows)}  ({(time.perf_counter() - t0) / (i + 1):.1f}s/case)",
                flush=True,
            )
    return out


def _rule_of_three(errors: int, n: int) -> str:
    if n == 0:
        return "n=0"
    ub = 3.0 / n if errors == 0 else (errors + 2.0 * (errors**0.5)) / n
    return f"<= {ub * 100:.1f}% err (95% UB, {errors} err / n={n})"


def _cat(r: dict[str, Any], which: str) -> str | None:
    return r[which]["category"]


def _reliability_loo(rows: list[dict[str, Any]], fieldname: str) -> dict[str, float]:
    """P(correct | predicted class) per class for one field, over the whole set (for reporting)."""
    correct: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    for r in rows:
        p, g = r["pred"][fieldname], r["gold"][fieldname]
        if p is None or g is None:
            continue
        total[p] += 1
        if p == g:
            correct[p] += 1
    return {c: correct[c] / total[c] for c in total}


def _confidence_loo(rows: list[dict[str, Any]], idx: int) -> float:
    """Calibrated category confidence for row `idx`: leave-one-out reliability of its predicted class ×
    grounding. UNCLEAR / null is an explicit abstention → 0 (always routed to review)."""
    cls = _cat(rows[idx], "pred")
    if cls == "UNCLEAR" or cls is None:
        return 0.0
    # LOO reliability over the gold-labeled peers that share this predicted class.
    peers = [
        o
        for j, o in enumerate(rows)
        if j != idx and _cat(o, "pred") == cls and _cat(o, "gold") is not None
    ]
    if not peers:
        return 0.0
    reliability = sum(_cat(o, "pred") == _cat(o, "gold") for o in peers) / len(peers)
    return reliability * float(rows[idx]["grounding"])


def _analyse(rows: list[dict[str, Any]]) -> None:
    n = len(rows)
    print(f"\n=== CALIBRATION CONFIDENCE SPIKE — {DATASET}, n={n} ===")
    cat_gold = [r for r in rows if _cat(r, "gold") is not None]
    base = sum(_cat(r, "pred") == _cat(r, "gold") for r in cat_gold) / len(cat_gold)
    print(f"main-extractor category accuracy = {base * 100:.1f}%  (n={len(cat_gold)})")

    for fieldname in GOV:
        rel = _reliability_loo(rows, fieldname)
        if not rel:
            continue
        print(f"\nper-predicted reliability P(correct | predicted)  [{fieldname}]:")
        for cls in sorted(rel, key=lambda c: -rel[c]):
            total = sum(
                1 for r in rows if r["pred"][fieldname] == cls and r["gold"][fieldname] is not None
            )
            print(f"    {cls:26s} {rel[cls] * 100:5.1f}%  (n={total})")

    # Selective prediction on the DRIVER field (category), leave-one-out, on the gold-labeled subset.
    conf = [_confidence_loo(rows, i) for i in range(n) if _cat(rows[i], "gold") is not None]
    correct = [_cat(r, "pred") == _cat(r, "gold") for r in cat_gold]
    n = len(correct)

    # Selective prediction: sweep τ; accept confidence ≥ τ. Report the PAIR at the lowest τ hitting ≥98%.
    levels = sorted(set(conf), reverse=True)
    best = None
    for tau in levels:
        acc_idx = [i for i in range(n) if conf[i] >= tau]
        if not acc_idx:
            continue
        acc = sum(correct[i] for i in acc_idx) / len(acc_idx)
        if acc >= 0.98:
            best = tau
    print("\n[calibrated confidence = LOO class-reliability × grounding; UNCLEAR/null → 0]")
    if best is not None:
        acc_idx = [i for i in range(n) if conf[i] >= best]
        acc = sum(correct[i] for i in acc_idx) / len(acc_idx)
        cov = len(acc_idx) / n
        wrong = [i for i in range(n) if not correct[i]]
        flagged = sum(1 for i in wrong if conf[i] < best)
        nerr = len(acc_idx) - sum(correct[i] for i in acc_idx)
        print(
            f"  τ={best:.3f}: accepted n={len(acc_idx)}  accuracy={acc * 100:.1f}%  COVERAGE={cov * 100:.1f}%"
        )
        print(f"    {_rule_of_three(nerr, len(acc_idx))}")
        print(
            f"  flagged→review catches {flagged}/{len(wrong)} wrong = {flagged / len(wrong) * 100:.0f}% of errors"
            if wrong
            else "  no errors"
        )
        pair = (
            "PASS-pair"
            if (acc >= 0.98 and (not wrong or flagged / len(wrong) >= 0.90))
            else "SUB-GATE (reported honestly)"
        )
        print(f"  PAIR verdict: {pair}")
    else:
        print(
            "  no τ reaches ≥98% accepted accuracy — the signal is too weak; reported, knob NOT forced"
        )

    # Also report a few coverage points so the accuracy/coverage trade-off is visible, not a single knob.
    print("\n  coverage @ accuracy trade-off:")
    for tau in [0.9, 0.8, 0.7, 0.6, 0.5]:
        acc_idx = [i for i in range(n) if conf[i] >= tau]
        if acc_idx:
            acc = sum(correct[i] for i in acc_idx) / len(acc_idx)
            print(
                f"    τ≥{tau:.1f}: cov={len(acc_idx) / n * 100:4.0f}%  acc={acc * 100:4.1f}%  (n={len(acc_idx)})"
            )


async def _amain() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--reuse", action="store_true")
    args = ap.parse_args()
    if args.reuse and _RAW.exists():
        rows = [json.loads(x) for x in _RAW.read_text(encoding="utf-8").splitlines() if x]
        print(f"reusing {len(rows)} cases from {_RAW.name}")
    else:
        print(f"running calibration spike on {DATASET} limit={args.limit} ...", flush=True)
        rows = await _collect(args.limit)
        _RAW.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        print(f"wrote {_RAW} ({len(rows)} cases)")
    _analyse(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
