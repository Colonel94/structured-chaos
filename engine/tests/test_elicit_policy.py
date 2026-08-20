"""The elicitation policy — the anchor + two-drill budget, enforced in code (winning-condition §4/§5).

Pure unit tests (no DB, no model): this is the trust gate that must never depend on a model's
judgement, so it is proven in isolation. The 4th question must never be asked; an angry incomplete case
is handed off, not interrogated; a stated field is never re-asked; the desired outcome (never inferable)
is always asked when absent.
"""

from __future__ import annotations

from app.elicit.policy import decide
from app.elicit.stage import _confirmation

_ESSENTIALS = {"category", "fault", "desired_outcome"}


def test_confirmation_states_record_facts_not_just_found() -> None:
    """Moment 3's second half: the confirmation STATES what the record says (the slot, the items, the
    delivery time), grounded in the object's own values — not a bare "we've found your order"."""
    obj = (
        "order",
        "BK-1001",
        {
            "order_id": "BK-1001",  # the display id — already shown, skipped
            "phone": "+971501234501",  # a contact identifier — never stated
            "items": "chocolate cake",
            "slot": "17:00",
            "delivered_at": "18:42",
        },
    )
    c = _confirmation(obj)
    assert c.startswith("We've found your order BK-1001:")
    assert "items chocolate cake" in c and "slot 17:00" in c and "delivered at 18:42" in c
    assert (
        "+971501234501" not in c and "BK-1001," not in c
    )  # id + contact are not restated as facts
    # A record with no descriptive facts degrades to the plain confirmation, never an empty ": .".
    assert _confirmation(("order", "BK-9", {"order_id": "BK-9"})) == "We've found your order BK-9."


def test_actionable_when_essentials_present_asks_nothing() -> None:
    p = decide(_ESSENTIALS, emotion="calm", has_anchor=True, anchor_asked=False, question_count=0)
    assert p.state == "actionable" and p.next_question is None


def test_anchor_is_asked_first_when_no_resolvable_identifier() -> None:
    p = decide(set(), emotion=None, has_anchor=False, anchor_asked=False, question_count=0)
    assert p.state == "incomplete" and p.question_kind == "anchor"


def test_outcome_asked_when_anchor_known_and_outcome_missing() -> None:
    p = decide(
        {"category", "fault"}, emotion="calm", has_anchor=True, anchor_asked=True, question_count=1
    )
    assert p.question_kind == "drill" and "put this right" in (p.next_question or "")


def test_confirmation_is_stated_before_the_drill() -> None:
    p = decide(
        {"category", "fault"},
        emotion="calm",
        has_anchor=True,
        anchor_asked=True,
        question_count=1,
        confirmation="We've found your order BK-1.",
    )
    assert (p.next_question or "").startswith("We've found your order BK-1.")


def test_present_field_is_never_reasked() -> None:
    # desired_outcome already stated, fault missing → the drill targets the gap, not the outcome.
    p = decide(
        {"category", "desired_outcome"},
        emotion="calm",
        has_anchor=True,
        anchor_asked=True,
        question_count=1,
    )
    assert "put this right" not in (p.next_question or "")  # outcome not re-asked
    assert p.question_kind == "drill"


def test_angry_incomplete_case_is_handed_off_not_interrogated() -> None:
    p = decide({"category"}, emotion="angry", has_anchor=True, anchor_asked=False, question_count=0)
    assert p.state == "in_review" and p.next_question is None


def test_budget_spent_after_anchor_plus_two_hands_off() -> None:
    # anchor asked (1) + two drills (→3): the 4th question must never be asked.
    p = decide(
        {"category", "fault"}, emotion="calm", has_anchor=True, anchor_asked=True, question_count=3
    )
    assert p.state == "in_review" and p.next_question is None


def test_two_drills_without_anchor_also_hits_the_cap() -> None:
    p = decide(
        {"category", "fault"}, emotion="calm", has_anchor=True, anchor_asked=False, question_count=2
    )
    assert p.state == "in_review" and p.next_question is None


def test_hard_cap_blocks_even_the_anchor_at_three_questions() -> None:
    p = decide(set(), emotion=None, has_anchor=False, anchor_asked=False, question_count=3)
    assert p.state == "in_review" and p.next_question is None


def test_anchor_not_reasked_once_asked_moves_to_drills() -> None:
    # anchor already asked but still unresolved → don't re-ask it; proceed to the outcome drill.
    p = decide(
        {"category", "fault"}, emotion=None, has_anchor=False, anchor_asked=True, question_count=1
    )
    assert p.question_kind == "drill"
