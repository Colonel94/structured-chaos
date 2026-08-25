"""Re-score the eval and (optionally) post the result to a tuning PR — the gate a prompt-delta must clear.

CLAUDE.md §10: never ship a prompt change without re-scoring. This is what runs on a ``tuning/…`` PR (via
``.github/workflows/tuning-eval.yml`` on a self-hosted runner, or by hand here) and posts the governed-core
accuracy so a human can see whether the delta helped or regressed BEFORE merging. It never merges and never
decides — it posts the numbers.

Two modes:
- ``--score-only`` (default, FAST, ~seconds): score the EXISTING extractions vs gold. Proves the plumbing
  and gives the current baseline, but does NOT reflect a new prompt (no re-extraction).
- full (``--reextract``, SLOW, ~30 min on the local GPU): re-run extraction with THIS branch's prompt, then
  score — the real "did the delta help" number. Needs Ollama + the local stack ($0), which is why CI must
  use a self-hosted runner (GitHub-hosted has no GPU/Ollama).

HELD-OUT BY DEFAULT (CLAUDE.md §10): the merge gate scores the ``heldout`` slice (~30% of the set),
DISJOINT from the ``tune`` slice a delta's signal is drawn from — otherwise a delta drafted to fix errors
on the set scores better on that same set by construction, and the gate is decorative. ``--split all``
gives the full-set scorecard number but is NOT a valid merge gate.

Run:
    uv run python scripts/tuning_eval.py                 # score-only on the HELD-OUT slice (the gate)
    uv run python scripts/tuning_eval.py --reextract     # full re-score on held-out (~30 min)
    uv run python scripts/tuning_eval.py --split all      # full-set number (diagnostic, not a gate)
    uv run python scripts/tuning_eval.py --post 42       # score-only + comment on PR #42
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ENGINE = Path(__file__).resolve().parent.parent  # engine/


def _run_capture(cmd: list[str], *, env_dataset: str, env_split: str = "all") -> str:
    """Run an eval script, streaming nothing but capturing stdout+stderr for the PR comment."""
    import os

    env = {
        **os.environ,
        "EVAL_DATASET": env_dataset,
        "EVAL_SPLIT": env_split,
        "PYTHONIOENCODING": "utf-8",
    }
    # The child emits UTF-8 (PYTHONIOENCODING above); decode it as UTF-8 too — else Windows' cp1252 default
    # mangles the em-dashes/≤ in score.py's output into mojibake in the posted PR comment.
    p = subprocess.run(
        cmd,
        cwd=_ENGINE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    return (p.stdout + p.stderr).strip()


def _prompt_version() -> str:
    import sys as _sys

    _sys.path.insert(0, str(_ENGINE))
    from app.extract.prompt import PROMPT_VERSION  # imported here so the branch's value is read

    return PROMPT_VERSION


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description="Re-score the eval for a tuning PR.")
    ap.add_argument("--dataset", default="cfpb", help="cfpb | multidomain")
    ap.add_argument(
        "--split",
        default="heldout",
        choices=["heldout", "tune", "all"],
        help="which slice to SCORE. Default 'heldout' — the tuning gate MUST score the held-out slice, "
        "disjoint from the tune slice a delta's signal came from (§10). 'all' = the full-set scorecard "
        "number (not a merge gate).",
    )
    ap.add_argument(
        "--reextract",
        action="store_true",
        help="re-run extraction with THIS branch's prompt first (~30 min, needs Ollama). Default: "
        "score existing extractions only (fast).",
    )
    ap.add_argument(
        "--post", metavar="PR", help="post the result as a comment on this PR number (gh)"
    )
    args = ap.parse_args()

    version = _prompt_version()
    mode = (
        "full re-score (re-extracted with this branch's prompt)"
        if args.reextract
        else "score-only (existing extractions — NOT a re-extraction)"
    )

    if args.reextract:
        print(f"re-extracting {args.dataset} with {version} … (~30 min, local model)", flush=True)
        extract_log = _run_capture(
            ["uv", "run", "python", "eval/run_extraction.py"], env_dataset=args.dataset
        )
        print(extract_log)

    score = _run_capture(
        ["uv", "run", "python", "eval/score.py"], env_dataset=args.dataset, env_split=args.split
    )
    print(score)

    comment = _format_comment(
        args.dataset, version, mode, score, reextracted=args.reextract, split=args.split
    )
    if args.post:
        _post(args.post, comment)
        print(f"\nposted to PR #{args.post}")
    return 0


def _format_comment(
    dataset: str, version: str, mode: str, score: str, *, reextracted: bool, split: str
) -> str:
    warn = (
        ""
        if reextracted
        else (
            "\n> ⚠️ **score-only run** — this scored the *existing* extractions, so it does NOT yet reflect "
            "this branch's prompt-delta. Re-run with `--reextract` (or the tuning-eval workflow on a "
            "self-hosted runner) for the real after-delta number.\n"
        )
    )
    split_note = (
        (
            "\n> ✅ **held-out scoring** — this is scored on the held-out slice (~30% of the set), "
            "DISJOINT from the tune slice a delta's signal is drawn from, so an improvement can't be "
            "by-construction (§10). It's a small-n regression check, not a high-confidence gate.\n"
        )
        if split == "heldout"
        else (
            f"\n> ⚠️ **split=`{split}`** — NOT the held-out slice. This is not a valid merge gate: a tuning "
            "delta scored on the same data its signal came from improves by construction (§10). Use the "
            "default `--split heldout`.\n"
        )
    )
    return (
        f"### Tuning eval — `{version}` on `{dataset}` (split=`{split}`)\n"
        f"_mode: {mode}_\n{warn}{split_note}\n"
        f"```\n{score}\n```\n"
        "**Merge rule (CLAUDE.md §10):** merge only if the governed metrics did **not** regress on the "
        "**held-out** slice vs main. Never merge a delta scored on its own signal set. On self-authored "
        "gold even the held-out number is self-grading — the binding lever for category stays an "
        "INDEPENDENT labelled slice (`holdout_labels.csv`, owner-blocked), not a prompt version."
    )


def _post(pr: str, body: str) -> None:
    p = subprocess.run(
        ["gh", "pr", "comment", pr, "--body", body],
        cwd=_ENGINE.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        sys.stderr.write(p.stdout + p.stderr)
        raise SystemExit(f"gh pr comment failed for #{pr}")


if __name__ == "__main__":
    raise SystemExit(main())
