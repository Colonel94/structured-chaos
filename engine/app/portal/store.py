"""Portal store reads — embed-key resolution + the REDACTED public status projection (PORTAL.md §4–5).

Two things the public surface needs that the agent read model must never do:
  * ``resolve_embed_key`` — turn the public embed key into ``(tenant_id, allowed_origins)`` via the
    ``app.embed_key`` RLS policy (migration 0018), before any tenant is known. Read-only, one row.
  * ``public_status`` — a customer-safe projection of a case: reference, an honestly-staged progress or a
    plain-language state, the deadline, a one-sentence read-back, and the pending question (+ options).
    It NEVER emits case_state/enums/confidence/priority/routing/agent identity/emergent names.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from ..store import api
from ..store.db import SessionFactory

# category enum → plain customer words (translated server-side; the enum itself is never sent)
_CATEGORY_PHRASE = {
    "product_fault": "a problem with a product",
    "service_fault": "a problem with the service",
    "delivery_fulfilment": "a delivery problem",
    "billing_charge": "a billing problem",
    "record_accuracy": "an issue with your records",
    "access_availability": "a problem accessing your account or service",
    "staff_conduct": "an issue with how you were treated",
    "safety_health": "a safety or health concern",
    "other": "an issue",
}
_OUTCOME_PHRASE = {
    "refund": "you'd like a refund",
    "replacement": "you'd like a replacement",
    "repair_redo": "you'd like it put right",
    "escalation": "you'd like it escalated",
    "information": "you'd like an answer",
    "acknowledgement": "you'd like it acknowledged",
    "other": "you've told us what you'd like",
}

# case_state (+ whether a question is pending) → customer-facing copy. No raw state ever leaves here.
_STATE_COPY = {
    "actionable": ("We've got it — and we're on it", "Your case is with our team."),
    # in_review = a human is stepping in (an angry/upset customer isn't interrogated, §5; or a flagged
    # case). Warm + honest — a person is taking over and will reach out — never "we've got everything we
    # need" (which reads as done, and isn't true when the case is still thin).
    "in_review": (
        "We're getting a person on your team to help",
        "This clearly matters, so someone will look at it personally and reach out to you directly.",
    ),
    "committed": ("This has been reviewed and actioned", "Thanks for letting us know."),
}
_NEEDS_INPUT = (
    "We need one more thing from you",
    "Just one quick question to finish your case.",
)


@contextmanager
def embed_key_session(
    embed_key: str, *, factory: sessionmaker[Session] = SessionFactory
) -> Any:
    """A session scoped by the ``app.embed_key`` GUC — the RLS policy then exposes exactly the one tenant
    row whose embed_key matches. Transaction-local (is_local=true), like ``tenant_session``.
    """
    session = factory()
    try:
        session.execute(
            text("SELECT set_config('app.embed_key', :k, true)"), {"k": embed_key}
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def resolve_embed_key(
    embed_key: str, *, factory: sessionmaker[Session] = SessionFactory
) -> tuple[UUID, list[str]] | None:
    """``(tenant_id, allowed_origins)`` for a public embed key, or None if unknown. RLS-scoped to that
    one row via the embed_key policy — a wrong/blank key reads nothing (fail-closed)."""
    if not embed_key or not embed_key.strip():
        return None
    with embed_key_session(embed_key.strip(), factory=factory) as s:
        row = s.execute(
            text("SELECT id, allowed_origins FROM tenant WHERE embed_key = :k"),
            {"k": embed_key.strip()},
        ).first()
    if row is None:
        return None
    origins = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    return UUID(str(row[0])), [str(o) for o in origins]


def tenant_allowed_origins(session: Session) -> list[str]:
    """The current tenant's portal CORS allowlist (session is already tenant-GUC scoped)."""
    raw = session.execute(text("SELECT allowed_origins FROM tenant LIMIT 1")).scalar_one_or_none()
    if raw is None:
        return []
    origins = raw if isinstance(raw, list) else json.loads(raw or "[]")
    return [str(origin) for origin in origins]


