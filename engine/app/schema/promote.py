"""Promotion — recurrence lifts a canonical emergent field toward the governed layer, STAGE 4 (EDD
§6.2, GOVERNED-CORE-SCHEMA §1).

*Recurrence proves necessity; one-offs stay in the bag.* A canonical field is promoted once it has
been attested across **N=4** distinct cases (and non-null rate ≥ 0.50 — vacuously true for grounded
emergent values, which always carry a value; the interface keeps the check for later null-valued
attributes). Support is counted over the alias group, so synonyms that merged in STAGE 3 all count
toward the same canonical. Promotion here MARKS the field; the ALTER-add-column + 100%-correct
backfill of history is the separate backfill unit (STAGE 6).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..obs.logging import get_logger
from ..store import api

log = get_logger(__name__)

PROMOTE_N = (
    4  # distinct supporting cases required to promote (the papers' default; tune on the set)
)


def promote_canonicals(session: Session) -> list[tuple[str, str, int]]:
    """Mark every canonical field with support ≥ ``PROMOTE_N`` as promoted (idempotent). Returns the
    promoted ``(hash, name, support)`` — the domain-specialised governed fields that emerged."""
    promoted: list[tuple[str, str, int]] = []
    for chash, cname, already in api.list_canonical_fields(session):
        support = api.canonical_field_support(session, canonical_hash=chash)
        if support >= PROMOTE_N:  # non-null rate == 1.0 for grounded emergent values
            if not already:
                api.mark_field_promoted(session, canonical_hash=chash)
            promoted.append((chash, cname, support))
    return promoted
