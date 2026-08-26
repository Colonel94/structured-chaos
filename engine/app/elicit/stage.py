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
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..backends.interfaces import BlobStore, EmbeddingBackend, LLMBackend
from ..config import settings
from ..extract.schema import GOVERNED_KEYS
from ..obs.logging import get_logger
from ..resolve import resolve_object
from ..resolve.contradiction import detect_contradictions
from ..resolve.profile import is_contact_field
from ..resolve.resolver import Resolution
from ..resolve.snapshot import snapshot_object
from ..store import api
from ..store.db import SessionFactory, tenant_session
from .policy import FAULT_OPTIONS, decide

# The narrowing question appended to the record confirmation for the analytical fault drill (Moment 3):
# after STATING what the record shows ("...delivered 18:42, slot 17:00"), narrow to the complaint shape
# rather than asking an open question. Tappable FAULT_OPTIONS render alongside, free text always too.
_FAULT_NARROW_Q = "What went wrong with it?"

log = get_logger(__name__)

_STAGE = "elicit"
POLICY_VERSION = "elicit-v5"  # in the idempotency key so a policy change re-elicits history
# ^ v2 (2026-08-21): closed-world fault-grounding gate + the "what happened" drill (§4/§5).
# ^ v3 (2026-08-21b): the ANALYTICAL fault drill — when the anchor resolves, STATE the record and
#   narrow (Moment 3) instead of the open question; confirmation stated once across drills.
# ^ v4 (2026-08-21c): a fault that narrates the CUSTOMER'S STATE ("the customer feels dismissed") is not
#   a grounded fault → don't assert a fabricated category on pure emotion; investigate/hand off instead.
# ^ v5 (2026-08-21c): a CONTENTLESS opener ("something hurt me") is investigated ("what happened") BEFORE
#   any angry→handoff — never build/close a case from three vague words with no conversation.

# Is the fault a real, actionable problem the CUSTOMER described — or one the extractor fabricated?
# The grammar forces `fault` to be a non-null string (unlike `desired_outcome`), so on a contentless
# message the model invents one two ways, and we need TWO deterministic signals to reject both (§4/§5):
#
#   1. Closed-world lexical grounding (`_fault_grounded`): is the fault ATTESTED in the customer's own
#      words? A fault the extractor inferred from the resolved ORDER RECORD ("not delivered or incorrect"
#      on an "i feel sad" case) shares nothing but the object noun with the customer's text and fails.
#      A real complaint echoes their words ("melted", "late") and clears the bar.
#   2. Concrete category: did the extractor place the complaint in a real class, or fall back to
#      "other"/"UNCLEAR"? An EMOTIONAL message ("i feel let down") gets echoed into a grounded-but-empty
#      fault ("feels let down after an unspecified event") that passes signal 1 — but the model couldn't
#      categorise it, which is the tell that there is no actionable problem yet.
#
# A fault is trusted only if BOTH hold. Either failing → ask "what happened" instead of asserting an
# invented problem to the customer. The bias is deliberately toward asking (refuse-to-guess >
# confidently-wrong, Claim 2); over-asking a rare genuinely-"other" complaint is the safe direction.
# Language-agnostic token overlap (works for Arabic/code-switched); the stopword list de-noises English.
_UNCATEGORISED = frozenset({"other", "UNCLEAR"})  # the extractor saw no actionable complaint class
_GROUNDING_RATIO = 0.4
_STOPWORD_STR = (
    "the a an and or but not was were is are be been being to of in on at for with from by "
    "that this it its they them their you your we our us my me have has had do did does done "
    "as so if then than there here about into out over under can could will would should may "
    "no yes any some all one two get got"
)
_STOPWORDS = frozenset(_STOPWORD_STR.split())


def _content_words(text_value: str) -> set[str]:
    """Lowercased alphanumeric tokens of length ≥ 3, minus common English stopwords — the words that
    carry a fault's meaning (the problem descriptors), so grounding compares substance, not filler.
    """
    tokens = "".join(c.lower() if c.isalnum() else " " for c in text_value).split()
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


