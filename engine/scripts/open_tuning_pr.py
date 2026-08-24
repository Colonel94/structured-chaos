"""Open a PR that APPLIES a drafted prompt-delta — the tuning loop's last mile, kept human-approved.

Takes the prompt-delta the tuning digest drafted (fetched live from the running engine, or passed inline),
applies it as a reviewer-tuned ADDENDUM (appends to ``app/extract/tuning_addenda.json`` + bumps
``PROMPT_VERSION``), commits it to a fresh ``tuning/…`` branch, pushes, and opens a GitHub PR whose body
carries the full provenance + the honest caveats + a DO-NOT-MERGE-until-eval checklist. It NEVER edits main
and NEVER merges — a human reviews the PR, the eval re-scores it (``scripts/tuning_eval.py`` /
``.github/workflows/tuning-eval.yml``), and only then is it merged (CLAUDE.md §10).

WHY a script, not a UI button: opening a PR means git push + gh with repo-write credentials. The headless
engine is a clean API and must NOT hold those or shell out — so this is a deliberate operator command, run
where the credentials live. The review UI shows the exact command; it does not run it.

Run (fetch the current draft from the engine):
    uv run python scripts/open_tuning_pr.py --tenant <TENANT_ID> [--engine http://localhost:8000]
Or pass a delta inline:
    uv run python scripts/open_tuning_pr.py --delta "…" --title "…" [--based-on "x" --based-on "y"]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent  # engine/
_REPO = _ROOT.parent  # repo root
_PROMPT_PY = _ROOT / "app" / "extract" / "prompt.py"
_ADDENDA_JSON = _ROOT / "app" / "extract" / "tuning_addenda.json"


def _run(
    cmd: list[str], *, cwd: Path = _REPO, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a git/gh command, surfacing stdout+stderr on failure (never a silent half-open PR)."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if check and p.returncode != 0:
        sys.stderr.write(f"$ {' '.join(cmd)}\n{p.stdout}{p.stderr}\n")
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}")
    return p


def _fetch_draft(engine: str, tenant: str) -> dict[str, object]:
    """Fetch the current drafted prompt-delta from the running engine (the exact digest a reviewer sees)."""
    r = httpx.post(
        f"{engine.rstrip('/')}/api/tuning-digest/draft",
        headers={"X-Tenant-Id": tenant},
        json={},
        timeout=180,
    )
    r.raise_for_status()
    body = r.json()
    if not body.get("draft"):
        raise SystemExit(f"no draft available: {body.get('reason', 'no signal yet')}")
    return body


def _bump_version(text: str) -> tuple[str, str]:
    """Bump the quoted ``PROMPT_VERSION`` string ONLY (leaving its long trailing comment intact): append a
    ``+tN`` tuning suffix, or increment an existing one. Returns (new_text, new_version)."""
    m = re.search(r'(PROMPT_VERSION = ")([^"]+)(")', text)
    if not m:
        raise SystemExit("could not find PROMPT_VERSION in prompt.py")
    ver = m.group(2)
    tm = re.search(r"\+t(\d+)$", ver)
    new_ver = re.sub(r"\+t\d+$", f"+t{int(tm.group(1)) + 1}", ver) if tm else f"{ver}+t1"
    return text[: m.start()] + f'PROMPT_VERSION = "{new_ver}"' + text[m.end() :], new_ver


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Open a PR applying a drafted prompt-delta (human-reviewed)."
    )
    ap.add_argument("--tenant", help="fetch the current draft from the engine for this tenant")
    ap.add_argument("--engine", default="http://localhost:8000")
    ap.add_argument("--delta", help="the prompt-delta text (instead of fetching from the engine)")
    ap.add_argument("--title", default="")
    ap.add_argument("--based-on", action="append", default=[], help="a signal line (repeatable)")
    ap.add_argument("--rationale", default="")
    ap.add_argument("--base", default="main", help="base branch for the PR")
    args = ap.parse_args()

    # 1. Get the delta — from the live engine draft, or inline.
    caveats: list[str] = []
    if args.delta:
        delta, title, based_on, rationale = args.delta, args.title, args.based_on, args.rationale
    elif args.tenant:
        body = _fetch_draft(args.engine, args.tenant)
        draft = body["draft"]  # type: ignore[index]
        delta = str(draft["delta"]).strip()
        title = str(draft["title"]).strip()
        rationale = str(draft["rationale"]).strip()
        based_on = [str(b) for b in body.get("based_on", [])]  # type: ignore[union-attr]
        caveats = [str(c) for c in body.get("caveats", [])]  # type: ignore[union-attr]
    else:
        raise SystemExit("pass --tenant (fetch the draft) or --delta (inline)")
    if not delta:
        raise SystemExit("empty delta — nothing to propose")
    title = title or "Tuning: prompt-delta from reviewer signal"

    # 2. Refuse on a dirty tree — a tuning PR must contain ONLY the addendum, never mixed changes.
    if _run(["git", "status", "--porcelain"]).stdout.strip():
        raise SystemExit(
            "working tree is dirty — commit/stash first so the PR is only the tuning delta"
        )

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    branch = f"tuning/prompt-delta-{stamp}"
    _run(["git", "checkout", "-b", branch])

    # 3. Apply: append the addendum (active) + bump PROMPT_VERSION. Both are clean, structural edits — the
    #    hand-authored core prompt is never touched, so the diff is small and reviewable.
    addenda = json.loads(_ADDENDA_JSON.read_text(encoding="utf-8"))
    addenda.append(
        {
            "delta": delta,
            "title": title,
            "rationale": rationale,
            "based_on": based_on,
            "added_at": stamp,
            "active": True,
        }
    )
    _ADDENDA_JSON.write_text(
        json.dumps(addenda, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    new_text, new_ver = _bump_version(_PROMPT_PY.read_text(encoding="utf-8"))
    _PROMPT_PY.write_text(new_text, encoding="utf-8")

    # 4. Commit + push.
    body_md = _pr_body(title, delta, rationale, based_on, caveats, new_ver)
    _run(["git", "add", str(_ADDENDA_JSON), str(_PROMPT_PY)])
    _run(
        [
            "git",
            "commit",
            "-m",
            f"tune(prompt): {title} [{new_ver}] — DRAFT, do not merge until eval",
        ]
    )
    _run(["git", "push", "-u", "origin", branch])

    # 5. Open the PR.
    pr = _run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            args.base,
            "--head",
            branch,
            "--title",
            f"Tuning (DRAFT — do not merge until eval): {title}",
            "--body",
            body_md,
        ]
    )
    url = pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else "(see gh output)"
    print(f"\nPR opened: {url}")
    print(
        "Next: the eval re-scores it — `uv run python scripts/tuning_eval.py --post <pr#>` "
        "(or the tuning-eval workflow on a self-hosted runner). Merge only if category has NOT regressed."
    )
    print(f"To restore your local checkout: git checkout {args.base}")
    return 0


def _pr_body(
    title: str, delta: str, rationale: str, based_on: list[str], caveats: list[str], version: str
) -> str:
    lines = [
        "## Reviewer-tuned prompt-delta (DRAFT — do not merge until the eval re-scores)",
        "",
        (
            f"Applies one additive clarification to the extraction prompt as a tuning addendum "
            f"(`app/extract/tuning_addenda.json`) and bumps `PROMPT_VERSION` → `{version}`. The "
            f"hand-authored core prompt is untouched."
        ),
        "",
        f"**{title}**",
        "",
        "```",
        delta,
        "```",
    ]
    if rationale:
        lines += ["", f"_Rationale:_ {rationale}"]
    if based_on:
        lines += ["", "**Grounded in** (the reviewer signal this came from):"]
        lines += [f"- {b}" for b in based_on]
    if caveats:
        lines += ["", "**Caveats (project law):**"]
        lines += [f"- {c}" for c in caveats]
    lines += [
        "",
        "### Before you merge (CLAUDE.md §10 — never ship a prompt change without re-scoring)",
        "- [ ] The eval re-ran (comment below, or `uv run python scripts/tuning_eval.py --post <pr#>`).",
        "- [ ] Category (and the other governed metrics) did **not** regress vs main.",
        "- [ ] The signal is from an **independent** reviewer (self-authored corrections = self-grading).",
        "- [ ] A human read the delta and agrees it won't over-fire.",
        "",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
