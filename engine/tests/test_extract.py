"""Phase 4.1 — extraction unit: parsing, closed-world grounding, refuse-to-guess (EDD §5–6).

No DB, no model — a fake LLM returns controlled JSON so we test the *mechanism* deterministically:
the grounding gate drops hallucinated candidates, field_validity is computed, names normalise, and a
non-JSON backend degrades to a flagged-empty result. (Accuracy on real complaints is a separate,
real-data + scorer question — never graded on authored cases here.)
"""

from __future__ import annotations

import json

from app.extract.extractor import extract
from app.extract.prompt import PROMPT_VERSION


class _ScriptedLLM:
    """Returns a fixed JSON payload regardless of prompt/schema — for deterministic extractor tests."""

    def __init__(self, payload: object) -> None:
        self._raw = payload if isinstance(payload, str) else json.dumps(payload)

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._raw


_CASE = "the chocolate cake arrived crushed and 2 hours late, order 4471"


async def test_grounding_gate_drops_hallucinated_candidates() -> None:
    payload = {
        "category": "product_fault",
        "fault": "cake crushed and late",
        "desired_outcome": "replacement",
        "emotion_signal": "frustrated",
        "severity_signal": "none",
        "anchor_value": "4471",
        "emergent_attributes": [
            {"name": "Packaging Condition", "value": "crushed"},  # grounded (in source)
            {"name": "flavour", "value": "chocolate"},  # grounded
            {"name": "colour", "value": "bright green sprinkles"},  # NOT in source → hallucinated
        ],
    }
    r = await extract(_CASE, llm=_ScriptedLLM(payload))
    assert r.governed["desired_outcome"] == "replacement"
    assert r.governed["anchor_value"] == "4471"
    names = {e.name: e.grounded for e in r.emergent}
    assert names["packaging_condition"] is True  # name normalised to snake_case + grounded
    assert names["flavour"] is True
    assert names["colour"] is False  # the invented value is flagged ungrounded
    assert r.field_validity == 2 / 3  # 2 of 3 grounded
    assert {e.name for e in r.grounded_emergent} == {"packaging_condition", "flavour"}
    assert r.prompt_version == PROMPT_VERSION


async def test_refuse_to_guess_null_outcome_is_preserved() -> None:
    payload = {
        "category": "UNCLEAR",
        "fault": "delivery was bad",
        "desired_outcome": None,  # customer didn't state a want → stays null (routes to elicitation)
        "emotion_signal": "calm",
        "severity_signal": "none",
        "anchor_value": None,
        "emergent_attributes": [],
    }
    r = await extract("delivery was bad", llm=_ScriptedLLM(payload))
    assert r.governed["desired_outcome"] is None
    assert r.governed["category"] == "UNCLEAR"
    assert r.field_validity == 1.0  # no emergent candidates → vacuously valid


async def test_duplicate_candidate_names_deduped() -> None:
    payload = {
        "category": "product_fault",
        "fault": "x",
        "desired_outcome": "refund",
        "emotion_signal": "calm",
        "severity_signal": "none",
        "anchor_value": None,
        "emergent_attributes": [
            {"name": "flavour", "value": "chocolate"},
            {"name": "Flavour", "value": "chocolate"},  # same normalised name → deduped
        ],
    }
    r = await extract(_CASE, llm=_ScriptedLLM(payload))
    assert len([e for e in r.emergent if e.name == "flavour"]) == 1


async def test_non_json_backend_degrades_to_flagged_empty() -> None:
    r = await extract(_CASE, llm=_ScriptedLLM("I think the category is product_fault..."))
    assert r.governed == {}
    assert r.emergent == []
    assert r.field_validity == 0.0  # fully flagged, not a crash
