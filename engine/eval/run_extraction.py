"""Run the extractor over the REAL CFPB complaint fixture and report structural quality + the
convergence signal — on data we did NOT author (CLAUDE.md §10-Q3).

What this measures WITHOUT ground-truth labels (so it's honest, not self-graded):
- **json_valid** — did grammar-constrained decoding hold on real messy text.
- **grounding rate** — mean field_validity: the closed-world gate's hallucination resistance.
- **governed-core distributions** — sanity that category/outcome/severity aren't garbage or constant.
- **new-field-rate curve** — distinct emergent field-names discovered per bucket. This is the raw
  convergence signal; WITHOUT dedup (unit 4.3) it will still sprawl on synonyms — that sprawl is the
  honest baseline that dedup must flatten. Re-run after 4.3 to show the curve settle + duplicates drop.

NOT measured here: governed-core ACCURACY (needs labels — a separate real-data + human-label step).
Usage:  uv run python eval/run_extraction.py [limit]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

from app.backends.local.llm_ollama import OllamaLLM
from app.extract.extractor import extract

_FIX = Path(__file__).resolve().parent / "fixtures" / "cfpb_sample.jsonl"
_OUT = Path(__file__).resolve().parent / "fixtures" / "cfpb_extractions.jsonl"
_BUCKET = 20


def _load(limit: int | None) -> list[dict[str, str]]:
    rows = [json.loads(line) for line in _FIX.read_text(encoding="utf-8").splitlines() if line]
    return rows[:limit] if limit else rows


async def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    rows = _load(limit)
    llm = OllamaLLM()

    cat: Counter[str] = Counter()
    outcome: Counter[str] = Counter()
    severity: Counter[str] = Counter()
    emotion: Counter[str] = Counter()
    field_freq: Counter[str] = Counter()
    seen_fields: set[str] = set()
    new_per_bucket: list[int] = []
    json_ok = 0
    validity_sum = 0.0
    latencies: list[float] = []
    results = []

    for i, row in enumerate(rows):
        t0 = time.perf_counter()
        r = await extract(row["narrative"], llm=llm)
        latencies.append((time.perf_counter() - t0) * 1000)
        ok = bool(r.governed)
        json_ok += int(ok)
        validity_sum += r.field_validity
        if ok:
            cat[str(r.governed.get("category"))] += 1
            outcome[str(r.governed.get("desired_outcome"))] += 1
            severity[str(r.governed.get("severity_signal"))] += 1
            emotion[str(r.governed.get("emotion_signal"))] += 1
        bucket_new = 0
        for e in r.grounded_emergent:
            field_freq[e.name] += 1
            if e.name not in seen_fields:
                seen_fields.add(e.name)
                bucket_new += 1
        if i % _BUCKET == 0:
            new_per_bucket.append(0)
        new_per_bucket[-1] += bucket_new
        results.append(
            {
                "id": row["id"],
                "product": row["product"],
                "governed": r.governed,
                "emergent": [e.name for e in r.grounded_emergent],
                "field_validity": r.field_validity,
            }
        )
        if (i + 1) % 10 == 0:
            print(f"  ...{i + 1}/{len(rows)}  distinct_fields={len(seen_fields)}")

    with _OUT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(rows)
    print(f"\n===== REAL-DATA EXTRACTION REPORT (CFPB, n={n}) =====")
    print(f"json_valid            : {json_ok}/{n} ({json_ok / n:.0%})")
    print(f"mean grounding (valid): {validity_sum / n:.3f}   (1.0 = no hallucinated emergent fields)")
    print(f"latency ms  p50/p95   : {sorted(latencies)[n // 2]:.0f} / {sorted(latencies)[int(n * 0.95)]:.0f}")
    print(f"distinct emergent flds: {len(seen_fields)}")
    print(f"new-field per {_BUCKET}-bucket: {new_per_bucket}   <- convergence signal (want: declining)")
    print(f"category dist         : {dict(cat.most_common())}")
    print(f"desired_outcome dist  : {dict(outcome.most_common())}")
    print(f"severity dist         : {dict(severity.most_common())}")
    print(f"emotion dist          : {dict(emotion.most_common())}")
    print(f"top emergent fields   : {dict(field_freq.most_common(15))}")
    print(f"\nwrote per-case extractions -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
