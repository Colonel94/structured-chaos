"""Diagnostic (NOT a proof): where do the real synonym pairs fall relative to the τ gate, and what
does the reframed adjudicator now say for them? Tells us whether the bottleneck is the ADJUDICATOR
(pairs reach the gray band but get rejected) or the EMBEDDING/THRESHOLD (real synonyms sit below
0.70 and never reach the adjudicator at all). Reuses the frozen extraction fixture — no re-extraction.

Usage:  uv run --group embed python eval/diag_pairs.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.backends.local.embed_bge import BGEEmbedding
from app.backends.local.llm_ollama import OllamaLLM
from app.schema.dedup import ADMIT_TAU, MERGE_TAU, _adjudicate, _name_text

_FIX = Path(__file__).resolve().parent / "fixtures" / "cfpb_extractions.jsonl"

# Pairs a human would call the same column. Grounded in the promoted-fields list from the proof.
PAIRS = [
    ("amount", "charged_amount"),
    ("amount", "fraudulent_amount"),
    ("charged_amount", "fraudulent_amount"),
    ("account_status", "payment_status"),
    ("account_status", "dispute_status"),
    ("bank_name", "company_name"),
    ("bank_name", "credit_card_provider"),
    ("customer_request", "requested_actions"),
    ("contact_attempts", "number_of_contacts"),
    ("account_number", "account_status"),  # a genuine NON-synonym control (should stay split)
]


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def main() -> int:
    cases = [json.loads(line) for line in _FIX.read_text(encoding="utf-8").splitlines() if line]
    names: set[str] = set()
    for c in cases:
        names.update(c["emergent"])
    wanted = sorted({n for pair in PAIRS for n in pair} & names)
    missing = sorted({n for pair in PAIRS for n in pair} - names)
    if missing:
        print(f"(not present in fixture, skipped): {missing}")

    embedder = BGEEmbedding()
    vecs = await embedder.embed([_name_text(n) for n in wanted])
    emb = dict(zip(wanted, vecs, strict=True))
    llm = OllamaLLM()

    print(f"MERGE_TAU={MERGE_TAU}  ADMIT_TAU={ADMIT_TAU}\n")
    print(f"{'pair':<42} {'cosine':>7}  {'band':<10} adjudicator")
    for a, b in PAIRS:
        if a not in emb or b not in emb:
            continue
        cos = _cos(emb[a], emb[b])
        if cos >= MERGE_TAU:
            band = "auto-merge"
            verdict = "(n/a)"
        elif cos < ADMIT_TAU:
            band = "auto-ADMIT"
            verdict = "(never asked)"
        else:
            band = "gray"
            verdict = "SAME" if await _adjudicate(llm, a, b) else "different"
        print(f"{a + ' | ' + b:<42} {cos:7.3f}  {band:<10} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
