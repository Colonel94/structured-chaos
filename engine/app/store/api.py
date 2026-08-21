"""The Phase-1 store surface: tenants, cases, immutable source docs, the append-only
provenance/correction logs, the disposable ``field_current`` projection, and the idempotency
ledger.

Design invariants enforced here + in migration 0001 (EDD §7):
- **Tenant isolation** — every write stamps ``tenant_id`` from the ``app.tenant_id`` GUC, so it
  can only ever land in the caller's tenant (RLS ``WITH CHECK``). Reads are auto-scoped by RLS.
- **Immutability** — ``source_document`` / ``field_extraction`` / ``field_correction`` /
  ``extraction_citation`` are append-only (UPDATE/DELETE raise, via triggers). Never overwrite.
- **Provenance is complete on every value** — model/version/prompt/confidence/run + **≥1 citation**
  (the ``extraction_citation`` bridge: many sources per value, each with a role, migration 0004).
- **Idempotency** — a stage is claimed once per ``(tenant, idempotency_key)``; replay is a no-op.

All statements are parameterised; JSON values are cast to ``jsonb`` in SQL, never string-built.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

# A JSON-serialisable value stored in a jsonb column. `object` keeps mypy strict honest at
# call sites without forcing every caller through a union.
JsonValue = object


@dataclass(frozen=True)
class Citation:
    """One source a value is drawn from. A value has many (migration 0004): ``delay`` cites the
    order record (``derived_from``) and the complaint message (``primary``); a record that
    disagrees is cited with role ``contradicts`` so contradiction detection is stored, not
    recomputed. ``locator`` is where in that source (char span / audio time-range / image bbox);
    ``weight`` is stored, never yet aggregated into confidence."""

    source_document_id: UUID
    role: str  # primary | corroborating | derived_from | contradicts
    locator: dict[str, JsonValue] | None = None
    weight: float | None = None


# tenant_id is taken from the transaction GUC on every write, so a caller physically cannot
# write into another tenant even by passing a stray id.
_GUC_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _json(value: JsonValue | None) -> str | None:
    """Serialise a JSON value for a jsonb bind; ``None`` maps to SQL NULL."""
    return None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------- tenants (admin)


def create_tenant(admin_session: Session, name: str) -> UUID:
    """Register a tenant. Runs on an **admin** session — tenant creation is an operator action,
    not something the RLS-bound app role may do."""
    row = admin_session.execute(
        text("INSERT INTO tenant (name) VALUES (:name) RETURNING id"),
        {"name": name},
    ).one()
    return UUID(str(row[0]))


def list_tenant_ids(admin_session: Session) -> list[UUID]:
    """Every tenant id — for operator-side fan-out (e.g. the periodic promote-scan runs per tenant).
    Admin session: this deliberately crosses tenants, so it is never available to the app role."""
    rows = admin_session.execute(text("SELECT id FROM tenant ORDER BY created_at, id")).all()
    return [UUID(str(r[0])) for r in rows]


# ----------------------------------------------------------------------------------- cases


def create_case(
    session: Session,
    *,
    channel: str,
    first_contact_at: datetime,
    contact_ref: str | None = None,
) -> UUID:
    """Create a case for the current tenant. Created immediately in ``created`` state —
    it exists before the questions do and is never blocked on completeness (CLAUDE.md §3).
    The SLA clock starts at ``first_contact_at``. ``contact_ref`` is the anchor (sender phone/handle)
    the case belongs to — set once here, used by windowing to find a sender's prior case."""
    row = session.execute(
        text(f"""
            INSERT INTO case_record (tenant_id, channel, first_contact_at, contact_ref)
            VALUES ({_GUC_TENANT}, :channel, :first_contact_at, :contact_ref)
            RETURNING id
            """),
        {"channel": channel, "first_contact_at": first_contact_at, "contact_ref": contact_ref},
    ).one()
    return UUID(str(row[0]))


def latest_case_for_contact(
    session: Session, *, contact_ref: str
) -> tuple[UUID, str, datetime] | None:
    """The sender's most recent case within the tenant — ``(case_id, case_state, last_activity_at)``
    — or ``None`` if they have no case yet. ``last_activity_at`` is the latest of the case's source
    documents' ``received_at`` (falling back to ``first_contact_at``), so windowing measures idle
    time from the real last message, not case creation. RLS scopes this to the current tenant."""
    row = session.execute(
        text("""
            SELECT c.id, c.case_state,
                   GREATEST(c.first_contact_at,
                            COALESCE(MAX(sd.received_at), c.first_contact_at)) AS last_activity
            FROM case_record c
            LEFT JOIN source_document sd ON sd.case_id = c.id
            WHERE c.contact_ref = :contact_ref
            GROUP BY c.id, c.case_state, c.first_contact_at
            ORDER BY last_activity DESC
            LIMIT 1
            """),
        {"contact_ref": contact_ref},
    ).first()
    if row is None:
        return None
    return UUID(str(row[0])), str(row[1]), row[2]


def list_case_source_documents(session: Session, case_id: UUID) -> list[UUID]:
    """The case's inbound source documents (messages/files), oldest first — what an extracted value
    cites as its provenance. RLS scopes to the current tenant."""
    rows = session.execute(
        text("""
            SELECT id FROM source_document
            WHERE case_id = :case_id AND doc_kind IN ('message', 'file')
            ORDER BY received_at, id
            """),
        {"case_id": case_id},
    ).all()
    return [UUID(str(r[0])) for r in rows]


def register_emergent_field(
    session: Session, *, field_name: str, field_name_hash: str, head: str | None = None
) -> int:
    """Upsert the emergent-field registry for the current tenant and recompute its ``support_count``
    (distinct cases attesting the field, from the append-only ``field_extraction`` log — recomputed
    rather than incremented, so a replay never double-counts). ``head`` (Path A) is the closed-vocab
    column this composite (``qualifier_head``) belongs to — stored so support can roll up to the head.
    Returns the new support_count. Call AFTER recording the emergent value, so the just-attested case
    is included."""
    row = session.execute(
        text(f"""
            INSERT INTO emergent_field (tenant_id, field_name_hash, field_name, head, support_count)
            VALUES (
                {_GUC_TENANT}, :hash, :name, :head,
                (SELECT count(DISTINCT case_id) FROM field_extraction
                 WHERE layer = 'emergent' AND field_path = :name)
            )
            ON CONFLICT (tenant_id, field_name_hash) DO UPDATE
                SET support_count = EXCLUDED.support_count,
                    head = COALESCE(EXCLUDED.head, emergent_field.head),
                    updated_at = now()
            RETURNING support_count
            """),
        {"hash": field_name_hash, "name": field_name, "head": head},
    ).one()
    return int(row[0])


def register_emergent_head(session: Session, *, head: str) -> int:
    """Upsert the head-level registry (the emergent COLUMN space, Path A) and recompute its
    ``support_count`` = distinct cases attesting ANY qualifier of this head, from the append-only log
    joined on ``emergent_field.head``. Recomputed (never incremented) so a replay can't double-count.
    Call AFTER ``register_emergent_field`` (which sets the composite's head). Returns support_count.
    """
    row = session.execute(
        text(f"""
            INSERT INTO emergent_head (tenant_id, head, support_count)
            VALUES (
                {_GUC_TENANT}, :head,
                (SELECT count(DISTINCT fe.case_id)
                   FROM field_extraction fe
                   JOIN emergent_field ef ON ef.field_name = fe.field_path
                  WHERE fe.layer = 'emergent' AND ef.head = :head)
            )
            ON CONFLICT (tenant_id, head) DO UPDATE
                SET support_count = EXCLUDED.support_count, updated_at = now()
            RETURNING support_count
            """),
        {"head": head},
    ).one()
    return int(row[0])


def _vec_literal(embedding: Sequence[float]) -> str:
    """A pgvector text literal ``[v1,v2,...]`` — bound as a parameter and cast to ``vector`` in SQL
    (no pgvector-python adapter dependency)."""
    return "[" + ",".join(f"{float(x):.8f}" for x in embedding) + "]"


