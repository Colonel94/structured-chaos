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

*** STATUS (updated 2026-08-21 — the earlier "ZERO callers" note is STALE). This module IS now wired
into the live pipeline: ``dedup_registry`` → ``dedup_scan.scan_and_dedup`` → the ``dedup_scan`` queue
task → ``scripts/run_worker.py`` on the 30-min scheduler (docker-compose ``worker``), head-scoped and
running BEFORE promote (remediation R1, done). What is STILL true is the *empirical* verdict, not the
wiring: convergence remains UNPROVEN on the available data — the composite (``qualifier_head``) curve is
flat at ~85–90% hapax because ~93% of qualifiers are genuinely DISTINCT data, not synonym sprawl dedup
can bend (R2 finding). The honest convergence unit is COLUMN-level (minted + promoted), and that needs
richer RECURRING real data to prove it bends — not more code. Do not re-add a "zero callers" claim. ***

Thresholds are the paper's numbers (Jonnalagedda et al. 2606.05415), hardcoded here and tuned on a
scored set — never guessed in prod (EDD §6.2).
"""

from __future__ import annotations

import json
from collections import Counter
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
    head: str | None = None,
    embedder: EmbeddingBackend | None = None,
    embedding: Sequence[float] | None = None,
    example_values: Mapping[str, Sequence[str]] | None = None,
) -> tuple[str, str, float]:
    """Assign one emergent field to a canonical (embed → nearest → threshold gate). ``embedding`` may
    be supplied precomputed (batch efficiency); otherwise ``embedder`` computes it. ``example_values``
    maps a field name → a few real attested values, handed to the gray-band adjudicator for context.
    ``head`` (Path A, remediation R1) scopes the comparison to canonicals under the SAME head — the
    closed head is the merge anchor, so cross-head collapses are impossible. Returns
    ``(canonical_hash, method, similarity)`` where method ∈ seed|merge|admit_new|llm_merge|llm_admit.
    """
    if embedding is None:
        if embedder is None:
            raise ValueError("dedup_field needs either an embedding or an embedder")
        [embedding] = await embedder.embed([_name_text(field_name)])

    nearest = api.nearest_canonical_field(
        session, embedding=embedding, exclude_hash=field_name_hash, head=head
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


async def dedup_registry(
    session: Session, *, embedder: EmbeddingBackend, llm: LLMBackend, batch_size: int = 256
) -> dict[str, int]:
    """The LIVE qualifier-space dedup pass (remediation R1) — head-scoped synonym-merge over the
    emergent registry, run OFF the hot path (the periodic dedup scan, never inline in extract, so the
    sub-60s intake latency is untouched). For every qualifier variant not yet embedded
    (``list_undeduped_variants``), embed its composite name and assign it to a canonical UNDER ITS HEAD
    (the closed head is the anchor — no cross-head collapse). Incremental + idempotent: a variant is
    embedded exactly once, in first-seen order, comparing only to existing canonicals, so re-running
    merges only what is new. Returns the method tally for observability. Over-merge fails safe to
    not-merging (τ gate + adjudicator) — a duplicate is cheaper than a lossy collapse (§3)."""
    pending = api.list_undeduped_variants(session)
    if not pending:
        return {}
    methods: Counter[str] = Counter()
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        # Batch-embed once; then dedup sequentially so each variant sees the canonicals the previous
        # ones in this chunk just created (the incremental growth the convergence proof depends on).
        vecs = await embedder.embed([_name_text(name) for _h, name, _hd in chunk])
        for (fhash, name, head), emb in zip(chunk, vecs, strict=True):
            _canon, method, _sim = await dedup_field(
                session,
                field_name=name,
                field_name_hash=fhash,
                head=head,
                llm=llm,
                embedding=list(emb),
            )
            methods[method] += 1
    return dict(methods)
