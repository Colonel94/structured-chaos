"""Export the labelling workbook's Cases sheet to the CSV the scorer consumes.

`holdout_labels.xlsx` is the human source of truth (Cases + Option Sets + QA Summary, dropdown-validated).
`score_holdout.py` reads `holdout_labels_<name>.csv`. This regenerates that CSV from the workbook so the
two never drift. Re-run after editing the workbook.

    cd engine && uv run --group dev python eval/export_holdout_workbook.py            # -> holdout_labels_owner.csv
    cd engine && uv run --group dev python eval/export_holdout_workbook.py alice      # -> holdout_labels_alice.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import openpyxl

_DIR = Path(__file__).resolve().parent / "fixtures"
_WORKBOOK = _DIR / "holdout_labels.xlsx"


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "owner"
    out = _DIR / f"holdout_labels_{name}.csv"
    wb = openpyxl.load_workbook(_WORKBOOK, data_only=True)
    rows = list(wb["Cases"].iter_rows(values_only=True))
    header = [(h or "").strip() for h in rows[0]]
    n = 0
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows[1:]:
            if r is None or r[0] in (None, ""):
                continue
            w.writerow(["" if c is None else str(c) for c in r])
            n += 1
    print(f"wrote {out} — {n} rows + header")


if __name__ == "__main__":
    main()
