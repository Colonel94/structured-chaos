"""WhatsApp Cloud API webhook — the live receive path (Phase 5 egress/ingress, deferred-until-now).

Meta calls this endpoint:
  * GET  — one-time verification. Meta sends ``hub.mode``/``hub.verify_token``/``hub.challenge``; we echo
           the challenge iff the token matches ``whatsapp_verify_token``.
  * POST — an inbound event. We verify the ``X-Hub-Signature-256`` HMAC (if an app secret is set), ACK
           200 immediately (Meta retries on any slow/non-200), and process the message(s) in the
           BACKGROUND: ingest → normalise → extract → decide → elicit → dispatch the drill question back
           to the sender over the SAME WhatsApp channel. The sender's phone (their wa_id) is the anchor,
           so a case whose order is on file resolves silently and the reply CONFIRMS the record (Moment 3).

The webhook carries no ``X-Tenant-Id`` (it is Meta calling, not the review UI), so the inbound message is
routed to ``whatsapp_tenant_id`` — one WhatsApp number ↔ one tenant for the PoC. A customer's reply is
just another inbound message from the same sender; windowing attaches it to the open case and the drill
advances to actionable. All processing is idempotent (message-content dedup + the outbound ledger), so a
Meta retry never doubles a case or a reply.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..obs.logging import get_logger

router = APIRouter(prefix="/api/whatsapp")
log = get_logger(__name__)


@router.get("/webhook")
def verify(request: Request) -> Response:
    """Meta's subscription handshake: echo ``hub.challenge`` iff the verify token matches."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    if mode == "subscribe" and token and token == settings.whatsapp_verify_token:
        return PlainTextResponse(challenge)
    log.info(
        "whatsapp.verify_rejected", mode=mode, token_ok=token == settings.whatsapp_verify_token
    )
    return PlainTextResponse("verification failed", status_code=403)


def _signature_ok(raw: bytes, header: str | None) -> bool:
    """Verify Meta's ``X-Hub-Signature-256: sha256=<hmac>`` over the RAW body, using the app secret. If no
    app secret is configured we do not enforce it (dev), but with one set a bad/absent signature fails.
    """
    secret = settings.whatsapp_app_secret
    if not secret:
        return True  # not configured → dev, skip (documented in WHATSAPP-SETUP.md)
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def _extract_text_messages(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Pull ``(sender_wa_id, text)`` from a Meta webhook payload. Ignores non-text events (status
    receipts, reactions) — those have no ``messages`` of ``type == "text"``."""
    out: list[tuple[str, str]] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []) or []:
                if msg.get("type") != "text":
                    continue
                sender = str(msg.get("from", "")).strip()
                body = str((msg.get("text") or {}).get("body", "")).strip()
                if sender and body:
                    out.append((sender, body))
    return out


async def _process(tenant: str, sender: str, body: str) -> None:
    """Run the real pipeline for one inbound WhatsApp message, then send the drill question back. Mirrors
    the inline ``/api/ingest`` pipeline but with ``channel="whatsapp"`` + the sender as the anchor, and an
    explicit dispatch so the reply goes out without depending on a running worker (idempotent either way).
    """
    from ..backends.registry import get_blob, get_channel, get_llm
    from ..channel.dispatch import dispatch_case_question
    from ..elicit.stage import elicit_case
    from ..extract.stage import extract_case
    from ..intake.ingest import ingest_messages
    from ..intake.models import InboundMessage
    from ..pipeline import normalise_source_document
    from ..rules.stage import decide_case
    from ..store.db import SessionFactory

    try:
        blob, llm = get_blob(), get_llm()
        msg = InboundMessage(
            channel="whatsapp",
            sender=sender,  # the wa_id — the anchor the drill resolves the order on
            sent_at=datetime.now(UTC),  # the clock starts at first contact
            text=body,
            attachments=(),
        )
        ing = await ingest_messages(tenant, [msg], blob=blob, factory=SessionFactory)
        for sdid in ing.source_document_ids:
            await normalise_source_document(tenant, sdid, blob=blob, factory=SessionFactory)
        channel = get_channel()
        for cid in ing.case_ids:
            await extract_case(tenant, cid, llm=llm, factory=SessionFactory)
            decide_case(tenant, cid, factory=SessionFactory)
            await elicit_case(tenant, cid, llm=llm, blob=blob, factory=SessionFactory)
            # Send the pending drill question (the confirmation) back to the sender. Idempotent — the
            # outbound ledger's UNIQUE (case, question_hash) means a Meta retry never double-sends.
            await dispatch_case_question(tenant, cid, channel=channel, factory=SessionFactory)
        log.info(
            "whatsapp.processed", tenant=tenant, cases=len(ing.case_ids), sender_len=len(sender)
        )
    except Exception:  # a webhook must never surface a 500 to Meta; log and move on
        log.exception("whatsapp.process_failed", tenant=tenant)


@router.post("/webhook")
async def receive(request: Request, background: BackgroundTasks) -> Response:
    """ACK Meta fast (200), then process inbound text messages in the background."""
    raw = await request.body()
    if not _signature_ok(raw, request.headers.get("X-Hub-Signature-256")):
        log.info("whatsapp.bad_signature")
        return PlainTextResponse("bad signature", status_code=403)

    import json

    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return Response(status_code=200)  # malformed → ACK anyway so Meta doesn't retry forever

    tenant = settings.whatsapp_tenant_id
    messages = _extract_text_messages(payload)
    if not tenant:
        if messages:
            log.info("whatsapp.no_tenant_configured", messages=len(messages))
        return Response(status_code=200)

    for sender, body in messages:
        background.add_task(_process, tenant, sender, body)
    return Response(status_code=200)
