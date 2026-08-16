"""Statistics-before-semantics (remediation R4, EDD §4.2) — a DETERMINISTIC profile of an extracted
value, computed WITHOUT the model.

Its job in the moat: gate the emergent layer so CLAUSES and redaction-junk never enter it. The
head-minting spike (2026-08-17b) proved emergence works BUT that ``other``/``description`` is polluted
with narrative clauses ("you are in violation", "financial hardship that contributed to this account")
and redaction junk ("partial partially XXXX XXXX"), which cluster into GARBAGE minted heads at every
threshold. A concrete value — a number, amount, date, id, name, short noun phrase — is what a structured
fact IS; a clause is narrative that already lives in ``fault``. This filter is what makes the escape
valve clean enough to mint real heads from (and dedup cleanly).

The discriminator is the FUNCTION-WORD RATIO, not raw length: "Fair Debt Collection Practices Act" is
five tokens but zero function words (a concrete name → keep), while "proof that I am responsible for
this debt" is function-word-heavy narrative (→ drop). This is deterministic, cheap, and runs before any
model call — the published "statistics before semantics" remedy for force-fit/hallucinated fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9]+")
_MONEY = re.compile(r"[$£€]|\bdollars?\b|\bcents?\b|\busd\b|\baed\b|\bgbp\b")
_DATE = re.compile(
    r"\b\d{1,4}[/-]\d{1,2}([/-]\d{1,4})?\b|\b(19|20)\d{2}\b|\bxx[/-]xx\b"
    r"|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
)

# Articles, prepositions, pronouns, conjunctions, auxiliary/common verbs, negations. A high ratio of
# these signals narrative (a clause), not a concrete value. Curated to NOT include content nouns/verbs
# that appear in real values (so proper-noun phrases and typed values pass).
_FUNCTION = frozenset(
    """
a an the this that these those such
my your our their his her its it they them we you i me he she who whom which what
to of in on at for with from by about into over under as than then
and or but nor so yet if because while when where
is are was were be been being am has have had do does did will would shall can could should may might must
not no nor never
""".split()
)


@dataclass(frozen=True)
class ValueProfile:
    """A deterministic read of a value. ``is_concrete`` is the gate: False → do NOT store in the
    emergent layer (it is a clause, redaction junk, or empty — narrative, not a structured fact)."""

    kind: str  # money | date | number | identifier | phrase | clause | redaction | empty
    is_concrete: bool
    tokens: int
    function_ratio: float


def profile_value(value: str) -> ValueProfile:
    """Classify a value deterministically. Concrete kinds (money/date/number/identifier/phrase) enter
    the emergent layer; clause/redaction/empty are rejected as narrative/junk."""
    v = value.strip()
    toks = _TOKEN.findall(v.lower())
    n = len(toks)
    if n == 0:
        return ValueProfile("empty", False, 0, 0.0)

    fn = sum(1 for t in toks if t in _FUNCTION)
    ratio = fn / n

    # Typed concrete values pass regardless of length or partial redaction — a money amount or a date
    # is never a clause, and "XX/XX/2023" is a real (partly-redacted) date, not junk. Checked BEFORE
    # the redaction rule so a partly-redacted typed value isn't mistaken for pure junk.
    low = v.lower()
    if _MONEY.search(low):
        return ValueProfile("money", True, n, ratio)
    if _DATE.search(low):
        return ValueProfile("date", True, n, ratio)

    # Redaction junk: half or more of the alnum tokens are the bare XXXX placeholder → no real content.
    redacted = sum(1 for t in toks if set(t) == {"x"})
    if redacted / n >= 0.5:
        return ValueProfile("redaction", False, n, 0.0)

    # Clause: narrative prose — long AND function-word-heavy, OR short but function-word-dominated.
    # This is what drops "you are in violation" (4 tok, 0.75) and "...that contributed to this account"
    # (8 tok, 0.375) while keeping "Fair Debt Collection Practices Act" (5 tok, 0.0).
    if (n >= 6 and ratio >= 0.25) or (n >= 4 and ratio >= 0.4):
        return ValueProfile("clause", False, n, ratio)

    has_digit = any(c.isdigit() for c in v)
    if has_digit and n <= 5:
        kind = "number" if all(c.isdigit() or not c.isalpha() for c in v) else "identifier"
        return ValueProfile(kind, True, n, ratio)
    return ValueProfile("phrase", True, n, ratio)
