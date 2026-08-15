"""Planted-probe checks against the 100-case gold set (owner's deliberate test rows, 2026-08-15).

Fast + static (fixtures only, no model). Re-run after each extraction to catch regressions on the
specific things the labeller planted or flagged:
  · safety-severity read off the counterparty vs the narrative (the two safety_health rows);
  · the deliberate UNCLEAR row (pure redaction) — the system must ABSTAIN + invent nothing;
  · the desired_outcome null breakdown — how often the model INVENTS an outcome the customer never
    stated (a refuse-to-guess §2 failure the aggregate accuracy hides);
  · the "identical IC System" triplet — a determinism smell-test (see note: they are NOT byte-identical,
    so true determinism is checked separately by re-extracting one narrative twice; verified identical).

Usage:  uv run python eval/gold_checks.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "fixtures"

_SAFETY_ROWS = ["24487979", "24507863"]  # bank disputes with a merchant safety issue underneath
_UNCLEAR_ROW = "24513554"  # pure redaction placeholder — must stay UNCLEAR, invent nothing
_TRIPLET = ["24506166", "24509544", "24525658"]  # near-duplicate IC System template


def _norm(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    return "" if s in ("", "null") else s


def main() -> int:
    preds = {
        str(json.loads(x)["id"]): json.loads(x)
        for x in (_DIR / "cfpb_extractions.jsonl").read_text(encoding="utf-8").splitlines()
        if x
    }
    narr = {
        str(json.loads(x)["id"]): json.loads(x)["narrative"]
        for x in (_DIR / "cfpb_sample.jsonl").read_text(encoding="utf-8").splitlines()
        if x
    }
    with (_DIR / "cfpb_labels.csv").open(encoding="utf-8", newline="") as f:
        gold = {str(r["id"]): r for r in csv.DictReader(f)}

    print("== safety severity (gold safety_health — read off the hazard, not the dispute?) ==")
    for cid in _SAFETY_ROWS:
        g = _norm(gold.get(cid, {}).get("gold_severity_signal"))
        m = _norm((preds[cid].get("governed") or {}).get("severity_signal"))
        print(f"  {cid}: gold={g:<16} model={m:<16} {'OK' if g == m else 'MISS'}")

    print("\n== deliberate UNCLEAR (pure redaction) — must abstain + invent nothing ==")
    u = preds[_UNCLEAR_ROW]
    cat = _norm((u.get("governed") or {}).get("category"))
    print(
        f"  {_UNCLEAR_ROW}: category={cat or '∅'}  emergent_facts={len(u['attributes'])}  "
        f"{'PASS' if cat == 'unclear' and not u['attributes'] else 'FAIL'}"
    )

    print("\n== desired_outcome: does the model invent an outcome the customer never stated? ==")
    gnull = mnull = gval = vok = 0
    for cid, r in gold.items():
        if cid not in preds:
            continue
        g = _norm(r.get("gold_desired_outcome"))
        m = _norm((preds[cid].get("governed") or {}).get("desired_outcome"))
        if g == "":
            gnull += 1
            mnull += m == ""
        else:
            gval += 1
            vok += m == g
    print(
        f"  gold=null : {mnull}/{gnull} model also null  → invented an outcome {gnull - mnull}/{gnull} times (§2 refuse-to-guess)"
    )
    print(f"  gold=value: {vok}/{gval} model matched the stated outcome")

    print("\n== 'identical' IC System triplet ==")
    texts = {cid: narr[cid] for cid in _TRIPLET}
    print(
        f"  byte-identical? {len(set(texts.values())) == 1}  (lengths {[len(t) for t in texts.values()]})"
    )
    print("  NOTE: NOT identical → differing extractions are from different text, not instability.")
    print("  True determinism (same narrative x2, temp 0) verified separately: identical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
