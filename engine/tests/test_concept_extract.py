"""Phase 4 STAGE 6 — targeted single-concept re-extraction (the backfill mechanism).

No DB, no model — a scripted LLM returns controlled {present,value,qualifier} JSON so the grounding +
absence logic is deterministic: a present, grounded value returns an attribute; an ungrounded value or
present=false returns None; a variant's fixed qualifier must itself be extractive in the case.
"""

from __future__ import annotations

import json

from app.extract.concept_extract import extract_concept

_CASE = "the late fee was $45.00 and the box arrived crushed"


class _LLM:
    def __init__(self, payload: object) -> None:
        self._raw = payload if isinstance(payload, str) else json.dumps(payload)

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._raw


async def test_head_concept_found_with_verbatim_qualifier() -> None:
    r = await extract_concept(
        _CASE,
        head="amount",
        qualifier=None,
        llm=_LLM({"present": True, "value": "$45.00", "qualifier": "late fee"}),
    )
    assert r is not None
    assert r.head == "amount" and r.value == "$45.00"
    assert r.qualifier == "late_fee"  # verbatim + normalised
    assert r.name == "late_fee_amount"


async def test_absent_when_not_present() -> None:
    r = await extract_concept(
        _CASE,
        head="amount",
        qualifier=None,
        llm=_LLM({"present": False, "value": None, "qualifier": None}),
    )
    assert r is None


async def test_ungrounded_value_is_rejected() -> None:
    # value the source never states → not grounded → None (never store a hallucinated backfill value).
    r = await extract_concept(
        _CASE,
        head="amount",
        qualifier=None,
        llm=_LLM({"present": True, "value": "$999.00", "qualifier": None}),
    )
    assert r is None


async def test_variant_requires_its_qualifier_to_be_extractive() -> None:
    # Re-extracting the "late fee" variant: value grounded AND the qualifier "late" appears → found.
    ok = await extract_concept(
        _CASE,
        head="fee",
        qualifier="late",
        llm=_LLM({"present": True, "value": "$45.00", "qualifier": None}),
    )
    assert ok is not None and ok.head == "fee" and ok.qualifier == "late"
    # The "overdraft" variant: even if the model claims present, "overdraft" is not in the source →
    # this case is not an instance of the variant → None.
    no = await extract_concept(
        _CASE,
        head="fee",
        qualifier="overdraft",
        llm=_LLM({"present": True, "value": "$45.00", "qualifier": None}),
    )
    assert no is None


async def test_non_json_is_absent() -> None:
    r = await extract_concept(_CASE, head="amount", qualifier=None, llm=_LLM("not json at all"))
    assert r is None
