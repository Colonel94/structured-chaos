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
from .models import EmergentAttribute, ExtractionResult
from .prompt import PROMPT_VERSION, build_prompt
from .schema import EXTRACTION_SCHEMA, GOVERNED_KEYS

log = get_logger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")
# A candidate value is grounded if this fraction of its significant tokens appears in the source.
_GROUNDING_MIN_OVERLAP = 0.6


def _normalise_name(name: str) -> str:
    """Field names → stable snake_case (the emergent store keys on a stable hash of this)."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


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
        name = _normalise_name(str(item.get("name", "")))
        value = str(item.get("value", "")).strip()
        if not name or not value or name in seen:
            continue
        seen.add(name)
        emergent.append(
            EmergentAttribute(name=name, value=value, grounded=_is_grounded(value, source_lower))
        )

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