def nearest_canonical_field(
    session: Session, *, embedding: Sequence[float], exclude_hash: str, head: str | None = None
) -> tuple[str, str, float] | None:
    """The nearest CANONICAL emergent field to ``embedding`` (cosine), excluding ``exclude_hash`` —
    the dedup lookup (EDD §6.2 STAGE 3). A field is canonical iff it is its own canonical
    (``canonical_hash = field_name_hash``); aliases are skipped so we never chain-merge. Returns
    ``(hash, name, cosine_similarity)`` or ``None`` if no canonical is embedded yet. RLS-scoped.

    ``head`` (Path A qualifier-space dedup, remediation R1): when given, the comparison universe is
    restricted to canonicals UNDER THE SAME HEAD — the closed head vocabulary is the ANCHOR, so a
    qualifier under ``amount`` never merges with one under ``date`` (``6 weeks`` under ``duration`` must
    not collapse into a ``date``). Without it the lookup is global (legacy pre-Path-A name dedup).
    """
    where_head = "AND head = :head" if head is not None else ""
    row = session.execute(
        text(f"""
            SELECT field_name_hash, field_name, 1 - (embedding <=> CAST(:emb AS vector)) AS sim
            FROM emergent_field
            WHERE embedding IS NOT NULL
              AND field_name_hash = canonical_hash
              AND field_name_hash <> :exclude
              {where_head}
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT 1
            """),
        {"emb": _vec_literal(embedding), "exclude": exclude_hash, "head": head},
    ).first()
    if row is None:
        return None
    return str(row[0]), str(row[1]), float(row[2])


def set_field_embedding_canonical(
    session: Session, *, field_name_hash: str, embedding: Sequence[float], canonical_hash: str
) -> None:
    """Store a field's BGE-M3 embedding and its canonical assignment (self = canonical; another
    field's hash = merged alias of it)."""
    session.execute(
        text("""
            UPDATE emergent_field
            SET embedding = CAST(:emb AS vector), canonical_hash = :canon, updated_at = now()
            WHERE field_name_hash = :hash
            """),
        {"emb": _vec_literal(embedding), "canon": canonical_hash, "hash": field_name_hash},
    )


def canonical_field_support(session: Session, canonical_hash: str) -> int:
    """Distinct cases attesting a canonical field OR ANY of its merged aliases — the recurrence
    count promotion gates on (EDD §6.2 STAGE 4). Counts over the append-only log, so it's exact."""
    row = session.execute(
        text("""
            SELECT count(DISTINCT fe.case_id)
            FROM field_extraction fe
            JOIN emergent_field ef ON ef.field_name = fe.field_path
            WHERE fe.layer = 'emergent' AND ef.canonical_hash = :canon
            """),
        {"canon": canonical_hash},
    ).scalar_one()
    return int(row)


def list_canonical_fields(session: Session) -> list[tuple[str, str, bool]]:
    """All canonical emergent fields for the tenant — ``(hash, name, promoted)`` — the converged
    schema (each alias group collapses to one row here). RLS-scoped."""
    rows = session.execute(text("""
            SELECT field_name_hash, field_name, promoted FROM emergent_field
            WHERE field_name_hash = canonical_hash
            ORDER BY field_name
            """)).all()
    return [(str(r[0]), str(r[1]), bool(r[2])) for r in rows]


def mark_field_promoted(session: Session, *, canonical_hash: str) -> None:
    """Mark a canonical field promoted to the governed layer (recurrence met). Idempotent."""
    session.execute(
        text(
            "UPDATE emergent_field SET promoted = true, updated_at = now() "
            "WHERE field_name_hash = :canon"
        ),
        {"canon": canonical_hash},
    )


# --------------------------------------------------------------------------- Path A: head promotion


def list_emergent_heads(session: Session) -> list[tuple[str, int, bool]]:
    """All heads for the tenant — ``(head, support_count, promoted)`` — the emergent COLUMN space
    (the convergence unit under Path A). RLS-scoped."""
    rows = session.execute(
        text("SELECT head, support_count, promoted FROM emergent_head ORDER BY head")
    ).all()
    return [(str(r[0]), int(r[1]), bool(r[2])) for r in rows]


def mark_head_promoted(session: Session, *, head: str) -> None:
    """Mark a head promoted to a governed column (recurrence met — promotion dimension 1). Idempotent."""
    session.execute(
        text("UPDATE emergent_head SET promoted = true, updated_at = now() WHERE head = :head"),
        {"head": head},
    )


def list_emergent_field_variants(session: Session) -> list[tuple[str, str, str | None, int, bool]]:
    """Every registered composite ``(field_name_hash, field_name, head, support_count, promoted)`` —
    the qualifier variants under each head. Qualifier promotion (dimension 2) marks these. RLS-scoped.
    """
    rows = session.execute(
        text(
            "SELECT field_name_hash, field_name, head, support_count, promoted "
            "FROM emergent_field ORDER BY head, field_name"
        )
    ).all()
    return [
        (str(r[0]), str(r[1]), (str(r[2]) if r[2] is not None else None), int(r[3]), bool(r[4]))
        for r in rows
    ]


def list_undeduped_variants(session: Session) -> list[tuple[str, str, str]]:
    """Qualifier variants awaiting dedup: ``(field_name_hash, field_name, head)`` for composites that
    have a head, carry a real qualifier (``field_name <> head`` — the bare-head row IS the head column,
    not a qualifier to merge), and have no embedding yet (never run through dedup). First-seen order
    (``created_at``) so the incremental canonical set grows deterministically. RLS-scoped. The dedup
    scan (remediation R1) embeds + canonicalises exactly these; once embedded a variant is skipped, so
    the pass is idempotent."""
    rows = session.execute(
        text(
            "SELECT field_name_hash, field_name, head FROM emergent_field "
            "WHERE head IS NOT NULL AND field_name <> head AND embedding IS NULL "
            "ORDER BY first_seen_at, field_name"
        )
    ).all()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


def list_promotable_qualifier_variants(
    session: Session,
) -> list[tuple[str, str, str, int, bool]]:
    """Qualifier variants ELIGIBLE for promotion (dimension 2), dedup-aware — the alias-collapsed view
    promotion must gate on so two SYNONYMS never both promote as duplicate columns (remediation R1).
    Returns ``(field_name_hash, field_name, head, effective_support, promoted)`` for each NON-ALIAS
    qualifier variant (``field_name <> head``; ``canonical_hash`` is NULL/self — merged aliases are
    excluded). ``effective_support`` = POOLED canonical support (distinct cases attesting the canonical
    OR any merged alias) once deduped, else the raw ``support_count`` (un-deduped variants behave as
    before dedup ran — backward compatible). RLS-scoped."""
    rows = session.execute(text("""
            SELECT ef.field_name_hash, ef.field_name, ef.head, ef.promoted,
              CASE WHEN ef.canonical_hash IS NULL THEN ef.support_count
                   ELSE (SELECT count(DISTINCT fe.case_id)
                           FROM field_extraction fe
                           JOIN emergent_field a ON a.field_name = fe.field_path
                          WHERE fe.layer = 'emergent' AND a.canonical_hash = ef.field_name_hash)
              END AS eff_support
            FROM emergent_field ef
            WHERE ef.head IS NOT NULL AND ef.field_name <> ef.head
              AND (ef.canonical_hash IS NULL OR ef.canonical_hash = ef.field_name_hash)
            ORDER BY ef.head, ef.field_name
            """)).all()
    return [(str(r[0]), str(r[1]), str(r[2]), int(r[4]), bool(r[3])) for r in rows]


# ------------------------------------------------------- head-minting (emergent columns are born here)


def list_escape_valve_facts(
    session: Session, heads: Sequence[str] = ("other", "description")
) -> list[tuple[UUID, str]]:
    """Current facts sitting under the escape-valve heads — ``(case_id, value)`` — the un-homed novelty
    that head-minting clusters. Reads ``field_current`` (the latest value per field, not the whole log)
    joined to the registry by head, so a value corrected/re-extracted away is not re-clustered.
    RLS-scoped."""
    rows = session.execute(
        text("""
            SELECT fc.case_id, fc.value #>> '{}' AS value
            FROM field_current fc
            JOIN emergent_field ef ON ef.field_name = fc.field_path
            WHERE ef.head = ANY(:heads) AND fc.value IS NOT NULL
            """),
        {"heads": list(heads)},
    ).all()
    return [(r[0], str(r[1])) for r in rows if r[1]]


