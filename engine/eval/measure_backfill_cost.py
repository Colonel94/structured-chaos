"""Measure the backfill cost spike the owner flagged ("the single largest cost spike… you'll discover
the number in production") — grounded: UNIT cost measured live, FAN-OUT computed from the real corpus.

Backfill fires on promotion and re-extracts the concept across every un-attempted case in its
category. This projects the cost from (a) the measured per-call cost of a concept re-extraction on real
narratives, and (b) the real fan-out: which heads would promote (support ≥ 4) and how many cases fall
in each promoted head's categories. Reports the NAIVE fan-out and the OPTIMIZED one (skip cases that
already attest the concept) — the gap is a cheap, honest cost lever.

Usage:  uv run python eval/measure_backfill_cost.py [unit_sample]
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from app.backends.local.llm_ollama import OllamaLLM
from app.extract.concept_extract import extract_concept
from app.schema.promote import PROMOTE_HEAD_N

_DIR = Path(__file__).resolve().parent / "fixtures"
_EXTRACTIONS = _DIR / "cfpb_extractions.jsonl"
_SAMPLE = _DIR / "cfpb_sample.jsonl"


async def main() -> int:
    unit_sample = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    cases = [json.loads(x) for x in _EXTRACTIONS.read_text(encoding="utf-8").splitlines() if x]
    narr = {
        str(json.loads(x)["id"]): json.loads(x)["narrative"]
        for x in _SAMPLE.read_text(encoding="utf-8").splitlines()
        if x
    }

    # --- fan-out from the real corpus --------------------------------------------------------------
    heads_of = [{a["head"] for a in c["attributes"]} for c in cases]
    category_of = [str((c.get("governed") or {}).get("category")) for c in cases]
    support: Counter[str] = Counter()
    for hs in heads_of:
        for h in hs:
            support[h] += 1
    promoted = sorted(
        [h for h, s in support.items() if s >= PROMOTE_HEAD_N], key=lambda h: -support[h]
    )

    naive = optimized = 0
    per_head: list[tuple[str, int, int, int]] = []
    for h in promoted:
        cats = {category_of[i] for i, hs in enumerate(heads_of) if h in hs}
        scan = [
            i for i, c in enumerate(category_of) if c in cats
        ]  # every case in the head's categories
        already = sum(1 for i in scan if h in heads_of[i])  # already attests the concept
        naive += len(scan)
        optimized += len(scan) - already
        per_head.append((h, support[h], len(scan), len(scan) - already))

    # --- unit cost: real concept re-extractions ----------------------------------------------------
    llm = OllamaLLM()
    ids = list(narr)[:unit_sample]
    lat: list[float] = []
    tin = tout = 0.0
    for cid in ids:
        await extract_concept(narr[cid], head="amount", qualifier=None, llm=llm)
        lat.append(float(llm.last_usage.get("wall_ms", 0.0)))
        tin += float(llm.last_usage.get("tokens_in", 0.0))
        tout += float(llm.last_usage.get("tokens_out", 0.0))
    mean_ms = sum(lat) / len(lat)
    mean_in, mean_out = tin / len(ids), tout / len(ids)

    print("===== BACKFILL COST (unit measured live, fan-out from real 120-case corpus) =====")
    print(f"promoted heads (support>={PROMOTE_HEAD_N}): {len(promoted)}  -> {promoted}")
    print(
        f"\nunit re-extraction (n={len(ids)}) : {mean_ms / 1000:.1f}s/call, {mean_in:.0f} in / {mean_out:.0f} out tokens"
    )
    print("\n-- fan-out (calls) per promoted head: scan-set vs already-attested --")
    for h, sup, scan, opt in per_head[:20]:
        print(f"  {h:<14} support={sup:<3} scan={scan:<4} needed(missing)={opt}")
    print(f"\nNAIVE total calls     : {naive}   (re-checks cases that already have the concept)")
    print(f"OPTIMIZED total calls : {optimized}   (skip already-attested → the cheap lever)")
    print(
        f"\nprojected wall-clock  : naive {naive * mean_ms / 1000 / 60:.0f} min  |  optimized {optimized * mean_ms / 1000 / 60:.0f} min  (serial, one 4070)"
    )
    print(
        f"projected tokens      : naive {naive * (mean_in + mean_out) / 1e6:.2f}M  |  optimized {optimized * (mean_in + mean_out) / 1e6:.2f}M"
    )
    print(
        "\nNOTE: local qwen3:14b on the 4070 = $0 in API terms; the spike is WALL-CLOCK + GPU, not $."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
