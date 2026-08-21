"""Case synthesis — the agent-facing analysis assembled deterministically from the case state.

Pure (no DB, no model): states only present, trusted fields; an ungrounded fault is never asserted as
the problem; a record contradiction is surfaced, never hidden; the next step is a pointer, not an action.
"""

from __future__ import annotations

from app.rules.synthesis import build_case_analysis

_DECISION = {
    "priority": "P3",
    "routing": "fulfilment",
    "rationale": "A delivery or fulfilment issue — routed to the fulfilment team.",
}


def test_grounded_case_reads_as_a_near_decided_summary() -> None:
    a = build_case_analysis(
        {
            "category": "delivery_fulfilment",
            "fault": "the cake arrived melted and 2 hours late",
            "desired_outcome": "refund",
            "emotion_signal": "frustrated",
            "anchor_value": "BK-1001",
        },
        _DECISION,
        [],
        fault_grounded=True,
    )
    assert a["headline"] == "A delivery problem — a refund sought"
    assert "Order BK-1001." in a["summary"]
    assert "melted and 2 hours late" in a["summary"]
    assert "frustrated" in a["summary"]
    assert a["discrepancy"] is None
    assert a["priority_reason"].startswith("P3 · fulfilment")
    assert "refund" in a["next_step"].lower()


def test_anchor_not_stated_twice_when_the_fault_already_names_it() -> None:
    a = build_case_analysis(
        {
            "category": "delivery_fulfilment",
            "fault": "the order BK-1004 arrived over 3 hours late",
            "anchor_value": "BK-1004",
        },
        _DECISION,
        [],
        fault_grounded=True,
    )
    assert a["summary"].count("BK-1004") == 1  # not "Order BK-1004. The order BK-1004 …"
    assert a["summary"].startswith("The order BK-1004")


def test_ungrounded_fault_is_not_asserted_as_the_problem() -> None:
    # The customer never described the fault → don't state an invented one; say it's being confirmed.
    a = build_case_analysis(
        {"category": "other", "fault": "the order was not delivered", "anchor_value": "BK-9"},
        {"priority": "P3", "routing": "general_queue", "rationale": "A general complaint."},
        [],
        fault_grounded=False,
    )
    assert "not delivered" not in a["summary"]
    assert "still being confirmed" in a["summary"]
    assert "Confirm the specific issue" in a["next_step"]


def test_contradiction_is_surfaced_and_leads_the_next_step() -> None:
    a = build_case_analysis(
        {"category": "delivery_fulfilment", "fault": "it never arrived", "anchor_value": "BK-2"},
        _DECISION,
        [
            {
                "record_field": "status",
                "record_value": "delivered on time",
                "claim": "customer says it never arrived",
            }
        ],
        fault_grounded=True,
    )
    assert a["discrepancy"] is not None
    assert "delivered on time" in a["discrepancy"]
    assert "discrepancy" in a["next_step"].lower()


def test_empty_case_degrades_without_inventing() -> None:
    a = build_case_analysis({}, None, [], fault_grounded=None)
    assert a["summary"] == "Not enough has been captured yet to summarise."
    assert a["priority_reason"] == "No decision computed yet."
    assert a["discrepancy"] is None