def register_minted_head(
    session: Session,
    *,
    head: str,
    support: int,
    gloss: str | None = None,
    source: str | None = None,
    sensitivity: str | None = None,
) -> None:
    """Register (or refresh) a minted head — a NEW emergent column born from an `other` cluster, not in
    the seed ``HEAD_NOUNS``. ``gloss`` is the one-line definition injected into the extraction prompt so
    the model actually routes facts to it (without it a minted head is dead — 2026-08-17c live finding).
    ``sensitivity`` (PII gate, R5): a non-``none`` value RECORDS that the concept holds protected data
    (health/id/card/…); such heads are stored for audit but EXCLUDED from the extraction vocabulary
    (``list_minted_heads``) so protected data never becomes a first-class column. Upsert on
    ``(tenant_id, head)`` so a re-scan updates idempotently."""
    session.execute(
        text(f"""
            INSERT INTO minted_head (tenant_id, head, support_count, gloss, source, sensitivity)
            VALUES ({_GUC_TENANT}, :head, :support, :gloss, :source, :sensitivity)
            ON CONFLICT (tenant_id, head) DO UPDATE
                SET support_count = EXCLUDED.support_count,
                    gloss = COALESCE(EXCLUDED.gloss, minted_head.gloss),
                    source = COALESCE(EXCLUDED.source, minted_head.source),
                    sensitivity = EXCLUDED.sensitivity,
                    updated_at = now()
            """),
        {
            "head": head,
            "support": support,
            "gloss": gloss,
            "source": source,
            "sensitivity": sensitivity,
        },
    )


def list_minted_heads(session: Session) -> list[str]:
    """This tenant's NON-SENSITIVE minted head names — appended to the seed ``HEAD_NOUNS`` to form the
    effective extraction vocabulary. Heads the PII gate flagged (health/id/card/…) are EXCLUDED so
    protected data never becomes a first-class column (R5). RLS-scoped."""
    rows = session.execute(
        text(
            "SELECT head FROM minted_head "
            "WHERE sensitivity IS NULL OR sensitivity = 'none' ORDER BY head"
        )
    ).all()
    return [str(r[0]) for r in rows]


def list_minted_head_glosses(session: Session) -> dict[str, str]:
    """``head → gloss`` for this tenant's NON-SENSITIVE minted heads — injected into the prompt so the
    model knows when to use each emerged column. Excludes PII-gated heads (R5). RLS-scoped."""
    rows = session.execute(
        text(
            "SELECT head, COALESCE(gloss, head) FROM minted_head "
            "WHERE sensitivity IS NULL OR sensitivity = 'none' ORDER BY head"
        )
    ).all()
    return {str(r[0]): str(r[1]) for r in rows}


def list_minted_heads_detail(session: Session) -> list[tuple[str, int, str | None, str | None]]:
    """``(head, support_count, source, sensitivity)`` for observability — includes PII-gated heads so a
    reviewer can see what was blocked and why. RLS-scoped."""
    rows = session.execute(
        text(
            "SELECT head, support_count, source, sensitivity "
            "FROM minted_head ORDER BY support_count DESC, head"
        )
    ).all()
    return [
        (str(r[0]), int(r[1]), (str(r[2]) if r[2] else None), (str(r[3]) if r[3] else None))
        for r in rows
    ]


def set_head_sensitivity(session: Session, *, head: str, sensitivity: str) -> None:
    """Flag an emergent HEAD as holding protected data (PII gate, R5) — recorded so promotion skips it
    and a reviewer sees why. RLS-scoped."""
    session.execute(
        text("UPDATE emergent_head SET sensitivity = :s, updated_at = now() WHERE head = :head"),
        {"s": sensitivity, "head": head},
    )


def set_field_sensitivity(session: Session, *, canonical_hash: str, sensitivity: str) -> None:
    """Flag an emergent QUALIFIER variant as holding protected data (PII gate, R5). RLS-scoped."""
    session.execute(
        text(
            "UPDATE emergent_field SET sensitivity = :s, updated_at = now() "
            "WHERE field_name_hash = :h"
        ),
        {"s": sensitivity, "h": canonical_hash},
    )


# ------------------------------------------------------- Path A: retroactive backfill (STAGE 6)


def concept_attested_categories(
    session: Session, *, head: str, qualifier_composite: str | None
) -> list[str]:
    """The distinct governed categories of cases that have attested a concept — the scope backfill
    re-extracts over (a promoted ``amount`` is re-extracted only across the categories where amounts
    actually occur, not the whole corpus). ``qualifier_composite`` set → a variant concept (match the
    exact composite ``field_path``); ``None`` → a head concept (match any composite with that head).
    Category is the case's ``field_current`` ``category`` value. RLS-scoped."""
    if qualifier_composite is not None:
        attesting = "SELECT DISTINCT case_id FROM field_extraction WHERE layer='emergent' AND field_path = :key"
        params: dict[str, object] = {"key": qualifier_composite}
    else:
        attesting = (
            "SELECT DISTINCT fe.case_id FROM field_extraction fe "
            "JOIN emergent_field ef ON ef.field_name = fe.field_path "
            "WHERE fe.layer='emergent' AND ef.head = :head"
        )
        params = {"head": head}
    rows = session.execute(
        text(f"""
            SELECT DISTINCT fc.value #>> '{{}}' AS category
            FROM field_current fc
            WHERE fc.field_path = 'category'
              AND fc.case_id IN ({attesting})
              AND fc.value IS NOT NULL
            """),
        params,
    ).all()
    return [str(r[0]) for r in rows if r[0] is not None]


def cases_needing_backfill(
    session: Session, *, concept_key: str, categories: Sequence[str], limit: int
) -> list[UUID]:
    """Cases in ``categories`` that have NOT yet had a backfill attempt for ``concept_key``, OLDEST
    first (``first_contact_at``) — the moat re-extracts history in order. Bounded by ``limit`` so a
    promotion never fans out unboundedly in one job. A case with an ``absent`` marker is excluded (it
    was already re-extracted and legitimately had nothing), so backfill converges. RLS-scoped."""
    if not categories:
        return []
    rows = session.execute(
        text("""
            SELECT cr.id
            FROM case_record cr
            JOIN field_current fc
              ON fc.case_id = cr.id AND fc.field_path = 'category'
            WHERE (fc.value #>> '{}') = ANY(:categories)
              AND NOT EXISTS (
                  SELECT 1 FROM backfill_attempt ba
                  WHERE ba.case_id = cr.id AND ba.concept_key = :concept_key
              )
            ORDER BY cr.first_contact_at, cr.id
            LIMIT :limit
            """),
        {"categories": list(categories), "concept_key": concept_key, "limit": limit},
    ).all()
    return [UUID(str(r[0])) for r in rows]


def record_backfill_attempt(
    session: Session, *, case_id: UUID, concept_key: str, outcome: str
) -> None:
    """Mark that ``concept_key`` was re-extracted against ``case_id`` — ``found`` (a value was written)
    or ``absent`` (nothing there). Idempotent (``ON CONFLICT DO NOTHING``): the marker is what stops a
    genuinely-absent case being re-extracted forever."""
    if outcome not in ("found", "absent"):
        raise ValueError(f"backfill outcome must be found|absent, got {outcome!r}")
    session.execute(
        text(f"""
            INSERT INTO backfill_attempt (tenant_id, case_id, concept_key, outcome)
            VALUES ({_GUC_TENANT}, :case_id, :concept_key, :outcome)
            ON CONFLICT (tenant_id, case_id, concept_key) DO NOTHING
            """),
        {"case_id": case_id, "concept_key": concept_key, "outcome": outcome},
    )


def get_source_document(
    session: Session, source_document_id: UUID
) -> tuple[UUID, str, str, str] | None:
    """Load one source document's ``(case_id, sha256, blob_key, mime)`` for normalisation. RLS
    scopes it to the current tenant (a cross-tenant id reads as absent)."""
    row = session.execute(
        text("""
            SELECT case_id, sha256, blob_key, mime FROM source_document WHERE id = :id
            """),
        {"id": source_document_id},
    ).first()
    if row is None:
        return None
    return UUID(str(row[0])), str(row[1]), str(row[2]), str(row[3])


