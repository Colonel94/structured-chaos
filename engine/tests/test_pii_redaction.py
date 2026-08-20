"""Trust gate — no customer data in logs (CLAUDE.md §3). A known-PII payload must never appear
raw in the rendered log line, whether under a sensitive key or buried inside free text."""

from __future__ import annotations

import pytest

from app.obs.logging import _SafeLogger, configure_logging, get_logger


def test_logging_never_raises_on_an_unencodable_char() -> None:
    """A logging error must never turn a request into a 500 (owner directive). Even when the sink can't
    encode the line (a Windows cp1252 console meeting a ``→``), emit swallows it — never propagates.
    """

    class _Cp1252Stream:
        def write(self, s: str) -> int:
            s.encode("cp1252")  # raises UnicodeEncodeError on → / em-dash, like a legacy console
            return len(s)

        def flush(self) -> None:
            pass

    log = _SafeLogger(file=_Cp1252Stream())
    log.msg("routing → review, id and em—dash")  # must not raise
    log.info("also via the level alias →")  # the aliased methods must be safe too


def test_configured_pipeline_logs_non_ascii_without_raising(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    # A non-ASCII value that previously 500'd the request on Windows now logs (ASCII-escaped) and returns.
    get_logger("test").info("rules_done", routing="triage → finance")
    out = capsys.readouterr().out
    assert "rules_done" in out and "\\u2192" in out  # arrow escaped, line intact


def test_pii_never_appears_in_logs(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    log = get_logger("test")
    log.info(
        "case_ingested",
        phone="+971501234567",
        email="ahmed@example.com",
        sender_identity="+971501234567",
        fault="customer +971 50 123 4567 said the cake was late",  # PII inside innocuous key
        case_id="abc-123",  # non-PII — must survive
    )
    out = capsys.readouterr().out

    # Raw PII is gone, in every form it was supplied.
    assert "971501234567" not in out
    assert "ahmed@example.com" not in out
    assert "+971 50 123 4567" not in out
    # Redaction markers present; structure preserved.
    assert "redacted" in out
    assert "case_ingested" in out
    assert "abc-123" in out


def test_pii_redacted_in_nested_and_list_structures(capsys: pytest.CaptureFixture[str]) -> None:
    """The redaction recurses: PII under a nested dict's sensitive key, and email/phone inside a
    list, must not leak. (Locks the recursion the 'no customer data in logs' gate depends on.)"""
    configure_logging("INFO")
    log = get_logger("test")
    log.info(
        "nested_event",
        payload={"phone": "+971501234567", "note": "ring back on +971 50 111 2222"},
        attachments=["email ahmed@example.com", "invoice 9988776655"],
    )
    out = capsys.readouterr().out
    assert "971501234567" not in out  # nested sensitive key → wholesale redacted
    assert "ahmed@example.com" not in out  # email inside a list → masked
    assert "9988776655" not in out  # long digit run inside a list → masked
    assert "111 2222" not in out  # spaced phone in a nested value → masked
