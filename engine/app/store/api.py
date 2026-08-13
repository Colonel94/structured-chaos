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
