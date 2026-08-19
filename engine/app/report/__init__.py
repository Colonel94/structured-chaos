"""WeasyPrint universal-register templates + CSV export, post-approval only (Phase 7).

The commit gate's outward-facing surface (CLAUDE.md §3): the per-case PDF report is generated ONLY for
an approved case (:func:`render_case_pdf` raises :class:`NotCommittedError` otherwise). The register CSV
is the internal operator list and is ungated. WeasyPrint is container-only; the HTML builder + CSV are
host-safe.
"""

from __future__ import annotations

from .errors import NotCommittedError, ReportBackendUnavailable
from .html import build_case_html
from .pdf import html_to_pdf, render_case_html, render_case_pdf
from .register import render_register_csv

__all__ = [
    "NotCommittedError",
    "ReportBackendUnavailable",
    "build_case_html",
    "html_to_pdf",
    "render_case_html",
    "render_case_pdf",
    "render_register_csv",
]
