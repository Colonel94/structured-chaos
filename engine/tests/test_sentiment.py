"""Sentiment trajectory (app.rules.sentiment) — pure, no DB. The arc a multi-turn conversation traces,
reduced to (current, peak, trend) so routing can act on the peak + direction, not just the latest word.
"""

from __future__ import annotations

from app.rules.sentiment import analyze


def test_single_reading_peak_equals_current_trend_single() -> None:
    t = analyze(["frustrated"])
    assert t.current == "frustrated" and t.peak == "frustrated"
    assert t.trend == "single" and t.readings == 1


def test_escalating_calm_to_angry() -> None:
    t = analyze(["calm", "frustrated", "angry"])
    assert t.peak == "angry" and t.current == "angry" and t.trend == "escalating"


def test_de_escalating_keeps_the_peak() -> None:
    # THE wash-out case: vented angry, then calmed. Peak must remain 'angry' so routing still escalates.
    t = analyze(["angry", "calm"])
    assert t.peak == "angry" and t.current == "calm" and t.trend == "de_escalating"


def test_mid_spike_that_returns_is_de_escalating() -> None:
    t = analyze(["frustrated", "angry", "frustrated"])
    assert t.peak == "angry" and t.current == "frustrated" and t.trend == "de_escalating"


def test_flat_is_steady() -> None:
    t = analyze(["frustrated", "frustrated"])
    assert t.trend == "steady" and t.peak == "frustrated"


def test_nulls_and_unknowns_are_dropped_not_treated_as_calm() -> None:
    t = analyze([None, "calm", "mixed", "angry"])
    assert (
        t.readings == 2 and t.peak == "angry" and t.current == "angry" and t.trend == "escalating"
    )


def test_empty_history() -> None:
    t = analyze([])
    assert t.peak is None and t.current is None and t.trend == "single" and t.readings == 0
