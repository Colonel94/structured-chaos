"""W2 — per-field EDIT breakdown: which governed fields a reviewer corrects, how often, which way.

The aggregate "28% zero-edit" (score_phase8.py) hides its own cause. A reviewer edits a case because
ONE OR MORE governed fields is wrong; this script decomposes that: for each governed field it reports
the EDIT rate (model != gold, over rows a human labelled), the DIRECTION of the error (the top
gold→model confusions), and — the number W3 needs — each field's CONTRIBUTION to the zero-edit gap
(of the cases that needed ≥1 edit, how often was THIS field the culprit).

Deterministic and $0: reads the same on-disk artifacts as score_phase8.py (the human-labelled slice +
the current extractions). Uses the SAME zero-edit definition (a row with ≥2 labelled governed fields,
every one matching gold) so this decomposes exactly the metric the scorecard gates on — not a new one
([[CLAUDE.md §10 — don't move the goalposts]]).

Honesty note: the gold here is authored by Claude, so "edit" means "disagrees-with-the-labeller", not
"disagrees-with-reality". That caveat is on every accuracy row in the project and applies here too; the
independent held-out slice (make_holdout_label_sheet.py) is what turns edit-rate into a truth-rate.

Usage:  uv run python eval/edit_breakdown.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "fixtures"
_DATASETS = ("cfpb", "multidomain")

# gold csv column -> extraction governed key. Emotion IS decomposed here (it drives routing/escalation
# and is part of what a reviewer corrects) even though §4 does not gate it — a field always corrected is
# a field worth cutting whether or not §4 names it.
_FIELD_MAP = {
    "gold_category": "category",
    "gold_desired_outcome": "desired_outcome",
    "gold_severity_signal": "severity_signal",
    "gold_emotion_signal": "emotion_signal",
}
_NULL_ON_BLANK = {"gold_desired_outcome"}


def _norm(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    return "" if s in ("", "null") else s


def _load(dataset: str) -> list[tuple[dict[str, str], set[str], dict[str, object]]]:
    """Returns (gold, labelled_keys, pred_governed) per case that has both a label row and an
    extraction. Mirrors score_phase8._load_cases blank-cell handling exactly."""
    labels = _DIR / f"{dataset}_labels.csv"
    extr = _DIR / f"{dataset}_extractions.jsonl"
    if not labels.exists() or not extr.exists():
        return []
    preds = {
        str(json.loads(line)["id"]): json.loads(line)
        for line in extr.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rows = list(csv.DictReader(labels.open(encoding="utf-8", newline="")))
    active_null_on_blank = {
        col for col in _NULL_ON_BLANK if any(str(r.get(col, "") or "").strip() for r in rows)
    }
    out = []
    for row in rows:
        p = preds.get(str(row["id"]))
        if p is None:
            continue
        gov = p.get("governed") or {}
        gold: dict[str, str] = {}
        labelled: set[str] = set()
        for col, key in _FIELD_MAP.items():
            raw = str(row.get(col, "") or "").strip()
            if raw == "" and col not in active_null_on_blank:
                continue
            labelled.add(key)
            gold[key] = _norm(raw)
        out.append((gold, labelled, {k: gov.get(k) for k in _FIELD_MAP.values()}))
    return out


def _report(dataset: str) -> None:
    cases = _load(dataset)
    if not cases:
        print(f"\n[{dataset}] no labelled cases — skipping")
        return

    keys = list(_FIELD_MAP.values())
    edits: Counter[str] = Counter()
    labelled_n: Counter[str] = Counter()
    confusion: dict[str, Counter[tuple[str, str]]] = {k: Counter() for k in keys}
    # zero-edit population (same rule as score_phase8): rows with >=2 labelled governed fields.
    ze_rows = [(g, lab, pr) for (g, lab, pr) in cases if len(lab) >= 2]
    culprit: Counter[str] = Counter()  # among edited rows, which fields were wrong
    ze_ok = 0

    for gold, lab, pred in cases:
        for k in keys:
            if k not in lab:
                continue
            labelled_n[k] += 1
            g, m = gold[k], _norm(pred.get(k))
            if g != m:
                edits[k] += 1
                confusion[k][(g or "∅", m or "∅")] += 1

    for gold, lab, pred in ze_rows:
        wrong = [k for k in lab if gold[k] != _norm(pred.get(k))]
        if not wrong:
            ze_ok += 1
        for k in wrong:
            culprit[k] += 1

    print(f"\n{'=' * 78}\n[{dataset}]  {len(cases)} labelled cases")
    dens = sum(len(lab) for _g, lab, _p in cases) / len(cases)
    print(f"  mean labelled governed fields/row: {dens:.1f}  (zero-edit only counts rows with ≥2)")

    print("\n  PER-FIELD EDIT RATE (model ≠ gold, over rows a human labelled this field)")
    for k in keys:
        n = labelled_n[k]
        if not n:
            print(f"    {k:<16}: no gold labelled")
            continue
        e = edits[k]
        print(f"    {k:<16}: edited {e}/{n} = {e / n:.0%}   (accuracy {(n - e) / n:.0%})")

    print("\n  DIRECTION of the errors (gold → model, top 6 per field)")
    for k in keys:
        if not confusion[k]:
            continue
        print(f"    {k}:")
        for (g, m), c in confusion[k].most_common(6):
            print(f"       {g:<20} → {m:<20} ×{c}")

    if ze_rows:
        ze_bad = len(ze_rows) - ze_ok
        print(
            f"\n  ZERO-EDIT DECOMPOSITION  (rows with ≥2 labelled fields = {len(ze_rows)})"
            f"\n    zero-edit (nothing to fix): {ze_ok}/{len(ze_rows)} = {ze_ok / len(ze_rows):.0%}"
            f"\n    needed ≥1 edit            : {ze_bad}/{len(ze_rows)}"
        )
        print("    culprit field among edited rows (a row can have several):")
        for k in keys:
            if culprit[k]:
                # share of edited rows this field spoiled
                print(
                    f"       {k:<16}: spoiled {culprit[k]}/{ze_bad} edited rows "
                    f"= {culprit[k] / ze_bad:.0%}"
                )
        # The counterfactual W3 cares about: if we CUT a field, how many currently-edited rows become
        # zero-edit (i.e. that field was the SOLE reason they needed an edit)?
        print(
            "\n    counterfactual — CUT a field → rows that flip to zero-edit (it was the SOLE culprit):"
        )
        for cut in keys:
            flips = 0
            for gold, lab, pred in ze_rows:
                if cut not in lab:
                    continue
                wrong = [k for k in lab if gold[k] != _norm(pred.get(k))]
                remaining = [k for k in lab if k != cut]
                # after cutting `cut`, does this row still qualify (≥2 fields) and is it now clean?
                if len(remaining) >= 2 and wrong == [cut]:
                    flips += 1
            if flips:
                # recompute the zero-edit rate over the rows that still have >=2 fields after the cut
                denom = sum(1 for _g, lab, _p in ze_rows if len([k for k in lab if k != cut]) >= 2)
                new_zero_rate = (ze_ok + flips) / denom if denom else 0.0
                print(
                    f"       cut {cut:<16}: +{flips} rows flip → zero-edit "
                    f"{ze_ok}/{len(ze_rows)}={ze_ok / len(ze_rows):.0%} "
                    f"→ {ze_ok + flips}/{denom}={new_zero_rate:.0%}"
                )
            else:
                print(f"       cut {cut:<16}: +0 rows flip (never the sole culprit)")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print("W2 — PER-FIELD EDIT BREAKDOWN (decomposes the zero-edit gate; $0, files-only)")
    print(
        "gold is Claude-authored → 'edit' = disagrees-with-labeller, not with reality (see docstring)"
    )
    for ds in _DATASETS:
        _report(ds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
