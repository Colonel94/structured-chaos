"""Ingest orchestrator — normalised messages → case(s) + immutable source docs + queued normalise.

The channel-agnostic core of intake (EDD §2/§11). Given a batch of :class:`InboundMessage` from any
adapter (file-drop today; WhatsApp/email behind the same shape), for each sender in time order it:

1. **Windows** the message (``windowing.decide_window``) against the sender's latest case — opening a
   new case or continuing an existing one. A multi-issue export therefore splits into several cases;
   a follow-up folds into the open one.
2. Stores the message text and every attachment as an **immutable, content-addressed
   ``source_document``** (blob + row) — the original, retained forever (CLAUDE.md §3). Idempotent:
   re-ingesting the same bytes returns the existing row (no duplicate case, no duplicate document).
3. **Transactionally enqueues** the normalise stage for each stored document, on the *same*
   transaction as the writes — commit ⇒ both persist, rollback ⇒ neither (no orphan case, no phantom
   job).

The case exists on first contact, in ``created`` state, never blocked on completeness; the SLA clock
starts at the message's ``sent_at`` (§3). Missing attachments (media-less export) are counted, not
stored — there are no bytes to retain immutably, and a zero-byte blob would collapse them all.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..backends.interfaces import BlobStore, LLMBackend
from ..backends.registry import get_blob
from ..obs.logging import get_logger
from ..queue import defer_in_transaction, normalise_document
from ..store import api
from ..store.db import SessionFactory, tenant_session
from .models import InboundMessage
from .windowing import PriorCase, decide_window

log = get_logger(__name__)

# How much recent case text to hand the windowing classifier as context.
_PRIOR_TEXT_CHARS = 500


@dataclass
class IngestResult:
    """What one ingest produced: the cases touched (in order), the source documents stored, and how
    many attachments were skipped for having no bytes (media-less export)."""

    case_ids: list[UUID] = field(default_factory=list)
    source_document_ids: list[UUID] = field(default_factory=list)
    missing_attachments: int = 0


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity_sha(msg: InboundMessage) -> str | None:
    """The content hash that identifies a message for idempotency: its text if any, else its first
    real attachment. ``None`` when nothing is storable (an all-missing-media message), which is left
    to create a case reflecting that something arrived we couldn't retain."""
    if msg.text:
        return _sha(msg.text.encode("utf-8"))
    for att in msg.attachments:
        if att.data and not att.missing:
            return _sha(att.data)
    return None


async def ingest_messages(
    tenant_id: str | UUID,
    messages: list[InboundMessage],
    *,
    blob: BlobStore | None = None,
    llm: LLMBackend | None = None,
    factory: sessionmaker[Session] | None = None,
) -> IngestResult:
    """Ingest a batch of normalised messages for one tenant. Returns an :class:`IngestResult`.

    All writes + enqueues run in a single tenant transaction, so the whole batch is atomic. Windowing
    is applied per sender in ascending ``sent_at`` order; within the batch, an in-memory view of the
    case being built is used so a run of messages folds into one case without a DB round-trip each.
    """
    blob = blob or get_blob()
    result = IngestResult()
    tid = str(tenant_id)

    # Group by sender; process each sender's messages oldest-first (windowing is time-ordered).
    by_sender: dict[str, list[InboundMessage]] = {}
    for m in messages:
        by_sender.setdefault(m.sender, []).append(m)

    with tenant_session(tenant_id, factory=factory or SessionFactory) as session:
        for sender, msgs in by_sender.items():
            msgs.sort(key=lambda m: m.sent_at)
            # The case currently being built for this sender, if any (in-memory windowing view).
            building: PriorCase | None = None

            for msg in msgs:
                # Idempotency: a message whose exact content was already ingested is a no-op —
                # no new case, no new document (regression gate: re-ingest → no dup case).
                identity = _identity_sha(msg)
                if identity is not None and api.source_document_exists(session, identity):
                    continue

                prior = building or _load_prior(session, sender)
                decision = await decide_window(msg, prior, llm=llm)

                if decision.action == "follow_up" and decision.case_id is not None:
                    case_id = decision.case_id
                else:
                    case_id = api.create_case(
                        session,
                        channel=msg.channel,
                        first_contact_at=msg.sent_at,
                        contact_ref=sender or None,
                    )
                if case_id not in result.case_ids:
                    result.case_ids.append(case_id)
                log.info(
                    "ingest.window",
                    sender_len=len(sender),  # never log the sender itself (PII)
                    action=decision.action,
                    method=decision.method,
                    case_id=str(case_id),
                )

                accumulated: list[str] = [prior.prior_text] if (prior and building) else []

                # 1) the message text → a 'message' source document
                if msg.text:
                    sdid = await _store_and_queue(
                        session,
                        blob,
                        tid,
                        case_id=case_id,
                        data=msg.text.encode("utf-8"),
                        mime="text/plain",
                        channel=msg.channel,
                        received_at=msg.sent_at,
                        doc_kind="message",
                    )
                    result.source_document_ids.append(sdid)
                    accumulated.append(msg.text)

                # 2) each attachment with bytes → a 'file' source document
                for att in msg.attachments:
                    if att.missing or not att.data:
                        result.missing_attachments += 1
                        continue
                    sdid = await _store_and_queue(
                        session,
                        blob,
                        tid,
                        case_id=case_id,
                        data=att.data,
                        mime=att.mime,
                        channel=msg.channel,
                        received_at=msg.sent_at,
                        doc_kind="file",
                    )
                    result.source_document_ids.append(sdid)

                # Advance the in-memory building view for the next message in this run.
                building = PriorCase(
                    case_id=case_id,
                    case_state="created",
                    last_activity_at=msg.sent_at,
                    prior_text=(" ".join(accumulated))[-_PRIOR_TEXT_CHARS:],
                )
    return result


def _load_prior(session: Session, sender: str) -> PriorCase | None:
    """Build the windowing context from the sender's latest DB case (its state, last activity, and a
    recent text slice for the classifier)."""
    if not sender:
        return None
    found = api.latest_case_for_contact(session, contact_ref=sender)
    if found is None:
        return None
    case_id, case_state, last_activity = found
    prior_text = api.get_case_normalised_text(session, case_id)[-_PRIOR_TEXT_CHARS:]
    return PriorCase(
        case_id=case_id,
        case_state=case_state,
        last_activity_at=last_activity,
        prior_text=prior_text,
    )


async def _store_and_queue(
    session: Session,
    blob: BlobStore,
    tenant_id: str,
    *,
    case_id: UUID,
    data: bytes,
    mime: str,
    channel: str,
    received_at: datetime,
    doc_kind: str,
) -> UUID:
    """Store one document immutably and enqueue its normalise stage on this transaction."""
    sha = _sha(data)
    blob_key = await blob.put(sha, data, content_type=mime)
    sdid = api.add_source_document(
        session,
        case_id=case_id,
        sha256=sha,
        blob_key=blob_key,
        mime=mime,
        channel=channel,
        byte_size=len(data),
        received_at=received_at,
        doc_kind=doc_kind,
    )
    defer_in_transaction(
        session,
        normalise_document,
        tenant_id=tenant_id,
        source_document_id=str(sdid),
    )
    return sdid
