"""Phase 3 — conversation windowing: new case vs follow-up (TECH-SPEC §2.4, EDD §11).

No DB. The deterministic branches (no prior / within-idle / long-after-close) never call the model;
the ambiguous branches consult an injected fake ``LLMBackend``. Bias-when-uncertain = new case.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.intake.models import InboundMessage
from app.intake.windowing import PriorCase, decide_window


def _msg(at: datetime, text: str = "hello") -> InboundMessage:
    return InboundMessage(channel="file_drop", sender="+9715", sent_at=at, text=text)


class _FakeLLM:
    """Returns a fixed windowing verdict, or malformed output to test the fail-safe."""

    def __init__(self, decision: str = "follow_up", *, malformed: bool = False) -> None:
        self._decision = decision
        self._malformed = malformed

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        if self._malformed:
            return "not json"
        return json.dumps({"decision": self._decision, "reason": "test"})


async def test_no_prior_is_new() -> None:
    d = await decide_window(_msg(datetime.now(UTC)), None)
    assert d.action == "new" and d.method == "no_prior"


async def test_within_idle_window_is_follow_up() -> None:
    now = datetime.now(UTC)
    prior = PriorCase(uuid4(), "incomplete", now - timedelta(hours=2))
    d = await decide_window(_msg(now), prior)
    assert d.action == "follow_up" and d.method == "idle_gap"
    assert d.case_id == prior.case_id


async def test_open_case_idle_beyond_window_defaults_new_without_llm() -> None:
    now = datetime.now(UTC)
    prior = PriorCase(uuid4(), "incomplete", now - timedelta(hours=48))
    d = await decide_window(_msg(now), prior, llm=None)
    assert d.action == "new" and d.method == "idle_gap"


async def test_open_case_idle_beyond_window_uses_classifier() -> None:
    now = datetime.now(UTC)
    prior = PriorCase(uuid4(), "actionable", now - timedelta(hours=48), prior_text="old issue")
    follow = await decide_window(_msg(now), prior, llm=_FakeLLM("follow_up"))
    assert follow.action == "follow_up" and follow.method == "classifier"
    new = await decide_window(_msg(now), prior, llm=_FakeLLM("new"))
    assert new.action == "new" and new.method == "classifier"


async def test_committed_case_long_after_is_new() -> None:
    now = datetime.now(UTC)
    prior = PriorCase(uuid4(), "committed", now - timedelta(days=10))
    d = await decide_window(_msg(now), prior)
    assert d.action == "new" and d.method == "terminal_state"


async def test_committed_case_within_reopen_window_classifies() -> None:
    now = datetime.now(UTC)
    prior = PriorCase(uuid4(), "committed", now - timedelta(hours=3), prior_text="was solved")
    d = await decide_window(_msg(now), prior, llm=_FakeLLM("follow_up"))
    assert d.action == "follow_up" and d.method == "classifier"


async def test_classifier_malformed_output_fails_safe_to_new() -> None:
    now = datetime.now(UTC)
    prior = PriorCase(uuid4(), "actionable", now - timedelta(hours=48), prior_text="x")
    d = await decide_window(_msg(now), prior, llm=_FakeLLM(malformed=True))
    assert d.action == "new"  # never merge on a guess
