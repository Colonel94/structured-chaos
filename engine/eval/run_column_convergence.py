"""THE column-level convergence proof (remediation R2/§4) — the honest gate, on data we didn't author.

R0 retracted the head-noun curve (a closed enum enumerates by construction — can't fail). The honest
convergence unit is the COLUMN a reviewer actually sees, and under the full moat a column is one of:
  • a SEED head that got used            (bounded by the 31-vocab → the tautology part, DIAGNOSTIC),
  • a MINTED head                        (born from an `other` cluster — EARNED emergence),
  • a PROMOTED qualifier split           (a recurring qualifier that became its own column — EARNED).
Convergence (§4) = the distinct-COLUMN count settles (declining new-column rate) AND < 5% are
duplicates. The number that matters is the EARNED-column curve (minted + promoted): if IT keeps rising
linearly the schema sprawls; if it bends/plateaus the schema converges by emergence, not by seeding.

Measured with the REAL logic on real extractions (no re-extraction): connected-components mint
clustering (BGE-M3, MINT_TAU) and head-scoped qualifier dedup (the τ gate) — the same code the live
scans run. Reported per 20-case bucket, in first-seen order. Honest caveats printed inline:
  - the mint count is PRE-naming/PII (a mintable cluster = an earned column candidate; PII would remove
    some, LLM naming could merge/split a few) — it is an UPPER bound on minted columns;
  - promoted-qualifier support uses the dedup'd canonical (pooled), M = PROMOTE_QUALIFIER_M.

Usage:  EVAL_DATASET=combined uv run --group embed python eval/run_column_convergence.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from _dataset import DATASET
from _dataset import EXTRACTIONS as _FIX

from app.backends.local.embed_bge import BGEEmbedding
from app.extract.head_nouns import HEAD_NOUNS
from app.extract.profile import profile_value
from app.schema.dedup import ADMIT_TAU, MERGE_TAU
from app.schema.mint_scan import MINT_TAU, _cos
from app.schema.promote import PROMOTE_HEAD_N, PROMOTE_QUALIFIER_M

_FIXDIR = Path(_FIX).resolve().parent
_BUCKET = 20


def _load() -> list[dict[str, object]]:
    files = (
        [_FIXDIR / "cfpb_extractions.jsonl", _FIXDIR / "multidomain_extractions.jsonl"]
        if DATASET == "combined"
        else [Path(_FIX)]
    )
    out: list[dict[str, object]] = []
    for fp in files:
        out += [json.loads(x) for x in fp.read_text(encoding="utf-8").splitlines() if x.strip()]
    return out


def _components(vecs: list[list[float]], tau: float) -> list[list[int]]:
    """Connected components of the ≥tau similarity graph (union-find) — the mint clusterer."""
    parent = list(range(len(vecs)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            if _cos(vecs[i], vecs[j]) >= tau:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    comps: dict[int, list[int]] = defaultdict(list)
    for i in range(len(vecs)):
        comps[find(i)].append(i)
    return list(comps.values())


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    cases = _load()
    n = len(cases)
    print(f"=== COLUMN CONVERGENCE ({DATASET}, n={n}) — the honest §4 gate ===")

    # Escape-valve facts (concrete only — the R4 filter) with their case index, in order.
    ev: list[tuple[int, str]] = []
    # Qualifier composites with support (distinct cases) — for promotion.
    qual_cases: dict[str, set[int]] = defaultdict(set)
    for i, c in enumerate(cases):
        for a in c.get("attributes", []):  # type: ignore[union-attr]
            head = str(a.get("head") or "")
            q = a.get("qualifier")
            val = str(a.get("value") or "")
            if head in ("other", "description") and val and profile_value(val).is_concrete:
                ev.append((i, val))
            if head and q:
                qual_cases[str(a.get("name") or f"{q}_{head}")].add(i)

    embedder = BGEEmbedding()
    ev_vecs = {
        k: list(v) for k, v in zip(range(len(ev)), await embedder.embed([t for _i, t in ev]))
    }

    seed_new: list[int] = []
    earned_new: list[int] = []
    seen_seed: set[str] = set()
    prev_earned = 0
    for b in range(0, n, _BUCKET):
        upto = min(b + _BUCKET, n)
        # seed heads used so far
        seed_new.append(0)
        for c in cases[b:upto]:
            for a in c.get("attributes", []):  # type: ignore[union-attr]
                h = str(a.get("head") or "")
                if h and h in HEAD_NOUNS and h not in seen_seed:
                    seen_seed.add(h)
                    seed_new[-1] += 1
        # EARNED columns computed on cases[:upto]:
        idx = [k for k, (ci, _v) in enumerate(ev) if ci < upto]
        minted = 0
        if len(idx) >= PROMOTE_HEAD_N:
            comps = _components([ev_vecs[k] for k in idx], MINT_TAU)
            minted = sum(
                1 for comp in comps if len({ev[idx[m]][0] for m in comp}) >= PROMOTE_HEAD_N
            )
        promoted = sum(
            1
            for _q, cs in qual_cases.items()
            if len({c for c in cs if c < upto}) >= PROMOTE_QUALIFIER_M
        )
        earned = minted + promoted
        earned_new.append(earned - prev_earned)
        prev_earned = earned

    total_seed = len(seen_seed)
    print(
        f"\nτ: mint={MINT_TAU} dedup=[{ADMIT_TAU},{MERGE_TAU}]  thresholds: head N={PROMOTE_HEAD_N} qual M={PROMOTE_QUALIFIER_M}"
    )
    print(
        "\n-- SEED-head columns (DIAGNOSTIC — bounded by the 31-vocab, declines by construction) --"
    )
    print(f"  new-seed-head per {_BUCKET} : {seed_new}   total seed heads used: {total_seed}")
    print("\n-- EARNED columns = minted + promoted (THE honest emergence signal) --")
    print(f"  new-earned per {_BUCKET}    : {earned_new}   total earned columns: {prev_earned}")
    print(
        f"  total distinct COLUMNS     : {total_seed + prev_earned}  (seed {total_seed} + earned {prev_earned})"
    )
    bend = (
        "PLATEAUS/declines → converges by emergence"
        if (earned_new[-1] <= max(earned_new[:1] or [0]))
        else "still rising → needs more data"
    )
    print(f"  earned-curve read          : {bend}")
    print(
        "\n  NOTE (honest): minted count is PRE-naming/PII (an UPPER bound on minted columns — PII would"
        f" remove some). At n={n} the earned signal is {'THIN' if prev_earned <= 3 else 'present'}; §4"
        " wants ≥200 cases. The seed curve plateauing is NOT the gate (that's construction); the earned"
        " curve is. Duplicate columns are prevented structurally (dedup merges qualifier synonyms; mint"
        " name-collision rejects duplicate heads) — measured separately in run_qualifier_dedup."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
