"""Retroactive backfill — re-extract a promoted concept across the retained originals of history
(STAGE 6, the moat, 2026-08-14).

This is the expensive, correct half of promotion (CLAUDE.md §10 "distrust the cheap path"): NOT a
re-projection of already-extracted values, but genuine re-EXTRACTION against the immutable source
documents, so a case that never had the concept — because the forward extractor wasn't looking for it
then — gets it now. New values land as fresh ``field_extraction`` rows with fresh citations; the log
stays append-only. Every attempt is recorded (``found``/``absent``) so a genuinely-empty case is never
re-extracted twice (idempotent, bounded).

Scoped tightly because one promotion can fan out to every historical case in a category — the single
largest cost spike in the system: one concept only, a focused prompt, cases in the concept's category
oldest-first, in bounded batches, EACH re-extraction metered per case (cost-per-case must be visible
before this runs on anything real).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid5

from sqlalchemy.orm import Session, sessionmaker

from ..backends.interfaces import LLMBackend
from ..backends.registry import get_llm
from ..confidence import load_calibration
from ..config import settings
from ..extract.concept_extract import CONCEPT_PROMPT_VERSION, extract_concept
from ..obs.logging import get_logger
from ..store import api, meter
from ..store.db import SessionFactory, tenant_session

log = get_logger(__name__)

# Namespace for deterministic backfill run_ids: hash(case, concept, prompt_version) → the same
# (case, concept) re-extraction always writes under the same run_id, so record_extraction's
# UNIQUE(run_id, field_path) makes a crash-retry idempotent even before the attempt marker lands.
_NS = UUID("b1f0a17e-0000-4a11-b000-0000c0ffee00")
# Same calibrated confidence as the forward extract stage (Phase 6). A backfilled concept is an emergent
# attribute that passed the grounding gate (extract_concept returns only grounded attrs), and emergent is
# uncalibrated (no gold), so its honest confidence is the grounding signal — here grounded → 1.0.
_CALIBRATION = load_calibration()


def _name_hash(field_name: str) -> str:
    return hashlib.sha256(field_name.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BackfillBatchResult:
    concept_key: str
    scanned: int  # cases pulled this batch
    found: int  # cases where re-extraction wrote a value
    absent: int  # cases legitimately without the concept (marked, never retried)
    skipped: int  # cases not yet extractable (no normalised text / no source doc) — no marker
    more: bool  # a full batch came back → likely more cases remain → re-enqueue


async def backfill_concept_batch(
    tenant_id: str | UUID,
    *,
    concept_key: str,
    head: str,
    qualifier: str | None,
    categories: list[str],
    batch_size: int,
    llm: LLMBackend | None = None,
    factory: sessionmaker[Session] | None = None,
) -> BackfillBatchResult:
    """Re-extract ``concept_key`` (a promoted ``head`` or its ``qualifier`` variant) across up to
    ``batch_size`` un-attempted cases in ``categories``, oldest-first. Each case is its own
    transaction (write + marker atomic) so a crash mid-batch leaves completed cases done and the rest
    resumable. Returns per-batch counts + ``more`` (whether to re-enqueue for the next batch)."""
    llm = llm or get_llm()
    factory = factory or SessionFactory

    with tenant_session(tenant_id, factory=factory) as s:
        case_ids = api.cases_needing_backfill(
            s, concept_key=concept_key, categories=categories, limit=batch_size
        )

    found = absent = skipped = 0
    for case_id in case_ids:
        with tenant_session(tenant_id, factory=factory) as s:
            case_text = api.get_case_normalised_text(s, case_id)
            docs = api.list_case_source_documents(s, case_id)
        if not case_text.strip() or not docs:
            skipped += 1  # not yet extractable — no marker, so a later normalise makes it retryable
            continue

        attr = await extract_concept(case_text, head=head, qualifier=qualifier, llm=llm)

        with tenant_session(tenant_id, factory=factory) as s:
            # Meter the re-extraction against THIS case — the cost fans out but is attributed per case.
            meter.meter_backend(
                s,
                backend=llm,
                interface="llm",
                backend_name=settings.llm_backend.value,
                model=settings.ollama_model,
                case_id=case_id,
            )
            if attr is not None:
                run_id = uuid5(_NS, f"{case_id}:{concept_key}:{CONCEPT_PROMPT_VERSION}")
                citations = [api.Citation(source_document_id=d, role="primary") for d in docs]
                api.record_extraction(
                    s,
                    case_id=case_id,
                    field_path=attr.name,
                    value=attr.value,
                    model=settings.ollama_model,
                    model_version=settings.ollama_model,
                    prompt_version=CONCEPT_PROMPT_VERSION,
                    run_id=run_id,
                    confidence=_CALIBRATION.confidence(attr.name, attr.value, grounding=1.0),
                    citations=citations,
                    layer="emergent",
                )
                api.register_emergent_field(
                    s, field_name=attr.name, field_name_hash=_name_hash(attr.name), head=attr.head
                )
                api.register_emergent_head(s, head=attr.head)
                api.rebuild_field_current(s, case_id)
                api.record_backfill_attempt(
                    s, case_id=case_id, concept_key=concept_key, outcome="found"
                )
                found += 1
            else:
                api.record_backfill_attempt(
                    s, case_id=case_id, concept_key=concept_key, outcome="absent"
                )
                absent += 1

    more = len(case_ids) == batch_size
    log.info(
        "backfill.batch",
        concept=concept_key,
        scanned=len(case_ids),
        found=found,
        absent=absent,
        skipped=skipped,
        more=more,
    )
    return BackfillBatchResult(
        concept_key=concept_key,
        scanned=len(case_ids),
        found=found,
        absent=absent,
        skipped=skipped,
        more=more,
    )
