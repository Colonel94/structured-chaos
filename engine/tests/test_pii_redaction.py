"""Trust gate — no customer data in logs (CLAUDE.md §3). A known-PII payload must never appear
raw in the rendered log line, whether under a sensitive key or buried inside free text."""

from __future__ import annotations

import pytest

from app.obs.logging import configure_logging, get_logger


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
