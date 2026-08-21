"""The elicitation policy — a PURE, deterministic decision (no DB, no model), so the trust-gate that
matters most is unit-testable in isolation: the question budget is enforced in CODE, not the model's
judgement (CLAUDE.md §3; winning-condition §4 "≤ 2 after the anchor", §5).

Given a case's current extracted state, decide the single next move:
  - ``actionable``  — enough to route/act; ask nothing.
  - ``incomplete``  — ask exactly ONE next question (the anchor, then drills), by information gain.
  - ``in_review``   — hand to a human: an angry incomplete case (never interrogate one, §5), or the
                      anchor+2 budget is spent.

The order encodes the design (§5): the ANCHOR first — it is a key, and resolving it lets everything
downstream be looked up and CONFIRMED rather than asked. Then the desired OUTCOME — the one fact that
can never be inferred. Then, only if the case is still too sparse to categorise, one clarifying drill.
We never ask for something already stated (a present field is never re-asked) or derivable from the
anchor (the stage confirms looked-up facts instead of asking).
"""

from __future__ import annotations

from dataclasses import dataclass

DRILL_BUDGET = 2  # at most two questions AFTER the anchor (winning-condition §4)
TOTAL_CAP = 3  # anchor + 2 drills — a hard ceiling; the 4th question must never be asked

_ANCHOR_Q = (
    "To pull up your case, what's your order number — or the phone number you used to order?"
)
_OUTCOME_Q = "What would you like us to do to put this right?"
_CLARIFY_Q = "Sorry to hear that — can you tell me briefly what went wrong?"


# Tappable options for the outcome drill — plain labels for the DESIRED_OUTCOMES vocab (concept §4.3:
# "offer tappable options rather than open questions" — but only AFTER narrowing, never an upfront
# type-picker). Defined ONCE here so every channel (portal buttons, WhatsApp interactive) renders the
# SAME set and they cannot diverge. A HINT, never a constraint: the caller must always keep free text
# available alongside these, so a customer whose answer isn't listed is never forced to pick a wrong one.
OUTCOME_OPTIONS: tuple[str, ...] = ("Refund", "Replacement", "Fix it", "An answer", "Escalate")


@dataclass(frozen=True)
class ElicitationPlan:
    state: str  # "actionable" | "incomplete" | "in_review"
    next_question: str | None  # the single question to ask, or None
    question_kind: str | None  # "anchor" | "drill" | None
    reason: str
    options: tuple[str, ...] | None = (
        None  # tappable choices for this question, or None → free text only
    )


def decide(
    present_fields: set[str],
    *,
    emotion: str | None,
    has_anchor: bool,
    anchor_asked: bool,
    question_count: int,
    confirmation: str | None = None,
) -> ElicitationPlan:
    """Decide the next elicitation move for one case.

    ``present_fields`` — governed keys with a non-null value (a present field is never re-asked).
    ``has_anchor`` — a resolvable identifier exists (a stated anchor, a known sender phone, or a
    silently-resolved object), so lookups are possible without asking. ``anchor_asked`` — whether the
    anchor has already been requested (so it isn't re-asked and doesn't consume a drill slot).
    ``question_count`` — total questions asked so far (durable across turns). ``confirmation`` — a fact
    looked up from the resolved object to STATE before the drill (turn a question into a confirmation).
    """
    # Enough to route and act → ask nothing, regardless of budget.
    essentials = {"category", "fault", "desired_outcome"}
    if essentials <= present_fields:
        return ElicitationPlan("actionable", None, None, "has category + fault + desired_outcome")

    # Emotion is data: an angry, incomplete case goes to a human — never interrogated (§5).
    if emotion == "angry":
        return ElicitationPlan(
            "in_review", None, None, "angry + incomplete → hand to a human, do not question"
        )

    drills_used = question_count - (1 if anchor_asked else 0)

    # 1. The anchor first — highest information gain (it unlocks every downstream lookup). It is a
    #    key, not a drill, so it does not consume the drill budget; but it still respects the hard cap.
    if not has_anchor and not anchor_asked and question_count < TOTAL_CAP:
        return ElicitationPlan(
            "incomplete", _ANCHOR_Q, "anchor", "no resolvable identifier → ask the anchor key"
        )

    # Budget enforced IN CODE: anchor + 2 drills, then hand off. Never a 3rd drill, never a 4th question.
    if drills_used >= DRILL_BUDGET or question_count >= TOTAL_CAP:
        return ElicitationPlan(
            "in_review", None, None, "anchor + 2 budget spent → hand off to a human"
        )

    # 2. The desired outcome — the one fact that can never be inferred. Confirm the looked-up fact first.
    #    Offer the outcome options (a hint, after narrowing — the caller keeps free text alongside them).
    if "desired_outcome" not in present_fields:
        q = f"{confirmation} {_OUTCOME_Q}" if confirmation else _OUTCOME_Q
        return ElicitationPlan(
            "incomplete",
            q,
            "drill",
            "missing desired_outcome (never inferable)",
            options=OUTCOME_OPTIONS,
        )

    # 3. Still too sparse to categorise even after the anchor → one clarifying drill.
    if "category" not in present_fields or "fault" not in present_fields:
        return ElicitationPlan(
            "incomplete", _CLARIFY_Q, "drill", "too sparse to categorise → one clarifying question"
        )

    return ElicitationPlan("actionable", None, None, "no further closable gaps")
