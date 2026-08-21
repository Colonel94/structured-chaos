"""The elicitation policy — a PURE, deterministic decision (no DB, no model), so the trust-gate that
matters most is unit-testable in isolation: the question budget is enforced in CODE, not the model's
judgement (CLAUDE.md §3; winning-condition §4 "≤ 2 after the anchor", §5).

Given a case's current extracted state, decide the single next move:
  - ``actionable``  — enough to route/act; ask nothing.
  - ``incomplete``  — ask exactly ONE next question (the anchor, then drills), by information gain.
  - ``in_review``   — hand to a human: an angry incomplete case (never interrogate one, §5), or the
                      anchor+2 budget is spent.

The order encodes the design (§5): the ANCHOR first — it is a key, and resolving it lets everything
downstream be looked up and CONFIRMED rather than asked. Then, if the customer hasn't actually said
what went wrong, WHAT HAPPENED — the fault in their own words (never one invented from the record).
Then the desired OUTCOME — the one fact that can never be inferred. We never ask for something already
stated (a present field is never re-asked) or derivable from the anchor (the stage confirms looked-up
facts instead of asking).

Closed-world grounding is a GATE here (§4): a ``fault`` the customer never described — absent, or one
the extractor INFERRED from the resolved order record — is not allowed to pass as fact. The stage
measures whether the fault is attested in the customer's own words and passes ``fault_grounded``; an
ungrounded fault (and the category derived from it) is treated as a gap, so the system asks "what
happened" instead of confidently telling the customer what their problem is (§5, Claim 2).
"""

from __future__ import annotations

from dataclasses import dataclass

DRILL_BUDGET = 2  # at most two questions AFTER the anchor (winning-condition §4)
TOTAL_CAP = 3  # anchor + 2 drills — a hard ceiling; the 4th question must never be asked

_ANCHOR_Q = (
    "To pull up your case, what's your order number — or the phone number you used to order?"
)
# "What happened" — the fault, in the customer's own words. Plain and low-pressure on purpose: no
# persona, no scripted "so sorry to hear that", no leading guess about the problem. It asks once, for a
# sentence, and hands the answer to the person in the back to resolve — a drill, not a chatbot turn (§5).
_FAULT_Q = (
    "What happened? A sentence or two is all we need — it goes straight to the person handling it."
)
_OUTCOME_Q = "What would you like us to do to put this right?"
_CLARIFY_Q = "Just so we route this right — can you tell us briefly what the issue is?"


# Tappable options for the outcome drill — plain labels for the DESIRED_OUTCOMES vocab (concept §4.3:
# "offer tappable options rather than open questions" — but only AFTER narrowing, never an upfront
# type-picker). Defined ONCE here so every channel (portal buttons, WhatsApp interactive) renders the
# SAME set and they cannot diverge. A HINT, never a constraint: the caller must always keep free text
# available alongside these, so a customer whose answer isn't listed is never forced to pick a wrong one.
OUTCOME_OPTIONS: tuple[str, ...] = ("Refund", "Replacement", "Fix it", "An answer", "Escalate")

