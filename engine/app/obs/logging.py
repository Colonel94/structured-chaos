"""Structured logging with a fail-safe PII redaction processor.

Trust invariant (CLAUDE.md §3): **no customer data in logs.** Rather than trusting every call
site to remember, a structlog processor scrubs each event *before* it is rendered:

1. keys whose name marks them as sensitive (phone, email, message body, transcript, address, …)
   are replaced wholesale;
2. any remaining string value is pattern-masked for emails and long digit runs (phone numbers,
   order ids), so a PII value that slips in under an innocuous key is still caught.

The redaction runs last in the chain, so nothing downstream can re-introduce raw PII into the
rendered line. This is a guard, not a licence to log customer content — don't.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import IO, Any

import structlog

# Key names that must never carry a raw value into a log line.
_SENSITIVE_KEYS = frozenset(
    {
        "phone",
        "phone_number",
        "msisdn",
        "sender",
        "sender_identity",
        "email",
        "address",
        "name",
        "customer",
        "customer_name",
        "body",
        "message",
        "text",
        "transcript",
        "content",
        "value",
        "new_value",
        "prev_value",
        "audio",
        "password",
        "secret",
        "token",
        "api_key",
    }
)

_REDACTED = "«redacted»"

# Email, and any run of 7+ digits (phones, order/tracking ids) possibly split by spaces/dashes.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_DIGITS_RE = re.compile(r"(?:\+?\d[\d\s\-().]{5,}\d)")


def _mask_text(value: str) -> str:
    value = _EMAIL_RE.sub("«redacted:email»", value)
    value = _DIGITS_RE.sub("«redacted:digits»", value)
    return value


def _scrub(value: Any) -> Any:
    """Recursively mask strings; leave structure intact so logs stay useful."""
    if isinstance(value, str):
        return _mask_text(value)
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k.lower() in _SENSITIVE_KEYS else _scrub(v)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


def redact_pii(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor — redact sensitive keys, then pattern-mask any remaining strings."""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = _REDACTED
        else:
            event_dict[key] = _scrub(event_dict[key])
    return event_dict


class _SafeLogger:
    """A logger whose emit can NEVER raise into the caller — a logging failure must never turn a
    request into a 500 (owner directive). If the console can't encode a rendered line (e.g. a ``→`` on a
    Windows cp1252 stdout), it retries with an ASCII-safe rendering, then gives up silently. Logs are
    preserved (as ``\\uXXXX`` escapes) rather than lost, and the request path is untouched either way.
    """

    def __init__(self, file: IO[str] | None = None) -> None:
        self._file = file  # None → resolve sys.stdout at emit time (respects later redirection)

    def msg(self, *args: Any, **_kw: Any) -> None:
        message = args[0] if args else ""
        out = self._file if self._file is not None else sys.stdout
        # The blind excepts + pass are DELIBERATE: this is the "logging never raises" guarantee — an
        # emit failure (encoding, closed pipe, disk full) must be swallowed, not turned into a 500.
        try:
            print(message, file=out, flush=True)
        except Exception:  # noqa: BLE001 — retry ASCII-safe, then give up (never propagate)
            try:
                safe = str(message).encode("ascii", "backslashreplace").decode("ascii")
                print(safe, file=out, flush=True)
            except Exception:  # noqa: BLE001, S110 — logging must never crash the caller
                pass

    # structlog's filtering bound logger calls the method named after the level.
    log = debug = info = warning = warn = error = err = fatal = exception = critical = msg


class _SafeLoggerFactory:
    def __call__(self, *_args: Any) -> _SafeLogger:
        return _SafeLogger()


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON structlog pipeline with redaction as the final pre-render step. Output goes
    through a logger that cannot raise on emit, and the JSON is ASCII-escaped, so a non-encodable
    character can never crash a request."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_pii,  # last transform before rendering — nothing re-adds PII after this
            # ensure_ascii escapes non-ASCII to \uXXXX, so the rendered line is always encodable even on
            # a legacy-codepage console; the safe logger below is the belt-and-braces guarantee.
            structlog.processors.JSONRenderer(ensure_ascii=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        logger_factory=_SafeLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