def _reference(case_id: UUID) -> str:
    """A short, human case reference shown to the customer (they hold the token; this is just a label)."""
    return f"C-{str(case_id).split('-')[0].upper()}"


def _read_back(gov: dict[str, str]) -> str | None:
    """One honest sentence in plain words from the governed core — never a field path, enum, or number."""
    category = gov.get("category")
    if not category or category == "UNCLEAR":
        return None
    phrase = _CATEGORY_PHRASE.get(category, "an issue")
    anchor = gov.get("anchor_value")
    if anchor:
        phrase += f" with order {anchor}"
    outcome = gov.get("desired_outcome")
    tail = _OUTCOME_PHRASE.get(outcome, "") if outcome else ""
    sentence = f"Looks like {phrase}"
    if tail:
        sentence += f", and {tail}"
    return sentence + "."


def _processing_stage(session: Session, case_id: UUID, category: str | None) -> str:
    """The honest progress stage, derived from what is actually PERSISTED (never a client timer)."""
    if category:
        return "checking"  # governed core extracted; decision/elicit about to finish
    has_norm = session.execute(
        text("SELECT 1 FROM normalised_content WHERE case_id = :c LIMIT 1"),
        {"c": case_id},
    ).first()
    if has_norm:
        return "understanding"
    has_audio = session.execute(
        text(
            "SELECT 1 FROM source_document WHERE case_id = :c AND mime LIKE 'audio/%' LIMIT 1"
        ),
        {"c": case_id},
    ).first()
    return "transcribing" if has_audio else "received"


def _reprocessing(
    session: Session, case_id: UUID, first_contact_at: datetime
) -> tuple[bool, datetime]:
    """Is a customer reply still being processed, and since when? A reply re-enters intake as a new
    inbound message; until the elicit stage re-runs on it, the case still carries the PRIOR turn's
    question, which the status projection must not serve as "ready" (it would freeze the chat on a stale
    question). True when the newest inbound message is newer than the last elicit decision. Returns
    (reprocessing, processing_since) — the clock the stall timer runs from (the latest message, so a
    turn-2 reply's stall isn't measured from the original first contact)."""
    row = session.execute(
        text("""
            SELECT
              (SELECT max(received_at) FROM source_document
                 WHERE case_id = :c AND doc_kind IN ('message','file')) AS newest_in,
              (external_mappings #>> '{elicit,processed_at}')::timestamptz AS processed_at
            FROM case_record WHERE id = :c
            """),
        {"c": case_id},
    ).first()
    newest_in: datetime | None = row[0] if row else None
    processed_at: datetime | None = row[1] if row else None
    since = newest_in or first_contact_at
    reproc = (
        newest_in is not None and processed_at is not None and newest_in > processed_at
    )
    return reproc, since


def worker_down(session: Session, *, liveness_seconds: int) -> bool:
    """Is the intake worker DOWN? (R3) True ONLY when a heartbeat row exists for the default queue but
    is older than ``liveness_seconds`` — i.e. a worker ran and then died. Returns False when NO heartbeat
    row exists at all (a cold start / never-provisioned worker), so a brand-new stack falls back to the
    gentler time-based stall copy rather than crying "snag" before the worker has beat even once. This
    distinguishes a genuinely dead worker (advance the customer to a human NOW) from a slow one.
    """
    beat = session.execute(
        text("SELECT max(beat_at) FROM worker_heartbeat WHERE queue LIKE '%default%'")
    ).scalar()
    if beat is None:
        return False
    return bool((datetime.now(UTC) - beat).total_seconds() > liveness_seconds)


