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

Run:
    uv run python scripts/tuning_eval.py                 # score-only, print
    uv run python scripts/tuning_eval.py --reextract     # full re-score (~30 min)
    uv run python scripts/tuning_eval.py --post 42       # score-only + comment on PR #42
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ENGINE = Path(__file__).resolve().parent.parent  # engine/


def _run_capture(cmd: list[str], *, env_dataset: str) -> str:
    """Run an eval script, streaming nothing but capturing stdout+stderr for the PR comment."""
    import os

    env = {**os.environ, "EVAL_DATASET": env_dataset, "PYTHONIOENCODING": "utf-8"}
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

    score = _run_capture(["uv", "run", "python", "eval/score.py"], env_dataset=args.dataset)
    print(score)

    comment = _format_comment(args.dataset, version, mode, score, reextracted=args.reextract)
    if args.post:
        _post(args.post, comment)
        print(f"\nposted to PR #{args.post}")
    return 0


def _format_comment(dataset: str, version: str, mode: str, score: str, *, reextracted: bool) -> str:
    warn = (
        ""
        if reextracted
        else (
            "\n> ⚠️ **score-only run** — this scored the *existing* extractions, so it does NOT yet reflect "
            "this branch's prompt-delta. Re-run with `--reextract` (or the tuning-eval workflow on a "
            "self-hosted runner) for the real after-delta number.\n"
        )
    )
    return (
        f"### Tuning eval — `{version}` on `{dataset}`\n"
        f"_mode: {mode}_\n{warn}\n"
        f"```\n{score}\n```\n"
        "**Merge rule (CLAUDE.md §10):** merge only if category (and the other governed metrics) did **not** "
        "regress vs main's scorecard (`eval/PHASE8_SCORECARD.md`). On self-authored gold this is self-grading "
        "— the binding lever for category stays an independent labelled slice, not a prompt version."
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