# When a message is pure emotion with no concrete problem ("i'm so upset, i feel dismissed"), the
# extractor doesn't leave the fault empty — it NARRATES THE CUSTOMER'S STATE ("the customer feels
# dismissed and doesn't know how to explain it"). That is not a fault we can act on or read back; it is
# the tell that there is no described problem yet. A real fault describes the THING/EVENT that went wrong
# ("the cake arrived smashed", "order BK-1004 was late"), not the person's feelings. We detect the
# customer-state narration by its subject and treat it as ungrounded — so the portal never asserts a
# category built on pure emotion, and the drill asks "what happened" (or, if angry, hands off) instead.
_CUSTOMER_STATE_STARTS = (
    "the customer",
    "customer ",
    "customer's",
    "the user",
    "the client",
    "the complainant",
    "they feel",
    "they are feeling",
    "they're feeling",
    "user feels",
    "user is",
)


def _is_customer_state_narration(fault_value: str) -> bool:
    """True when the fault describes the customer's feelings/state rather than a concrete problem — the
    extractor's fallback on a contentless/emotional message. These must not count as a grounded fault.
    """
    return fault_value.strip().lower().startswith(_CUSTOMER_STATE_STARTS)


def _fault_grounded(fault_value: str | None, customer_text: str) -> bool:
    """True iff the ``fault`` is a concrete problem attested in the customer's own words (§4). False when
    there is no fault, when the extractor merely narrated the customer's emotional state (no described
    problem), or when too few of its content words appear in the customer's text — i.e. it was inferred
    from the record, not heard from the customer. In every false case we ask "what happened" instead.
    """
    if not fault_value or not customer_text:
        return False
    if _is_customer_state_narration(fault_value):
        return False  # "the customer feels dismissed" — emotion restated, not a problem to act on
    fault_words = _content_words(fault_value)
    if not fault_words:
        return False
    text_words = _content_words(customer_text)
    hits = sum(1 for w in fault_words if w in text_words)
    return hits / len(fault_words) >= _GROUNDING_RATIO


# How many record facts to STATE in a confirmation, and the per-value length cap — enough to show the
# system already knows the order (the delay, the items, the slot), short enough to stay a confirmation.
_MAX_CONFIRM_FACTS = 4
_MAX_FACT_LEN = 40


