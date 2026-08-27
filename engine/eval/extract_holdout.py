"""Run the SHIPPED extractor over the held-out narratives → holdout_extractions.jsonl (the MODEL side).

This is the MODEL side of the independent-labelling comparison (W1). The held-out cases are fresh, so no
model output exists for them yet. We produce it with the exact shipped extractor + prompt and keep it in a
SEPARATE file that is NEVER shown to the labeller (showing predictions would make the labels grade
agreement-with-the-model, the circularity the whole exercise escapes).

INCREMENTAL + RESUMABLE + OBSERVABLE (2026-08-26): each result is written and flushed the moment it
completes, so ``wc -l`` shows live progress and a crash keeps completed work. On restart, ids already
present UNDER THE CURRENT PROMPT_VERSION are skipped; a prompt bump invalidates the old rows (they carry
the old version) so they are re-extracted. Local Ollama on the 4070 is ~15-25 s/case → budget ~60-80 min
for 200; $0.

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
from app.extract.prompt import PROMPT_VERSION

_DIR = Path(__file__).resolve().parent / "fixtures"
# The 200-case labelling set (66 original + 134 owner-authored), exported from holdout_labels.xlsx via
# eval/export_holdout_workbook.py. Only the `narrative` column is read here — the gold columns are never
# seen by the extractor (blind, see docstring).
_SHEET = _DIR / "holdout_labels_owner.csv"
_OUT = _DIR / "holdout_extractions.jsonl"


def _already_done(current_version: str) -> set[str]:
    """Ids already extracted under the CURRENT prompt version (resume support). Rows from an older prompt
    version are ignored so a version bump forces a clean re-extraction."""
    if not _OUT.exists():
        return set()
    done: set[str] = set()
    kept: list[str] = []
    for line in _OUT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("prompt_version") == current_version:
            done.add(str(rec["id"]))
            kept.append(line)
    # Rewrite the file to drop stale-version rows, so the final file is exactly the current run.
    _OUT.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return done


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if not _SHEET.exists():
        print(f"no holdout sheet at {_SHEET} — run eval/export_holdout_workbook.py first")
        return 1
    with _SHEET.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    done = _already_done(PROMPT_VERSION)
    todo = [r for r in rows if str(r["id"]) not in done]
    print(
        f"{len(rows)} held-out cases; {len(done)} already at {PROMPT_VERSION}; extracting {len(todo)}…",
        flush=True,
    )

    llm = OllamaLLM()
    with _OUT.open("a", encoding="utf-8") as out:
        for i, row in enumerate(todo):
            r = await extract(row["narrative"], llm=llm)
            rec = {
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
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if (i + 1) % 5 == 0 or (i + 1) == len(todo):
                print(
                    f"  …{i + 1}/{len(todo)}  (last cat={r.governed.get('category')})", flush=True
                )

    total = len(_already_done(PROMPT_VERSION))
    print(f"done — {total}/{len(rows)} model extractions at {PROMPT_VERSION} → {_OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
