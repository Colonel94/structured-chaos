"""Promotion — recurrence lifts an emergent concept toward the governed layer, STAGE 4 (EDD §6.2,
GOVERNED-CORE-SCHEMA §1). Path A makes this **two-dimensional** (owner constraint #2, 2026-08-14):

    Dimension 1 — HEAD promotion: a head (the emergent *column*) attested across ``PROMOTE_HEAD_N``
      distinct cases is promoted to a governed column. This is the common case.

    Dimension 2 — QUALIFIER promotion: a single ``qualifier_head`` variant (e.g. ``overdraft_fee``
      under the promoted head ``fee``) attested across ``PROMOTE_QUALIFIER_M`` distinct cases is
      *split out* into its own variant column. Splitting a column is a schema change with backfill
      implications on already-committed data, so it is **strictly harder** than head promotion
      (``M > N``) and **requires the head to be promoted first** — there is never an orphan-qualifier
      column whose parent head doesn't exist.

Promotion here MARKS the concept and returns which were NEWLY promoted; the retroactive **backfill**
(re-EXTRACTION across history, `app/schema/backfill.py`) is fired for the new ones by the periodic
promote-scan task — NOT inline per case (a promotion mid-burst must not cascade backfill into live
intake). *Recurrence proves necessity; one-offs stay in the bag.*
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..extract.head_nouns import split_qualifier
from ..obs.logging import get_logger
from ..store import api

log = get_logger(__name__)

# Distinct supporting cases to promote a HEAD to a governed column (the papers' default; tune on the
# scored set, never guessed in prod).
PROMOTE_HEAD_N = 4
# Distinct supporting cases to split a QUALIFIER into its own variant column. STRICTLY HARDER than a
# head (M > N): a column split rewrites committed data, so we demand stronger recurrence. Tunable on a
# held-out slice — NOT on the convergence proof set (self-grading, CLAUDE.md §10).
PROMOTE_QUALIFIER_M = 8


@dataclass(frozen=True)
class PromotedConcept:
    """A concept that IS promoted after a scan. ``is_new`` distinguishes a promotion that happened
    THIS scan (→ trigger backfill) from one already promoted before (→ already backfilled). ``head``
    + ``qualifier`` name the exact thing backfill re-extracts; ``concept_key`` is the backfill/marker
    identity (the head, or the composite ``qualifier_head``)."""

    kind: str  # 'head' | 'variant'
    concept_key: str
    head: str
    qualifier: str | None
    support: int
    is_new: bool


def promote_heads(session: Session) -> list[PromotedConcept]:
    """Dimension 1: promote every head with support ≥ ``PROMOTE_HEAD_N`` (idempotent)."""
    out: list[PromotedConcept] = []
    for head, support, already in api.list_emergent_heads(session):
        if support >= PROMOTE_HEAD_N:
            if not already:
                api.mark_head_promoted(session, head=head)
                log.info("promote.head", head=head, support=support)
            out.append(PromotedConcept("head", head, head, None, support, is_new=not already))
    return out


def promote_qualifiers(session: Session) -> list[PromotedConcept]:
    """Dimension 2: split a qualifier variant into its own column when it recurs across ≥
    ``PROMOTE_QUALIFIER_M`` cases AND its head is already promoted (constraint #2). Idempotent. Run
    AFTER ``promote_heads`` so the head-promoted precondition sees this scan's promotions."""
    promoted_heads = {h for h, _s, is_p in api.list_emergent_heads(session) if is_p}
    out: list[PromotedConcept] = []
    for fhash, fname, head, support, already in api.list_emergent_field_variants(session):
        if head is None or head not in promoted_heads:
            continue  # a qualifier can only split under a promoted head — no orphan variants
        if fname == head:
            continue  # the bare-head variant IS the head column, not a split of it
        if support >= PROMOTE_QUALIFIER_M:
            if not already:
                api.mark_field_promoted(session, canonical_hash=fhash)
                log.info("promote.qualifier", field=fname, head=head, support=support)
            out.append(
                PromotedConcept(
                    "variant",
                    fname,
                    head,
                    split_qualifier(fname, head),
                    support,
                    is_new=not already,
                )
            )
    return out


def promote(session: Session) -> list[PromotedConcept]:
    """Run both promotion dimensions in the correct order (heads first, then qualifier splits under
    the freshly-promoted heads). Returns all promoted concepts (``is_new`` flags this scan's)."""
    return promote_heads(session) + promote_qualifiers(session)