# ------------------------------------------------------------------------- source documents


def add_source_document(
    session: Session,
    *,
    case_id: UUID,
    sha256: str,
    blob_key: str,
    mime: str,
    channel: str,
    byte_size: int,
    received_at: datetime,
    doc_kind: str = "message",
) -> UUID:
    """Record an immutable, content-addressed original. ``doc_kind`` is ``message`` | ``file`` |
    ``object_snapshot`` — an object-store row snapshotted at extraction time is a source document
    too, so provenance survives the record later changing (migration 0004). Idempotent per
    ``(tenant, sha256)``: re-ingesting the same bytes returns the existing row, not a duplicate."""
    row = session.execute(
        text(f"""
            INSERT INTO source_document
                (tenant_id, case_id, sha256, blob_key, mime, channel, byte_size, received_at, doc_kind)
            VALUES ({_GUC_TENANT}, :case_id, :sha256, :blob_key, :mime, :channel, :byte_size,
                    :received_at, :doc_kind)
            ON CONFLICT (tenant_id, sha256) DO NOTHING
            RETURNING id
            """),
        {
            "case_id": case_id,
            "sha256": sha256,
            "blob_key": blob_key,
            "mime": mime,
            "channel": channel,
            "byte_size": byte_size,
            "received_at": received_at,
            "doc_kind": doc_kind,
        },
    ).first()
    if row is not None:
        return UUID(str(row[0]))
    # Conflict → the bytes already exist for this tenant; return the existing id.
    existing = session.execute(
        text("SELECT id FROM source_document WHERE sha256 = :sha256"),
        {"sha256": sha256},
    ).one()
    return UUID(str(existing[0]))


# ------------------------------------------------------------- provenance / correction logs


def record_extraction(
    session: Session,
    *,
    case_id: UUID,
    field_path: str,
    value: JsonValue | None,
    model: str,
    model_version: str,
    prompt_version: str,
    run_id: UUID,
    confidence: float,
    citations: Sequence[Citation],
    layer: str = "governed_core",
) -> UUID:
    """Append one extracted value together with its citations, atomically. ``citations`` must be
    non-empty — no value exists without provenance (CLAUDE.md §3), and provenance is now many
    sources per value (migration 0004): the extraction + all its citations are one transaction, so
    a citation-less extraction can never persist. ``UNIQUE(run_id, field_path)`` makes a re-run a
    no-op (its citations were written on the original run, so they are not re-inserted)."""
    if not citations:
        raise ValueError(
            "an extraction must cite at least one source (no value without provenance)"
        )
    row = session.execute(
        text(f"""
            INSERT INTO field_extraction
                (tenant_id, case_id, field_path, value, layer, model, model_version,
                 prompt_version, confidence, run_id)
            VALUES ({_GUC_TENANT}, :case_id, :field_path, CAST(:value AS jsonb), :layer, :model,
                    :model_version, :prompt_version, :confidence, :run_id)
            ON CONFLICT (run_id, field_path) DO NOTHING
            RETURNING id
            """),
        {
            "case_id": case_id,
            "field_path": field_path,
            "value": _json(value),
            "layer": layer,
            "model": model,
            "model_version": model_version,
            "prompt_version": prompt_version,
            "confidence": confidence,
            "run_id": run_id,
        },
    ).first()
    if row is None:
        # Replay: the extraction (and its citations) already exist for this run.
        existing = session.execute(
            text("SELECT id FROM field_extraction WHERE run_id = :run_id AND field_path = :fp"),
            {"run_id": run_id, "fp": field_path},
        ).one()
        return UUID(str(existing[0]))
    extraction_id = UUID(str(row[0]))
    for c in citations:
        add_citation(
            session,
            extraction_id=extraction_id,
            source_document_id=c.source_document_id,
            role=c.role,
            locator=c.locator,
            weight=c.weight,
        )
    return extraction_id


def add_citation(
    session: Session,
    *,
    extraction_id: UUID,
    source_document_id: UUID,
    role: str,
    locator: dict[str, JsonValue] | None = None,
    weight: float | None = None,
) -> UUID:
    """Append one citation linking a value (extraction) to a source it was drawn from, with a role
    (primary / corroborating / derived_from / contradicts). Immutable + tenant-scoped like the logs
    it cites. Normally called via :func:`record_extraction`; exposed for tests + provenance tools.
    """
    row = session.execute(
        text(f"""
            INSERT INTO extraction_citation
                (tenant_id, extraction_id, source_document_id, role, locator, weight)
            VALUES ({_GUC_TENANT}, :extraction_id, :source_document_id, :role,
                    CAST(:locator AS jsonb), :weight)
            RETURNING id
            """),
        {
            "extraction_id": extraction_id,
            "source_document_id": source_document_id,
            "role": role,
            "locator": _json(locator),
            "weight": weight,
        },
    ).one()
    return UUID(str(row[0]))


def record_correction(
    session: Session,
    *,
    case_id: UUID,
    field_path: str,
    prev_value: JsonValue | None,
    new_value: JsonValue | None,
    based_on_extraction_id: UUID | None,
    reviewer_id: str,
    note: str | None = None,
) -> UUID:
    """Append a human correction against the extraction it revises. Never overwrites the
    extraction — this log is the moat asset and the eval set (EDD §7.2)."""
    row = session.execute(
        text(f"""
            INSERT INTO field_correction
                (tenant_id, case_id, field_path, prev_value, new_value,
                 based_on_extraction_id, reviewer_id, note)
            VALUES ({_GUC_TENANT}, :case_id, :field_path, CAST(:prev AS jsonb),
                    CAST(:new AS jsonb), :based_on, :reviewer_id, :note)
            RETURNING id
            """),
        {
            "case_id": case_id,
            "field_path": field_path,
            "prev": _json(prev_value),
            "new": _json(new_value),
            "based_on": based_on_extraction_id,
            "reviewer_id": reviewer_id,
            "note": note,
        },
    ).one()
    return UUID(str(row[0]))


# ------------------------------------------------------------------- field_current projection


def rebuild_field_current(session: Session, case_id: UUID) -> int:
    """Recompute the disposable ``field_current`` projection for a case from the append-only
    logs: **latest correction, else latest extraction**, per ``field_path``. Returns the number
    of projected fields. Idempotent — safe to replay; the logs are the source of truth."""
    session.execute(
        text("DELETE FROM field_current WHERE case_id = :case_id"),
        {"case_id": case_id},
    )
    session.execute(
        text(f"""
            WITH latest_ext AS (
                SELECT DISTINCT ON (field_path)
                       field_path, id, value, confidence
                FROM field_extraction
                WHERE case_id = :case_id
                ORDER BY field_path, seq DESC   -- monotonic append order; ties impossible
            ),
            latest_corr AS (
                SELECT DISTINCT ON (field_path)
                       field_path, id, new_value
                FROM field_correction
                WHERE case_id = :case_id
                ORDER BY field_path, seq DESC
            )
            INSERT INTO field_current
                (tenant_id, case_id, field_path, value, source_kind, source_id, confidence)
            SELECT
                {_GUC_TENANT},
                :case_id,
                COALESCE(c.field_path, e.field_path),
                CASE WHEN c.field_path IS NOT NULL THEN c.new_value ELSE e.value END,
                CASE WHEN c.field_path IS NOT NULL THEN 'correction' ELSE 'extraction' END,
                CASE WHEN c.field_path IS NOT NULL THEN c.id ELSE e.id END,
                CASE WHEN c.field_path IS NOT NULL THEN NULL ELSE e.confidence END
            FROM latest_ext e
            FULL OUTER JOIN latest_corr c ON e.field_path = c.field_path
            """),
        {"case_id": case_id},
    )
    n = session.execute(
        text("SELECT count(*) FROM field_current WHERE case_id = :case_id"),
        {"case_id": case_id},
    ).scalar_one()
    return int(n)


# --------------------------------------------------------------------- normalised content (Phase 3)


