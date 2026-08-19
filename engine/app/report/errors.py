"""Report-generation errors (Phase 7)."""

from __future__ import annotations


class NotCommittedError(Exception):
    """Raised when a report is requested for a case that a human has not yet approved. The commit gate
    (CLAUDE.md §3): nothing external — no report — is issued on model output alone."""


class ReportBackendUnavailable(Exception):
    """Raised when the PDF backend (WeasyPrint) is not importable — it is container-only (GTK/Pango;
    PREREQUISITES §3 forbids installing it on the Windows host). The HTML/CSV paths still work."""
