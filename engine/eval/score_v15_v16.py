"""Compare v15 vs v16 (service↔record tighten) against the new CFPB gold. Watch: service_fault recall
UP, record_accuracy recall NOT regressed, overall accuracy, and the service→record leak."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows cp1252 chokes on ->arrow

_FIX = Path(__file__).resolve().parent / "fixtures"


def _preds(p: Path) -> dict[str, str]:
    d = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            d[str(r["id"])] = str((r.get("governed") or {}).get("category") or "").strip().lower()
    return d


def _acc(preds, gold):
    return sum(int(preds.get(i) == g) for i, g in gold.items()), len(gold)


def _recall(preds, gold, cat):
    ids = [i for i, g in gold.items() if g == cat]
    return sum(int(preds.get(i) == cat) for i in ids), len(ids)


gold = {
    r["id"]: r["gold_category"].strip().lower()
    for r in csv.DictReader((_FIX / "cfpb_labels.csv").open(encoding="utf-8"))
    if r["gold_category"].strip()
}
v15, v16 = _preds(_FIX / "cfpb_extractions_v15.jsonl"), _preds(_FIX / "cfpb_extractions.jsonl")

print("                     v15        v16")
for name, p in (("overall accuracy", None), ("record_accuracy recall", "record_accuracy"),
                ("service_fault recall", "service_fault"), ("billing_charge recall", "billing_charge"),
                ("access_availability recall", "access_availability")):
    if p is None:
        a5, t = _acc(v15, gold)
        a6, _ = _acc(v16, gold)
    else:
        a5, t = _recall(v15, gold, p)
        a6, _ = _recall(v16, gold, p)
    print(f"  {name:26} {a5}/{t:<3}     {a6}/{t}")

for tag, preds in (("v15", v15), ("v16", v16)):
    leak = sum(1 for i, g in gold.items() if g == "service_fault" and preds.get(i) == "record_accuracy")
    print(f"  service→record leak ({tag}): {leak}")
print("\nv16 dist:", dict(Counter(v16.values()).most_common()))
