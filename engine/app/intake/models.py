"""The channel-agnostic inbound model (EDD §11, TECH-SPEC §2.2).

Every intake channel — file drop, WhatsApp, email — is an *adapter* that normalises its input to
the same shape: a sequence of :class:`InboundMessage`. Nothing downstream knows or cares which
channel a message came from; the ingest orchestrator (``intake/ingest.py``) turns each message and
each attachment into an immutable, content-addressed ``source_document`` and drives the pipeline.

Design notes:
- ``sender`` is the anchor key downstream (the phone/email the customer used) — a *key*, not a
  field (concept §4.3). It is never invented; an adapter that can't determine it passes ``""``.
- Bytes live on the attachment until ingest stores them; the model itself carries no DB/blob state,
  so adapters are pure and unit-testable with no infrastructure.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from datetime import datetime

# WhatsApp voice notes are .opus (Android PTT) or .m4a (iOS); the stdlib map misses .opus on some
# platforms, so we pin the media types intake actually sees rather than trusting the OS registry.
_MIME_OVERRIDES = {
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".amr": "audio/amr",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def guess_mime(filename: str) -> str:
    """Best-effort MIME from a filename, with intake-specific overrides. Falls back to
    ``application/octet-stream`` (routed to the raw-bytes path, never guessed at)."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


@dataclass(frozen=True)
class InboundAttachment:
    """One media file carried by a message (voice note, photo, forwarded PDF). ``data`` are the
    raw bytes; ``mime`` decides the normalisation route. ``missing`` marks an attachment named in a
    chat export whose bytes were not included (the "without media" export) — recorded, not dropped,
    so the case reflects that something was sent even when we can't read it."""

    filename: str
    mime: str
    data: bytes
    missing: bool = False


@dataclass(frozen=True)
class InboundMessage:
    """One normalised inbound message. Either carries ``text``, or ``attachments``, or both. A pure
    system line (e.g. "Messages are end-to-end encrypted") is dropped by the adapter and never
    reaches here."""

    channel: str  # 'file_drop' | 'whatsapp' | 'email'
    sender: str  # the anchor key — phone/email/handle; "" if the adapter can't determine it
    sent_at: datetime
    text: str | None = None
    attachments: tuple[InboundAttachment, ...] = ()
    # Free-form, channel-specific hints (e.g. the raw export line number) — provenance/debugging
    # only, never load-bearing for extraction.
    meta: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.text is None and not self.attachments:
            raise ValueError("an InboundMessage must carry text or at least one attachment")
