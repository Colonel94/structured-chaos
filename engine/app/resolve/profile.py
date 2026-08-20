"""Statistics-before-semantics profiling of an uploaded object collection (EDD §16.1, §4.2).

A tenant uploads objects with an arbitrary schema; before anything is stored, a DETERMINISTIC pass
(no LLM) decides which fields are IDENTIFIERS — the ones the resolver can look a customer's anchor up
against. The PRIMARY signal is cardinality (a statistic, not a guess): a field whose non-null values
are ≳ unique across the batch is an identifier (an ``order_id`` is unique; ``items`` is not). The one
typed EXCEPTION is contact identifiers — a phone or email is a real key even when it repeats (a
customer with two orders shares a phone), so it qualifies on name/value shape even below the
uniqueness bar; the resolver handles the repeat by asking rather than guessing.

Free-text/descriptive fields (``items``, ``notes``, ``customer_name``, ``address``) are deliberately
NOT keys: matching a customer to an order by a fuzzy name or address is how you act on the wrong one.
Those feed the embedding (fuzzy fallback), not the exact-key index.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

# unique-enough to be treated as an identifier on cardinality alone.
_UNIQUE_RATIO = 0.9
_CONTACT_HINT = re.compile(r"(^|_)(phone|mobile|tel|cell|email|msisdn)(_|$)", re.IGNORECASE)
# Names that read like a record's own reference id — used to pick the DISPLAY id when several columns
# are coincidentally unique (with few rows a timestamp can be as unique as the order number, so
# cardinality alone can't disambiguate the display id; the name hint does).
_ID_NAME = re.compile(
    r"(^|_)(id|ref|reference|code|number|sku|barcode|ticket|uuid|guid)(_|$)", re.IGNORECASE
)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_VALUE = re.compile(r"^[+(]?\d[\d\s().-]{6,}$")


def _is_contact_field(field: str, values: Sequence[str]) -> bool:
    if _CONTACT_HINT.search(field):
        return True
    hits = sum(bool(_EMAIL.match(v) or _PHONE_VALUE.match(v)) for v in values)
    return hits / len(values) >= 0.8 if values else False


def profile_key_fields(objects: Sequence[Mapping[str, object]]) -> list[str]:
    """Return the identifier field names for a batch, most-selective first. Empty if none qualify
    (the collection is then only fuzzy-resolvable)."""
    if not objects:
        return []
    fields: dict[str, list[str]] = {}
    for obj in objects:
        for k, v in obj.items():
            if v is None:
                continue
            s = str(v).strip()
            if s:
                fields.setdefault(k, []).append(s)

    scored: list[tuple[float, str]] = []
    for field, values in fields.items():
        if not values:
            continue
        uniqueness = len(set(values)) / len(values)
        if uniqueness >= _UNIQUE_RATIO or _is_contact_field(field, values):
            scored.append((uniqueness, field))
    scored.sort(key=lambda t: (-t[0], t[1]))  # most-selective first, then name for stability
    return [field for _u, field in scored]


def is_contact_field(field: str) -> bool:
    """Whether a field is a contact identifier (phone/email) by name — used to prefer a non-contact
    field as the object's display ``external_id``."""
    return bool(_CONTACT_HINT.search(field))


def is_identifier_name(field: str) -> bool:
    """Whether a field NAME reads like a reference id (``order_id``, ``booking_ref``, ``invoice_number``)
    — the preferred display ``external_id`` when several columns are coincidentally unique."""
    return bool(_ID_NAME.search(field))
