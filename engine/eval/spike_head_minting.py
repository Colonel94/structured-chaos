"""SPIKE — does emergent head-minting work on real data? (the moat's true convergence mechanism)

The R2 finding (2026-08-17b): the composite curve does not bend because qualifiers are genuinely
high-cardinality DATA, not synonym sprawl — so convergence must be measured at the COLUMN (head) level,
and the head space must GROW by emergence, not stay a hand-seeded closed list. The escape valve (`other`,
now 11.7% after v13) is where genuinely-new concepts land. This spike tests whether those `other` facts
CLUSTER into a coherent new head that recurs enough to mint — the precondition for "specialisation is
emergent, never seeded" being TRUE.

Mechanism (the same primitives as dedup, retargeted from field-NAMES to `other` fact SEMANTICS):
  1. collect every `other`/`description` fact (case, qualifier, value) — the un-homed novelty;
  2. embed each fact's text with BGE-M3;
  3. greedy incremental concept-clustering (looser τ than synonym-dedup: these are different VALUES of
     one concept, e.g. two different statutes, not two spellings of one word);
  4. a cluster spanning >= PROMOTE_HEAD_N distinct cases is a MINTABLE head — one LLM call names it
     (a single snake_case noun) from example values;
  5. report the mint candidates: proposed head, distinct-case support, examples.

This is a read-only spike on data we did NOT author — it proves the premise before the architecture
(the per-tenant grammar extension + backfill) is built. Run AFTER the GPU is free (BGE + Ollama).

Usage:  EVAL_DATASET=cfpb uv run --group embed python eval/spike_head_minting.py [tau]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from _dataset import DATASET
from _dataset import EXTRACTIONS as _FIX

from app.backends.local.embed_bge import BGEEmbedding
from app.backends.local.llm_ollama import OllamaLLM
from app.extract.head_nouns import HEAD_NOUNS
from app.schema.promote import PROMOTE_HEAD_N

# Concept-cluster threshold: different values of ONE concept (two statutes) sit further apart than two
# spellings of one word, so this is looser than the 0.85 synonym-merge τ. Tunable (CLI arg).
DEFAULT_TAU = 0.55

_NAME_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"head": {"type": "string"}},
    "required": ["head"],
}


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def _name_cluster(llm: OllamaLLM, examples: list[str]) -> str:
    """One LLM call: propose a SINGLE snake_case head noun for a cluster of facts, distinct from the
    existing seed heads (so we mint a genuinely-new column, not a synonym of a seed)."""
    sample = "; ".join(f'"{e}"' for e in examples[:6])
    prompt = (
        "These facts were extracted from customer complaints and did not fit any existing column. "
        "They form ONE new kind of thing. Propose a SINGLE snake_case noun naming the column that "
        "would hold them all (e.g. regulation, warranty, symptom). It MUST NOT be any of these "
        f"existing columns: {', '.join(HEAD_NOUNS)}.\nFacts: {sample}\n"
        'Answer JSON: {"head": "<one snake_case noun>"}.'
    )
    try:
        raw = await llm.complete(prompt, schema=_NAME_SCHEMA)
        head = str(json.loads(raw).get("head", "")).strip().lower().replace(" ", "_")
        return head or "unnamed"
    except Exception:  # noqa: BLE001
        return "unnamed"


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    tau = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TAU
    cases = [
        json.loads(line)
        for line in Path(_FIX).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # Collect un-homed novelty: (case_index, text) for every other/description fact.
    facts: list[tuple[int, str]] = []
    for i, c in enumerate(cases):
        for a in c.get("attributes", []):
            if a.get("head") in ("other", "description"):
                q = a.get("qualifier") or ""
                v = a.get("value") or ""
                text = f"{q} {v}".strip()
                if text:
                    facts.append((i, text))
    print(f"dataset={DATASET}  other/description facts={len(facts)}  cluster_tau={tau}")

    embedder = BGEEmbedding()
    vecs = await embedder.embed([t for _i, t in facts])

    # Greedy incremental concept-clustering: each fact joins the nearest existing centroid above τ,
    # else opens a new cluster. Centroid = running mean (cheap, order-sensitive — fine for a spike).
    centroids: list[list[float]] = []
    members: list[list[int]] = []  # cluster -> fact indices
    for fi, v in enumerate(vecs):
        best, best_sim = -1, -1.0
        for ci, cen in enumerate(centroids):
            s = _cos(list(v), cen)
            if s > best_sim:
                best, best_sim = ci, s
        if best_sim >= tau:
            members[best].append(fi)
            n = len(members[best])
            centroids[best] = [
                (c * (n - 1) + x) / n for c, x in zip(centroids[best], v, strict=True)
            ]
        else:
            centroids.append(list(v))
            members.append([fi])

    # A cluster is a MINT candidate iff it spans >= PROMOTE_HEAD_N DISTINCT cases (recurrence, not one
    # chatty case). Name each candidate with one LLM call.
    llm = OllamaLLM()
    candidates = []
    for mem in members:
        distinct_cases = {facts[fi][0] for fi in mem}
        if len(distinct_cases) >= PROMOTE_HEAD_N:
            examples = [facts[fi][1] for fi in mem]
            name = await _name_cluster(llm, examples)
            candidates.append((name, len(distinct_cases), len(mem), examples[:5]))

    candidates.sort(key=lambda x: -x[1])
    print(f"\n===== MINT CANDIDATES (cluster spans >= {PROMOTE_HEAD_N} distinct cases) =====")
    if not candidates:
        print(
            "  NONE — no other/description cluster recurs enough to mint. Emergence has no fuel here."
        )
    for name, ncases, nfacts, ex in candidates:
        print(f"  MINT head '{name}'  ({ncases} distinct cases, {nfacts} facts)")
        for e in ex:
            print(f"       - {e[:60]}")
    total_clusters = len(members)
    singletons = sum(1 for m in members if len({facts[fi][0] for fi in m}) < PROMOTE_HEAD_N)
    print(
        f"\nclusters total={total_clusters}  mintable={len(candidates)}  "
        f"below-threshold={singletons}  (the below-threshold stay in `other`, the promotion bag)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
