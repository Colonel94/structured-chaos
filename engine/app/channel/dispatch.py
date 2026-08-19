"""Dispatch — transmit a case's pending elicitation question, once (Phase 5, §5).

Reads the question the elicit stage recorded, claims it in the ``outbound_message`` ledger (idempotent),
sends it over the case's channel, and records the channel's ref. A case with no pending question, or no
recipient to reply to (a file drop with no return address), is a no-op. Idempotent by construction: the
claim's UNIQUE ``(case, question_hash)`` means a replay never double-sends.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..backends.interfaces import Channel
from ..obs.logging import get_logger
from ..store import api
from ..store.db import SessionFactory, tenant_session

log = get_logger(__name__)


def _question_hash(case_id: UUID, body: str) -> str:
    return hashlib.sha256(f"{case_id}\x1f{body}".encode()).hexdigest()


async def dispatch_case_question(
    tenant_id: str | UUID,
    case_id: UUID,
    *,
    channel: Channel,
    factory: sessionmaker[Session] | None = None,
) -> bool:
    """Send the case's pending elicitation question over ``channel``. Returns True if a message was
    transmitted, False if there was nothing to send (no pending question, no recipient, or already
    sent). The whole claim→send→record runs in one tenant transaction: a send failure rolls the claim
    back so a later retry re-sends; a success is durably audited."""
    with tenant_session(tenant_id, factory=factory or SessionFactory) as session:
        question = api.get_pending_question(session, case_id)
        if question is None:
            return False
        meta = api.get_case_elicit_state(session, case_id)
        if meta is None:
            return False
        _state, _qcount, _anchor_asked, recipient = meta
        if not recipient:
            log.info("dispatch.no_recipient", case_id=str(case_id))
            return (
                False  # nowhere to reply to (e.g. a file drop) → the operator relays; not a failure
            )

        channel_name = api.get_case_channel(session, case_id) or "whatsapp"
        qhash = _question_hash(case_id, question)
        claimed = api.claim_outbound(
            session,
            case_id=case_id,
            channel=channel_name,
            recipient=recipient,
            body=question,
            question_hash=qhash,
        )
        if claimed is None:
            return False  # already sent — never transmit the same question twice

        ref = await channel.send(recipient=recipient, text=question)
        api.mark_outbound_sent(session, claimed, external_ref=ref)
        log.info("dispatch.sent", case_id=str(case_id), channel=channel_name, ref=ref)
        return True
