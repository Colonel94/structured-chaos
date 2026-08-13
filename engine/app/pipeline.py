"""Pipeline stage bodies — the idempotent, retryable units the queue runs (EDD §2, CLAUDE.md §3).

Each stage: reopen a tenant session, **claim** the stage on the Phase-1 idempotency ledger, do the
work, **complete** it. A stage already ``done`` is skipped (replay is a no-op); a stage left
``running``/``failed`` by a crash is re-claimed and retried — so replay never loses or duplicates
work. These functions are called by the Procrastinate task bodies (``queue.py``) *and* directly by
the demo/tests, so the same code path is exercised with or without a worker running.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from .backends.interfaces import BlobStore
from .backends.registry import get_blob
from .config import settings
from .normalise.router import normalise
from .obs.logging import get_logger
from .store import api, meter
from .store.db import SessionFactory, tenant_session

log = get_logger(__name__)

_STAGE = "normalise"


def _model_version_tag(mime: str) -> str:
    """The normaliser identity that participates in the idempotency key — bump-sensitive, so a model
    swap (whisper weights, OCR lang/version) forces a fresh normalisation instead of colliding."""
    if mime.startswith("audio/"):
        return f"faster-whisper/{settings.whisper_model}"
    if mime.startswith("image/"):
        return f"paddleocr/{settings.ocr_lang}"
    if mime == "application/pdf":
        return "pdfplumber+pypdfium2"
    if mime.startswith("text/"):
        return f"passthrough/{settings.code_version}"
    return "raw"


async def normalise_source_document(
    tenant_id: str | UUID,
    source_document_id: UUID,
    *,
    blob: BlobStore | None = None,
    factory: sessionmaker[Session] | None = None,
) -> str | None:
    """Normalise one source document into ``normalised_content`` (transcript/OCR/text + provenance
    spans). Idempotent via the stage ledger; returns the normalised text, or ``None`` if the doc is
    absent (cross-tenant/unknown) or the stage was already done.

    One transaction brackets claim→work→complete so a crash mid-work leaves the stage re-claimable
    (never silently half-done). The expensive ASR/OCR call is awaited while the session is held —
    acceptable at PoC concurrency; the scale path splits claim and complete across two transactions.
    """
    blob = blob or get_blob()
    with tenant_session(tenant_id, factory=factory or SessionFactory) as session:
        doc = api.get_source_document(session, source_document_id)
        if doc is None:
            log.info("normalise.skip_absent", source_document_id=str(source_document_id))
            return None
        case_id, sha256, blob_key, mime = doc

        key = api.compute_idempotency_key(
            source_sha256=sha256,
            stage=_STAGE,
            model_version=_model_version_tag(mime),
            prompt_version="-",
            code_version=settings.code_version,
        )
        if not api.claim_stage(session, stage=_STAGE, idempotency_key=key, case_id=case_id):
            log.info("normalise.skip_done", source_document_id=str(source_document_id))
            return None

        data = await blob.get(blob_key)
        content = await normalise(str(source_document_id), data, mime)

        api.save_normalised_content(
            session,
            case_id=case_id,
            source_document_id=source_document_id,
            content_text=content.text,
            language=content.language,
            spans=[asdict(s) for s in content.spans],
            stage=content.stage,
            model=content.model,
            model_version=content.model_version,
            meta=content.meta,
        )

        # Cost-per-case meter (GAP-1 / Phase-2 invariant): record the inference call against the case
        # when this stage used a metered backend (ASR/OCR). Local backends → $0; wall_ms / audio-
        # seconds / tokens are the real per-case figure. Recorded in the same tenant transaction.
        if content.interface in ("asr", "ocr") and content.usage:
            backend_name = settings.asr_backend.value if content.interface == "asr" else "local"
            meter.meter_usage(
                session,
                interface=content.interface,
                backend=backend_name,
                model=content.model,
                usage=content.usage,
                case_id=case_id,
            )

        if content.degraded:
            # Normalisation was incomplete (e.g. OCR unavailable on this host). Leave the stage
            # re-claimable (H3) so a capable environment re-runs it, instead of committing an empty
            # 'done'. The partial text we did extract is already persisted above.
            api.fail_stage(session, idempotency_key=key)
            log.info(
                "normalise.degraded",
                source_document_id=str(source_document_id),
                stage=content.stage,
                reason=content.meta.get("ocr") or content.meta.get("pdf") or "incomplete",
            )
            return content.text or None

        api.complete_stage(session, idempotency_key=key)
        log.info(
            "normalise.done",
            source_document_id=str(source_document_id),
            stage=content.stage,
            chars=len(content.text),
            spans=len(content.spans),
        )
        return content.text