def save_normalised_content(
    session: Session,
    *,
    case_id: UUID,
    source_document_id: UUID,
    content_text: str,
    language: str,
    spans: Sequence[dict[str, JsonValue]],
    stage: str,
    model: str,
    model_version: str,
    meta: Mapping[str, JsonValue] | None = None,
) -> UUID:
    """Upsert the derived normalisation (transcript/OCR/text + provenance spans) for one source
    document + stage. Rebuildable, so re-normalising replaces the row (``ON CONFLICT DO UPDATE``) —
    the immutable original is untouched. Returns the row id. (Param is ``content_text`` so it never
    shadows the imported SQL ``text`` helper.)"""
    row = session.execute(
        text(f"""
            INSERT INTO normalised_content
                (tenant_id, case_id, source_document_id, text, language, spans, stage, model,
                 model_version, meta)
            VALUES ({_GUC_TENANT}, :case_id, :sdid, :text, :language, CAST(:spans AS jsonb),
                    :stage, :model, :model_version, CAST(:meta AS jsonb))
            ON CONFLICT (tenant_id, source_document_id, stage) DO UPDATE
                SET text = EXCLUDED.text, language = EXCLUDED.language, spans = EXCLUDED.spans,
                    model = EXCLUDED.model, model_version = EXCLUDED.model_version,
                    meta = EXCLUDED.meta, updated_at = now()
            RETURNING id
            """),
        {
            "case_id": case_id,
            "sdid": source_document_id,
            "text": content_text,
            "language": language,
            "spans": _json(list(spans)),
            "stage": stage,
            "model": model,
            "model_version": model_version,
            "meta": _json(meta or {}),
        },
    ).one()
    return UUID(str(row[0]))


def get_case_normalised_text(session: Session, case_id: UUID) -> str:
    """The concatenated normalised text for a case, in source order — what Phase-4 extraction reads.
    RLS scopes it to the current tenant."""
    rows = session.execute(
        text("""
            SELECT text FROM normalised_content
            WHERE case_id = :case_id AND text <> ''
            ORDER BY created_at, id
            """),
        {"case_id": case_id},
    ).all()
    return "\n".join(str(r[0]) for r in rows)


def list_case_normalised_spans(session: Session, case_id: UUID) -> list[dict[str, JsonValue]]:
    """Per source document: its mime, normalised text, and provenance spans — in the SAME order and
    with the SAME ``text <> ''`` filter as :func:`get_case_normalised_text`, so char offsets computed
    against this list line up with the concatenated text the review UI renders. Drives per-field span
    attribution (Phase 7): a value is located here → its exact sentence / audio segment / image region.
    RLS-scoped."""
    rows = session.execute(
        text("""
            SELECT nc.source_document_id, sd.mime, nc.text, nc.spans
            FROM normalised_content nc
            JOIN source_document sd ON sd.id = nc.source_document_id
            WHERE nc.case_id = :cid AND nc.text <> ''
            ORDER BY nc.created_at, nc.id
            """),
        {"cid": case_id},
    ).all()
    return [
        {
            "source_document_id": str(r[0]),
            "mime": str(r[1]),
            "text": str(r[2]),
            "spans": r[3] or [],
        }
        for r in rows
    ]


# ----------------------------------------------------------------- review read model (Phase 4.7)
#
# The review view (the engine's first client) reads the assembled case: the governed core + the
# emergent attributes, each with its confidence, provenance (which sources it was drawn from), and —
# where a human has corrected it — the prev→new diff. All reads are RLS-scoped to the current tenant,
# so a stray or cross-tenant id returns nothing (fail-closed), never another tenant's case.


def list_cases(session: Session, *, limit: int = 100) -> list[dict[str, JsonValue]]:
    """Recent cases for the current tenant, newest first, with the manager-register summary: category +
    fault (from the ``field_current`` projection), the deterministic priority/SLA (from ``case_decision``),
    the lowest governed confidence (the low-confidence-first review hint), and the approval stamp — so the
    register can render, sort, and triage without a per-row round-trip. All RLS-scoped."""
    rows = session.execute(
        text("""
            SELECT c.id, c.channel, c.case_state, c.first_contact_at,
                   (SELECT value FROM field_current
                    WHERE case_id = c.id AND field_path = 'category') AS category,
                   (SELECT value FROM field_current
                    WHERE case_id = c.id AND field_path = 'fault') AS fault,
                   (SELECT count(*) FROM field_current WHERE case_id = c.id) AS field_count,
                   (SELECT min(confidence) FROM field_current
                    WHERE case_id = c.id AND confidence IS NOT NULL
                      AND field_path IN ('category','fault','desired_outcome',
                                         'severity_signal','emotion_signal','anchor_value')
                   ) AS min_gov_conf,
                   (SELECT priority FROM case_decision WHERE case_id = c.id) AS priority,
                   (SELECT routing FROM case_decision WHERE case_id = c.id) AS routing,
                   (SELECT sla_response_due_at FROM case_decision WHERE case_id = c.id) AS sla_due,
                   c.committed_at
            FROM case_record c
            ORDER BY c.first_contact_at DESC, c.id
            LIMIT :limit
            """),
        {"limit": limit},
    ).all()
    return [
        {
            "case_id": str(r[0]),
            "channel": r[1],
            "case_state": r[2],
            "first_contact_at": r[3].isoformat(),
            "category": r[4],
            "fault": r[5],
            "field_count": int(r[6]),
            "min_governed_confidence": float(r[7]) if r[7] is not None else None,
            "priority": r[8],
            "routing": r[9],
            "sla_response_due_at": r[10].isoformat() if r[10] is not None else None,
            "committed_at": r[11].isoformat() if r[11] is not None else None,
        }
        for r in rows
    ]


def _citations_for(session: Session, extraction_id: UUID) -> list[dict[str, JsonValue]]:
    """The sources one extracted value was drawn from — the provenance a reviewer clicks into."""
    rows = session.execute(
        text("""
            SELECT source_document_id, role, locator FROM extraction_citation
            WHERE extraction_id = :eid ORDER BY id
            """),
        {"eid": extraction_id},
    ).all()
    return [{"source_document_id": str(r[0]), "role": r[1], "locator": r[2]} for r in rows]


