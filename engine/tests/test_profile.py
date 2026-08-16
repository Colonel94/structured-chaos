"""R4 statistics-before-semantics — the deterministic value profiler + its escape-valve filtering.

No DB, no model: the profiler is pure, and the extractor uses a scripted LLM. Proves the profiler
keeps concrete values (money/date/name/id/short phrase, incl. long proper-noun names like a statute)
and rejects clauses + redaction junk; and that the extractor drops a clause from `other`/`description`
(the escape valve) while KEEPING the same clause under a content head (a symptom is real signal)."""

from __future__ import annotations

import json

from app.extract.extractor import extract
from app.extract.profile import profile_value


def test_profiler_keeps_concrete_rejects_clauses_and_junk() -> None:
    concrete = [
        "Fair Debt Collection Practices Act",  # long proper name, 0 function words
        "15 U.S.C. 1692c (c)",  # legal citation
        "12 CFR 1006.34",
        "collection accounts",
        "Wells Fargo",
        "$500.00",
        "XX/XX/2023",  # partly-redacted DATE — still concrete
        "past due",
        "6 months",
    ]
    junk = [
        "you are in violation",  # clause (0.75 function words)
        "financial hardship that contributed to this account becoming",  # clause
        "proof that I am responsible for this debt",  # clause
        "stress causing a lot of stress and XXXX",  # clause
        "XXXX",  # redaction
        "partial partially XXXX XXXX XXXX XXXX",  # redaction-dominant
        "",  # empty
    ]
    for v in concrete:
        assert profile_value(v).is_concrete, f"should keep: {v!r} ({profile_value(v).kind})"
    for v in junk:
        assert not profile_value(v).is_concrete, f"should drop: {v!r} ({profile_value(v).kind})"


class _ScriptedLLM:
    def __init__(self, payload: dict[str, object]) -> None:
        self._raw = json.dumps(payload)

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return self._raw


async def test_extractor_drops_clause_from_escape_valve_keeps_it_in_content_head() -> None:
    # Same clausal value under `other` (escape valve → dropped) and `condition` (content → kept).
    case = "the airbag light stays on and the seatbelt does not retract after a crash"
    clause = "the seatbelt does not retract after a crash"
    payload: dict[str, object] = {
        "category": "safety_health",
        "fault": "airbag/seatbelt fault",
        "desired_outcome": None,
        "emotion_signal": "frustrated",
        "severity_signal": "safety_health",
        "anchor_value": None,
        "emergent_attributes": [
            {"head": "other", "qualifier": None, "value": clause},  # escape valve → R4 drops
            {"head": "condition", "qualifier": None, "value": clause},  # content head → kept
            {"head": "other", "qualifier": None, "value": "airbag light"},  # concrete → kept
        ],
    }
    result = await extract(case, llm=_ScriptedLLM(payload))
    kept = {(a.head, a.value) for a in result.emergent}
    assert ("other", clause) not in kept  # clause dropped from the escape valve
    assert ("condition", clause) in kept  # same clause kept under a content head
    assert ("other", "airbag light") in kept  # a concrete escape-valve value survives
