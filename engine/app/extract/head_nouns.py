"""The closed head-noun vocabulary — the emergent COLUMN space (Path A, 2026-08-14).

The convergence root cause (longterm_context §0): the extractor was minting one-off compound field
names (``pension_amount``, ``deposit_date_2``, ``overdrawn_amount_after_deposit``) — 90% hapax — so the
emergent-column count never converged. Path A fixes it upstream: an emergent attribute is now
``{head, qualifier, value}``. The **head is the column** and MUST come from this closed list (enforced
in code via the extraction-schema enum, not left to the model). The **qualifier is open** free text
that carries the specificity (``charged``/``pension``/``refunded``), so ``charged_amount`` becomes
``head=amount, qualifier=charged`` — the schema converges at the head while qualifiers proliferate as
DATA, losing no information (owner constraint #1, 2026-08-14).

**Why a fixed seed does NOT violate §4 ("no industry-specific field is ever configured; specialisation
is emergent, never seeded").** These are universal, domain-agnostic *data primitives* — the kinds of
thing any complaint mentions (an amount, a date, a status), true for a bakery and a ministry alike.
None is an industry field. Domain specialisation still emerges ONLY by promotion: a recurring head not
in this seed enters via the promotion path (STAGE 4), never by hand-configuration. ``other`` is the
escape valve so the model is never forced to mis-map a genuinely-new concept — those ``other`` heads
are exactly the promotion candidates.

*(Owner's "seeded per category" is implemented as this single universal seed available to every
universal governed category — see the 2026-08-14 DECISION block in longterm_context §0. Per-category
seed subsets are a trivial future refinement.)*
"""

from __future__ import annotations

import re

# The closed emergent-column vocabulary. Universal structural primitives, curated to avoid internal
# synonyms (so two heads are never synonyms of each other — that guard is what keeps the COLUMN space
# convergent by construction). Extended per-tenant ONLY by promotion, never by hand.
HEAD_NOUNS: tuple[str, ...] = (
    "identifier",  # account/order/ref/case numbers, tracking ids
    "name",  # a label/title that is not a person or org (product model, plan name)
    "amount",  # a sum of money
    "fee",  # a charge/penalty/fee specifically
    "rate",  # a percentage or per-unit rate (APR, interest)
    "balance",  # an account/outstanding balance
    "quantity",  # a non-money count of things
    "count",  # a tally of events/occurrences (calls made, attempts)
    "frequency",  # how often something recurs
    "duration",  # a length of time (how long)
    "date",  # a calendar date
    "time",  # a clock time / moment
    "status",  # a state (open, closed, pending, declined)
    "type",  # a kind/classification of something
    "condition",  # physical/qualitative condition (damaged, expired)
    "rating",  # a score/rating/rank
    "method",  # how something was done (payment method, contact method)
    "action",  # an action taken or to take
    "request",  # what the customer asked for (specifics beyond governed desired_outcome)
    "response",  # what a party replied/did in response
    "reason",  # a stated cause/justification
    "outcome",  # a result/resolution of something
    "description",  # a free-text descriptive fact that fits no other head
    "person",  # a named/among individual (customer, agent, relative)
    "organization",  # a company/bank/institution/agency
    "product",  # a product involved
    "service",  # a service involved
    "location",  # a place/address/region
    "document",  # a document/evidence/record referenced
    "event",  # an incident/occurrence
    "other",  # ESCAPE: a genuinely-new concept — a promotion candidate, never a dumping ground
)

_HEAD_SET = frozenset(HEAD_NOUNS)

_SNAKE = re.compile(r"[^a-z0-9]+")


def is_head(head: str) -> bool:
    """Whether ``head`` is in the closed vocabulary (case/space-insensitive)."""
    return normalise_token(head) in _HEAD_SET


def normalise_token(token: str) -> str:
    """A free token → stable snake_case (the qualifier/head normal form)."""
    return _SNAKE.sub("_", token.strip().lower()).strip("_")


def compose_name(head: str, qualifier: str | None) -> str:
    """The composite column display-name stored in the ``field_extraction`` log: ``qualifier_head``
    (e.g. ``charged_amount``) or bare ``head`` when there is no qualifier. Preserves within-case
    multiplicity (a case with a charged amount AND a refunded amount stays two distinct rows) while
    the head is what the schema converges on."""
    h = normalise_token(head)
    q = normalise_token(qualifier) if qualifier else ""
    return f"{q}_{h}" if q and q != h else h


def split_qualifier(field_name: str, head: str) -> str | None:
    """Inverse of :func:`compose_name`: recover the qualifier from a composite ``qualifier_head`` given
    its head (``overdraft_fee`` + ``fee`` → ``overdraft``; a bare ``fee`` → ``None``). Used to name the
    exact variant a qualifier-promotion must re-extract."""
    if field_name == head:
        return None
    suffix = f"_{head}"
    if field_name.endswith(suffix):
        return field_name[: -len(suffix)] or None
    return None
