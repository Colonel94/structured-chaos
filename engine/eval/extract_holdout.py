"""Run the SHIPPED v20 extractor over the 66 held-out narratives → holdout_extractions.jsonl.

This is the MODEL side of the independent-labelling comparison (W1). The held-out cases are fresh (not in
the 216), so no model output exists for them yet. We produce it ONCE, with the exact shipped extractor +
prompt, and keep it in a SEPARATE file that is NEVER shown to the labeller (showing predictions would make
the labels grade agreement-with-the-model, the circularity the whole exercise escapes — make_holdout_label
_sheet.py §BLIND). When the filled human labels come back, eval/score_holdout.py reads THIS file as the
model and the human CSV(s) as gold.

Deterministic per the model; $0 (local Ollama, host→GPU). Idempotent overwrite.

Usage:  uv run python eval/extract_holdout.py
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
from pathlib import Path

from app.backends.local.llm_ollama import OllamaLLM
from app.extract.extractor import extract

_DIR = Path(__file__).resolve().parent / "fixtures"
_SHEET = _DIR / "holdout_labels.csv"
_OUT = _DIR / "holdout_extractions.jsonl"


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if not _SHEET.exists():
        print(f"no holdout sheet at {_SHEET} — run eval/make_holdout_label_sheet.py first")
        return 1
    with _SHEET.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"extracting {len(rows)} held-out cases with the shipped v20 extractor…")

    llm = OllamaLLM()
    from app.extract.prompt import PROMPT_VERSION

    results = []
    for i, row in enumerate(rows):
        r = await extract(row["narrative"], llm=llm)
        results.append(
            {
                "id": row["id"],
                "product": row.get("product", ""),
                "governed": r.governed,
                "attributes": [
                    {"head": e.head, "qualifier": e.qualifier, "value": e.value, "name": e.name}
                    for e in r.grounded_emergent
                ],
                "field_validity": r.field_validity,
                "prompt_version": PROMPT_VERSION,
            }
        )
        if (i + 1) % 10 == 0:
            print(f"  …{i + 1}/{len(rows)}")

    with _OUT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(results)} model extractions → {_OUT}  (prompt {PROMPT_VERSION})")
    print("This file is the MODEL side; it is NEVER shown to the labeller (blind — see docstring).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
