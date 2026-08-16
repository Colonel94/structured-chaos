"""Emergent-schema dedup / canonicalisation — the self-converging moat, STAGE 3 (EDD §6.2).

Each distinct emergent field name is embedded (BGE-M3, 1024-d) and compared, in pgvector, to the
nearest existing *canonical* field. The two-threshold gate decides:

    cosine ≥ 0.85           → MERGE   (a synonym of that canonical → becomes its alias)
    cosine < 0.70           → ADMIT   (a genuinely new field → its own canonical)
    0.70 ≤ cosine < 0.85    → ONE LLM adjudication ("would one DB column hold both? y/n")

The asymmetric gap + gray-band adjudication follow the design rule that **over-merge (lossy collapse)
is more expensive than a duplicate** — so the adjudicator, and any error, fail SAFE to *not merging*.
This is what is DESIGNED to turn the raw 378-field sprawl into a converging schema. Incremental: fields
are processed in first-seen order, growing the canonical set; new fields only ever compare against
canonicals (never aliases), so there is no chain-merge.

*** STATUS (2026-08-17, owner + remediation R0/R1). This module has ZERO callers in ``app/`` — it has
never run in the live pipeline (``extract/stage.py`` registers fields and stops; nothing embeds or
merges). So the "converging schema" above is DESIGN INTENT, not a measured result: the emergent schema
is currently NOT deduped and remains ~90% hapax. Wiring this into the live flow (head-scoped, on the
qualifier space) is remediation R1 — and note the measured hazard (run_qualifier_dedup.py, 2026-08-16):
on the value-polluted qualifier slot this over-merges distinct DATA (6_weeks↔6_months, distinct dates),
so R1 depends on qualifier hygiene (R3/R4) landing first. ***

Thresholds are the paper's numbers (Jonnalagedda et al. 2606.05415), hardcoded here and tuned on a
scored set — never guessed in prod (EDD §6.2).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

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


def _field_clause(name: str, values: Sequence[str] | None) -> str:
    """Render a field for the adjudicator: its name plus, when available, up to two real example
    values — the concrete context a bare snake_case name lacks."""
    clause = f'"{name}"'
    if values:
        sample = ", ".join(repr(v) for v in list(values)[:2] if v)
        if sample:
            clause += f" (example values: {sample})"
    return clause


async def _adjudicate(
    llm: LLMBackend,
    name_a: str,
    name_b: str,
    values_a: Sequence[str] | None = None,
    values_b: Sequence[str] | None = None,
) -> bool:
    """One LLM call for the gray band. The question is framed as a *schema-normalisation* decision —
    "would a single database COLUMN hold both of these fields?" — NOT the abstract "are they the same
    attribute?". The column framing is decisive for the real synonyms (``amount``/``charged_amount``,
    ``phone``/``contact_number``) that the stricter "synonyms of one field" wording rejected 95% of
    the time on real data. Optional example values give the model the concrete context a bare name
    lacks. Fails safe to False (do not merge) on any error — a duplicate is cheaper than a lossy
    over-merge, so the illustrative examples teach the *concept* without naming the pairs we measure.
    """
    prompt = (
        "You are normalising an emergent database schema. Two fields were extracted from customer "
        "messages. Decide whether ONE canonical database COLUMN should store BOTH of them without "
        "losing meaning.\n"
        f"Field A: {_field_clause(name_a, values_a)}\n"
        f"Field B: {_field_clause(name_b, values_b)}\n"
        "They belong in the SAME column when one is a synonym, abbreviation, or reworded name of the "
        "other, or both hold the same kind of value about the same underlying thing (for example "
        '"contact_phone" and "phone_number", or "delivery_date" and "date_delivered"). They belong '
        "in DIFFERENT columns only when they capture genuinely distinct attributes (for example "
        '"order_date" and "order_number", which are a date and an identifier).\n'
        'Answer JSON: {"same": true} if one column should hold both, else {"same": false}.'
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
    example_values: Mapping[str, Sequence[str]] | None = None,
) -> tuple[str, str, float]:
    """Assign one emergent field to a canonical (embed → nearest → threshold gate). ``embedding`` may
    be supplied precomputed (batch efficiency); otherwise ``embedder`` computes it. ``example_values``
    maps a field name → a few real attested values, handed to the gray-band adjudicator for context.
    Returns ``(canonical_hash, method, similarity)`` where method ∈
    seed|merge|admit_new|llm_merge|llm_admit.
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
    elif await _adjudicate(
        llm,
        field_name,
        cand_name,
        values_a=(example_values or {}).get(field_name),
        values_b=(example_values or {}).get(cand_name),
    ):
        canonical, method = cand_hash, "llm_merge"
    else:
        canonical, method = field_name_hash, "llm_admit"

    api.set_field_embedding_canonical(
        session, field_name_hash=field_name_hash, embedding=embedding, canonical_hash=canonical
    )
    return canonical, method, sim
