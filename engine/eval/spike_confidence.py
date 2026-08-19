"""SPIKE (throwaway, §10 riskiest-assumption-first) — does a $0 confidence signal separate correct
from wrong extracted field values well enough for selective-prediction routing, on data we did NOT
author?

This is the killer for Phase 6's confidence half. The spec's own falsification test (EDD §10): pick the
lowest threshold tau whose accepted-set accuracy stays >= 98%, then verify >= 90% of the ambiguous/wrong
cases fall below tau. "If both can't hold at any tau, the signal is too weak — raise N, don't force the
knob." We prove or disprove that BEFORE building the calibration/routing pipeline upstream of it.

Signal under test: SELF-CONSISTENCY (the spec's strongest-ranked signal, EDD §10; and the one that needs
no logprobs — verified live 2026-08-19 that Ollama 0.12.3 returns logprobs:null). We re-run the real
extractor N times at temperature>0 with varied seeds and measure, per governed field, the fraction of
samples agreeing with the modal value. Correctness = modal value == human gold.

Reports the metric as a PAIR (accepted accuracy AND coverage) per [[report-metric-pairs-and-n]]: an
abstain-everything resolver scores 100% accuracy / 0% coverage and is worse, so accuracy-up+coverage-down
is a regression. Prints rule-of-three bounds so a small-n zero-error slice is never mistaken for a >=98%
gate (need ~300 clean obs for a real 99% claim).

Run (Ollama up, on the 4070):
    EVAL_DATASET=cfpb uv run python eval/spike_confidence.py --n 5 --temp 0.7 --limit 120
Writes eval/fixtures/spike_confidence_<dataset>.jsonl (raw per-case samples) so the analysis is
re-runnable without re-sampling.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset import DATASET, LABELS, SAMPLE

from app.config import settings
from app.extract.extractor import extract

# The governed fields with clean human gold in the label CSVs.
FIELDS = ("category", "desired_outcome", "severity_signal", "emotion_signal")
_GOLD_COL = {
    "category": "gold_category",
    "desired_outcome": "gold_desired_outcome",
    "severity_signal": "gold_severity_signal",
    "emotion_signal": "gold_emotion_signal",
}
_RAW = Path(__file__).resolve().parent / "fixtures" / f"spike_confidence_{DATASET}.jsonl"


class SamplingOllama:
    """OllamaLLM twin that SAMPLES (temperature>0, per-call seed) instead of greedy temp0 — so N calls
    actually vary and self-consistency has a signal to measure. Throwaway; the production backend stays
    temp0/deterministic."""

    def __init__(self, temperature: float, seed: int) -> None:
        self._host = settings.ollama_host.rstrip("/")
        self._model = settings.ollama_model
        self._temp = temperature
        self._seed = seed
        self.last_usage: dict[str, float] = {}

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {"temperature": self._temp, "seed": self._seed},
        }
        if schema is not None:
            payload["format"] = schema
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(f"{self._host}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return str(data["message"]["content"])


def _norm(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _load_gold() -> dict[str, dict[str, str | None]]:
    gold: dict[str, dict[str, str | None]] = {}
    with LABELS.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            gold[row["id"]] = {f: _norm(row.get(_GOLD_COL[f])) for f in FIELDS}
    return gold


async def _sample_case(narrative: str, n: int, temp: float) -> list[dict[str, str | None]]:
    """N extractions of one case; return the governed value of each field per sample."""
    out: list[dict[str, str | None]] = []
    for k in range(n):
        r = await extract(narrative, llm=SamplingOllama(temp, seed=1000 + k))
        out.append({f: _norm(r.governed.get(f)) for f in FIELDS})
    return out


async def _collect(limit: int | None, n: int, temp: float) -> list[dict[str, Any]]:
    gold = _load_gold()
    rows = [json.loads(x) for x in SAMPLE.read_text(encoding="utf-8").splitlines() if x]
    if limit:
        rows = rows[:limit]
    results: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for i, row in enumerate(rows):
        cid = str(row["id"])
        if cid not in gold:
            continue
        samples = await _sample_case(row["narrative"], n, temp)
        results.append({"id": cid, "gold": gold[cid], "samples": samples})
        if (i + 1) % 10 == 0:
            dt = time.perf_counter() - t0
            print(f"  {i + 1}/{len(rows)} cases  ({dt / (i + 1):.1f}s/case)", flush=True)
    return results


def _rule_of_three(errors: int, n: int) -> str:
    """95% upper bound on the true error rate. Zero errors -> ~3/n (rule of three)."""
    if n == 0:
        return "n=0"
    ub = 3.0 / n if errors == 0 else (errors + 2.0 * (errors**0.5)) / n
    return f"<= {ub * 100:.1f}% err (95% UB, {errors} err / n={n})"


def _analyse(results: list[dict[str, Any]], n: int) -> None:
    print(f"\n=== SELF-CONSISTENCY CONFIDENCE SPIKE — {DATASET}, N={n}, {len(results)} cases ===")
    for field in FIELDS:
        # Per case: modal value + agreement fraction (the confidence signal); correctness vs gold.
        obs: list[tuple[float, bool, bool]] = []  # (agreement, correct, gold_present)
        for r in results:
            vals = [s[field] for s in r["samples"]]
            present = [v for v in vals if v is not None]
            # modal over ALL samples (None counts as a vote — abstention IS a prediction here)
            counts = Counter(vals)
            modal, modal_n = counts.most_common(1)[0]
            agreement = modal_n / len(vals)
            g = r["gold"][field]
            correct = (modal == g) if g is not None else (modal is None)
            obs.append((agreement, correct, g is not None))
            _ = present
        gold_rows = [
            (a, c) for (a, c, gp) in obs if gp
        ]  # only cases with a gold label for this field
        if not gold_rows:
            print(f"\n[{field}] no gold labels — skipped")
            continue
        base_acc = sum(c for _, c in gold_rows) / len(gold_rows)
        print(
            f"\n[{field}] n={len(gold_rows)} gold-labeled  modal-accuracy(all)={base_acc * 100:.1f}%"
        )
        # Distribution of the signal
        by_level: dict[float, list[bool]] = {}
        for a, c in gold_rows:
            by_level.setdefault(round(a, 3), []).append(c)
        print("  agreement -> accuracy (count):")
        for lvl in sorted(by_level, reverse=True):
            cs = by_level[lvl]
            print(f"    {lvl:.2f}: {sum(cs) / len(cs) * 100:5.1f}%  (n={len(cs)})")
        # Selective prediction: sweep tau over the observed agreement levels; accept those >= tau.
        levels = sorted({a for a, _ in gold_rows}, reverse=True)
        best = None  # (tau, coverage, accepted_acc, errors_below_tau_frac)
        for tau in levels:
            accepted = [c for a, c in gold_rows if a >= tau]
            if not accepted:
                continue
            acc = sum(accepted) / len(accepted)
            coverage = len(accepted) / len(gold_rows)
            if acc >= 0.98:
                errors = [(a, c) for a, c in gold_rows if not c]
                below = sum(1 for a, _c in errors if a < tau)
                flagged = below / len(errors) if errors else 1.0
                best = (tau, coverage, acc, flagged, len(accepted), len(accepted) - sum(accepted))
        if best:
            tau, cov, acc, flagged, na, nerr = best
            print(
                f"  >>> DUAL-GATE @ tau={tau:.2f}: accepted-acc={acc * 100:.1f}% "
                f"COVERAGE={cov * 100:.1f}%  ambiguous-flagged={flagged * 100:.1f}%"
            )
            print(f"      accepted-set {_rule_of_three(nerr, na)}")
            verdict = (
                "PASS-pair" if (acc >= 0.98 and flagged >= 0.90) else "accuracy-only (rate weak)"
            )
            print(f"      PAIR verdict: {verdict}  (need acc>=98% AND flagged>=90%)")
        else:
            print("  >>> NO tau reaches >=98% accepted accuracy — signal too weak for this field")


async def _amain() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--temp", type=float, default=0.7)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--reuse", action="store_true", help="skip sampling, re-analyse the saved jsonl"
    )
    args = ap.parse_args()

    if args.reuse and _RAW.exists():
        results = [json.loads(x) for x in _RAW.read_text(encoding="utf-8").splitlines() if x]
        print(f"reusing {len(results)} cases from {_RAW.name}")
    else:
        print(f"sampling {DATASET} N={args.n} temp={args.temp} limit={args.limit} ...", flush=True)
        results = await _collect(args.limit, args.n, args.temp)
        _RAW.write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")
        print(f"wrote {_RAW}")
    _analyse(results, args.n)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
