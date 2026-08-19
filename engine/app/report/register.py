"""The universal manager register — a CSV export of every case with its decision (Phase 7).

Host-safe (stdlib ``csv`` only, no WeasyPrint). The register is the operator's internal list, so — unlike
the per-case PDF report — it is not gated on approval: it shows the queue as it stands (including cases
still in review), which is exactly what a manager triaging by priority/SLA needs. It is "universal" in
the domain-agnostic sense (§4): the same columns serve a bakery and a ministry — nothing here is
industry-specific.
"""

from __future__ import annotations

import csv
import io
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..store import api

_COLUMNS = [
    "case_id",
    "first_contact_at",
    "channel",
    "case_state",
    "category",
    "priority",
    "routing",
    "sla_target_hours",
    "sla_response_due_at",
    "committed_at",
    "committed_by",
    "field_count",
]


def render_register_csv(session: Session) -> str:
    """The register for the current tenant as a CSV string: one row per case, newest first, joined to
    its deterministic decision + approval stamp. RLS-scoped (``list_cases`` reads only this tenant).
    """
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for case in api.list_cases(session):
        cid = UUID(str(case["case_id"]))
        decision = api.get_case_decision(session, cid) or {}
        commit = api.commit_status(session, cid) or {}
        row: dict[str, Any] = {
            "case_id": case["case_id"],
            "first_contact_at": case["first_contact_at"],
            "channel": case["channel"],
            "case_state": case["case_state"],
            "category": case.get("category"),
            "priority": decision.get("priority"),
            "routing": decision.get("routing"),
            "sla_target_hours": decision.get("sla_target_hours"),
            "sla_response_due_at": decision.get("sla_response_due_at"),
            "committed_at": commit.get("committed_at"),
            "committed_by": commit.get("committed_by"),
            "field_count": case.get("field_count"),
        }
        writer.writerow(row)
    return out.getvalue()
