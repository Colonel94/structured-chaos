"""Case synthesis — turn the logged fields into an agent-facing ANALYSIS that moves toward resolution.

The governed core + the deterministic decision + any record contradiction are, on their own, a tidy
LOG. This assembles them into the one-glance read a fulfiller actually acts on: what this is, the
discrepancy (if the record disagrees), why it is prioritised the way it is, and the suggested next
step. It is a VIEW, computed at review time from the case's current state, so a correction that
recomputes the decision is reflected immediately.

DETERMINISTIC and GROUNDED, on purpose (§3/§5): no model call, no invented facts. It states only what
the governed core actually holds — an UNGROUNDED fault (one the customer never described) is never
asserted as the problem. The `next_step` is a POINTER for the human, never an action: nothing external
happens without approval (§3), so this guides the reviewer, it does not resolve for them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict

# Agent-facing phrasing (more precise than the customer-facing copy in the portal). Kept here so the
# synthesis reads naturally without leaking enum tokens into the review screen.
_CATEGORY_PHRASE: dict[str, str] = {
    "delivery_fulfilment": "a delivery problem",
    "product_fault": "a product fault",
    "service_fault": "a service issue",
    "billing_charge": "a billing dispute",
    "record_accuracy": "a record-accuracy dispute",
    "staff_conduct": "a staff-conduct complaint",
    "access_availability": "an access or availability issue",
    "safety_health": "a safety or health concern",
    "other": "a complaint",
    "UNCLEAR": "an as-yet-unclear complaint",
}
_OUTCOME_PHRASE: dict[str, str] = {
    "refund": "a refund",
    "replacement": "a replacement",
    "repair_redo": "it put right",
    "acknowledgement": "an acknowledgement",
    "information": "an answer",
    "escalation": "escalation",
    "other": "a resolution",
}
# What resolving each desired outcome concretely asks of the reviewer (the actionable half of next_step).
_OUTCOME_ACTION: dict[str, str] = {
    "refund": "confirm refund eligibility and process it",
    "replacement": "arrange a replacement",
    "repair_redo": "arrange to put it right",
    "acknowledgement": "acknowledge the complaint to the customer",
    "information": "get the customer the answer they asked for",
    "escalation": "escalate per policy",
    "other": "decide and action the resolution",
}


class CaseAnalysis(TypedDict):
    headline: str
    summary: str
    discrepancy: str | None
    priority_reason: str
    next_step: str


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def build_case_analysis(
    governed: Mapping[str, str],
    decision: Mapping[str, object] | None,
    contradictions: Sequence[Mapping[str, object]],
    *,
    fault_grounded: bool | None,
) -> CaseAnalysis:
    """Assemble the agent-facing analysis from the case's current state. Pure + grounded: states only
    present, trusted fields; an ungrounded fault is treated as not-yet-known rather than asserted.
    """
    category = governed.get("category")
    fault = governed.get("fault")
    outcome = governed.get("desired_outcome")
    anchor = governed.get("anchor_value")
    emotion = governed.get("emotion_signal")

    cat_phrase = _CATEGORY_PHRASE.get(category or "", "a complaint")
    out_phrase = _OUTCOME_PHRASE.get(outcome or "", "") if outcome else ""

    # Headline — the one-line "what this is", plus what they want if we know it.
    headline = _cap(cat_phrase)
    if out_phrase:
        headline += f" — {out_phrase} sought"

    # Summary — a short, grounded narrative. Only assert the fault if the customer actually described it
    # (fault_grounded); otherwise say the specifics are still being confirmed, never invent them.
    parts: list[str] = []
    # Lead with the order ref — but not if the fault sentence already names it (avoid "Order BK-1. The
    # order BK-1 arrived…").
    if anchor and not (fault and anchor.lower() in fault.lower()):
        parts.append(f"Order {anchor}.")
    if fault and fault_grounded is not False:
        parts.append(_cap(fault.rstrip(".")) + ".")
    elif fault_grounded is False:
        parts.append("The specific issue is still being confirmed with the customer.")
    if emotion in ("frustrated", "angry"):
        parts.append(f"The customer is {emotion}.")
    if out_phrase:
        parts.append(f"They're asking for {out_phrase}.")
    summary = " ".join(parts) if parts else "Not enough has been captured yet to summarise."

    # Discrepancy — surface a record-vs-complaint contradiction plainly (§5: never argued, never hidden).
    discrepancy: str | None = None
    if contradictions:
        c = contradictions[0]
        claim = str(c.get("claim") or "").strip()
        rec_field = str(c.get("record_field") or "").strip()
        rec_value = str(c.get("record_value") or "").strip()
        if rec_field and rec_value:
            discrepancy = f"The record shows {rec_field.replace('_', ' ')} = {rec_value}"
            discrepancy += f", but {claim}." if claim else ", which the complaint disputes."
        elif claim:
            discrepancy = f"Record vs complaint: {claim}."
        else:
            discrepancy = "The record and the complaint disagree — check before actioning."

    # Priority reason — the deterministic decision, stated as the reviewer sees it (one sentence).
    if decision:
        pr = str(decision.get("priority") or "")
        route = str(decision.get("routing") or "")
        rationale = str(decision.get("rationale") or "")
        priority_reason = f"{pr} · {route}. {rationale}".strip(" .") + "."
    else:
        priority_reason = "No decision computed yet."

    # Next step — a POINTER for the reviewer (never an action). Lead with the discrepancy if there is
    # one; otherwise point at what resolving the stated outcome concretely takes.
    if discrepancy:
        next_step = "Resolve the discrepancy first, then action the outcome."
    elif outcome:
        action = _OUTCOME_ACTION.get(outcome, "decide and action the resolution")
        next_step = _cap(action) + "."
    elif fault_grounded is False:
        next_step = "Confirm the specific issue with the customer before actioning."
    else:
        next_step = "Review and action per the routed team's process."

    return CaseAnalysis(
        headline=headline,
        summary=summary,
        discrepancy=discrepancy,
        priority_reason=priority_reason,
        next_step=next_step,
    )