def public_status(
    session: Session,
    case_id: UUID,
    *,
    stall_seconds: int,
    worker_liveness_seconds: int | None = None,
) -> dict[str, Any] | None:
    """The customer-safe status for one case, or None if absent for this tenant (RLS fail-closed)."""
    row = session.execute(
        text("SELECT case_state, first_contact_at FROM case_record WHERE id = :c"),
        {"c": case_id},
    ).first()
    if row is None:
        return None
    case_state = str(row[0])
    first_contact_at: datetime = row[1]
    gov = api.get_field_values(
        session, case_id, ["category", "anchor_value", "desired_outcome"]
    )
    ref = _reference(case_id)

    # PROCESSING FAILED: a durable pipeline stage exhausted its retries (an Ollama crash, a dropped job).
    # The case must NOT render as a finished-but-empty case ("we read it and found nothing"). Show the
    # honest stalled/handoff copy — the case exists, originals are safe, a person takes over — reusing the
    # widget's stalled presentation (PORTAL.md §8; owner directive 2026-08-21). Never resend, never a lie.
    if case_state == "processing_failed":
        return {
            "ref": ref,
            "processing": True,
            "stalled": True,
            "stage": "delayed",
            "headline": "We've hit a snag on our end — a person is taking over",
            "detail": "We've got everything you sent and it's safe. Someone on our team will pick this "
            "up personally — you don't need to resend it.",
        }

    # STILL PROCESSING: either the first pass hasn't reached elicitation yet (state == 'created'), or a
    # customer reply is being re-processed (the case carries the prior turn's question until elicit
    # re-runs). Both must read as "we're working on it", not a stale ready-state (the chat would freeze).
    reproc, since = _reprocessing(session, case_id, first_contact_at)
    if case_state == "created" or reproc:
        # WORKER DOWN (R3): if the intake worker's heartbeat has gone stale, nothing will advance this
        # case until a human steps in — say so honestly and immediately, rather than an open-ended
        # spinner that implies progress. Same handoff copy as the processing_failed terminal state.
        if worker_liveness_seconds is not None and worker_down(
            session, liveness_seconds=worker_liveness_seconds
        ):
            return {
                "ref": ref,
                "processing": True,
                "stalled": True,
                "stage": "delayed",
                "headline": "We've hit a snag on our end — a person is taking over",
                "detail": "We've got everything you sent and it's safe. Someone on our team will pick "
                "this up personally — you don't need to resend it.",
            }
        age = (datetime.now(UTC) - since).total_seconds()
        if age > stall_seconds:
            # A restart may have dropped the in-flight background task — never hang the customer on a
            # spinner. The case exists regardless; say so honestly (PORTAL.md §8, the stall guarantee).
            return {
                "ref": ref,
                "processing": True,
                "stalled": True,
                "stage": "delayed",
                "headline": "This is taking a little longer than usual",
                "detail": "We've got your case and we'll pick it up — you don't need to resend it.",
            }
        return {
            "ref": ref,
            "processing": True,
            "stalled": False,
            "stage": _processing_stage(session, case_id, gov.get("category")),
            "headline": "Reading what you sent…",
            "detail": "This usually takes a few seconds.",
        }

    # READY: elicitation has run → a status + maybe one question.
    pending = api.get_pending_question(session, case_id)
    elicit = session.execute(
        text(
            "SELECT external_mappings #> '{elicit,options}' FROM case_record WHERE id = :c"
        ),
        {"c": case_id},
    ).scalar()
    options = list(elicit) if isinstance(elicit, list) else None
    # Never assert a category built on a fault the customer didn't describe: if the elicit stage flagged
    # the fault as ungrounded, drop the category from the read-back so we don't tell the customer what
    # their problem is before they've told us (§5). Only suppress on an explicit False (None = unknown).
    fault_grounded = session.execute(
        text(
            "SELECT external_mappings #> '{elicit,fault_grounded}' FROM case_record WHERE id = :c"
        ),
        {"c": case_id},
    ).scalar()
    if fault_grounded is False:
        gov = {k: v for k, v in gov.items() if k != "category"}
    if pending:
        headline, detail = _NEEDS_INPUT
    else:
        headline, detail = _STATE_COPY.get(
            case_state,
            ("We've got it — and we're on it", "Your case is with our team."),
        )
    decision = api.get_case_decision(session, case_id)
    deadline = decision.get("sla_response_due_at") if decision else None
    return {
        "ref": ref,
        "processing": False,
        "headline": headline,
        "detail": detail,
        "deadline": deadline,
        "understood": _read_back(gov),
        "question": pending,
        "options": options,
    }
