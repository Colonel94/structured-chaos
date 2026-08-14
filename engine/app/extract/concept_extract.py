"""Targeted single-concept re-extraction — the retroactive backfill mechanism (STAGE 6, 2026-08-14).

When a head/qualifier is PROMOTED, the moat re-extracts THAT ONE concept against the retained
originals of history — the cases the forward extractor never captured it in, because at the time it
wasn't looking for it (an "other"-escape head that later promoted, a qualifier that only became a
first-class column on recurrence, or simply an earlier/weaker prompt). This is the part no incumbent
does: the schema improves BACKWARDS. It is re-EXTRACTION against source text, NOT a re-projection of
already-extracted values (which finds nothing new — CLAUDE.md §10 "distrust the cheap path").

Deliberately narrow: one concept, one focused prompt (not the full extraction schema), so a promotion
does not re-run the whole extractor over history. Grounding reuses the EXACT gates the forward
extractor uses (value overlap + strictly-extractive, length-capped qualifier), so a backfilled value
is held to the same closed-world standard as a live one.
"""

from __future__ import annotations

import json

from ..backends.interfaces import LLMBackend
from ..obs.logging import get_logger
from .extractor import _MAX_QUALIFIER_TOKENS, _is_extractive, _is_grounded
from .head_nouns import normalise_token
from .models import EmergentAttribute

log = get_logger(__name__)

# Bump on any change to the concept prompt — it is stamped into backfilled provenance + the
# idempotency key, so a re-run under a new prompt is a fresh attempt, never a silent overwrite.
CONCEPT_PROMPT_VERSION = "concept-v1"

_CONCEPT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "present": {"type": "boolean"},
        "value": {"type": ["string", "null"]},
        "qualifier": {"type": ["string", "null"]},
    },
    "required": ["present", "value", "qualifier"],
}


def _build_prompt(case_text: str, *, head: str, qualifier: str | None) -> str:
    if qualifier is not None:
        what = f'a "{qualifier} {head}" (a {head} of the specific kind "{qualifier}")'
        rules = (
            f"If the message states {what}, set present=true and value = the exact value copied from "
            f'the message. The word "{qualifier}" (or an obvious form of it) must actually appear — if '
            f"it does not, set present=false. Set qualifier = null (it is fixed)."
        )
    else:
        what = f"a {head}"
        rules = (
            f"If the message states {what}, set present=true, value = the exact {head} value copied "
            f"from the message, and qualifier = a 1-3 word phrase COPIED VERBATIM from the message "
            f"that specifies which {head} it is (or null if the head alone is enough)."
        )
    return (
        f"You are checking a customer message for ONE specific fact: {what}. Look ONLY for this — "
        f"ignore everything else.\n{rules}\nIf it is not stated, set present=false, value=null, "
        f"qualifier=null. NEVER invent — copy from the message.\nReturn JSON only.\n\n"
        f'Message:\n"""{case_text}"""'
    )


async def extract_concept(
    case_text: str, *, head: str, qualifier: str | None, llm: LLMBackend
) -> EmergentAttribute | None:
    """Re-extract ONE concept from ``case_text``. Returns a grounded :class:`EmergentAttribute` if the
    concept is genuinely present, else ``None`` (legitimately absent → the caller records an ``absent``
    marker so this case is never re-extracted for this concept again). ``head``/``qualifier`` name the
    concept: ``qualifier=None`` re-extracts a head; a set ``qualifier`` re-extracts that exact variant.
    """
    raw = await llm.complete(
        _build_prompt(case_text, head=head, qualifier=qualifier), schema=_CONCEPT_SCHEMA
    )
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise TypeError
    except (json.JSONDecodeError, TypeError):
        log.info("concept.non_json", head=head)
        return None
    if not obj.get("present") or not str(obj.get("value", "")).strip():
        return None

    source_lower = case_text.lower()
    value = str(obj["value"]).strip()
    if not _is_grounded(
        value, source_lower
    ):  # value must trace to the source, same gate as forward
        return None

    if qualifier is not None:
        # A variant: the qualifier is fixed to the promoted one and must itself be extractive here,
        # else this case is not really an instance of the variant.
        q_norm = normalise_token(qualifier)
        if not _is_extractive(q_norm, source_lower):
            return None
        final_qualifier: str | None = q_norm
    else:
        raw_q = obj.get("qualifier")
        q_norm = normalise_token(str(raw_q)) if raw_q else ""
        final_qualifier = q_norm or None
        if final_qualifier is not None and (
            len(final_qualifier.split("_")) > _MAX_QUALIFIER_TOKENS
            or not _is_extractive(final_qualifier, source_lower)
        ):
            final_qualifier = None

    return EmergentAttribute(head=head, qualifier=final_qualifier, value=value, grounded=True)
