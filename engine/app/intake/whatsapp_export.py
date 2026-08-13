"""In-house WhatsApp chat-export parser — file-drop channel (TECH-SPEC §2.2, EDD §11).

We parse the ``.txt``/``.zip`` export **in house** rather than depending on ``whatstk`` (GPL, §14 of
the licence ledger) — the grammar is small and we need to control attachment resolution and bidi
handling anyway. Two export dialects are supported:

- **Android**: ``13/08/2026, 14:05 - Sender Name: message`` (also ``M/D/YY, h:mm``). Attachments as
  ``IMG-20260813-WA0001.jpg (file attached)`` or ``<Media omitted>`` (media-less export).
- **iOS**: ``[13/08/2026, 2:05:33 PM] Sender: message`` (bracketed, seconds, AM/PM). Attachments as
  ``<attached: 00000042-PHOTO-2026-08-13.jpg>``. iOS sprinkles bidi marks (U+200E/200F) which we
  strip.

Robustness rules that matter on real exports:
- **Continuation lines** (a line that doesn't start with a timestamp) belong to the previous
  message — WhatsApp messages are multi-line. Never drop them.
- **Locale ambiguity** (``MM/DD`` vs ``DD/MM``) is real and unresolvable per-line; we try a fixed
  ladder of formats and, once a file's first timestamp parses, *lock that format* for the file so a
  day ≤12 doesn't silently flip interpretation mid-thread.
- **System messages** (no ``Sender:`` after the timestamp) are dropped — they carry no customer text.
- Media not included in the export is recorded as a ``missing`` attachment, never silently lost.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime

from .models import InboundAttachment, InboundMessage, guess_mime

_CHANNEL = "file_drop"

# Bidi/directionality marks iOS injects around timestamps, senders and filenames (LRM, RLM, LRE,
# RLE, PDF, LRI, RLI, FSI, PDI) — written as escapes so the source stays plain-ASCII.
_BIDI = dict.fromkeys(
    (0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x2066, 0x2067, 0x2068, 0x2069),
    None,
)

# Android:  "13/08/2026, 14:05 - Sender: body"   (also "M/D/YY, h:mm AM")
_ANDROID = re.compile(
    r"^(?P<ts>\d{1,4}[/.-]\d{1,2}[/.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)"
    r"\s+-\s+(?P<rest>.*)$"
)
# iOS:  "[13/08/2026, 2:05:33 PM] Sender: body"
_IOS = re.compile(
    r"^\[(?P<ts>\d{1,4}[/.-]\d{1,2}[/.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)"
    r"\]\s+(?P<rest>.*)$"
)

# Attachment markers. Android "(file attached)" / iOS "<attached: name>" / media-less placeholder.
_ATTACH_IOS = re.compile(r"^<attached:\s*(?P<name>.+?)>\s*$", re.IGNORECASE)
_ATTACH_ANDROID = re.compile(r"^(?P<name>.+?)\s*\((?:file attached|ملف مرفق)\)\s*$", re.IGNORECASE)
_MEDIA_OMITTED = re.compile(
    r"^(?:<Media omitted>|<وسائط مستبعدة>|image omitted|audio omitted)", re.IGNORECASE
)

# Timestamp format ladder — first one that parses the file's first timestamp is locked for the file.
_TS_FORMATS = (
    "%d/%m/%Y, %H:%M:%S",
    "%d/%m/%Y, %H:%M",
    "%m/%d/%Y, %H:%M:%S",
    "%m/%d/%Y, %H:%M",
    "%d/%m/%y, %H:%M:%S",
    "%d/%m/%y, %H:%M",
    "%m/%d/%y, %H:%M:%S",
    "%m/%d/%y, %H:%M",
    "%d/%m/%Y, %I:%M:%S %p",
    "%d/%m/%Y, %I:%M %p",
    "%m/%d/%Y, %I:%M:%S %p",
    "%m/%d/%Y, %I:%M %p",
    "%d/%m/%y, %I:%M:%S %p",
    "%d/%m/%y, %I:%M %p",
    "%m/%d/%y, %I:%M:%S %p",
    "%m/%d/%y, %I:%M %p",
)


def _clean(s: str) -> str:
    return s.translate(_BIDI).replace(" ", " ").replace("\xa0", " ").strip()


def _norm_ts(raw: str) -> str:
    # Unify separators/spacing so one format string matches, and normalise AM/PM casing.
    t = _clean(raw).replace(".", "/").replace("-", "/")
    t = re.sub(r"\s+", " ", t)
    return re.sub(r"\s*([APap][Mm])\s*$", lambda m: " " + m.group(1).upper(), t)


class _TsParser:
    """Locks the first format that parses, so a whole file reads with one interpretation."""

    def __init__(self) -> None:
        self._locked: str | None = None

    def parse(self, raw: str) -> datetime | None:
        # WhatsApp exports carry local wall-clock with no timezone. We assume UTC so every datetime
        # in the system is tz-aware (matching the DB's timestamptz + datetime.now(UTC)) — otherwise
        # windowing would mix naive export times with aware DB times and raise on subtraction. The
        # absolute offset is approximate; windowing only uses *relative* gaps, so it is unaffected.
        t = _norm_ts(raw)
        if self._locked:
            try:
                return datetime.strptime(t, self._locked).replace(tzinfo=UTC)
            except ValueError:
                pass  # a stray malformed line — fall through and re-scan the ladder
        for fmt in _TS_FORMATS:
            try:
                dt = datetime.strptime(t, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
            self._locked = fmt
            return dt
        return None


def _split_sender(rest: str) -> tuple[str | None, str]:
    """``"Sender: body"`` → ``("Sender", "body")``; a system line (no ``": "``) → ``(None, rest)``.
    Only the first ``": "`` splits, so a body containing a colon survives intact."""
    if ": " in rest:
        sender, body = rest.split(": ", 1)
        # A sender is a short handle/name/phone — a "colon" inside a URL/time isn't a sender.
        if "\n" not in sender and len(sender) <= 80:
            return _clean(sender), body
    return None, rest


def _match(line: str) -> tuple[str, str] | None:
    for rx in (_IOS, _ANDROID):
        m = rx.match(line)
        if m:
            return m.group("ts"), m.group("rest")
    return None


def _flush(
    ts: datetime | None,
    sender: str | None,
    body_lines: list[str],
    attachments: dict[str, bytes],
    line_no: int,
) -> InboundMessage | None:
    """Turn accumulated lines for one message into an InboundMessage, resolving any attachment
    reference against the zip's files. Returns ``None`` for a system message (no sender)."""
    if ts is None or sender is None:
        return None
    body = "\n".join(body_lines).strip()
    atts: list[InboundAttachment] = []
    text: str | None = body or None

    ios = _ATTACH_IOS.match(body)
    android = _ATTACH_ANDROID.match(body)
    marker = ios or android
    if marker:
        name = _clean(marker.group("name"))
        data = attachments.get(name)
        atts.append(
            InboundAttachment(
                filename=name,
                mime=guess_mime(name),
                data=data if data is not None else b"",
                missing=data is None,
            )
        )
        text = None  # the body was only the attachment reference
    elif _MEDIA_OMITTED.match(body):
        atts.append(
            InboundAttachment(
                filename="<omitted>", mime="application/octet-stream", data=b"", missing=True
            )
        )
        text = None

    if text is None and not atts:
        return None
    return InboundMessage(
        channel=_CHANNEL,
        sender=sender,
        sent_at=ts,
        text=text,
        attachments=tuple(atts),
        meta={"export_line": str(line_no)},
    )


