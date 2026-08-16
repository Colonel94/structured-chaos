"""Head-minting — the emergent-column BIRTH mechanism (remediation, the R2 pivot).

R2 proved convergence is a COLUMN-level property and that the composite curve can't bend because
qualifiers are data — so the moat's real claim ("specialisation is emergent, never seeded") lives or
dies on whether NEW heads can EMERGE. This scan is that mechanism: it clusters the un-homed facts in
the escape valve (`other`/`description`, kept clean by the R4 profiler), and when a cluster recurs
across ≥ ``PROMOTE_HEAD_N`` distinct cases it MINTS a new head — an LLM names it, and it is registered
so it EXTENDS the tenant's extraction vocabulary. A `regulation` column emerging from CFPB, a `symptom`
column from vehicle complaints, with zero configuration.

Same primitives as dedup, retargeted from field-NAMES to fact SEMANTICS: BGE-M3 embeddings + greedy
incremental clustering — but a LOOSER threshold, because two members of one concept (two different
statutes) sit further apart than two spellings of one qualifier. Minting fails SAFE: a cluster below
the recurrence floor stays in `other` (the bag), and a proposed name colliding with an existing head is
rejected (no duplicate columns). Off the hot path (a periodic scan), AFTER dedup, BEFORE promote.

Factored so the per-tenant logic is unit-testable with fakes; ``queue.mint_scan`` injects real backends
and enqueues re-extraction of the affected cases (the minted head re-homes history via the vocab-aware
idempotency key).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..backends.interfaces import EmbeddingBackend, LLMBackend
from ..extract.head_nouns import HEAD_NOUNS, normalise_token
from ..extract.profile import profile_value
from ..obs.logging import get_logger
from ..store import api
from ..store.db import SessionFactory, admin_session, tenant_session
from .promote import PROMOTE_HEAD_N

log = get_logger(__name__)

# Concept-cluster threshold: members are different VALUES of one concept, not synonyms of one word, so
# this is looser than the 0.85 synonym-merge τ. Tuned on the real `other` distribution (spike 2026-08-17b).
MINT_TAU = 0.55

_NAME_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"head": {"type": "string"}},
    "required": ["head"],
}

# Names that must never be minted (would collide with the escape valve or be meaningless).
_FORBIDDEN = frozenset({"other", "description", "unnamed", "misc", "miscellaneous", ""})


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def _name_cluster(
    llm: LLMBackend, examples: list[str], existing: frozenset[str]
) -> str | None:
    """One LLM call: propose a single snake_case head naming the cluster, distinct from every existing
    head. Returns the normalised name, or None if it collides / is forbidden / the call fails (fail
    safe → don't mint, the facts stay in `other`)."""
    sample = "; ".join(f'"{e}"' for e in examples[:6])
    prompt = (
        "These facts were extracted from customer complaints and did not fit any existing column, but "
        "they are all the SAME kind of thing. Propose a SINGLE snake_case noun naming the column that "
        "would hold them all (e.g. regulation, warranty, symptom, coverage). It MUST NOT be any of "
        f"these existing columns: {', '.join(sorted(existing))}.\nFacts: {sample}\n"
        'Answer JSON: {"head": "<one snake_case noun>"}.'
    )
    try:
        raw = await llm.complete(prompt, schema=_NAME_SCHEMA)
        name = normalise_token(str(json.loads(raw).get("head", "")))
    except Exception:  # noqa: BLE001 — a naming failure must not mint garbage
        return None
    if name in _FORBIDDEN or name in existing:
        return None
    return name


async def mint_for_tenant(
    session: Session, *, embedder: EmbeddingBackend, llm: LLMBackend, tau: float = MINT_TAU
) -> list[tuple[str, int, list[UUID]]]:
    """Cluster this tenant's escape-valve facts and mint a head for each cluster recurring across ≥
    ``PROMOTE_HEAD_N`` distinct cases. Returns ``(head, support, affected_case_ids)`` per minted head —
    the caller re-extracts the affected cases so the new column re-homes history. Idempotent-ish: a
    re-mint of the same cluster upserts the same head (register is an upsert) and the affected cases,
    already re-extracted under the vocab-aware key, are a no-op on the second pass."""
    facts = [(cid, v) for cid, v in api.list_escape_valve_facts(session) if profile_value(v).is_concrete]
    if len(facts) < PROMOTE_HEAD_N:
        return []

    vecs = await embedder.embed([v for _c, v in facts])
    centroids: list[list[float]] = []
    members: list[list[int]] = []
    for i, v in enumerate(vecs):
        best, best_sim = -1, -1.0
        for ci, cen in enumerate(centroids):
            s = _cos(list(v), cen)
            if s > best_sim:
                best, best_sim = ci, s
        if best_sim >= tau:
            members[best].append(i)
            n = len(members[best])
            centroids[best] = [(c * (n - 1) + x) / n for c, x in zip(centroids[best], v, strict=True)]
        else:
            centroids.append(list(v))
            members.append([i])

    existing = frozenset(normalise_token(h) for h in HEAD_NOUNS) | frozenset(
        api.list_minted_heads(session)
    )
    minted: list[tuple[str, int, list[UUID]]] = []
    # Largest clusters first, so the strongest concepts claim their names before smaller ones.
    for mem in sorted(members, key=len, reverse=True):
        cases = sorted({facts[i][0] for i in mem})
        if len(cases) < PROMOTE_HEAD_N:
            continue
        examples = [facts[i][1] for i in mem][:6]
        name = await _name_cluster(llm, examples, existing)
        if name is None:
            continue
        api.register_minted_head(
            session, head=name, support=len(cases), source=f"other_cluster: {examples[:3]}"
        )
        existing = existing | {name}  # two clusters can't mint the same name in one scan
        minted.append((name, len(cases), cases))
        log.info("mint.head", head=name, support=len(cases))
    return minted


async def scan_and_mint(
    *,
    embedder: EmbeddingBackend,
    llm: LLMBackend,
    tenant_ids: list[UUID] | None = None,
    factory: sessionmaker[Session] | None = None,
) -> dict[UUID, list[tuple[str, int, list[UUID]]]]:
    """Mint heads across tenants (all by default). Returns per-tenant minted ``(head, support, cases)``
    — the caller re-extracts the affected cases to re-home them into the new columns."""
    factory = factory or SessionFactory
    if tenant_ids is None:
        with admin_session() as adm:
            tenant_ids = api.list_tenant_ids(adm)
    out: dict[UUID, list[tuple[str, int, list[UUID]]]] = {}
    for tid in tenant_ids:
        with tenant_session(tid, factory=factory) as s:
            out[tid] = await mint_for_tenant(s, embedder=embedder, llm=llm)
    return out
