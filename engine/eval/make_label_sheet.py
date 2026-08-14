"""Generate a BLIND human-labeling sheet for the accuracy eval (4.6).

Everything measured so far is STRUCTURAL (json-valid, grounding, convergence). Accuracy — is the
governed core actually CORRECT — is unmeasured, and the winning condition (§4, "cannot name a field
the system got wrong") is fundamentally an accuracy claim. That needs ground truth we did NOT author:
a human labels the correct answer for a sample of the REAL CFPB cases (CLAUDE.md §10-Q3).

Blind on purpose: the sheet shows the narrative + the valid vocab and leaves the ``gold_*`` columns
empty. The model's predictions are deliberately NOT shown, so the labels can't be anchored to them —
otherwise the score grades the labeller's agreement with the model, not the model's correctness.

Stratified 10 cases per CFPB product (40 total) so the slice isn't dominated by one complaint type.
Deterministic (sorted by id) — re-running yields the same sheet. Fill it, then run ``eval/score.py``.

Usage:  uv run python eval/make_label_sheet.py [per_product]
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


def main() -> int:
    per_product = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    rows = [json.loads(line) for line in _SAMPLE.read_text(encoding="utf-8").splitlines() if line]

    by_product: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_product.setdefault(r["product"], []).append(r)
    sample: list[dict[str, str]] = []
    for product in sorted(by_product):
        picks = sorted(by_product[product], key=lambda r: str(r["id"]))[:per_product]
        sample.extend(picks)

    with _SHEET.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "product", "issue", "narrative", *_GOLD_COLS])
        for r in sample:
            w.writerow(
                [r["id"], r["product"], r.get("issue", ""), r["narrative"], "", "", "", "", ""]
            )

    _INSTRUCTIONS.write_text(
        "# Labeling instructions — CFPB accuracy slice\n\n"
        f"{len(sample)} real complaints ({per_product} per product). Fill the `gold_*` columns in "
        "`cfpb_labels.csv` with the CORRECT answer — what a careful human says the case is, reading "
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
        "  - `financial_harm` for a disputed charge/overcharge; `none` for a late/damaged item with no "
        "hazard.\n"
        f"- **gold_emotion_signal**: {' | '.join(EMOTIONS)}\n"
        "- **gold_key_facts** (optional): the specific facts that SHOULD be captured, `;`-separated, as "
        "`name=value` — e.g. `charged amount=$500; account status=closed`. Used for a soft recall check "
        "(did the system capture what matters).\n\n"
        f"Then run: `uv run python eval/score.py`\n",
        encoding="utf-8",
    )

    print(f"wrote {len(sample)} rows -> {_SHEET}")
    print(f"instructions -> {_INSTRUCTIONS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