def parse_export_text(
    transcript: str, *, attachments: dict[str, bytes] | None = None
) -> list[InboundMessage]:
    """Parse a WhatsApp export ``.txt`` body into normalised messages. ``attachments`` maps a
    filename (as referenced in the transcript) to its bytes, resolved from the ``.zip`` — pass
    ``{}`` for a media-less export (attachments become ``missing``)."""
    files = attachments or {}
    parser = _TsParser()
    out: list[InboundMessage] = []

    cur_ts: datetime | None = None
    cur_sender: str | None = None
    cur_body: list[str] = []
    cur_line = 0

    for i, raw_line in enumerate(transcript.splitlines(), start=1):
        line = _clean(raw_line)
        hit = _match(line)
        if hit is None:
            # Continuation of the current message (multi-line body). Keep original, unclean-stripped
            # spacing minimally — but we already cleaned bidi above.
            if cur_ts is not None:
                cur_body.append(line)
            continue
        ts_raw, rest = hit
        ts = parser.parse(ts_raw)
        if ts is None:
            # Looked like a header but the timestamp didn't parse → treat as continuation.
            if cur_ts is not None:
                cur_body.append(line)
            continue
        # A new message starts — flush the previous one.
        msg = _flush(cur_ts, cur_sender, cur_body, files, cur_line)
        if msg is not None:
            out.append(msg)
        sender, body = _split_sender(rest)
        cur_ts, cur_sender, cur_body, cur_line = ts, sender, [body], i

    msg = _flush(cur_ts, cur_sender, cur_body, files, cur_line)
    if msg is not None:
        out.append(msg)
    return out


def _pick_transcript(names: Iterable[str]) -> str | None:
    txts = [n for n in names if n.lower().endswith(".txt")]
    if not txts:
        return None
    # WhatsApp names it "_chat.txt" (iOS) or "WhatsApp Chat with X.txt" (Android). Prefer _chat.txt.
    for n in txts:
        if n.lower().endswith("_chat.txt"):
            return n
    return min(txts, key=len)


def parse_export_zip(data: bytes) -> list[InboundMessage]:
    """Parse a WhatsApp export ``.zip`` (transcript + media) into normalised messages. The
    transcript is auto-detected; every other entry is offered as a resolvable attachment."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        transcript_name = _pick_transcript(names)
        if transcript_name is None:
            raise ValueError("no .txt transcript found in the WhatsApp export zip")
        transcript = zf.read(transcript_name).decode("utf-8", errors="replace")
        # Index media by basename (the transcript references the bare filename).
        attachments = {n.rsplit("/", 1)[-1]: zf.read(n) for n in names if n != transcript_name}
    return parse_export_text(transcript, attachments=attachments)


def parse_export(filename: str, data: bytes) -> list[InboundMessage]:
    """Dispatch a file-drop upload to the right parser by extension. A ``.zip`` carries media; a
    ``.txt`` is media-less (attachment references become ``missing``)."""
    lower = filename.lower()
    if lower.endswith(".zip"):
        return parse_export_zip(data)
    if lower.endswith(".txt"):
        return parse_export_text(data.decode("utf-8", errors="replace"))
    raise ValueError(f"unsupported chat-export file type: {filename!r} (expected .zip or .txt)")
