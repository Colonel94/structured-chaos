"""Score governed-core ACCURACY against the human-labeled slice (4.6) — on data we did NOT author.

Reads the filled ``cfpb_labels.csv`` (human gold) + ``cfpb_extractions.jsonl`` (model output), matched
by id, and reports per-field exact-match accuracy for the closed-vocab governed fields, a category
confusion breakdown (is UNCLEAR right?), and a SOFT recall of the human-flagged key facts against the
emergent attributes. Only rows with a non-empty gold cell for a field count toward that field.

This is the first CORRECTNESS measurement — everything before it was structural. Honest by
construction: the labels are the human's, the predictions are the model's, matched blind.

Usage:  uv run python eval/score.py
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "fixtures"
_SHEET = _DIR / "cfpb_labels.csv"
_EXTRACTIONS = _DIR / "cfpb_extractions.jsonl"
_TOKEN = re.compile(r"[a-z0-9]+")
_GOVERNED = ["category", "desired_outcome", "severity_signal", "emotion_signal"]
# Fields where a BLANK gold cell is a real label meaning "null / not stated" (scored against a model
# null), not an unlabeled skip — the owner's convention for desired_outcome (refuse-to-guess).
_NULL_ON_BLANK = {"desired_outcome"}


def _norm(v: object) -> str:
    """Canonicalise a value for comparison: a Python ``None`` (model null), an empty cell, and the
    literal string ``null`` all map to the same empty token, so a human ``null`` matches a model null.
    Note ``none`` (a real severity value) is preserved — only ``null`` is treated as absence."""
    if v is None:
        return ""
    s = str(v).strip().lower()
    return "" if s in ("", "null") else s


def _tokens(s: str) -> set[str]:
    return {t for t in _TOKEN.findall(s.lower()) if len(t) > 2}


def main() -> int:
    if not _SHEET.exists():
        print(f"no label sheet at {_SHEET} — run eval/make_label_sheet.py and fill it first.")
        return 1
    preds = {
        str(json.loads(line)["id"]): json.loads(line)
        for line in _EXTRACTIONS.read_text(encoding="utf-8").splitlines()
        if line
    }
    with _SHEET.open(encoding="utf-8", newline="") as f:
        gold_rows = list(csv.DictReader(f))

    labeled_any = 0
    correct: Counter[str] = Counter()
    total: Counter[str] = Counter()
    cat_confusion: Counter[tuple[str, str]] = Counter()
    gold_cat: Counter[str] = Counter()  # gold category distribution → majority-class baseline
    kf_hit = kf_total = 0

    for row in gold_rows:
        pred = preds.get(str(row["id"]))
        if pred is None:
            continue
        gov = pred.get("governed") or {}
        row_labeled = False

        for field in _GOVERNED:
            raw = str(row.get(f"gold_{field}", "")).strip()
            # A blank cell is normally "unlabeled → skip". EXCEPT for a field in _NULL_ON_BLANK
            # (desired_outcome): the owner leaves it blank to mean "customer stated no outcome → null",
            # which is a REAL label — the model is correct iff it also returned null (refuse-to-guess).
            if raw == "" and field not in _NULL_ON_BLANK:
                continue
            row_labeled = True
            g = _norm(raw)  # blank/"null" → "" (labeled-as-absent); a real value → itself
            m = _norm(gov.get(field))
            total[field] += 1
            if m == g:
                correct[field] += 1
            if field == "category":
                cat_confusion[(g or "∅", m or "∅")] += 1
                if g:
                    gold_cat[g] += 1

        kf = str(row.get("gold_key_facts", "")).strip()
        if kf:
            row_labeled = True
            model_vals = " ".join(str(a.get("value", "")) for a in pred.get("attributes", []))
            model_tok = _tokens(model_vals)
            for fact in (p for p in kf.split(";") if p.strip()):
                kf_total += 1
                want = _tokens(fact.split("=", 1)[-1])  # tokens of the value side
                if want and len(want & model_tok) / len(want) >= 0.5:
                    kf_hit += 1
        labeled_any += int(row_labeled)

    print("===== GOVERNED-CORE ACCURACY (human-labeled slice) =====")
    print(f"labeled rows scored : {labeled_any}/{len(gold_rows)}")
    if labeled_any == 0:
        print("\nNo gold labels filled yet — fill cfpb_labels.csv (see the INSTRUCTIONS.md).")
        return 0
    for field in _GOVERNED:
        if total[field]:
            print(
                f"  {field:<16}: {correct[field]}/{total[field]} = {correct[field] / total[field]:.0%}"
            )
    if kf_total:
        print(
            f"  key-fact recall : {kf_hit}/{kf_total} = {kf_hit / kf_total:.0%}   (soft, value-token overlap)"
        )

    # Majority-class baseline: a dumb classifier that always predicts the most common gold category.
    # Category accuracy is only meaningful ABOVE this line (the corpus concentration ceiling).
    if gold_cat:
        n_cat = sum(gold_cat.values())
        top, top_n = gold_cat.most_common(1)[0]
        top2 = sum(c for _g, c in gold_cat.most_common(2))
        rare = [g for g, c in gold_cat.items() if c <= 2]
        print(
            f"\n  category baseline : always-'{top}' = {top_n}/{n_cat} = {top_n / n_cat:.0%} "
            f"(majority-class); top-2 hold {top2 / n_cat:.0%}"
        )
        if rare:
            print(f"  unmeasurable classes (≤2 gold): {', '.join(sorted(rare))}")

    print("\n-- category confusion (gold -> model), top 15 --")
    for (g, m), n in cat_confusion.most_common(15):
        mark = "OK " if g == m else "XX "
        print(f"  {mark} gold={g:<18} model={m:<18} x{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
