"""Zero-shot extraction — case text → governed core + grounded emergent candidates (EDD §5–6).

STAGE 2 of the moat pipeline: the LLM extracts semantics only, JSON-schema-constrained (valid JSON
guaranteed), and every emergent candidate is checked against the source text (**closed-world
grounding**) so a hallucinated field can't enter the emergent layer. The LLM backend is injected, so
this is backend-agnostic (local Ollama today) and unit-testable with a fake.

Grounding is checked at the VALUE level: a candidate's value must trace back to the case text (exact
substring, or a strong token overlap for paraphrases). ``field_validity`` = grounded fraction; below
1.0 the extraction is flagged (the caller decides to drop the ungrounded candidates and/or repair).
"""

from __future__ import annotations

import json
import re

from ..backends.interfaces import LLMBackend
from ..obs.logging import get_logger
from .head_nouns import HEAD_NOUNS, normalise_token
from .models import EmergentAttribute, ExtractionResult
from .prompt import PROMPT_VERSION, build_prompt
from .schema import EXTRACTION_SCHEMA, GOVERNED_KEYS

log = get_logger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")
# A candidate value is grounded if this fraction of its significant tokens appears in the source.
_GROUNDING_MIN_OVERLAP = 0.6
# A qualifier is a SHORT discriminator (the prompt asks for 1-3 words). Enforced in code, not left to
# the model: a longer "qualifier" is a sentence/clause the model dumped, so it is nulled. This is what
# stops the `description`-as-narrative-dump failure mode (a whole verbatim sentence otherwise passes
# the extractive check). Allow up to 4 to tolerate the odd legitimate phrase ("credit card provider").
_MAX_QUALIFIER_TOKENS = 4


def _is_extractive(qualifier_norm: str, source_lower: str) -> bool:
    """Whether the qualifier is a VERBATIM contiguous span of the source — strict extractiveness
    (owner directive 2026-08-14). The qualifier's tokens, space-joined, must appear as a contiguous
    run in the source's token stream (both sides reduced to alnum tokens, so punctuation/whitespace
    differences — "past-due" vs "past due" — don't matter). A paraphrase or a reordering
    ("payment_status" from "status of my payment") is NOT extractive and is rejected. This is stricter
    than value grounding on purpose: the qualifier is optional context, so a non-extractive one is
    dropped (nulled) rather than allowed to invent structure."""
    phrase = " ".join(qualifier_norm.split("_"))
    if not phrase:
        return False
    source_tokens = " ".join(_TOKEN.findall(source_lower))
    return phrase in source_tokens


def _is_grounded(value: str, source_lower: str) -> bool:
    """Whether ``value`` traces back to the source text — the anti-hallucination check. Exact
    substring wins; otherwise require a strong overlap of the value's significant tokens (so a
    paraphrase like "crushed on one side" grounds against "the box was crushed on one side", but an
    invented value does not)."""
    v = value.strip().lower()
    if not v:
        return False
    if v in source_lower:
        return True
    tokens = _TOKEN.findall(v)
    significant = [t for t in tokens if len(t) > 2]
    if not significant:
        # Short value (a number / "5pm") — ground on any of its raw tokens appearing verbatim.
        return any(t in source_lower for t in tokens)
    hits = sum(1 for t in significant if t in source_lower)
    return hits / len(significant) >= _GROUNDING_MIN_OVERLAP


async def extract(case_text: str, *, llm: LLMBackend) -> ExtractionResult:
    """Extract one case's governed core + grounded emergent candidates from its normalised text."""
    raw = await llm.complete(build_prompt(case_text), schema=EXTRACTION_SCHEMA)
    # Schema-constrained → valid JSON. Be defensive anyway: a backend without grammar support could
    # return prose, in which case we surface an empty, fully-flagged result rather than crashing.
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise TypeError("extraction output was not a JSON object")
    except (json.JSONDecodeError, TypeError):
        log.info("extract.non_json", chars=len(raw))
        return ExtractionResult(
            governed={}, emergent=[], field_validity=0.0, prompt_version=PROMPT_VERSION, raw=raw
        )

    source_lower = case_text.lower()
    emergent: list[EmergentAttribute] = []
    seen: set[str] = set()
    for item in obj.get("emergent_attributes", []) or []:
        if not isinstance(item, dict):
            continue
        head = normalise_token(str(item.get("head", "")))
        if head not in HEAD_NOUNS:  # grammar enum guarantees this; defensive against a raw backend
            continue
        raw_qual = item.get("qualifier")
        qualifier = normalise_token(str(raw_qual)) if raw_qual else None
        qualifier = qualifier or None  # normalised-to-empty → no qualifier
        value = str(item.get("value", "")).strip()
        if not value:
            continue
        # Closed-world grounding on BOTH free-text slots, independently (owner constraint #3) — but the
        # two slots are handled asymmetrically because they mean different things:
        #  * VALUE gates the attribute: an ungrounded value has nothing real to store → drop the whole
        #    attribute (overlap grounding tolerates reformatting like "$4,200.00" vs "4200").
        #  * QUALIFIER is optional context and must be strictly EXTRACTIVE (a verbatim source span). A
        #    non-extractive qualifier is NULLED, not allowed to nuke a grounded value — so we keep the
        #    fact (head + value) and simply drop the invented context. Nothing ungrounded is stored.
        if qualifier is not None and (
            len(qualifier.split("_")) > _MAX_QUALIFIER_TOKENS
            or not _is_extractive(qualifier, source_lower)
        ):
            qualifier = None
        attr = EmergentAttribute(
            head=head, qualifier=qualifier, value=value, grounded=_is_grounded(value, source_lower)
        )
        if attr.name in seen:  # same (head, qualifier) already seen this case → drop the duplicate
            continue
        seen.add(attr.name)
        emergent.append(attr)

    n = len(emergent)
    field_validity = 1.0 if n == 0 else sum(e.grounded for e in emergent) / n
    governed = {k: obj.get(k) for k in GOVERNED_KEYS}
    return ExtractionResult(
        governed=governed,
        emergent=emergent,
        field_validity=field_validity,
        prompt_version=PROMPT_VERSION,
        raw=raw,
    )
