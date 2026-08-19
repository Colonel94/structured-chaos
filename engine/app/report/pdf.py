"""Per-case PDF report generation — the commit gate's external artifact (Phase 7, §3 + §16.4).

This is the one place the engine emits something outward-facing. The gate is absolute: a report is
generated ONLY for an approved case. :func:`render_case_pdf` re-checks ``commit_status`` at generation
time (never trusting a caller's claim) and raises :class:`NotCommittedError` otherwise — nothing
external is issued on model output alone.

WeasyPrint is imported LAZILY, inside the render call: it is container-only (GTK/Pango; PREREQUISITES
§3 forbids the Windows host install), so importing this module — and unit-testing the gate + the HTML
builder — stays host-safe. A missing backend surfaces as :class:`ReportBackendUnavailable`, distinct
from the approval refusal, so the caller can tell "not approved" from "run me in the container".
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ..store import api
from .errors import NotCommittedError, ReportBackendUnavailable
from .html import build_case_html


def render_case_html(session: Session, case_id: UUID) -> str:
    """The report HTML for an APPROVED case. Raises :class:`NotCommittedError` if not yet approved, or
    ``LookupError`` if the case is absent for this tenant. Host-safe (no WeasyPrint)."""
    if api.commit_status(session, case_id) is None:
        raise NotCommittedError(f"case {case_id} is not approved — no report may be issued")
    review = api.get_case_review(session, case_id)
    if review is None:  # RLS fail-closed / absent
        raise LookupError(f"case {case_id} not found")
    return build_case_html(review)


def html_to_pdf(html: str) -> bytes:
    """Render report HTML to PDF bytes via WeasyPrint (container-only; lazy import). Raises
    :class:`ReportBackendUnavailable` when the backend is absent (e.g. on the Windows host). Kept
    separate from :func:`render_case_html` so a route can render OUTSIDE the DB transaction."""
    try:
        from weasyprint import HTML  # lazy: container-only (GTK/Pango)
    except (ImportError, OSError) as exc:  # OSError = native GTK/Pango libs missing on the host
        raise ReportBackendUnavailable(
            "WeasyPrint is unavailable — the PDF report is container-only (PREREQUISITES §3)"
        ) from exc
    return bytes(HTML(string=html).write_pdf())


def render_case_pdf(session: Session, case_id: UUID) -> bytes:
    """The approved case rendered to PDF bytes. Gate-checked (``NotCommittedError`` if not approved);
    container-only render (``ReportBackendUnavailable`` if WeasyPrint is absent, e.g. on the host).
    """
    html = render_case_html(session, case_id)  # gate check happens here, before any heavy import
    return html_to_pdf(html)
