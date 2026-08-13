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
from ..config import settings
from ..obs.logging import get_logger
from ..queue import defer_in_transaction, normalise_document
from ..store import api, meter
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


def _message_key(msg: InboundMessage) -> str | None:
    """A per-message idempotency key = hash(sender + sent_at + content). Re-uploading the SAME export
    yields identical keys (skipped), but a customer legitimately repeating a message ("ok", "still
    broken") at a different time yields a different key (processed) — the H1 fix. Content-only keying
    over-matched: it dropped repeated messages tenant-wide and could fail to open a new case. ``None``
    when nothing is storable (an all-missing-media message), which is left to create a case."""
    content: str | None = None
    if msg.text:
        content = _sha(msg.text.encode("utf-8"))
    else:
        for att in msg.attachments:
            if att.data and not att.missing:
                content = _sha(att.data)
                break
    if content is None:
        return None
    material = f"{msg.sender}\x1f{msg.sent_at.isoformat()}\x1f{content}"
    return _sha(material.encode("utf-8"))


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

    PoC-scale note (M3): the whole batch runs in one tenant transaction spanning every ``blob.put``
    and (opt-in) classifier call. For typical exports (<~100 messages) this is fine and gives all-or-
    nothing atomicity; the scale path is to commit per bounded chunk. Blobs are content-addressed +
    write-once, so a rollback leaves only unreferenced (harmless, dedup-safe) objects.
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
                # Idempotency (regression gate: re-ingest → no dup case): claim a per-message key
                # on the Phase-1 stage ledger. A re-uploaded export re-claims a 'done' key → skipped;
                # a genuinely new message (incl. a repeated phrase at a new time) gets a fresh key.
                msg_key = _message_key(msg)
                if msg_key is not None and not api.claim_stage(
                    session, stage="intake_message", idempotency_key=msg_key, case_id=None
                ):
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
                # Meter the windowing classifier's LLM call against the case (GAP-1 completeness):
                # it only fires in the ambiguous gray band, and only when an llm is provided.
                if decision.method == "classifier" and llm is not None:
                    meter.meter_backend(
                        session,
                        backend=llm,
                        interface="llm",
                        backend_name=settings.llm_backend.value,
                        model=settings.ollama_model,
                        case_id=case_id,
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

                # Mark the message ingested (claim → done). Same transaction as the writes, so a
                # crash rolls back the claim too; a successful commit makes a re-upload a no-op.
                if msg_key is not None:
                    api.complete_stage(session, idempotency_key=msg_key)

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
    recent text slice for the classifier).

    Known limitation (M2): ``prior_text`` comes from ``normalised_content``, populated by the deferred
    normalise stage — so on a cross-call follow-up arriving before that stage has run, the classifier
    sees empty prior context and (by its safe bias) tends to open a new case. This degrades toward the
    cheap-to-fix direction (split, not wrong-merge); sourcing the slice from raw message text is a
    Phase-4+ improvement. Intra-batch runs are unaffected (they use the in-memory building view)."""
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
