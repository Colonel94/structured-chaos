"""Sentiment TRAJECTORY over a conversation — the best-practice enhancement (Phase 6, sentiment).

The extractor gives ONE ``emotion_signal`` per turn. On a single message that is the whole story, but the
portal is now a multi-turn chat, and the contact-centre best practice is to read sentiment *over the
interaction*, not as a lone snapshot (CallMiner: "identifying frustration in the early stages … followed
by positive sentiments in the later portion", "continuously track sentiment over time"). The failure this
fixes: a customer vents ANGRY, then calmly answers "what's your order number?" — the latest snapshot reads
``calm`` and the router stops escalating, losing the anger. Routing must act on the PEAK of the arc and on
its DIRECTION, not just the last reading.

This module is PURE and deterministic ($0 — no model call, no paid sentiment API): it ranks the governed
emotion enum by intensity and reduces an ordered list of per-turn readings to (current, peak, trend). The
rules stage feeds ``peak`` to the engine (so an earlier angry moment still escalates) and ``trend`` as a
new routing input (so an *escalating* customer is caught early, before they hit full anger).

Deliberately additive: it never changes what the extractor emits, so the single-message eval set is
unaffected (one reading → peak == current, trend == "single").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# The governed emotion enum, ranked by intensity. calm < frustrated < angry. Kept in lockstep with
# app.extract.schema.EMOTIONS — an unknown value is ignored (never guessed onto the scale).
_INTENSITY: dict[str, int] = {"calm": 0, "frustrated": 1, "angry": 2}
_BY_RANK: dict[int, str] = {v: k for k, v in _INTENSITY.items()}

# The trend vocabulary the policy can key on. "single" = one reading (no arc yet, the eval case).
TRENDS: tuple[str, ...] = ("single", "steady", "escalating", "de_escalating")


@dataclass(frozen=True)
class Trajectory:
    current: str | None  # the latest reading (what the customer feels now)
    peak: str | None  # the most intense reading across the whole conversation
    trend: str  # single | steady | escalating | de_escalating
    readings: int  # how many usable emotion readings the arc was built from


def analyze(emotions: Sequence[str | None]) -> Trajectory:
    """Reduce an ORDERED list of per-turn emotion readings (oldest→newest) to a trajectory. Null/unknown
    readings are dropped (a turn the extractor couldn't read emotion for is not evidence of calm). Trend
    is endpoint-based with a mid-spike catch: last > first → escalating; last < first → de_escalating; a
    flat pair whose peak rose and fell → de_escalating ("talked down"); otherwise steady."""
    vals = [e for e in emotions if isinstance(e, str) and e in _INTENSITY]
    if not vals:
        return Trajectory(current=None, peak=None, trend="single", readings=0)
    ranks = [_INTENSITY[e] for e in vals]
    current = vals[-1]
    peak = _BY_RANK[max(ranks)]
    if len(vals) == 1:
        trend = "single"
    elif ranks[-1] > ranks[0]:
        trend = "escalating"
    elif ranks[-1] < ranks[0]:
        trend = "de_escalating"
    elif max(ranks) > ranks[-1]:
        # endpoints equal but it spiked in between and came back down — de-escalated ("talked down").
        trend = "de_escalating"
    else:
        trend = "steady"
    return Trajectory(current=current, peak=peak, trend=trend, readings=len(vals))