def get_case_review(session: Session, case_id: UUID) -> dict[str, JsonValue] | None:
    """Assemble one case for review: header + every current field (governed and emergent) with its
    confidence, provenance and any human correction, plus the source documents and the normalised
    text that back it. Returns ``None`` if the case is absent for this tenant (RLS fail-closed)."""
    header = session.execute(
        text("""
            SELECT id, channel, case_state, first_contact_at
            FROM case_record WHERE id = :cid
            """),
        {"cid": case_id},
    ).first()
    if header is None:
        return None

    # Authoritative layer per field_path (a path is consistently one layer) — avoids importing the
    # extract vocabulary into the store layer and covers correction-sourced rows too.
    layers = {
        str(r[0]): str(r[1])
        for r in session.execute(
            text("SELECT DISTINCT field_path, layer FROM field_extraction WHERE case_id = :cid"),
            {"cid": case_id},
        ).all()
    }
    # The closed-vocab head each emergent composite belongs to (Path A), for a clean column render.
    heads = {
        str(r[0]): str(r[1])
        for r in session.execute(
            text("SELECT field_name, head FROM emergent_field WHERE head IS NOT NULL")
        ).all()
    }

    fields: list[dict[str, JsonValue]] = []
    rows = session.execute(
        text("""
            SELECT field_path, value, source_kind, source_id, confidence
            FROM field_current WHERE case_id = :cid ORDER BY field_path
            """),
        {"cid": case_id},
    ).all()
    for field_path, value, source_kind, source_id, confidence in rows:
        layer = layers.get(field_path, "governed_core" if "_" not in field_path else "emergent")
        provenance: list[dict[str, JsonValue]] = []
        correction: dict[str, JsonValue] | None = None
        model_version: str | None = None
        prompt_version: str | None = None
        if source_kind == "extraction":
            meta = session.execute(
                text("SELECT model_version, prompt_version FROM field_extraction WHERE id = :id"),
                {"id": source_id},
            ).first()
            if meta is not None:
                model_version, prompt_version = meta[0], meta[1]
            provenance = _citations_for(session, source_id)
        else:  # a human correction is the current value → surface the prev→new diff + who/why
            corr = session.execute(
                text("""
                    SELECT prev_value, reviewer_id, note, based_on_extraction_id
                    FROM field_correction WHERE id = :id
                    """),
                {"id": source_id},
            ).first()
            if corr is not None:
                correction = {"prev_value": corr[0], "reviewer_id": corr[1], "note": corr[2]}
                if corr[3] is not None:
                    provenance = _citations_for(session, corr[3])

        head = heads.get(field_path) if layer == "emergent" else None
        qualifier = None
        if head and field_path != head and field_path.endswith(f"_{head}"):
            qualifier = field_path[: -(len(head) + 1)]
        fields.append(
            {
                "field_path": field_path,
                "value": value,
                "layer": layer,
                "head": head,
                "qualifier": qualifier,
                "confidence": confidence,
                "source_kind": source_kind,
                "correction": correction,
                "provenance": provenance,
                "model_version": model_version,
                "prompt_version": prompt_version,
            }
        )

    source_docs = session.execute(
        text("""
            SELECT id, channel, mime, received_at FROM source_document
            WHERE case_id = :cid AND doc_kind IN ('message', 'file')
            ORDER BY received_at, id
            """),
        {"cid": case_id},
    ).all()
    # The lowest governed-core confidence — the review-routing hint (low-confidence-first). A field the
    # system is unsure of is what should pull a case into human review (Phase 6 "refuse to guess").
    gov_conf = [
        float(f["confidence"])  # type: ignore[arg-type]
        for f in fields
        if f["layer"] == "governed_core" and f["confidence"] is not None
    ]

    # The agent-facing analysis — what this is / the discrepancy / why prioritised / the next step —
    # synthesised (deterministically, grounded) from the governed core + decision + any contradiction,
    # so the reviewer gets a near-decided case, not seven logged fields. Computed as a VIEW at read time.
    from ..rules.synthesis import build_case_analysis

    decision = get_case_decision(session, case_id)
    governed_values = {
        str(f["field_path"]): str(f["value"])
        for f in fields
        if f["layer"] == "governed_core" and f["value"] not in (None, "")
    }
    contradictions = [
        c["locator"]  # {record_field, record_value, claim}
        for f in fields
        for c in f["provenance"]  # type: ignore[attr-defined]
        if c.get("role") == "contradicts" and isinstance(c.get("locator"), dict)
    ]
    fg = session.execute(
        text(
            "SELECT external_mappings #> '{elicit,fault_grounded}' FROM case_record WHERE id = :c"
        ),
        {"c": case_id},
    ).scalar()
    analysis = build_case_analysis(
        governed_values,
        decision,
        contradictions,
        fault_grounded=fg if isinstance(fg, bool) else None,
    )

    return {
        "case_id": str(header[0]),
        "channel": header[1],
        "case_state": header[2],
        "first_contact_at": header[3].isoformat(),
        "fields": fields,
        # The deterministic priority/SLA/routing decision (Phase 6 rules engine), if computed.
        "decision": decision,
        # The synthesised agent-facing read (what it is / discrepancy / priority reason / next step).
        "analysis": analysis,
        # The human-approval stamp (Phase 7). Non-null ⇒ approved; the report gate + UI read it.
        "commit": commit_status(session, case_id),
        "min_governed_confidence": min(gov_conf) if gov_conf else None,
        "normalised_text": get_case_normalised_text(session, case_id),
        "source_documents": [
            {
                "id": str(d[0]),
                "channel": d[1],
                "mime": d[2],
                "received_at": d[3].isoformat(),
            }
            for d in source_docs
        ],
    }


# ------------------------------------------------------------------------------ idempotency


def compute_idempotency_key(
    *, source_sha256: str, stage: str, model_version: str, prompt_version: str, code_version: str
) -> str:
    """``hash(source.sha256 + stage + model_ver + prompt_ver + code_ver)`` (EDD §7.3). Bumping
    any version yields a new key → a fresh run whose provenance never overwrites the old."""
    material = (
        f"{source_sha256}\x1f{stage}\x1f{model_version}\x1f{prompt_version}\x1f{code_version}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def claim_stage(
    session: Session, *, stage: str, idempotency_key: str, case_id: UUID | None = None
) -> bool:
    """Claim a pipeline stage as ``running`` for the current tenant.

    Returns ``True`` if the caller should do the work — a fresh claim, or a **re-claim** of a prior
    attempt left ``running``/``failed`` (a crash between claim and completion). Returns ``False``
    only when the stage is already ``done`` (a successful replay → skip). Call
    :func:`complete_stage` on success (and :func:`fail_stage` on a handled failure). Marking
    ``done`` at *claim* time would lose work on a crash — this honours "replay any stage → no lost
    data, retryable" (CLAUDE.md §3). The UNIQUE ``(tenant_id, idempotency_key)`` keeps it atomic."""
    row = session.execute(
        text(f"""
            INSERT INTO stage_execution (tenant_id, case_id, stage, idempotency_key, status)
            VALUES ({_GUC_TENANT}, :case_id, :stage, :key, 'running')
            ON CONFLICT (tenant_id, idempotency_key) DO UPDATE
                SET status = 'running'
                WHERE stage_execution.status <> 'done'
            RETURNING id
            """),
        {"case_id": case_id, "stage": stage, "key": idempotency_key},
    ).first()
    return row is not None


def complete_stage(session: Session, *, idempotency_key: str) -> None:
    """Mark a claimed stage ``done``. After this, replays of the same key skip (idempotent
    success). RLS scopes the update to the current tenant's row."""
    session.execute(
        text("UPDATE stage_execution SET status = 'done' WHERE idempotency_key = :key"),
        {"key": idempotency_key},
    )


def fail_stage(session: Session, *, idempotency_key: str) -> None:
    """Mark a claimed stage ``failed`` so a later replay re-claims and retries it."""
    session.execute(
        text("UPDATE stage_execution SET status = 'failed' WHERE idempotency_key = :key"),
        {"key": idempotency_key},
    )


# ------------------------------------------------------------------- object store (Phase 5, §16.1)


@dataclass(frozen=True)
class ObjectHit:
    """One object an anchor resolves to. ``key_field`` is which identifier matched (None for a
    fuzzy/embedding hit)."""

    object_id: UUID
    object_type: str
    external_id: str | None
    key_field: str | None = None


def upsert_object_record(
    session: Session,
    *,
    object_type: str,
    external_id: str | None,
    content_hash: str,
    attributes: Mapping[str, JsonValue],
    key_fields: Sequence[str],
) -> tuple[UUID, bool]:
    """Insert an object for the current tenant, idempotent on ``(tenant, content_hash)``. Returns
    ``(object_id, created)`` — ``created`` is False when the identical object already existed (a
    replayed ingest batch is a no-op, never a duplicate). ``key_fields`` records which attributes the
    profiler chose as identifiers (transparency; the resolvable keys live in ``object_key``)."""
    row = session.execute(
        text(f"""
            INSERT INTO object_record
                (tenant_id, object_type, external_id, content_hash, attributes, key_fields)
            VALUES ({_GUC_TENANT}, :otype, :ext, :chash, CAST(:attrs AS jsonb), CAST(:kf AS jsonb))
            ON CONFLICT (tenant_id, content_hash) DO NOTHING
            RETURNING id
            """),
        {
            "otype": object_type,
            "ext": external_id,
            "chash": content_hash,
            "attrs": _json(dict(attributes)),
            "kf": _json(list(key_fields)),
        },
    ).first()
    if row is not None:
        return UUID(str(row[0])), True
    existing = session.execute(
        text("SELECT id FROM object_record WHERE content_hash = :chash"),
        {"chash": content_hash},
    ).one()
    return UUID(str(existing[0])), False


