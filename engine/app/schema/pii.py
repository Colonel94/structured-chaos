"""PII / sensitivity gate at promotion + minting (remediation R5, EDD §4.5, trust invariant).

A concept must never enter the DURABLE governed schema — by promotion (a recurring head/qualifier) or by
MINTING (a new head born from `other`) — if it holds protected data: health conditions, government IDs,
payment-card numbers, biometrics, credentials. One promoted health attribute is a disclosure problem,
not a bug. Blocked concepts stay in the emergent bag with a ``sensitivity`` flag (audit trail); they are
never dropped (the raw data already lives, immutable, in the append-only log) — they are just barred from
becoming a first-class column.

Deterministic-first ($0, no model): value patterns (SSN, card numbers) + a CURATED keyword set on the
concept NAME. The keyword set is deliberately narrow and excludes every seed ``HEAD_NOUNS`` word (so the
universal ``condition``/``status``/``amount`` columns are never false-flagged) — it catches only
unambiguous protected terms. The nuanced semantic cases (is this `symptom` head medical?) are caught by
an LLM assessment folded into the mint naming call; this module is the reliable deterministic floor.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Structured-PII patterns in VALUES — high-precision, always applied.
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# 13–19 digit runs (optionally space/dash grouped) → a payment-card / long account number.
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

# Curated sensitive keywords on the concept NAME (snake_case tokens). NONE is a seed HEAD_NOUNS word —
# so a minted/promoted `condition`, `status`, `amount`, `person`, `document` is never mis-flagged.
_NAME_KEYWORDS: dict[str, frozenset[str]] = {
    "government_id": frozenset(
        {
            "ssn",
            "social_security",
            "passport",
            "passport_number",
            "drivers_license",
            "driver_license",
            "national_id",
            "tax_id",
            "ein",
            "state_id",
            "green_card",
            "visa_number",
        }
    ),
    "payment_card": frozenset(
        {
            "card_number",
            "cardnumber",
            "cvv",
            "cvc",
            "ccv",
            "credit_card_number",
            "debit_card_number",
            "pan",
            "card_num",
            "expiry",
            "expiration_date",
            "security_code",
        }
    ),
    "health": frozenset(
        {
            "diagnosis",
            "disease",
            "medical",
            "medical_record",
            "prescription",
            "medication",
            "disability",
            "pregnancy",
            "mental_health",
            "therapy",
            "hiv",
            "cancer",
            "illness",
            "patient",
            "blood_type",
            "allergy",
            "immunization",
            "vaccination",
        }
    ),
    "biometric": frozenset(
        {"fingerprint", "biometric", "retina", "iris", "dna", "faceprint", "voiceprint"}
    ),
    "credentials": frozenset(
        {"password", "passcode", "pin", "pin_number", "security_answer", "secret_question"}
    ),
}

_TOKEN = re.compile(r"[a-z0-9]+")

NONE = "none"


def _luhn_ok(digits: str) -> bool:
    """Luhn checksum — reduces false positives on arbitrary long digit runs (only real card numbers
    pass). A non-card long number (e.g. a case ref) usually fails, so it is NOT flagged as a card.
    """
    ds = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(ds) <= 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(ds)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def classify_sensitivity(name: str, values: Sequence[object] = ()) -> str:
    """Classify a concept's sensitivity from its NAME (+ optional example values). Returns a category
    (``government_id`` | ``payment_card`` | ``health`` | ``biometric`` | ``credentials``) or ``none``.
    A non-``none`` result BARS the concept from the governed schema (promotion/minting)."""
    tokens = set(_TOKEN.findall(name.lower()))
    full = name.lower()
    for category, kws in _NAME_KEYWORDS.items():
        # match a keyword as a whole token, or as a contiguous substring for multi-word keywords
        if tokens & kws or any(
            "_" in k and k.replace("_", "") in full.replace("_", "") for k in kws
        ):
            return category

    for v in values or ():
        s = str(v)
        if _SSN.search(s):
            return "government_id"
        for m in _CARD.finditer(s):
            if _luhn_ok(m.group()):
                return "payment_card"
    return NONE
