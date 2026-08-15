"""Generate a BLIND human-labeling sheet for the accuracy eval (4.6).

Everything measured so far is STRUCTURAL (json-valid, grounding, convergence). Accuracy — is the
governed core actually CORRECT — is unmeasured, and the winning condition (§4, "cannot name a field
the system got wrong") is fundamentally an accuracy claim. That needs ground truth we did NOT author:
a human labels the correct answer for a sample of the REAL CFPB cases (CLAUDE.md §10-Q3).

Blind on purpose: the sheet shows the narrative + the valid vocab and leaves the ``gold_*`` columns
empty. The model's predictions are deliberately NOT shown, so the labels can't be anchored to them —
otherwise the score grades the labeller's agreement with the model, not the model's correctness.

Stratified ``per_product`` cases per CFPB product so the slice isn't dominated by one complaint type.
Deterministic (sorted by id) and a strict SUPERSET as ``per_product`` grows, so it can be re-run to
GROW the set. **Merge-safe: any gold labels already in the sheet are preserved** (matched by id) — a
re-run never clobbers work already done; it only tops up with new blank rows + restores the narrative
column for reading. Fill it, then run ``eval/score.py``.

Usage:  uv run python eval/make_label_sheet.py [per_product]   (default 25 → 100 total)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from app.extract.schema import DESIRED_OUTCOMES, EMOTIONS, SEVERITIES, TAXONOMY

_DIR = Path(__file__).resolve().parent / "fixtures"
_SAMPLE = _DIR / "cfpb_sample.jsonl"
_SHEET = _DIR / "cfpb_labels.csv"
_INSTRUCTIONS = _DIR / "cfpb_labels_INSTRUCTIONS.md"

_GOLD_COLS = [
    "gold_category",
    "gold_desired_outcome",
    "gold_severity_signal",
    "gold_emotion_signal",
    "gold_key_facts",
]


def _existing_gold() -> dict[str, dict[str, str]]:
    """Gold values already labelled, keyed by id — so a re-run PRESERVES them (never clobbers work)."""
    if not _SHEET.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with _SHEET.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            gold = {c: str(r.get(c, "") or "").strip() for c in _GOLD_COLS}
            if any(gold.values()):
                out[str(r["id"])] = gold
    return out


def main() -> int:
    per_product = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    rows = [json.loads(line) for line in _SAMPLE.read_text(encoding="utf-8").splitlines() if line]
    kept = _existing_gold()  # read BEFORE we overwrite the sheet

    by_product: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_product.setdefault(r["product"], []).append(r)
    sample: list[dict[str, str]] = []
    for product in sorted(by_product):
        picks = sorted(by_product[product], key=lambda r: str(r["id"]))[:per_product]
        sample.extend(picks)

    preserved = 0
    with _SHEET.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "product", "issue", "narrative", *_GOLD_COLS])
        for r in sample:
            g = kept.get(str(r["id"]))
            if g:
                preserved += 1
            w.writerow(
                [
                    r["id"],
                    r["product"],
                    r.get("issue", ""),
                    r["narrative"],
                    *[(g or {}).get(c, "") for c in _GOLD_COLS],
                ]
            )

    _INSTRUCTIONS.write_text(
        "# Labeling instructions — CFPB accuracy slice\n\n"
        f"{len(sample)} real complaints ({per_product} per product), of which {preserved} are already "
        "labelled from the first pass (leave those rows as they are). Fill the `gold_*` columns for the "
        "REMAINING blank rows with the CORRECT answer — what a careful human says the case is, reading "
        "only the narrative. Leave a cell EMPTY to skip that field for that row (it won't be scored). "
        "Do not look at the model output first.\n\n"
        "## Valid values (exact strings)\n"
        f"- **gold_category**: {' | '.join(TAXONOMY)}\n"
        "  - Use `UNCLEAR` only if the narrative is genuinely too sparse/ambiguous to classify — NOT "
        "just because the retail-flavoured list fits a financial complaint awkwardly. If `billing_charge` "
        "is the least-bad fit for a disputed charge, use it.\n"
        f"- **gold_desired_outcome**: {' | '.join(DESIRED_OUTCOMES)} | `null`\n"
        "  - `null` = the customer did NOT state what they want. Pick the value only if they explicitly "
        "ask for it; if they state two, the one they say FIRST.\n"
        f"- **gold_severity_signal**: {' | '.join(SEVERITIES)}\n"
        "  - `financial_harm` = MONETARY harm of any kind (unauthorized/disputed charge, overcharge or "
        "fee, money taken/withheld/frozen, a debt wrongly owed or reported, damaged credit, a denied/"
        "withheld refund). `none` = no monetary/safety/vulnerability harm (e.g. a plain information "
        "request, or a late/damaged item with no hazard).\n"
        f"- **gold_emotion_signal**: {' | '.join(EMOTIONS)}\n"
        "- **gold_key_facts** (optional): the specific facts that SHOULD be captured, `;`-separated, as "
        "`name=value` — e.g. `charged amount=$500; account status=closed`. Used for a soft recall check "
        "(did the system capture what matters).\n\n"
        f"Then run: `uv run python eval/score.py`\n",
        encoding="utf-8",
    )

    print(
        f"wrote {len(sample)} rows ({preserved} preserved labelled, {len(sample) - preserved} blank) -> {_SHEET}"
    )
    print(f"instructions -> {_INSTRUCTIONS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
