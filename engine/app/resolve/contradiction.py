"""Complaint-vs-record contradiction detection (Phase 5, §5; winning-condition §4 "discrepancies
surfaced 100%, never argued with the customer").

When a case binds to an object, the customer's complaint sometimes asserts a fact the RECORD refutes —
"it never arrived" against a record showing it was delivered, "you charged me twice" against a single
charge. Those discrepancies must be SURFACED to the agent (they are also a fraud/pattern signal over
time), never argued with the customer and never silently dropped.

Detection is domain-agnostic, so it uses the LLM (the honest tool for comparing a free-text complaint
against an arbitrary record) under strict grounding: only report a contradiction that is a DIRECT,
checkable disagreement on a specific record field; when unsure, report nothing (a false discrepancy
shown to an agent erodes trust). The result is stored as ``contradicts`` citations and reviewed by a
human — nothing acts on it automatically (trust gate: nothing external on model output alone).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


class _LLM(Protocol):
    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str: ...


@dataclass(frozen=True)
class Contradiction:
    record_field: str  # the record field that disagrees
    record_value: str  # what the record says
    claim: str  # what the complaint asserts instead


_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "record_field": {"type": "string"},
                    "record_value": {"type": "string"},
                    "claim": {"type": "string"},
                },
                "required": ["record_field", "record_value", "claim"],
            },
        }
    },
    "required": ["contradictions"],
}

_PROMPT = """You compare a customer complaint against the record on file and report ONLY direct, \
checkable contradictions — where the complaint asserts something a specific record field REFUTES.

Rules:
- Report a contradiction ONLY when the complaint clearly states a fact and a specific record field \
clearly says the OPPOSITE (e.g. complaint "never delivered" vs record status "delivered"; complaint \
"charged twice" vs record showing one amount).
- Weigh the WHOLE record, not one field. If ANY record field is CONSISTENT with the complaint, it is \
NOT a contradiction — report nothing. (e.g. a "delivered late" status already agrees with a "late" \
complaint.)
- A PROMISED or TARGET value differing from what actually happened is NOT a contradiction — that gap is \
usually the complaint itself. A promised slot of 17:00 does not contradict "2 hours late"; a due date \
does not contradict "it was late". Only the ACTUAL-outcome fields (what happened) can refute a claim.
- Do NOT report when the complaint is about something the record does not cover, when it is a \
subjective judgement (quality, rudeness), or when you are unsure. Prefer an EMPTY list.
- Never invent a record field. Use the exact field name from the record.

RECORD (fields the company holds):
{record}

COMPLAINT (what the customer said):
{complaint}

Return JSON: {{"contradictions": [{{"record_field": ..., "record_value": ..., "claim": ...}}]}}"""


async def detect_contradictions(
    llm: _LLM, *, complaint: str, record: Mapping[str, object]
) -> list[Contradiction]:
    """Return the record fields the complaint directly contradicts (empty if none/unsure). Grounded +
    conservative — a false discrepancy surfaced to an agent costs trust, so the bar is 'clearly refutes'.
    """
    if not complaint.strip() or not record:
        return []
    prompt = _PROMPT.format(
        record=json.dumps(dict(record), ensure_ascii=False, sort_keys=True), complaint=complaint
    )
    raw = await llm.complete(prompt, schema=_SCHEMA)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    out: list[Contradiction] = []
    for c in data.get("contradictions", []) or []:
        field, value, claim = c.get("record_field"), c.get("record_value"), c.get("claim")
        # Grounding gate: the cited field must actually exist in the record (never invent one).
        if field in record and value and claim:
            out.append(Contradiction(str(field), str(value), str(claim)))
    return out