def _confirmation(obj: tuple[str, str | None, dict[str, object]]) -> str:
    """State what the RECORD says, so the drill confirms instead of asks (§5, winning-condition Moment 3:
    "delivered 6:42pm against a 5:00pm slot" rather than "we've found your order").

    Domain-agnostic and GROUNDED: it surfaces the resolved object's own descriptive attributes verbatim
    — never generated, never inferred — because this text is customer-facing (§3: nothing confidently
    wrong to a customer). Identifiers are skipped (the contact phone/email, and the display id already
    shown); the first few remaining facts are stated in record order (an orders export usually leads with
    the salient columns). A future refinement can pair promised-vs-actual fields ("6:42 against 5:00")
    per-tenant; the general form states the facts plainly."""
    object_type, external_id, attrs = obj
    head = (
        f"We've found your {object_type} {external_id}"
        if external_id
        else f"We've found your {object_type}"
    )
    facts: list[str] = []
    for key, value in attrs.items():
        if is_contact_field(key):
            continue
        text = "" if value is None else " ".join(str(value).split())
        if not text or text == (external_id or ""):
            continue
        if len(text) > _MAX_FACT_LEN:
            text = text[: _MAX_FACT_LEN - 1].rstrip() + "…"
        facts.append(f"{key.replace('_', ' ')} {text}")
        if len(facts) >= _MAX_CONFIRM_FACTS:
            break
    return f"{head}: {', '.join(facts)}." if facts else f"{head}."


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
    embedder: EmbeddingBackend | None = None,
    factory: sessionmaker[Session] | None = None,
) -> bool:
    """Run elicitation for one case. Returns True if a decision was recorded, False if skipped
    (case absent, already past elicitation, or this extracted state was already handled).

    ``blob`` enables object-snapshot-on-bind (provenance); ``llm`` enables the complaint-vs-record
    contradiction check; ``embedder`` enables the guarded customer-name fallback when no key resolves.
    All are optional — without them the budget decision still runs (deterministic).
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
            # This exact extracted state was already elicited — the standing question/decision still
            # holds. But a customer reply that changed nothing extractable (an unhelpful "idk") still
            # arrived AFTER the last run, so stamp "processed just now": the portal status stops
            # reporting the reply as in-flight and shows the standing question again (not a false stall).
            api.touch_elicit_processed(session, case_id, at_iso=datetime.now(UTC).isoformat())
            return False

        # Resolve the anchor: a stated key and/or the sender phone. A silent match lets us CONFIRM.
        anchor_value = governed.get("anchor_value")
        confirmation: str | None = None
        resolved = False
        resolution: Resolution | None = None
        customer_name = next(
            (
                value
                for qualifier, value in api.get_emergent_values_by_head(session, case_id, "person")
                if qualifier in {"customer", "customer_name", "complainant", "caller", "client"}
            ),
            None,
        )
        if anchor_value or contact_ref or (customer_name and embedder is not None):
            resolution = await resolve_object(
                session,
                anchor_id=anchor_value,
                phone=contact_ref,
                name=customer_name,
                embedder=embedder,
            )
            if resolution.mode == "silent" and resolution.object_id is not None:
                resolved = True
                obj = api.get_object(session, resolution.object_id)
                if obj is not None:
                    confirmation = _confirmation(obj)
        # A stated anchor, or an object that actually resolved, counts. The sender's phone (contact_ref)
        # does NOT on its own — it may not be the number used to order, so if it didn't resolve we still
        # ask the anchor ("order number, or the phone you used to order").
        has_anchor = bool(anchor_value) or resolved

        # Is the fault a real, customer-described problem? Trust it only if it is attested in the
        # customer's own words (not inferred from the record) AND the extractor could place it in a
        # concrete class (not "other"/"UNCLEAR", the tell of pure emotion echoed into the fault). Either
        # failing → the policy asks "what happened" rather than asserting an invented problem (§4/§5).
        category_known = governed.get("category") not in _UNCATEGORISED
        fault_grounded = (
            _fault_grounded(governed.get("fault"), api.get_case_normalised_text(session, case_id))
            and category_known
        )

        # State the record confirmation exactly ONCE — on the first drill after the anchor, whichever it
        # is (fault or outcome) — so the customer never sees "We've found your order BK-1001: …" twice
        # across turns. A later drill narrows without restating the record.
        first_drill = max(0, question_count - (1 if anchor_asked else 0)) == 0
        state_conf = confirmation if first_drill else None

        # The ANALYTICAL fault drill (Moment 3): when the anchor resolved, STATE what the record shows
        # and narrow with tappable options — instead of an open "what happened". Only meaningful when we
        # have a confirmation to state; otherwise the policy falls back to the open question.
        fault_prompt = f"{state_conf} {_FAULT_NARROW_Q}" if state_conf else None

        plan = decide(
            set(governed),
            emotion=governed.get("emotion_signal"),
            has_anchor=has_anchor,
            anchor_asked=anchor_asked,
            question_count=question_count,
            confirmation=state_conf,
            fault_grounded=fault_grounded,
            category_known=category_known,
            fault_prompt=fault_prompt,
            fault_options=FAULT_OPTIONS if fault_prompt else None,
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
            # Tappable options for this question (outcome drill), so every channel renders the SAME set
            # (portal buttons, WhatsApp interactive) — a hint the client shows alongside free text.
            "options": list(plan.options) if plan.options else None,
            "object_snapshot": str(snapshot_id) if snapshot_id is not None else None,
            "contradictions": n_contradictions,
            # So the customer-facing read-back never asserts a category derived from an ungrounded fault
            # (portal store suppresses it): "we won't tell you your problem until you've told us" (§5).
            "fault_grounded": fault_grounded,
            # When this move was decided — the portal status compares it to the newest inbound message
            # to tell "we're processing your latest reply" from "here's the standing question" (chat UX).
            "processed_at": datetime.now(UTC).isoformat(),
        }
        api.apply_elicitation(session, case_id, state=plan.state, asked=asked, meta=meta)
        api.complete_stage(session, idempotency_key=key)
        # Chain (Phase 5): when a question was issued, transmit it off the SAME transaction that
        # recorded it (mirroring extract→elicit) — the drill's question is sent with no manual trigger,
        # and the customer's reply re-enters intake to advance the loop. Lazy import avoids a cycle.
        if asked:
            from ..queue import defer_in_transaction, dispatch_case_task

            defer_in_transaction(
                session, dispatch_case_task, tenant_id=str(tenant_id), case_id=str(case_id)
            )
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
