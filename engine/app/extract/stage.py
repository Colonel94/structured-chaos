"""The extract pipeline stage — normalised case text → persisted governed core + emergent (Phase 4).

Wires the extractor (EDD §6.2 STAGE 2) into the trust spine: reads the case's normalised text, runs
extraction, and writes every value through the append-only ``field_extraction`` log with complete
provenance (citations to the case's source documents), maintains the emergent-field registry, and
rebuilds the ``field_current`` projection — all inside one tenant transaction, guarded by the Phase-1
idempotency ledger (a replay is a no-op; a version bump re-extracts under a new run).

Design choices held here:
- **Refuse to guess persists as absence.** A ``null`` governed value (e.g. ``desired_outcome`` the
  customer never stated) is NOT recorded — its absence is what routes to elicitation (Phase 5).
- **Ungrounded emergent candidates are dropped**, never stored (closed-world grounding).
- **Confidence is a placeholder (0.5) pre-calibration.** Real per-field confidence is Phase 6
  (self-consistency + calibration); until then every value reads "uncertain" → flagged for human
  review, which is the safe default (refuse to guess). Documented, not hidden.
- The LLM call is metered against the case (GAP-1 consistency).
"""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from ..backends.interfaces import LLMBackend
from ..backends.registry import get_llm
from ..config import settings
from ..obs.logging import get_logger
from ..store import api, meter
from ..store.db import SessionFactory, tenant_session
from .extractor import extract
from .head_nouns import HEAD_NOUNS
from .prompt import PROMPT_VERSION

log = get_logger(__name__)

_STAGE = "extract"
# Placeholder confidence until Phase 6 calibration. 0.5 = "uncertain" → flagged for review (safe).
_PLACEHOLDER_CONFIDENCE = 0.5


def _name_hash(field_name: str) -> str:
    return hashlib.sha256(field_name.encode("utf-8")).hexdigest()


async def extract_case(
    tenant_id: str | UUID,
    case_id: UUID,
    *,
    llm: LLMBackend | None = None,
    factory: sessionmaker[Session] | None = None,
) -> bool:
    """Extract one case and persist its governed core + grounded emergent candidates. Returns True if
    extraction ran, False if it was skipped (no text yet, or already done this version)."""
    llm = llm or get_llm()
    with tenant_session(tenant_id, factory=factory or SessionFactory) as session:
        case_text = api.get_case_normalised_text(session, case_id)
        if not case_text.strip():
            log.info("extract.skip_empty", case_id=str(case_id))
            return False

        # Effective head vocabulary = universal seed + this tenant's MINTED heads (head-minting). Once a
        # tenant has minted e.g. `regulation`, extraction offers it directly instead of dumping to `other`.
        minted_glosses = api.list_minted_head_glosses(session)
        minted = list(minted_glosses)
        effective_heads = (*HEAD_NOUNS, *minted)
        # The minted heads change what extraction can PRODUCE, so they belong in the idempotency key:
        # minting a head must FORCE re-extraction of history (re-home the `other` facts into the new
        # column) rather than being skipped as "already done". No minted heads → signature empty → key
        # unchanged (backward compatible with every pre-minting extraction).
        vocab_sig = (
            "+h" + hashlib.sha256(",".join(sorted(minted)).encode()).hexdigest()[:8] if minted else ""
        )
        key = api.compute_idempotency_key(
            source_sha256=hashlib.sha256(case_text.encode("utf-8")).hexdigest(),
            stage=_STAGE,
            model_version=settings.ollama_model,
            # PROMPT_VERSION is in the key so a prompt bump (e.g. v8→v10) forces a fresh re-extraction
            # of already-extracted cases instead of the ledger skipping them as "done" — the §3/§4
            # guarantee that a better prompt re-runs history (was "" here, a silent re-extraction hole).
            # ``vocab_sig`` extends that to minted-head changes (head-minting re-homes history).
            prompt_version=PROMPT_VERSION + vocab_sig,
            code_version=settings.code_version,
        )
        if not api.claim_stage(session, stage=_STAGE, idempotency_key=key, case_id=case_id):
            log.info("extract.skip_done", case_id=str(case_id))
            return False

        result = await extract(
            case_text, llm=llm, heads=effective_heads, minted_glosses=minted_glosses
        )

        # Every extracted value cites the case's source documents (its provenance). Locator is null
        # (whole-source) — per-field span attribution is a Phase-7 review refinement.
        docs = api.list_case_source_documents(session, case_id)
        citations = [api.Citation(source_document_id=d, role="primary") for d in docs]
        run_id = uuid4()

        n_gov = 0
        for field_path, value in result.governed.items():
            if value is None or value == "":
                continue  # refuse-to-guess absence → not recorded (routes to elicitation)
            api.record_extraction(
                session,
                case_id=case_id,
                field_path=field_path,
                value=value,
                model=settings.ollama_model,
                model_version=settings.ollama_model,
                prompt_version=result.prompt_version,
                run_id=run_id,
                confidence=_PLACEHOLDER_CONFIDENCE,
                citations=citations,
                layer="governed_core",
            )
            n_gov += 1

        for attr in result.grounded_emergent:
            api.record_extraction(
                session,
                case_id=case_id,
                field_path=attr.name,
                value=attr.value,
                model=settings.ollama_model,
                model_version=settings.ollama_model,
                prompt_version=result.prompt_version,
                run_id=run_id,
                confidence=_PLACEHOLDER_CONFIDENCE,
                citations=citations,
                layer="emergent",
            )
            # Path A: register the composite (qualifier_head) AND roll its support up to the head —
            # the head is the column the convergence gate + promotion count on.
            api.register_emergent_field(
                session,
                field_name=attr.name,
                field_name_hash=_name_hash(attr.name),
                head=attr.head,
            )
            api.register_emergent_head(session, head=attr.head)

        api.rebuild_field_current(session, case_id)
        meter.meter_backend(
            session,
            backend=llm,
            interface="llm",
            backend_name=settings.llm_backend.value,
            model=settings.ollama_model,
            case_id=case_id,
        )
        api.complete_stage(session, idempotency_key=key)
        log.info(
            "extract.done",
            case_id=str(case_id),
            governed=n_gov,
            emergent=len(result.grounded_emergent),
            dropped_ungrounded=len(result.emergent) - len(result.grounded_emergent),
            field_validity=round(result.field_validity, 3),
        )
        return True
