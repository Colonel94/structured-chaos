"""R6 four-number matrix — separate the TAXONOMY effect from the PROMPT effect (owner requirement).

Category accuracy is reported for the 2x2 of {old gold, new gold} x {old prompt (v14), new prompt (v15)}
so the effect of adding `record_accuracy` + re-labelling (taxonomy) is separable from the effect of the
updated prompt. Plus the majority-class baseline for the NEW distribution (accuracy near baseline is not
a result) and the confusion of the true new baseline (v15 x new gold).

Usage:  uv run python eval/score_r6_matrix.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

_FIX = Path(__file__).resolve().parent / "fixtures"


def _preds(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[str(r["id"])] = str((r.get("governed") or {}).get("category") or "").strip().lower()
    return out


def _gold(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            g = str(row.get("gold_category", "")).strip().lower()
            if g:
                out[str(row["id"])] = g
    return out


def _acc(preds: dict[str, str], gold: dict[str, str]) -> tuple[int, int]:
    hit = tot = 0
    for gid, g in gold.items():
        if gid in preds:
            tot += 1
            hit += int(preds[gid] == g)
    return hit, tot


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    v14 = _preds(_FIX / "cfpb_extractions_v14.jsonl")
    v15 = _preds(_FIX / "cfpb_extractions.jsonl")
    gold_old = _gold(_FIX / "cfpb_labels_oldgold.csv")
    gold_new = _gold(_FIX / "cfpb_labels.csv")

    print("===== R6 FOUR-NUMBER MATRIX — category accuracy (CFPB, n=100) =====")
    print(f"{'':22}| old prompt (v14)     | new prompt (v15)")
    for gname, gold in (("old gold", gold_old), ("new gold (record_accuracy)", gold_new)):
        h14, t14 = _acc(v14, gold)
        h15, t15 = _acc(v15, gold)
        a14 = f"{h14}/{t14} = {h14 / t14:.0%}" if t14 else "n/a"
        a15 = f"{h15}/{t15} = {h15 / t15:.0%}" if t15 else "n/a"
        print(f"{gname:22}| {a14:20} | {a15}")

    # Majority-class baseline for the NEW distribution — accuracy must clear this to mean anything.
    dist = Counter(gold_new.values())
    n = sum(dist.values())
    top, topn = dist.most_common(1)[0]
    print(f"\nNEW gold distribution : {dict(dist.most_common())}")
    print(f"majority-class baseline (always-'{top}') : {topn}/{n} = {topn / n:.0%}")

    print("\n-- confusion of the TRUE new baseline (v15 preds x new gold), top 16 --")
    conf: Counter[tuple[str, str]] = Counter()
    for gid, g in gold_new.items():
        if gid in v15:
            conf[(g, v15[gid] or "∅")] += 1
    for (g, m), c in conf.most_common(16):
        print(f"  {'OK ' if g == m else 'XX '} gold={g:<18} model={m:<18} x{c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
