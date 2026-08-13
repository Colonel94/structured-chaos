"""Emergent-schema dedup / canonicalisation — the self-converging moat, STAGE 3 (EDD §6.2).

Each distinct emergent field name is embedded (BGE-M3, 1024-d) and compared, in pgvector, to the
nearest existing *canonical* field. The two-threshold gate decides:

    cosine ≥ 0.85           → MERGE   (a synonym of that canonical → becomes its alias)
    cosine < 0.70           → ADMIT   (a genuinely new field → its own canonical)
    0.70 ≤ cosine < 0.85    → ONE LLM adjudication ("same attribute? y/n")

The asymmetric gap + gray-band adjudication follow the design rule that **over-merge (lossy collapse)
is more expensive than a duplicate** — so the adjudicator, and any error, fail SAFE to *not merging*.
This is what turns the raw 378-field sprawl into a converging schema. Incremental: fields are
processed in first-seen order, growing the canonical set; new fields only ever compare against
canonicals (never aliases), so there is no chain-merge.

Thresholds are the paper's numbers (Jonnalagedda et al. 2606.05415), hardcoded here and tuned on a
scored set — never guessed in prod (EDD §6.2).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy.orm import Session

from ..backends.interfaces import EmbeddingBackend, LLMBackend
from ..obs.logging import get_logger
from ..store import api

log = get_logger(__name__)

MERGE_TAU = 0.85  # ≥ → merge (synonym of an existing canonical)
ADMIT_TAU = 0.70  # < → admit as a new canonical; [0.70, 0.85) → LLM adjudicates

_ADJUDICATE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"same": {"type": "boolean"}},
    "required": ["same"],
}


def _name_text(field_name: str) -> str:
    """Embed the human-readable form of the snake_case name (``charged_amount`` → "charged amount")."""
    return field_name.replace("_", " ")


async def _adjudicate(llm: LLMBackend, name_a: str, name_b: str) -> bool:
    """One LLM call for the gray band: are these two field names the SAME attribute? Fails safe to
    False (do not merge) on any error — a duplicate is cheaper than a lossy over-merge."""
    prompt = (
        "Do these two data-field names denote the SAME attribute (synonyms of one field), or "
        "DIFFERENT attributes?\n"
        f'A: "{name_a}"\nB: "{name_b}"\n'
        'Answer JSON: {"same": true} only if they are the same attribute, else {"same": false}.'
    )
    try:
        raw = await llm.complete(prompt, schema=_ADJUDICATE_SCHEMA)
        verdict = json.loads(raw)
        return isinstance(verdict, dict) and verdict.get("same") is True
    except Exception:  # noqa: BLE001 — never over-merge on a backend/parse failure
        return False


async def dedup_field(
    session: Session,
    *,
    field_name: str,
    field_name_hash: str,
    llm: LLMBackend,
    embedder: EmbeddingBackend | None = None,
    embedding: Sequence[float] | None = None,
) -> tuple[str, str, float]:
    """Assign one emergent field to a canonical (embed → nearest → threshold gate). ``embedding`` may
    be supplied precomputed (batch efficiency); otherwise ``embedder`` computes it. Returns
    ``(canonical_hash, method, similarity)`` where method ∈ seed|merge|admit_new|llm_merge|llm_admit.
    """
    if embedding is None:
        if embedder is None:
            raise ValueError("dedup_field needs either an embedding or an embedder")
        [embedding] = await embedder.embed([_name_text(field_name)])

    nearest = api.nearest_canonical_field(
        session, embedding=embedding, exclude_hash=field_name_hash
    )
    if nearest is None:
        # First field in the tenant → it seeds the canonical set.
        api.set_field_embedding_canonical(
            session,
            field_name_hash=field_name_hash,
            embedding=embedding,
            canonical_hash=field_name_hash,
        )
        return field_name_hash, "seed", 0.0

    cand_hash, cand_name, sim = nearest
    if sim >= MERGE_TAU:
        canonical, method = cand_hash, "merge"
    elif sim < ADMIT_TAU:
        canonical, method = field_name_hash, "admit_new"
    elif await _adjudicate(llm, field_name, cand_name):
        canonical, method = cand_hash, "llm_merge"
    else:
        canonical, method = field_name_hash, "llm_admit"

    api.set_field_embedding_canonical(
        session, field_name_hash=field_name_hash, embedding=embedding, canonical_hash=canonical
    )
    return canonical, method, sim