# Narrowed fault dimensions for the ANALYTICAL drill (winning-condition Moment 3): once the anchor
# resolves and the stage can STATE what the record shows, we don't ask an open "what happened" — we
# offer the universal complaint SHAPES so the customer taps rather than types. Deliberately domain-
# neutral (a cake, a parcel, a booking, a charge all fit): timing / correctness-or-quality / non-arrival
# / other. A HINT alongside free text, like OUTCOME_OPTIONS — never a constraint.
FAULT_OPTIONS: tuple[str, ...] = (
    "It was late",
    "It was wrong or faulty",
    "It never arrived",
    "Something else",
)


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
    fault_grounded: bool = True,
    category_known: bool = False,
    fault_prompt: str | None = None,
    fault_options: tuple[str, ...] | None = None,
) -> ElicitationPlan:
    """Decide the next elicitation move for one case.

    ``present_fields`` — governed keys with a non-null value (a present field is never re-asked).
    ``has_anchor`` — a resolvable identifier exists (a stated anchor, a known sender phone, or a
    silently-resolved object), so lookups are possible without asking. ``anchor_asked`` — whether the
    anchor has already been requested (so it isn't re-asked and doesn't consume a drill slot).
    ``question_count`` — total questions asked so far (durable across turns). ``confirmation`` — a fact
    looked up from the resolved object to STATE before the drill (turn a question into a confirmation).
    ``fault_grounded`` — whether the ``fault`` value is attested in the customer's OWN words (the stage
    measures this). ``False`` means the fault is absent or was inferred from the record; we then treat
    the fault (and the category derived from it) as a gap and ask "what happened" rather than presenting
    an invented problem as fact (§4 closed-world grounding, §5 never confidently wrong). Defaults to
    ``True`` so a caller that doesn't measure grounding keeps the pre-grounding behaviour.
    ``category_known`` — whether the extractor placed the complaint in a CONCRETE class (not
    ``other``/``UNCLEAR``). Distinguishes a directional-but-thin case (e.g. a delivery complaint with no
    order number → ask the anchor, we know the domain) from a truly contentless opener ("something hurt
    me", category ``other`` → ask "what happened", we don't even know what kind of problem it is).
    ``fault_prompt`` / ``fault_options`` — the ANALYTICAL fault drill (Moment 3): when the anchor
    resolved and the stage can STATE what the record shows, it passes a record-grounded prompt (the
    confirmation + a narrowing question) and tappable options, so the fault drill states-and-narrows
    instead of asking the open ``_FAULT_Q``. ``None`` → the open question (no record to reason over).
    """
    # A fault the customer never actually described must not count as known. Drop it (and the category
    # inferred from it) from the fields we treat as satisfied, so the gate below asks instead of asserts.
    effective_fields = set(present_fields)
    if not fault_grounded:
        effective_fields.discard("fault")
        effective_fields.discard("category")

    # Enough to route and act → ask nothing, regardless of budget.
    essentials = {"category", "fault", "desired_outcome"}
    if essentials <= effective_fields:
        return ElicitationPlan("actionable", None, None, "has category + fault + desired_outcome")

    drills_used = question_count - (1 if anchor_asked else 0)
    budget_left = drills_used < DRILL_BUDGET and question_count < TOTAL_CAP

    # INVESTIGATE BEFORE YOU HAND OFF (owner directive 2026-08-21c). A contentless / purely emotional
    # opener ("something hurt me") — no problem described AND no order to look up — must never be closed
    # into a case without a single question. Handing an empty case to a human gives them nothing to act
    # on; asking for an order number may be irrelevant (it might not be an order issue at all). So ask
    # "what happened" FIRST, even when the extractor flagged the mood as angry. One gentle question is
    # investigation, not interrogation — §5's angry→handoff protects a customer with a REAL grievance
    # from being grilled, NOT an empty opener from being heard. This is what stops the system building a
    # case straight from three vague words with no conversation. A concrete category (a delivery/billing/
    # etc. complaint) is directional even without a fault → that path asks the anchor, not this.
    contentless = "fault" not in effective_fields and not has_anchor and not category_known
    if contentless and budget_left:
        return ElicitationPlan(
            "incomplete",
            _FAULT_Q,
            "drill",
            "contentless opener → ask what happened before any handoff",
        )

    # Emotion is data: an angry customer whose grievance we now understand (or whose order we found) goes
    # to a human — never interrogated further (§5). Fires AFTER the investigate-first check above, so an
    # empty angry opener is heard before it is ever handed off.
    if emotion == "angry":
        return ElicitationPlan(
            "in_review", None, None, "angry + incomplete → hand to a human, do not question"
        )

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

    # 2. What happened — the fault, asked BEFORE the outcome (understand the problem before asking what
    #    they'd like done). Only fires when the customer hasn't described it: a present, grounded fault
    #    skips this; an absent or record-inferred one asks rather than invents. When the anchor resolved,
    #    STATE what the record shows and narrow (Moment 3); otherwise ask the open question.
    if "fault" not in effective_fields:
        return ElicitationPlan(
            "incomplete",
            fault_prompt or _FAULT_Q,
            "drill",
            "fault not grounded in the customer's words → "
            + ("state the record and narrow" if fault_prompt else "ask what happened"),
            options=fault_options if fault_prompt else None,
        )

    # 3. The desired outcome — the one fact that can never be inferred. Confirm the looked-up fact first.
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

    # 4. Fault known and outcome known, but still uncategorised → one clarifying drill.
    if "category" not in effective_fields:
        return ElicitationPlan(
            "incomplete", _CLARIFY_Q, "drill", "too sparse to categorise → one clarifying question"
        )

    return ElicitationPlan("actionable", None, None, "no further closable gaps")
