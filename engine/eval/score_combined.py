"""Combined ~200-case category accuracy (v16) — CFPB + multidomain, per-domain and pooled. The grown
gold set. Majority-class baseline per set so accuracy is read against the right floor."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

_FIX = Path(__file__).resolve().parent / "fixtures"


def _preds(p: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            d[str(r["id"])] = str((r.get("governed") or {}).get("category") or "").strip().lower()
    return d


def _gold(p: Path) -> dict[str, str]:
    return {
        r["id"]: r["gold_category"].strip().lower()
        for r in csv.DictReader(p.open(encoding="utf-8"))
        if r["gold_category"].strip()
    }


def _report(name: str, gold: dict[str, str], preds: dict[str, str]) -> tuple[int, int]:
    hit = sum(int(preds.get(i) == g) for i, g in gold.items() if i in preds)
    tot = sum(1 for i in gold if i in preds)
    dist = Counter(gold.values())
    top, topn = dist.most_common(1)[0]
    n = sum(dist.values())
    print(f"\n{name}: {hit}/{tot} = {hit / tot:.0%}   (majority '{top}' = {topn}/{n} = {topn / n:.0%})")
    ra = dist.get("record_accuracy", 0)
    if ra:
        rah = sum(int(preds.get(i) == "record_accuracy") for i, g in gold.items() if g == "record_accuracy" and i in preds)
        print(f"    record_accuracy recall: {rah}/{ra}   ({ra / n:.0%} of this set)")
    return hit, tot


def main() -> int:
    cg, cp = _gold(_FIX / "cfpb_labels.csv"), _preds(_FIX / "cfpb_extractions.jsonl")
    mg, mp = _gold(_FIX / "multidomain_labels.csv"), _preds(_FIX / "multidomain_extractions.jsonl")
    print(f"===== COMBINED GOLD (v16) — CFPB {len(cg)} + multidomain {len(mg)} = {len(cg) + len(mg)} rows =====")
    h1, t1 = _report("CFPB (finance)", cg, cp)
    h2, t2 = _report("multidomain (9 sectors)", mg, mp)
    both_g = {**{f"c:{k}": v for k, v in cg.items()}, **{f"m:{k}": v for k, v in mg.items()}}
    both_p = {**{f"c:{k}": v for k, v in cp.items()}, **{f"m:{k}": v for k, v in mp.items()}}
    _report("COMBINED (cross-domain)", both_g, both_p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
