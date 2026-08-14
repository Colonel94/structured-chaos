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

*Recurrence proves necessity; one-offs stay in the bag.* Promotion here MARKS the concept; the
ALTER-add-column + 100%-correct backfill of history is the separate backfill unit (STAGE 6).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

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


def promote_heads(session: Session) -> list[tuple[str, int]]:
    """Dimension 1: mark every head with support ≥ ``PROMOTE_HEAD_N`` promoted (idempotent). Returns
    the promoted ``(head, support)`` — the domain-specialised governed columns that emerged."""
    promoted: list[tuple[str, int]] = []
    for head, support, already in api.list_emergent_heads(session):
        if support >= PROMOTE_HEAD_N:
            if not already:
                api.mark_head_promoted(session, head=head)
                log.info("promote.head", head=head, support=support)
            promoted.append((head, support))
    return promoted


def promote_qualifiers(session: Session) -> list[tuple[str, str, int]]:
    """Dimension 2: split a qualifier variant into its own column when it recurs across ≥
    ``PROMOTE_QUALIFIER_M`` cases AND its head is already promoted (constraint #2). Idempotent.
    Returns the promoted ``(field_name, head, support)`` variants. Run AFTER ``promote_heads`` so the
    head-promoted precondition sees this round's promotions."""
    promoted_heads = {h for h, _s, is_p in api.list_emergent_heads(session) if is_p}
    split: list[tuple[str, str, int]] = []
    for fhash, fname, head, support, already in api.list_emergent_field_variants(session):
        if head is None or head not in promoted_heads:
            continue  # a qualifier can only split under a promoted head — no orphan variants
        if fname == head:
            continue  # the bare-head variant IS the head column, not a split of it
        if support >= PROMOTE_QUALIFIER_M:
            if not already:
                api.mark_field_promoted(session, canonical_hash=fhash)
                log.info("promote.qualifier", field=fname, head=head, support=support)
            split.append((fname, head, support))
    return split


def promote(session: Session) -> tuple[list[tuple[str, int]], list[tuple[str, str, int]]]:
    """Run both promotion dimensions in the correct order (heads first, then qualifier splits under
    the freshly-promoted heads). Returns ``(promoted_heads, split_qualifiers)``."""
    heads = promote_heads(session)
    quals = promote_qualifiers(session)
    return heads, quals
