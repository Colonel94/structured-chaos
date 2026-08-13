"""Generic file-drop adapter (TECH-SPEC §2.2, EDD §11).

The other half of the file-drop channel: a customer/agent drops a *single* file that is not a chat
export — a forwarded PDF, a photographed complaint, a lone voice note, or a plain-text note. Each
becomes one :class:`InboundMessage`. A ``.zip``/``.txt`` WhatsApp export is handled by
``whatsapp_export.parse_export`` instead; this path is for everything else.
"""

from __future__ import annotations

from datetime import datetime

from .models import InboundAttachment, InboundMessage, guess_mime

_CHANNEL = "file_drop"


def message_from_upload(
    filename: str,
    data: bytes,
    *,
    sender: str = "",
    received_at: datetime,
    text: str | None = None,
) -> InboundMessage:
    """Wrap one dropped file as a normalised message. A ``text/*`` upload with no separate note is
    carried as the message ``text`` (so a plain note needs no OCR/ASR round-trip); anything else is
    an attachment routed to normalisation by MIME. ``received_at`` is the ingest clock (there is no
    embedded send-time in a bare file); ``sender`` is passed through when the channel knows it."""
    mime = guess_mime(filename)
    if mime.startswith("text/") and text is None:
        return InboundMessage(
            channel=_CHANNEL,
            sender=sender,
            sent_at=received_at,
            text=data.decode("utf-8", errors="replace"),
            meta={"filename": filename},
        )
    return InboundMessage(
        channel=_CHANNEL,
        sender=sender,
        sent_at=received_at,
        text=text,
        attachments=(InboundAttachment(filename=filename, mime=mime, data=data),),
        meta={"filename": filename},
    )
