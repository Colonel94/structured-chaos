"""The tuning last-mile plumbing (host-safe, no DB/model): apply a delta, keep the prompt eval-neutral on
main, bump the version cleanly, and format the eval comment honestly.

The trust points here:
- ``tuning_addenda.json`` is ``[]`` on main → the prompt is byte-identical and the eval is unaffected.
- an ACTIVE addendum is appended under a clear header; an inactive/malformed one is ignored (fail-safe).
- ``_bump_version`` changes ONLY the quoted version, never its long trailing comment.
- the eval comment flags a score-only run as NOT reflecting the delta (no silent "looks scored").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import app.extract.prompt as P

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import open_tuning_pr
import tuning_eval


def test_main_is_eval_neutral() -> None:
    """On main the addenda file is empty → no addenda, version unbumped, no header in the built prompt."""
    assert json.loads(P._ADDENDA_PATH.read_text(encoding="utf-8")) == []
    assert P._load_tuning_addenda() == []
    assert P.PROMPT_VERSION == "extract-v21"
    assert "ADDITIONAL DISAMBIGUATION" not in P.build_prompt("my order was late")


def test_addenda_load_filters_inactive_and_malformed(tmp_path: Path, monkeypatch) -> None:
    """Active deltas load; inactive and shapeless entries are skipped; a broken file → no addenda."""
    f = tmp_path / "a.json"
    f.write_text(
        json.dumps(
            [
                {"delta": "Prefer B over A when blocked.", "active": True},
                {"delta": "should be skipped", "active": False},
                {"nope": 1},
                "garbage",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(P, "_ADDENDA_PATH", f)
    assert P._load_tuning_addenda() == ["Prefer B over A when blocked."]

    f.write_text("{ not json", encoding="utf-8")
    assert P._load_tuning_addenda() == []


def test_build_prompt_appends_active_addenda(monkeypatch) -> None:
    """A loaded addendum is appended under the reviewer-tuned header (the applied-delta path)."""
    monkeypatch.setattr(
        P, "_TUNING_ADDENDA", ["Prefer service_fault only for post-delivery handling."]
    )
    out = P.build_prompt("late delivery")
    assert "ADDITIONAL DISAMBIGUATION (reviewer-tuned):" in out
    assert "post-delivery handling" in out


def test_bump_version_only_touches_the_quoted_string() -> None:
    """+t1 first, then increments; the giant trailing comment is preserved untouched."""
    text = 'PROMPT_VERSION = "extract-v20"  # long note — with an em-dash and "quotes" inside\n'
    bumped, ver = open_tuning_pr._bump_version(text)
    assert ver == "extract-v20+t1"
    assert 'PROMPT_VERSION = "extract-v20+t1"' in bumped
    assert "long note — with an em-dash" in bumped  # comment intact

    bumped2, ver2 = open_tuning_pr._bump_version(bumped)
    assert ver2 == "extract-v20+t2"
    assert 'PROMPT_VERSION = "extract-v20+t2"' in bumped2


def test_eval_comment_flags_score_only() -> None:
    """A score-only comment must say it does NOT reflect the delta; a full re-score must not carry that warning.
    Both carry the version and the §10 merge rule."""
    score_only = tuning_eval._format_comment(
        "cfpb",
        "extract-v20+t1",
        "score-only …",
        "category: 82%",
        reextracted=False,
        split="heldout",
    )
    assert "does NOT yet reflect" in score_only
    assert "extract-v20+t1" in score_only and "regress" in score_only

    full = tuning_eval._format_comment(
        "cfpb", "extract-v20+t1", "full …", "category: 84%", reextracted=True, split="heldout"
    )
    assert "does NOT yet reflect" not in full


def test_eval_comment_flags_the_split_as_the_merge_gate() -> None:
    """§10: the merge gate must score the HELD-OUT slice (disjoint from tuning signal). A held-out comment
    reads as a valid gate; a full-set ('all') comment must be flagged as NOT a valid gate — the whole point
    of the train/test split (a delta scored on its own signal set improves by construction)."""
    heldout = tuning_eval._format_comment(
        "cfpb", "extract-v20+t1", "score-only …", "category: 68%", reextracted=True, split="heldout"
    )
    assert "held-out" in heldout and "by-construction" in heldout
    assert "split=`heldout`" in heldout

    full_set = tuning_eval._format_comment(
        "cfpb", "extract-v20+t1", "score-only …", "category: 82%", reextracted=True, split="all"
    )
    assert "NOT the held-out slice" in full_set and "not a valid merge gate" in full_set


def test_tune_and_heldout_splits_are_disjoint_and_deterministic() -> None:
    """The split that makes the gate honest: every id is in exactly one of tune/heldout, and the assignment
    is stable across calls (a data-file-free, reproducible partition — §10 no-self-grading)."""
    import importlib

    _EVAL = Path(__file__).resolve().parent.parent / "eval"
    if str(_EVAL) not in sys.path:
        sys.path.insert(0, str(_EVAL))
    ds = importlib.import_module("_dataset")

    ids = [f"case-{i}" for i in range(400)]
    labels = {i: ds.split_of(i) for i in ids}
    assert set(labels.values()) == {"tune", "heldout"}  # both slices are populated
    assert all(ds.split_of(i) == labels[i] for i in ids)  # deterministic
    heldout = [i for i in ids if labels[i] == "heldout"]
    # ~30% reserved as held-out (loose bounds — the point is a real disjoint slice, not an exact ratio).
    assert 0.15 < len(heldout) / len(ids) < 0.45
