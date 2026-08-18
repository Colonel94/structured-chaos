"""Key normalisation + hashing — the SINGLE source of truth shared by ingest and lookup.

Ingest hashes an object's identifier values into ``object_key``; the resolver hashes the anchor a
customer quotes and looks it up. If the two normalised a value even slightly differently, an exact
match would silently miss — so both MUST call these functions. Normalisation is deliberately
conservative (it only removes formatting noise, never disambiguating content):

- phone-like fields (name hints ``phone``/``mobile``/``tel``/``cell``): keep DIGITS only, so
  ``+44 7700 900112``, ``(07700) 900112`` and ``07700900112`` collapse. (International-vs-national
  prefixes are a known PoC limitation — digits-only won't unify ``+44…`` with a ``0…`` national form;
  that needs libphonenumber, deferred.)
- everything else (order ids, refs, emails): casefold + collapse internal whitespace, so
  ``BK-10231`` == ``bk-10231`` == ``BK 10231``. Dashes are KEPT (they can be significant).
"""

from __future__ import annotations

import hashlib
import re

_PHONE_HINT = re.compile(r"\b(phone|mobile|tel|cell|contact_number|msisdn)\b", re.IGNORECASE)
_WS = re.compile(r"\s+")


def is_phone_field(field: str) -> bool:
    """Whether a field name looks like a phone number (→ digits-only normalisation)."""
    return bool(_PHONE_HINT.search(field))


def normalise_key_value(field: str, value: str) -> str:
    """Normalise one identifier value for hashing. Returns "" for an all-noise value (caller skips)."""
    v = value.strip()
    if not v:
        return ""
    if is_phone_field(field):
        digits = re.sub(r"\D", "", v)
        return digits
    return _WS.sub(" ", v).casefold()


def hash_key(normalised: str) -> str:
    """sha256 of an already-normalised value — the ``object_key.key_value_hash`` lookup key."""
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def normalised_hash(field: str, value: str) -> tuple[str, str] | None:
    """``(normalised, hash)`` for a raw ``(field, value)``, or None if the value is empty/all-noise."""
    norm = normalise_key_value(field, value)
    if not norm:
        return None
    return norm, hash_key(norm)