def add_object_key(
    session: Session, *, object_id: UUID, key_field: str, key_value_hash: str, key_value: str
) -> None:
    """Index one identifier of an object for exact-match lookup. Upsert on
    ``(tenant, object, key_field)`` so re-ingest refreshes rather than duplicates. ``key_value_hash``
    is the sha256 of the caller-NORMALISED value (see ``app.resolve`` — normalisation lives with the
    resolver so ingest and lookup hash a value identically)."""
    session.execute(
        text(f"""
            INSERT INTO object_key (tenant_id, object_id, key_field, key_value_hash, key_value)
            VALUES ({_GUC_TENANT}, :oid, :field, :vhash, :val)
            ON CONFLICT (tenant_id, object_id, key_field) DO UPDATE
                SET key_value_hash = EXCLUDED.key_value_hash, key_value = EXCLUDED.key_value
            """),
        {"oid": object_id, "field": key_field, "vhash": key_value_hash, "val": key_value},
    )


def resolve_object_by_key(
    session: Session, *, key_value_hash: str, key_field: str | None = None
) -> list[ObjectHit]:
    """Every object whose ``key_field`` value hashes to ``key_value_hash`` (RLS-scoped to the current
    tenant). ``key_field=None`` searches all identifier fields. Exactly one hit → a silent-match
    candidate; more than one → ambiguous, must confirm; zero → fall back to fuzzy/elicit. The resolver
    (``app.resolve``) applies that policy; this only returns the matches."""
    where_field = "AND ok.key_field = :field" if key_field is not None else ""
    rows = session.execute(
        text(f"""
            SELECT r.id, r.object_type, r.external_id, ok.key_field
            FROM object_key ok
            JOIN object_record r ON r.tenant_id = ok.tenant_id AND r.id = ok.object_id
            WHERE ok.key_value_hash = :vhash
              {where_field}
            ORDER BY r.object_type, r.external_id
            """),
        {"vhash": key_value_hash, "field": key_field},
    ).all()
    return [
        ObjectHit(UUID(str(r[0])), str(r[1]), (None if r[2] is None else str(r[2])), str(r[3]))
        for r in rows
    ]


def nearest_objects(
    session: Session, *, embedding: Sequence[float], k: int = 2, object_type: str | None = None
) -> list[tuple[UUID, str, float]]:
    """The ``k`` nearest embedded objects to ``embedding`` (cosine desc), for the fuzzy fallback when
    no exact key was quoted. Returns ``[(object_id, external_id, cosine), ...]``. RLS-scoped. The
    resolver silent-binds a fuzzy hit only above a high τ AND with a clear margin over the runner-up
    (hence k≥2) — a name alone is weak evidence, and acting on the wrong order is worse than asking.
    """
    where_type = "AND object_type = :otype" if object_type is not None else ""
    rows = session.execute(
        text(f"""
            SELECT id, external_id, 1 - (embedding <=> CAST(:emb AS vector)) AS sim
            FROM object_record
            WHERE embedding IS NOT NULL
              {where_type}
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :k
            """),
        {"emb": _vec_literal(embedding), "otype": object_type, "k": k},
    ).all()
    return [(UUID(str(r[0])), ("" if r[1] is None else str(r[1])), float(r[2])) for r in rows]


def set_object_embedding(session: Session, *, object_id: UUID, embedding: Sequence[float]) -> None:
    """Store an object's BGE-M3 embedding (the fuzzy-match vector). Kept off the ingest hot path so a
    large upload isn't blocked on the GPU; the resolver's exact-key path never needs it."""
    session.execute(
        text("UPDATE object_record SET embedding = CAST(:emb AS vector) WHERE id = :oid"),
        {"emb": _vec_literal(embedding), "oid": object_id},
    )


def get_object(
    session: Session, object_id: UUID
) -> tuple[str, str | None, dict[str, JsonValue]] | None:
    """One object's ``(object_type, external_id, attributes)`` — for the confirmation prompt and for
    the ``object_snapshot`` source document written when a case binds to it. RLS-scoped."""
    row = session.execute(
        text("SELECT object_type, external_id, attributes FROM object_record WHERE id = :oid"),
        {"oid": object_id},
    ).first()
    if row is None:
        return None
    return str(row[0]), (None if row[1] is None else str(row[1])), dict(row[2])


def count_objects(session: Session, *, object_type: str | None = None) -> int:
    """How many objects the current tenant has (optionally of one type). For ingest reporting/tests."""
    where_type = "WHERE object_type = :otype" if object_type is not None else ""
    row = session.execute(
        text(f"SELECT count(*) FROM object_record {where_type}"),
        {"otype": object_type},
    ).scalar_one()
    return int(row)


# ---------------------------------------------------------------------- elicitation (Phase 5, §5)


def get_case_elicit_state(
    session: Session, case_id: UUID
) -> tuple[str, int, bool, str | None] | None:
    """``(case_state, question_count, anchor_asked, contact_ref)`` for the elicitation policy, or None
    if the case is absent. ``anchor_asked`` (from ``external_mappings.elicit``) keeps the anchor from
    being re-asked or counted as a drill; ``contact_ref`` is the sender phone (a free anchor)."""
    row = session.execute(
        text("""
            SELECT case_state, question_count,
                   COALESCE((external_mappings #>> '{elicit,anchor_asked}')::boolean, false),
                   contact_ref
            FROM case_record WHERE id = :cid
            """),
        {"cid": case_id},
    ).first()
    if row is None:
        return None
    return str(row[0]), int(row[1]), bool(row[2]), (None if row[3] is None else str(row[3]))


def get_case_channel(session: Session, case_id: UUID) -> str | None:
    """The case's intake channel — needed to stamp a derived source (an object snapshot inherits the
    case's channel, the only values the channel CHECK allows). RLS-scoped."""
    row = session.execute(
        text("SELECT channel FROM case_record WHERE id = :cid"), {"cid": case_id}
    ).first()
    return None if row is None else str(row[0])


def get_latest_extraction_id(session: Session, case_id: UUID, field_path: str) -> UUID | None:
    """The id of the most recent ``field_extraction`` for a value — what a later citation (e.g. a
    ``contradicts`` link to an object snapshot) attaches to. Latest wins (a re-extraction supersedes).
    """
    row = session.execute(
        text("""
            SELECT id FROM field_extraction
            WHERE case_id = :cid AND field_path = :fp
            ORDER BY seq DESC LIMIT 1
            """),
        {"cid": case_id, "fp": field_path},
    ).first()
    return None if row is None else UUID(str(row[0]))


def get_field_values(session: Session, case_id: UUID, field_paths: Sequence[str]) -> dict[str, str]:
    """The present (non-null) ``field_current`` values for the given paths — used to find which
    governed fields are STILL GAPS (an absent key = a gap the elicitation policy may ask about)."""
    rows = session.execute(
        text("""
            SELECT field_path, value FROM field_current
            WHERE case_id = :cid AND field_path = ANY(:paths)
            """),
        {"cid": case_id, "paths": list(field_paths)},
    ).all()
    return {str(r[0]): str(r[1]) for r in rows if r[1] not in (None, "")}


def apply_elicitation(
    session: Session, case_id: UUID, *, state: str, asked: bool, meta: Mapping[str, JsonValue]
) -> None:
    """Persist an elicitation decision: set ``case_state``, increment ``question_count`` by one iff a
    question was ``asked`` (the budget is spent HERE, in code), and store the plan under
    ``external_mappings.elicit`` for the channel/review to read. RLS-scoped."""
    session.execute(
        text("""
            UPDATE case_record
            SET case_state = :state,
                question_count = question_count + :delta,
                external_mappings = jsonb_set(external_mappings, '{elicit}', CAST(:meta AS jsonb), true)
            WHERE id = :cid
            """),
        {"cid": case_id, "state": state, "delta": 1 if asked else 0, "meta": _json(dict(meta))},
    )


# ----------------------------------------------------------------- outbound channel (Phase 5, §5)


def get_pending_question(session: Session, case_id: UUID) -> str | None:
    """The elicitation question awaiting dispatch — the ``next_question`` the elicit stage recorded
    while the case is still ``incomplete``. None when the case is actionable/handed-off or nothing is
    pending. RLS-scoped."""
    row = session.execute(
        text("""
            SELECT external_mappings->'elicit'->>'next_question'
            FROM case_record
            WHERE id = :cid AND case_state = 'incomplete'
              AND external_mappings->'elicit'->>'next_question' IS NOT NULL
            """),
        {"cid": case_id},
    ).first()
    return None if row is None or row[0] is None else str(row[0])


