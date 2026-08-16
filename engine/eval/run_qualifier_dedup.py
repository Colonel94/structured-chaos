"""QUALIFIER-SPACE dedup — the first end-to-end run of the synonym-merge moat, MEASURED on real data
we did NOT author (CLAUDE.md §10-Q3). This is the "<5% duplicate/synonym fields" half of the §4
convergence gate that has never been measured.

Under Path A the emergent COLUMN is the head (closed vocab → ~0 head duplicates by construction — the
cheap, substance-free way to "pass" this gate, §10). The real open invention site is the QUALIFIER,
and a duplicate COLUMN can only appear when two SYNONYM qualifiers each recur enough to promote into
their own variant column under the same head (``overdraft_fee`` and ``overdraft_charge`` both promoting
as separate columns). So dedup must run in qualifier-space, ANCHORED BY HEAD (a qualifier under ``fee``
never merges with one under ``date``), BEFORE qualifier-promotion splits columns.

This harness runs that exact mechanism — same BGE-M3 embeddings, same τ gate, same gray-band
``_adjudicate`` LLM call as ``app/schema/dedup.py`` (imported, not reimplemented) — over the real
extracted qualifier variants, scoped within each head, incrementally in first-seen order. It reports:

- the RAW distinct-variant count (the no-dedup dumb baseline — every variant its own column);
- how many variants MERGE (are synonyms) → the qualifier-space duplicate rate;
- the PROMOTION-eligible duplicate rate — the true §4 gate under Path A: of the variants that reach
  promotion support (≥ M distinct cases at the CANONICAL level after merge), how many are duplicate
  columns. At small n few/no qualifiers promote, so this states honestly whether the gate is even
  stressed yet rather than reporting a trivial 0%;
- the actual synonym pairs collapsed (proof the mechanism fires) and near-misses NOT merged (proof it
  fails safe — over-merge is worse than a duplicate, §3);
- how many "qualifiers" are really per-case VALUES leaked into the slot (task 4's separate concern):
  a LOW duplicate rate driven by value-leakage is NOT a clean schema — flagged, not spun.

Usage:  EVAL_DATASET=cfpb uv run --group embed python eval/run_qualifier_dedup.py
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from pathlib import Path

from _dataset import DATASET
from _dataset import EXTRACTIONS as _FIX

# EVAL_DATASET=combined stitches cfpb+multidomain into ONE tenant so the run clears the ≥200-case §4
# threshold (216) and the column-duplicate gate can actually be stressed (a real tenant sees a mixed
# case stream, so this is the harder, more honest convergence test — not a cherry-picked single domain).
_FIXDIR = Path(_FIX).resolve().parent
_COMBINED = DATASET == "combined"

from app.backends.local.embed_bge import BGEEmbedding
from app.backends.local.llm_ollama import OllamaLLM
from app.schema.dedup import ADMIT_TAU, MERGE_TAU, _adjudicate, _name_text
from app.schema.promote import PROMOTE_QUALIFIER_M

# A duplicate variant = one that merged into an existing canonical under its head.
_MERGE_METHODS = {"merge", "llm_merge"}


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _load() -> list[dict[str, object]]:
    files = (
        [_FIXDIR / "cfpb_extractions.jsonl", _FIXDIR / "multidomain_extractions.jsonl"]
        if _COMBINED
        else [Path(_FIX)]
    )
    out: list[dict[str, object]] = []
    for fp in files:
        out += [json.loads(ln) for ln in fp.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return out


async def main() -> int:
    cases = _load()

    # Per head: distinct qualifiers, first-seen order, support (distinct cases attesting the composite),
    # and up to two example values (context for the gray-band adjudicator). Bare-head (qualifier=None)
    # variants ARE the head column itself, not a qualifier split — excluded from qualifier dedup.
    first_seen: dict[str, dict[str, int]] = defaultdict(dict)
    support: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    seq = 0
    for c in cases:
        seen_in_case: set[tuple[str, str]] = set()
        for a in c.get("attributes", []):  # type: ignore[union-attr]
            head = str(a.get("head") or "")
            qual = a.get("qualifier")
            if not head or not qual:
                continue
            q = str(qual)
            key = (head, q)
            if key not in seen_in_case:  # support = DISTINCT cases, not raw occurrences
                support[head][q] += 1
                seen_in_case.add(key)
            if q not in first_seen[head]:
                first_seen[head][q] = seq
                seq += 1
            val = str(a.get("value") or "")
            if val and len(examples[head][q]) < 2:
                examples[head][q].append(val)

    heads = sorted(first_seen)
    total_variants = sum(len(first_seen[h]) for h in heads)
    print(f"dataset={DATASET}  cases={len(cases)}  heads_with_qualifiers={len(heads)}")
    print(f"RAW distinct qualifier variants (no-dedup baseline = column count): {total_variants}")

    embedder = BGEEmbedding()
    llm = OllamaLLM()

    # Embed every distinct qualifier ONCE (batched). We embed the QUALIFIER text alone — the head is the
    # fixed anchor, so within a head the shared head token would only inflate similarity and risk
    # over-merging genuinely-distinct qualifiers (annual_fee vs overdraft_fee). Values-as-context go to
    # the adjudicator, not the embedding.
    flat = [(h, q) for h in heads for q in first_seen[h]]
    vecs = await embedder.embed([_name_text(q) for _h, q in flat])
    emb: dict[tuple[str, str], list[float]] = {
        hq: list(v) for hq, v in zip(flat, vecs, strict=True)
    }

    methods: Counter[str] = Counter()
    canonical_of: dict[tuple[str, str], str] = {}
    merges: list[tuple[str, str, str, float, str]] = []  # (head, from_q, into_q, sim, method)
    near_miss: list[tuple[str, str, str, float]] = []  # gray-band NOT merged (fail-safe proof)

    for head in heads:
        canon_qs: list[str] = []  # canonical qualifiers under THIS head, first-seen order
        for q in sorted(first_seen[head], key=lambda x: first_seen[head][x]):
            v = emb[(head, q)]
            best_q, best_sim = None, -1.0
            for cq in canon_qs:  # compare ONLY within the same head (the closed-head anchor)
                s = _cos(v, emb[(head, cq)])
                if s > best_sim:
                    best_q, best_sim = cq, s
            if best_q is None:
                canonical_of[(head, q)] = q
                canon_qs.append(q)
                methods["seed"] += 1
                continue
            if best_sim >= MERGE_TAU:
                method = "merge"
            elif best_sim < ADMIT_TAU:
                method = "admit_new"
            else:
                same = await _adjudicate(
                    llm,
                    f"{q} {head}",
                    f"{best_q} {head}",
                    values_a=examples[head][q],
                    values_b=examples[head][best_q],
                )
                method = "llm_merge" if same else "llm_admit"
            methods[method] += 1
            if method in _MERGE_METHODS:
                canonical_of[(head, q)] = canonical_of[(head, best_q)]
                merges.append((head, q, best_q, best_sim, method))
            else:
                canonical_of[(head, q)] = q
                canon_qs.append(q)
                if method == "llm_admit":
                    near_miss.append((head, q, best_q, best_sim))

    # Canonical variant count after dedup, and support rolled up to the canonical (merged aliases sum).
    canon_support: dict[tuple[str, str], int] = Counter()
    for (head, q), sup in ((k, support[k[0]][k[1]]) for k in canonical_of):
        canon_support[(head, canonical_of[(head, q)])] += sup
    canonicals = set(canonical_of.values())
    n_canon = len({(h, canonical_of[(h, q)]) for (h, q) in canonical_of})
    merged = len(merges)
    dup_rate = merged / total_variants if total_variants else 0.0

    print("\n===== QUALIFIER-SPACE DEDUP (first live run of the moat) =====")
    print(f"raw distinct variants     : {total_variants}")
    print(f"canonical variants (deduped): {n_canon}")
    print(f"duplicates merged         : {merged}")
    print(f"QUALIFIER duplicate rate  : {dup_rate:.1%}   (merged / raw distinct variants)")
    print(f"methods                   : {dict(methods)}")

    # The TRUE §4 gate under Path A: duplicate/synonym COLUMNS < 5%. A promoted COLUMN is a canonical
    # qualifier whose POOLED (post-merge) support reaches M. Two measures, both honest:
    #   (1) pre-merge  : how many RAW variants would promote if we never deduped (synonyms split their
    #                    support, so this is usually LOWER — dedup enables promotion by pooling);
    #   (2) post-merge : how many CANONICAL columns promote after synonym-merge (the real Path-A schema).
    # Duplicate columns = promoted canonicals that are still pairwise synonyms (a dedup MISS) under one
    # head — those are the §4 "<5% synonym fields". By construction dedup collapses synonyms, so this is
    # a check on dedup's misses, not on the raw sprawl.
    promo_raw = [
        (h, q) for h in heads for q in first_seen[h] if support[h][q] >= PROMOTE_QUALIFIER_M
    ]
    max_sup = max(canon_support.values()) if canon_support else 0
    ge = {k: sum(1 for v in canon_support.values() if v >= k) for k in (2, 3, 4, PROMOTE_QUALIFIER_M)}
    print(
        f"\n-- distance to the qualifier-promotion gate --\n"
        f"  max qualifier support (post-merge): {max_sup} case(s)   canonical variants recurring "
        f">=2:{ge[2]} >=3:{ge[3]} >=4:{ge[4]} >={PROMOTE_QUALIFIER_M}:{ge[PROMOTE_QUALIFIER_M]}"
    )
    promo_canon = sorted(c for c in canon_support if canon_support[c] >= PROMOTE_QUALIFIER_M)
    print("\n-- the actual §4 gate under Path A (duplicate COLUMNS, not data) --")
    print(
        f"  promoting WITHOUT dedup (raw variants >={PROMOTE_QUALIFIER_M}): {len(promo_raw)}\n"
        f"  promoting WITH dedup (canonical columns >={PROMOTE_QUALIFIER_M}): {len(promo_canon)}"
    )
    if len(promo_canon) > len(promo_raw):
        print(
            "  -> dedup ENABLED promotion: synonym-merge pooled support that was otherwise fragmented "
            "below the gate (the mechanism's real value at this n, not duplicate-prevention)."
        )
    if len(promo_canon) < 2:
        print(
            f"  duplicate COLUMNS: unmeasurable — only {len(promo_canon)} column promotes even at "
            f"n={len(cases)}, so the <5% synonym-column gate has ~nothing to bite on yet. Reporting a "
            "0% pass here would be trivial/substance-free (§10). The 200-case gate needs a corpus where "
            "qualifiers actually recur; these are dominated by hapax values (hygiene note below)."
        )
        for (h, c) in promo_canon:
            print(f"    promoted column: [{h}] {c!r}  (support {canon_support[(h, c)]})")
    else:
        # ≥2 promoted canonicals: check for dedup-missed synonym pairs UNDER THE SAME HEAD.
        dup = 0
        by_head: dict[str, list[str]] = defaultdict(list)
        for h, c in promo_canon:
            by_head[h].append(c)
        for h, cs in by_head.items():
            for i in range(len(cs)):
                for j in range(i + 1, len(cs)):
                    if _cos(emb[(h, cs[i])], emb[(h, cs[j])]) >= MERGE_TAU:
                        dup += 1
                        print(f"    DUP COLUMN [{h}] {cs[i]!r} ~ {cs[j]!r} (dedup miss)")
        print(
            f"  duplicate COLUMNS (dedup misses among promoted): {dup}/{len(promo_canon)} = "
            f"{dup / len(promo_canon):.1%}   (<5% = §4 gate PASS)"
        )

    if merges:
        print(f"\n-- synonym pairs COLLAPSED (proof it fires), showing up to 25 of {merged} --")
        for head, frm, into, sim, method in sorted(merges, key=lambda x: -x[3])[:25]:
            print(f"  [{head}] {frm!r} -> {into!r}   sim={sim:.3f} ({method})")
    if near_miss:
        print(f"\n-- gray-band NOT merged (fail-safe, over-merge is worse than a dup) up to 15 --")
        for head, q, other, sim in sorted(near_miss, key=lambda x: -x[3])[:15]:
            print(f"  [{head}] {q!r} kept vs {other!r}   sim={sim:.3f}")

    # Honesty check (task 4 adjacency): a LOW duplicate rate can mean a clean schema OR that the
    # qualifier slot is holding per-case VALUES (which are distinct by nature and SHOULD NOT merge).
    # Flag the value-leakage pressure so a low rate is never spun as "schema is clean".
    def _looks_like_value(q: str) -> bool:
        toks = q.split("_")
        return (
            any(t.isdigit() for t in toks)
            or "xxxx" in q
            or len(toks) >= 4  # long clausal qualifier = leaked value/description
        )

    leaky = [(h, q) for h in heads for q in first_seen[h] if _looks_like_value(q)]
    print("\n-- schema-hygiene note (task 4 adjacency, NOT the dedup gate) --")
    print(
        f"variants that look like leaked VALUES (digits/xxxx/clausal): {len(leaky)}/{total_variants}"
        f" = {len(leaky) / total_variants:.0%}"
    )
    print(
        "  a low duplicate rate driven by value-leakage is NOT a clean schema — it means values are"
        " landing in the qualifier slot (a 2nd invention site). Measured separately by qualifier"
        " grounding (task 4)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
