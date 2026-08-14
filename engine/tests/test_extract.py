"""Phase 4.1 — extraction unit: parsing, closed-world grounding, refuse-to-guess (EDD §5–6).

Path A (2026-08-14): an emergent attribute is ``{head, qualifier, value}`` — the head is the column
(closed vocabulary), the qualifier is the open specificity token. No DB, no model — a fake LLM returns
controlled JSON so we test the *mechanism* deterministically: grounding on BOTH free-text slots (value
AND qualifier, independently — owner constraint #3), field_validity, head-enum enforcement, composite
(head,qualifier) dedup, and a non-JSON backend degrading to a flagged-empty result. (Accuracy on real
complaints is a separate real-data + scorer question — never graded on authored cases here.)
"""

from __future__ import annotations

import json

from app.extract.extractor import extract
from app.extract.prompt import PROMPT_VERSION

_CASE = "the chocolate cake arrived crushed and 2 hours late, order 4471"


class _ScriptedLLM:
    """Returns a fixed JSON payload regardless of prompt/schema — for deterministic extractor tests."""

    def __init__(self, payload: object) -> None:
        self._raw = payload if isinstance(payload, str) else json.dumps(payload)

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._raw


def _payload(emergent: list[dict[str, object]], **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "category": "product_fault",
        "fault": "cake crushed and late",
        "desired_outcome": "replacement",
        "emotion_signal": "frustrated",
        "severity_signal": "none",
        "anchor_value": "4471",
        "emergent_attributes": emergent,
    }
    base.update(over)
    return base


async def test_value_gates_attribute_qualifier_must_be_extractive() -> None:
    payload = _payload(
        [
            {"head": "condition", "qualifier": "crushed", "value": "crushed"},  # both grounded
            {"head": "product", "qualifier": None, "value": "chocolate cake"},  # grounded, no qual
            {
                "head": "description",
                "qualifier": None,
                "value": "bright green sprinkles",
            },  # bad val
            {
                "head": "amount",
                "qualifier": "pension",
                "value": "4471",
            },  # val ok, qual NOT verbatim
        ]
    )
    r = await extract(_CASE, llm=_ScriptedLLM(payload))
    assert r.governed["desired_outcome"] == "replacement"
    assert r.governed["anchor_value"] == "4471"
    # VALUE gates the attribute: only "bright green sprinkles" is ungrounded → dropped. The other
    # three are kept. The non-extractive qualifier "pension" (not in the source) is NULLED, not
    # allowed to nuke the grounded value 4471 → the fact survives as a bare "amount".
    grounded = {e.name: e.qualifier for e in r.grounded_emergent}
    assert set(grounded) == {"crushed_condition", "product", "amount"}
    assert grounded["amount"] is None  # invented qualifier dropped, value kept
    assert grounded["crushed_condition"] == "crushed"  # verbatim qualifier retained
    assert r.field_validity == 3 / 4  # 3 of 4 have a grounded VALUE
    assert r.prompt_version == PROMPT_VERSION


async def test_non_extractive_multiword_qualifier_is_nulled() -> None:
    # "badly crushed" is NOT a contiguous span of the source ("arrived crushed") → qualifier nulled,
    # value kept. "chocolate cake" IS contiguous → retained.
    payload = _payload(
        [
            {"head": "condition", "qualifier": "badly crushed", "value": "crushed"},
            {"head": "product", "qualifier": "chocolate cake", "value": "chocolate cake"},
        ]
    )
    r = await extract(_CASE, llm=_ScriptedLLM(payload))
    got = {e.name: e.qualifier for e in r.grounded_emergent}
    assert got == {"condition": None, "chocolate_cake_product": "chocolate_cake"}


async def test_head_must_be_in_closed_vocabulary() -> None:
    # "flavour" is not a head in the closed list → the whole attribute is dropped (never counted).
    payload = _payload(
        [
            {"head": "flavour", "qualifier": None, "value": "chocolate"},  # invalid head → skipped
            {"head": "product", "qualifier": None, "value": "chocolate cake"},  # valid
        ]
    )
    r = await extract(_CASE, llm=_ScriptedLLM(payload))
    assert {e.head for e in r.emergent} == {"product"}
    assert r.field_validity == 1.0  # the one valid, grounded attribute


async def test_refuse_to_guess_null_outcome_is_preserved() -> None:
    payload = _payload([], category="UNCLEAR", desired_outcome=None, anchor_value=None)
    r = await extract("delivery was bad", llm=_ScriptedLLM(payload))
    assert r.governed["desired_outcome"] is None
    assert r.governed["category"] == "UNCLEAR"
    assert r.field_validity == 1.0  # no emergent candidates → vacuously valid


async def test_duplicate_head_qualifier_deduped() -> None:
    payload = _payload(
        [
            {"head": "condition", "qualifier": "Crushed", "value": "crushed"},
            {
                "head": "Condition",
                "qualifier": "crushed",
                "value": "crushed",
            },  # same normalised name
        ]
    )
    r = await extract(_CASE, llm=_ScriptedLLM(payload))
    assert len([e for e in r.emergent if e.name == "crushed_condition"]) == 1


async def test_non_json_backend_degrades_to_flagged_empty() -> None:
    r = await extract(_CASE, llm=_ScriptedLLM("I think the category is product_fault..."))
    assert r.governed == {}
    assert r.emergent == []
    assert r.field_validity == 0.0  # fully flagged, not a crash
