"""The convergence PROOF (STAGE 3+4) — run the real dedup over the real 120-case extraction baseline
and measure whether the emergent schema converges. On data we did NOT author (CLAUDE.md §10-Q3).

Reuses ``fixtures/cfpb_extractions.jsonl`` (the baseline extraction — no 12-min re-extraction), then
runs the PRODUCTION dedup (BGE-M3 embeddings in pgvector + τ=0.85/0.70 gate + gray-band LLM
adjudication) incrementally in case order. Reports the canonical schema size vs the raw 378, the
new-canonical-per-bucket curve (compare to the flat raw baseline [48,52,74,64,77,63]), the reduction
ratio, and the promoted (recurrence ≥4) fields.

Usage:  uv run --group embed python eval/run_convergence.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path

from app.backends.local.embed_bge import BGEEmbedding
from app.backends.local.llm_ollama import OllamaLLM
from app.schema.dedup import _name_text, dedup_field
from app.store import api
from app.store.db import admin_session, tenant_session

_FIX = Path(__file__).resolve().parent / "fixtures" / "cfpb_extractions.jsonl"
_BUCKET = 20


def _hash(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()


async def main() -> int:
    cases = [json.loads(line) for line in _FIX.read_text(encoding="utf-8").splitlines() if line]
    # First-seen order + support (distinct cases attesting each raw field).
    first_seen: dict[str, int] = {}
    support: Counter[str] = Counter()
    for i, c in enumerate(cases):
        for name in dict.fromkeys(c["emergent"]):  # dedup within a case
            support[name] += 1
            if name not in first_seen:
                first_seen[name] = i
    unique = sorted(first_seen, key=lambda n: first_seen[n])
    print(f"cases={len(cases)}  raw distinct emergent fields={len(unique)}")

    # Batch-embed every unique field name once (BGE-M3).
    embedder = BGEEmbedding()
    llm = OllamaLLM()
    vecs = await embedder.embed([_name_text(n) for n in unique])
    emb = dict(zip(unique, vecs, strict=True))
    print("embedded all field names; running dedup...")

    with admin_session() as s:
        tid = api.create_tenant(s, "convergence-proof")

    canonical_of: dict[str, str] = {}
    methods: Counter[str] = Counter()
    new_canon_per_bucket = [0] * ((len(cases) + _BUCKET - 1) // _BUCKET)
    with tenant_session(tid) as s:
        for name in unique:
            h = _hash(name)
            api.register_emergent_field(s, field_name=name, field_name_hash=h)
            canon, method, _sim = await dedup_field(
                s, field_name=name, field_name_hash=h, llm=llm, embedding=emb[name]
            )
            canonical_of[name] = canon
            methods[method] += 1
            if method in ("seed", "admit_new", "llm_admit"):  # a NEW canonical was created
                new_canon_per_bucket[first_seen[name] // _BUCKET] += 1

    canon_hashes = set(canonical_of.values())
    # Support per canonical = distinct cases attesting ANY field in its alias group.
    canon_support: Counter[str] = Counter()
    hash_to_canon = {_hash(n): canonical_of[n] for n in unique}
    for c in cases:
        hit: set[str] = {
            hash_to_canon[_hash(n)] for n in c["emergent"] if _hash(n) in hash_to_canon
        }
        for ch in hit:
            canon_support[ch] += 1
    promoted = sorted((canon_support[ch], ch) for ch in canon_hashes if canon_support[ch] >= 4)
    hash_to_name = {_hash(n): n for n in unique}

    print("\n===== CONVERGENCE PROOF (real dedup over real CFPB baseline) =====")
    print(f"raw distinct fields      : {len(unique)}")
    print(f"canonical fields (deduped): {len(canon_hashes)}")
    print(f"reduction                : {1 - len(canon_hashes) / len(unique):.0%}")
    print(
        f"new-canonical per {_BUCKET}   : {new_canon_per_bucket}   (baseline raw was [48,52,74,64,77,63])"
    )
    print(f"dedup methods            : {dict(methods)}")
    print(f"promoted (support>=4)    : {len(promoted)} fields")
    for sup, ch in sorted(promoted, reverse=True)[:20]:
        print(f"    [{sup:2d} cases] {hash_to_name.get(ch, ch[:10])}")

    # --- Concept-family signal (the altitude where the moat actually converges). -----------------
    # 90% of raw field NAMES are hapax compounds ({qualifier}_{headnoun}: pension_amount,
    # deposit_date_2). The full-NAME curve is therefore flat — but the underlying CONCEPT space
    # (the head noun: amount / date / status) converges. Name-level dedup cannot and MUST NOT
    # collapse distinct compounds (deposit_date vs dispute_date are different columns — over-merge
    # is worse than a duplicate, §3). So we report the concept curve alongside, crude head-noun
    # heuristic = last token that is neither a digit nor an ordinal index.
    _ORD = {"first", "second", "third", "1", "2", "3"}

    def _head(n: str) -> str:
        toks = [t for t in n.split("_") if t and not t.isdigit() and t not in _ORD]
        return toks[-1] if toks else n

    seen_head: set[str] = set()
    head_per_bucket = [0] * len(new_canon_per_bucket)
    head_support: Counter[str] = Counter()
    for i, c in enumerate(cases):
        for n in dict.fromkeys(c["emergent"]):
            head_support[_head(n)] += 1
            h = _head(n)
            if h not in seen_head:
                seen_head.add(h)
                head_per_bucket[i // _BUCKET] += 1
    print("\n----- concept-family signal (head-noun heuristic) -----")
    print(f"distinct concepts        : {len(seen_head)}   (vs {len(unique)} raw names)")
    print(
        f"new-concept per {_BUCKET}     : {head_per_bucket}   <- THIS is the curve that should bend"
    )
    print(f"top concepts             : {dict(head_support.most_common(12))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
