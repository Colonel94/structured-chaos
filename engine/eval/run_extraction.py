"""Run the extractor over the REAL CFPB complaint fixture and report structural quality + the
convergence signal — on data we did NOT author (CLAUDE.md §10-Q3).

Path A (2026-08-14): an emergent attribute is ``{head, qualifier, value}`` — the HEAD is the column
(closed vocabulary), the QUALIFIER carries specificity as data.

*** RETRACTION (2026-08-17, owner + remediation R0). The earlier claim in this docstring — "convergence
is achieved AT EXTRACTION TIME ... this harness IS the Path-A proof ... no downstream dedup needed" — was
INVALID and is withdrawn. ``HEAD_NOUNS`` is a closed 31-element enum enforced in the schema, so the
new-HEAD-per-bucket curve [15,4,4,1,1,1] is the enumeration of a finite list: it declines because finite
sets exhaust, and would draw the same shape on random noise. A gate that cannot fail is not a gate.
The REAL convergence signal is the composite (``qualifier_head``) curve — and it is FLAT: cfpb
[46,38,54,45,51,41] / 275 composites / 89% hapax; multidomain [70,34,49,41,37] / 231 / 92% hapax —
statistically the same as the pre-Path-A full-name curve [48,52,74,64,77,63] this was meant to fix. The
sprawl did not disappear; it moved into the qualifier space, which is unmeasured here and undeduped
(``dedup_field`` has ZERO callers in ``app/``). Convergence is therefore CURRENTLY UNPROVEN. The gate is
the composite curve AFTER dedup runs live (remediation R1/R2); the head curve is a bounded-by-construction
DIAGNOSTIC, not evidence of convergence. Do not re-promote it to the pass line (self-grading, CLAUDE.md
§10 — this is the 2026-08-14 head-noun-altitude move, recommitted under the Path A name). ***

What this measures WITHOUT ground-truth labels (so it's honest, not self-graded):
- **json_valid** — did grammar-constrained decoding hold on real messy text.
- **grounding (value)** — the VALUE gates the attribute (overlap grounding tolerates reformatting);
  comparable to the pre-Path-A 0.941. The QUALIFIER must be strictly EXTRACTIVE (a verbatim source
  span, v4) — a non-extractive qualifier is NULLED, not dropped, so a grounded value survives.
- **qualifier retention** — fraction of kept attributes carrying a verbatim qualifier: how much
  specificity survives strict extraction (Path A relies on qualifiers to carry specificity as data).
- **head enumeration (NOT a gate)** — distinct heads used + the new-head-per-bucket curve. Bounded by
  the closed vocab → declines by construction; reported ONLY as a diagnostic of enum coverage.
- **composite-name curve (THE REAL GATE, currently FAILING)** — new distinct ``qualifier_head`` names
  per bucket + hapax rate. Winning-condition §4 (schema settles: duplicate/synonym fields <5% +
  declining new-field rate) is measured HERE. It is flat and ~90% hapax → unproven until dedup runs.

NOT measured here: governed-core ACCURACY (needs labels — a separate real-data + human-label step).
Usage:  uv run python eval/run_extraction.py [limit]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections import Counter

import httpx
from _dataset import DATASET
from _dataset import EXTRACTIONS as _OUT
from _dataset import SAMPLE as _FIX

from app.backends.local.llm_ollama import OllamaLLM
from app.extract.extractor import extract

_BUCKET = 20
_TOKEN = re.compile(r"[a-z0-9]+")


def _load(limit: int | None) -> list[dict[str, str]]:
    rows = [json.loads(line) for line in _FIX.read_text(encoding="utf-8").splitlines() if line]
    return rows[:limit] if limit else rows


def _value_grounded(value: str, source_lower: str) -> bool:
    """Value-only grounding — the pre-Path-A measure, recomputed here for an apples-to-apples compare
    against the 0.941 baseline (the extractor's field_validity now also folds in qualifier grounding).
    """
    v = value.strip().lower()
    if not v:
        return False
    if v in source_lower:
        return True
    sig = [t for t in _TOKEN.findall(v) if len(t) > 2]
    if not sig:
        return any(t in source_lower for t in _TOKEN.findall(v))
    return sum(1 for t in sig if t in source_lower) / len(sig) >= 0.6


async def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    rows = _load(limit)
    llm = OllamaLLM()

    cat: Counter[str] = Counter()
    outcome: Counter[str] = Counter()
    severity: Counter[str] = Counter()
    emotion: Counter[str] = Counter()
    head_freq: Counter[str] = Counter()
    seen_heads: set[str] = set()
    seen_names: set[str] = set()
    name_support: Counter[str] = Counter()  # composite attestations → hapax rate (the real §4 gate)
    new_head_per_bucket: list[int] = []
    new_name_per_bucket: list[int] = []  # THE GATE: new distinct composites per bucket (must bend)
    json_ok = 0
    validity_sum = 0.0  # extractor field_validity (value grounding, per-case mean)
    value_only_grounded = 0
    candidates_all = 0  # ALL emergent candidates (incl. dropped) — the value-only denominator
    emergent_kept = 0  # grounded candidates actually kept
    qualifiers_retained = 0  # kept attrs carrying a (strictly-extractive) qualifier
    latencies: list[float] = []
    results = []

    from app.extract.models import ExtractionResult

    timed_out: list[str] = []
    for i, row in enumerate(rows):
        t0 = time.perf_counter()
        # Resilience: one pathologically-slow case (schema-constrained generation can stall a single
        # request past the client timeout) must not nuke a 12-minute batch. Retry once, then record an
        # empty result and carry on, logging the id so the failure is visible, not silently swallowed.
        try:
            r = await extract(row["narrative"], llm=llm)
        except httpx.ReadTimeout:
            print(f"  ! {row['id']} timed out; retrying once")
            try:
                r = await extract(row["narrative"], llm=llm)
            except httpx.ReadTimeout:
                print(f"  !! {row['id']} timed out again; recording empty and continuing")
                timed_out.append(str(row["id"]))
                r = ExtractionResult(
                    governed={}, emergent=[], field_validity=0.0, prompt_version="timeout", raw=""
                )
        latencies.append((time.perf_counter() - t0) * 1000)
        ok = bool(r.governed)
        json_ok += int(ok)
        validity_sum += r.field_validity
        if ok:
            cat[str(r.governed.get("category"))] += 1
            outcome[str(r.governed.get("desired_outcome"))] += 1
            severity[str(r.governed.get("severity_signal"))] += 1
            emotion[str(r.governed.get("emotion_signal"))] += 1
        source_lower = row["narrative"].lower()
        if i % _BUCKET == 0:
            new_head_per_bucket.append(0)
            new_name_per_bucket.append(0)
        # Value-only grounding over ALL candidates (incl. dropped) — the apples-to-apples denominator
        # vs the pre-Path-A 0.941; measuring over grounded-only would be circular (always 1.0).
        for e in r.emergent:
            candidates_all += 1
            value_only_grounded += int(_value_grounded(e.value, source_lower))
        for e in r.grounded_emergent:
            head_freq[e.head] += 1
            emergent_kept += 1
            if e.qualifier:
                qualifiers_retained += 1
            if e.head not in seen_heads:
                seen_heads.add(e.head)
                new_head_per_bucket[-1] += 1
            if e.name not in seen_names:
                seen_names.add(e.name)
                new_name_per_bucket[-1] += 1
            name_support[e.name] += 1
        results.append(
            {
                "id": row["id"],
                "product": row["product"],
                "governed": r.governed,
                # Path A: store head/qualifier/value/name so the proof can measure at the head (column)
                # level; `emergent` (composite names) kept for backward-compatible readers.
                "attributes": [
                    {"head": e.head, "qualifier": e.qualifier, "value": e.value, "name": e.name}
                    for e in r.grounded_emergent
                ],
                "emergent": [e.name for e in r.grounded_emergent],
                "field_validity": r.field_validity,
            }
        )
        if (i + 1) % 10 == 0:
            print(f"  ...{i + 1}/{len(rows)}  distinct_heads={len(seen_heads)}")

    with _OUT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(rows)
    from app.extract.prompt import PROMPT_VERSION

    print(
        f"\n===== REAL-DATA EXTRACTION REPORT ({DATASET}, n={n}) — Path A ({PROMPT_VERSION}) ====="
    )
    print(f"json_valid              : {json_ok}/{n} ({json_ok / n:.0%})")
    vo = (value_only_grounded / candidates_all) if candidates_all else 1.0
    print(f"grounding (value)        : {vo:.3f}   (over ALL candidates — vs pre-Path-A 0.941)")
    print(f"  field_validity per-case: {validity_sum / n:.3f}   (same signal, per-case mean)")
    qr = (qualifiers_retained / emergent_kept) if emergent_kept else 0.0
    print(
        f"qualifier retention      : {qr:.3f}   ({qualifiers_retained}/{emergent_kept} kept attrs carry a VERBATIM qualifier)"
    )
    print(f"emergent attrs kept/all  : {emergent_kept}/{candidates_all}")
    print("\n-- HEAD ENUMERATION (NOT the gate — bounded by the closed 31-vocab, declines by construction) --")
    print(f"distinct heads (columns) : {len(seen_heads)}   (closed vocab, bounded by construction)")
    print(
        f"new-head per {_BUCKET}-bucket : {new_head_per_bucket}   <- declines because the enum is FINITE, not because anything converged"
    )
    print("\n-- COMPOSITE CURVE (THE REAL §4 GATE — currently FAILING: flat + ~90% hapax) --")
    hapax = sum(1 for v in name_support.values() if v == 1)
    print(f"distinct composite names : {len(seen_names)}   (the qualifier_head space where sprawl actually lives)")
    print(
        f"new-composite per {_BUCKET}   : {new_name_per_bucket}   <- MUST bend down to converge "
        f"(pre-Path-A was [48,52,74,64,77,63]); flat = unproven"
    )
    print(
        f"hapax rate               : {hapax}/{len(seen_names)} = "
        f"{hapax / len(seen_names) if seen_names else 0:.0%}   (fraction seen once; a converging schema drives this DOWN)"
    )
    print(f"head frequency           : {dict(head_freq.most_common())}")
    print("\n-- governed-core distributions --")
    print(
        f"latency ms  p50/p95      : {sorted(latencies)[n // 2]:.0f} / {sorted(latencies)[int(n * 0.95)]:.0f}"
    )
    print(f"category dist            : {dict(cat.most_common())}")
    print(f"desired_outcome dist     : {dict(outcome.most_common())}")
    print(f"severity dist            : {dict(severity.most_common())}")
    print(f"emotion dist             : {dict(emotion.most_common())}")
    if timed_out:
        print(f"\n!! {len(timed_out)} case(s) timed out (recorded empty): {', '.join(timed_out)}")
    print(f"\nwrote per-case extractions -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