def claim_outbound(
    session: Session,
    *,
    case_id: UUID,
    channel: str,
    recipient: str,
    body: str,
    question_hash: str,
) -> UUID | None:
    """Claim a question for sending — insert an ``outbound_message`` row, idempotent on
    ``(tenant, case, question_hash)``. Returns the new row id if the caller should transmit, or None
    if this exact question was already sent (never send twice). Call :func:`mark_outbound_sent` after a
    successful transmit."""
    row = session.execute(
        text(f"""
            INSERT INTO outbound_message
                (tenant_id, case_id, channel, recipient, body, question_hash, status)
            VALUES ({_GUC_TENANT}, :cid, :channel, :recipient, :body, :qhash, 'sending')
            ON CONFLICT (tenant_id, case_id, question_hash) DO NOTHING
            RETURNING id
            """),
        {
            "cid": case_id,
            "channel": channel,
            "recipient": recipient,
            "body": body,
            "qhash": question_hash,
        },
    ).first()
    return None if row is None else UUID(str(row[0]))


def mark_outbound_sent(session: Session, outbound_id: UUID, *, external_ref: str) -> None:
    """Record the channel's message ref and flip a claimed outbound to ``sent`` (the audit trail)."""
    session.execute(
        text("""
            UPDATE outbound_message SET external_ref = :ref, status = 'sent' WHERE id = :oid
            """),
        {"ref": external_ref, "oid": outbound_id},
    )


# ------------------------------------------------ deterministic priority/SLA/routing (Phase 6, §8)


def get_case_decision_inputs(
    session: Session, case_id: UUID
) -> tuple[datetime, dict[str, str | None]] | None:
    """``(first_contact_at, {category, severity_signal, emotion_signal})`` for the rules engine, or None
    if the case is absent. ``first_contact_at`` is the SLA clock start (§3 — the clock starts at first
    contact); the three signals are the governed inputs the deterministic policy reads. A missing
    governed value is None (the policy's rules simply won't fire on it). RLS-scoped."""
    row = session.execute(
        text("SELECT first_contact_at FROM case_record WHERE id = :cid"), {"cid": case_id}
    ).first()
    if row is None:
        return None
    first_contact_at = row[0]
    keys = ("category", "severity_signal", "emotion_signal")
    values = get_field_values(session, case_id, keys)
    return first_contact_at, {k: values.get(k) for k in keys}


def get_tenant_policy_yaml(session: Session) -> str | None:
    """The current tenant's optional policy override text (``tenant.policy_yaml``), or None → the case
    runs on the universal default policy (zero-config). RLS scopes ``tenant`` to the caller's own row.
    """
    row = session.execute(text("SELECT policy_yaml FROM tenant WHERE id = " + _GUC_TENANT)).first()
    return None if row is None or row[0] is None else str(row[0])


def upsert_case_decision(
    session: Session,
    case_id: UUID,
    *,
    priority: str,
    routing: str,
    sla_target_hours: float,
    sla_response_due_at: datetime,
    matched_rule_id: str,
    rationale: str,
    policy_version: str,
    inputs: Mapping[str, JsonValue],
) -> None:
    """Write (or rebuild) the deterministic decision for a case — the disposable projection derived from
    (governed core × policy). Idempotent by primary key: re-running the rules stage on unchanged inputs
    overwrites with the identical row. RLS-scoped (INSERT stamps the caller's tenant)."""
    session.execute(
        text(f"""
            INSERT INTO case_decision
                (tenant_id, case_id, priority, routing, sla_target_hours, sla_response_due_at,
                 matched_rule_id, rationale, policy_version, inputs)
            VALUES ({_GUC_TENANT}, :cid, :priority, :routing, :sla_hours, :due_at,
                    :rule_id, :rationale, :policy_version, CAST(:inputs AS jsonb))
            ON CONFLICT (tenant_id, case_id) DO UPDATE SET
                priority = EXCLUDED.priority,
                routing = EXCLUDED.routing,
                sla_target_hours = EXCLUDED.sla_target_hours,
                sla_response_due_at = EXCLUDED.sla_response_due_at,
                matched_rule_id = EXCLUDED.matched_rule_id,
                rationale = EXCLUDED.rationale,
                policy_version = EXCLUDED.policy_version,
                inputs = EXCLUDED.inputs,
                computed_at = now()
            """),
        {
            "cid": case_id,
            "priority": priority,
            "routing": routing,
            "sla_hours": sla_target_hours,
            "due_at": sla_response_due_at,
            "rule_id": matched_rule_id,
            "rationale": rationale,
            "policy_version": policy_version,
            "inputs": _json(dict(inputs)),
        },
    )


def get_case_decision(session: Session, case_id: UUID) -> dict[str, JsonValue] | None:
    """The case's current priority/SLA/routing decision (for the review read model + tests), or None if
    none computed yet. RLS-scoped."""
    row = session.execute(
        text("""
            SELECT priority, routing, sla_target_hours, sla_response_due_at, matched_rule_id,
                   rationale, policy_version, inputs, computed_at
            FROM case_decision WHERE case_id = :cid
            """),
        {"cid": case_id},
    ).first()
    if row is None:
        return None
    return {
        "priority": str(row[0]),
        "routing": str(row[1]),
        "sla_target_hours": float(row[2]),
        "sla_response_due_at": row[3].isoformat() if row[3] is not None else None,
        "matched_rule_id": str(row[4]),
        "rationale": str(row[5]),
        "policy_version": str(row[6]),
        "inputs": row[7],
        "computed_at": row[8].isoformat() if row[8] is not None else None,
    }


# ---------------------------------------------- the commit gate (Phase 7, §3 trust gate + §16.4)


def commit_status(session: Session, case_id: UUID) -> dict[str, JsonValue] | None:
    """The human-approval stamp on a case — ``{committed_at, committed_by}`` — or None if the case is
    not yet approved (or absent for this tenant). This is what the report generator checks: no stamp,
    no external artifact (CLAUDE.md §3). RLS-scoped."""
    row = session.execute(
        text("SELECT committed_at, committed_by FROM case_record WHERE id = :cid"),
        {"cid": case_id},
    ).first()
    if row is None or row[0] is None:
        return None
    return {"committed_at": row[0].isoformat(), "committed_by": str(row[1])}


def commit_case(
    session: Session, case_id: UUID, *, reviewer_id: str
) -> dict[str, JsonValue] | None:
    """Approve a case: stamp ``committed_at``/``committed_by`` and move it to ``committed``. This is the
    human-approval act the trust gate turns on — only after it may a report be issued or an external
    record written (CLAUDE.md §3).

    ONE-WAY and first-writer-wins: the ``COALESCE`` guards mean a re-commit never overwrites the original
    stamp (the approval can't be silently re-attributed or re-timed), so the call is idempotent — a
    replay returns the existing stamp unchanged. Returns the commit status, or None if the case is
    absent for this tenant (RLS fail-closed). The clock stamp is the DB's ``now()`` (server-side, not a
    client clock)."""
    exists = session.execute(
        text("SELECT 1 FROM case_record WHERE id = :cid"), {"cid": case_id}
    ).first()
    if exists is None:
        return None
    session.execute(
        text("""
            UPDATE case_record
            SET committed_at = COALESCE(committed_at, now()),
                committed_by = COALESCE(committed_by, :reviewer),
                case_state   = 'committed'
            WHERE id = :cid AND committed_at IS NULL
            """),
        {"cid": case_id, "reviewer": reviewer_id},
    )
    return commit_status(session, case_id)


def get_source_blob_ref(session: Session, source_document_id: UUID) -> tuple[str, str] | None:
    """The ``(blob_key, mime)`` for a source document, so the provenance route can stream the original
    (audio/image) a reviewer clicks through to. RLS-scoped: a document outside the tenant reads as None
    (fail-closed), never a cross-tenant blob leak."""
    row = session.execute(
        text("SELECT blob_key, mime FROM source_document WHERE id = :did"),
        {"did": source_document_id},
    ).first()
    return None if row is None else (str(row[0]), str(row[1]))
