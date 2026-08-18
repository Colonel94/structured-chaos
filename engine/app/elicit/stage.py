"""The elicit pipeline stage — decide and record the next question for a case (Phase 5).

Chains off extraction: the moment a case's governed core is (re-)extracted, this runs, resolves the
anchor against the object store (so looked-up facts are CONFIRMED, not asked), applies the pure
:func:`app.elicit.policy.decide` (the anchor + two-drill budget, enforced in code), and persists the
move — ``case_state`` + an incremented ``question_count`` when a question is issued.

Idempotent on the EXTRACTED STATE, not the run: the stage-ledger key is the hash of the case's current
governed values, so a replayed extraction re-elicits to the same decision WITHOUT re-asking or
double-spending the budget; only genuinely new information (a customer reply → re-extraction changes
the governed state) produces a new key and advances the drill. The budget accumulates durably on
``case_record.question_count`` across turns.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..backends.interfaces import BlobStore, LLMBackend
from ..config import settings
from ..extract.schema import GOVERNED_KEYS
from ..obs.logging import get_logger
from ..resolve import resolve_object
from ..resolve.contradiction import detect_contradictions
from ..resolve.resolver import Resolution
from ..resolve.snapshot import snapshot_object
from ..store import api
from ..store.db import SessionFactory, tenant_session
from .policy import decide

log = get_logger(__name__)

_STAGE = "elicit"
POLICY_VERSION = "elicit-v1"  # in the idempotency key so a policy change re-elicits history


def _confirmation(obj: tuple[str, str | None, dict[str, object]]) -> str:
    """A short fact to STATE from the resolved object (turn a question into a confirmation, §5)."""
    object_type, external_id, _attrs = obj
    return (
        f"We've found your {object_type} {external_id}."
        if external_id
        else f"We've found your {object_type}."
    )


async def _record_provenance(
    session: Session,
    case_id: UUID,
    resolution: Resolution,
    *,
    governed: dict[str, str],
    blob: BlobStore,
    llm: LLMBackend | None,
) -> tuple[UUID | None, int]:
    """On bind, freeze the record as an ``object_snapshot`` and store any discrepancy as ``contradicts``
    citations (§5 — surface to the agent, never argue). Returns (snapshot_id, contradiction_count).
    """
    if resolution.mode == "silent" and resolution.object_id is not None:
        snap = await snapshot_object(
            session, case_id=case_id, object_id=resolution.object_id, blob=blob
        )
        n = 0
        obj = api.get_object(session, resolution.object_id)
        fault = governed.get("fault")
        if snap is not None and llm is not None and fault and obj is not None:
            contradictions = await detect_contradictions(llm, complaint=fault, record=obj[2])
            fault_ext = api.get_latest_extraction_id(session, case_id, "fault")
            if fault_ext is not None:
                for c in contradictions:
                    api.add_citation(
                        session,
                        extraction_id=fault_ext,
                        source_document_id=snap,
                        role="contradicts",
                        locator={
                            "record_field": c.record_field,
                            "record_value": c.record_value,
                            "claim": c.claim,
                        },
                    )
                n = len(contradictions)
        return snap, n

    # The anchor cross-check contradiction (quoted id ≠ sender phone) — snapshot the mismatched record
    # and cite anchor_value as contradicting it (a deterministic fraud/error signal, no model needed).
    if resolution.is_contradiction and resolution.object_id is not None:
        snap = await snapshot_object(
            session, case_id=case_id, object_id=resolution.object_id, blob=blob
        )
        anchor_ext = api.get_latest_extraction_id(session, case_id, "anchor_value")
        if snap is not None and anchor_ext is not None:
            api.add_citation(
                session,
                extraction_id=anchor_ext,
                source_document_id=snap,
                role="contradicts",
                locator={
                    "reason": "quoted id belongs to a different record than the sender's phone"
                },
            )
            return snap, 1
        return snap, 0
    return None, 0


async def elicit_case(
    tenant_id: str | UUID,
    case_id: UUID,
    *,
    llm: LLMBackend | None = None,
    blob: BlobStore | None = None,
    factory: sessionmaker[Session] | None = None,
) -> bool:
    """Run elicitation for one case. Returns True if a decision was recorded, False if skipped
    (case absent, already past elicitation, or this extracted state was already handled).

    ``blob`` enables object-snapshot-on-bind (provenance); ``llm`` enables the complaint-vs-record
    contradiction check. Both optional — without them the budget decision still runs (deterministic).
    """
    with tenant_session(tenant_id, factory=factory or SessionFactory) as session:
        state = api.get_case_elicit_state(session, case_id)
        if state is None:
            return False
        case_state, question_count, anchor_asked, contact_ref = state
        if case_state in ("in_review", "committed"):
            return False  # already handed off / finished — elicitation is done

        governed = api.get_field_values(session, case_id, GOVERNED_KEYS)

        # Idempotent on the EXTRACTED STATE: same governed values → same key → a replay is a no-op
        # (never re-asks). A customer reply changes the state → new key → the drill advances.
        state_material = json.dumps(governed, sort_keys=True)
        key = api.compute_idempotency_key(
            source_sha256=hashlib.sha256(f"{case_id}\x1f{state_material}".encode()).hexdigest(),
            stage=_STAGE,
            model_version="-",
            prompt_version=POLICY_VERSION,
            code_version=settings.code_version,
        )
        if not api.claim_stage(session, stage=_STAGE, idempotency_key=key, case_id=case_id):
            return False

        # Resolve the anchor: a stated key and/or the sender phone. A silent match lets us CONFIRM.
        anchor_value = governed.get("anchor_value")
        confirmation: str | None = None
        resolved = False
        resolution: Resolution | None = None
        if anchor_value or contact_ref:
            resolution = await resolve_object(session, anchor_id=anchor_value, phone=contact_ref)
            if resolution.mode == "silent" and resolution.object_id is not None:
                resolved = True
                obj = api.get_object(session, resolution.object_id)
                if obj is not None:
                    confirmation = _confirmation(obj)
        has_anchor = bool(anchor_value or contact_ref or resolved)

        plan = decide(
            set(governed),
            emotion=governed.get("emotion_signal"),
            has_anchor=has_anchor,
            anchor_asked=anchor_asked,
            question_count=question_count,
            confirmation=confirmation,
        )

        # Object-snapshot-on-bind + contradiction surfacing (§5). Runs when a bind/contradiction
        # occurred and a blob is available; a replay is skipped by the ledger above, so no duplicates.
        snapshot_id: UUID | None = None
        n_contradictions = 0
        if resolution is not None and blob is not None:
            snapshot_id, n_contradictions = await _record_provenance(
                session, case_id, resolution, governed=governed, blob=blob, llm=llm
            )

        asked = plan.next_question is not None
        meta: dict[str, object] = {
            "anchor_asked": anchor_asked or plan.question_kind == "anchor",
            "next_question": plan.next_question,
            "question_kind": plan.question_kind,
            "reason": plan.reason,
            "state": plan.state,
            "object_snapshot": str(snapshot_id) if snapshot_id is not None else None,
            "contradictions": n_contradictions,
        }
        api.apply_elicitation(session, case_id, state=plan.state, asked=asked, meta=meta)
        api.complete_stage(session, idempotency_key=key)
        log.info(
            "elicit.done",
            case_id=str(case_id),
            state=plan.state,
            kind=plan.question_kind,
            asked=asked,
            question_count=question_count + (1 if asked else 0),
            reason=plan.reason,
        )
        return True
