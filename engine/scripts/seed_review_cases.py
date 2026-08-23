"""Seed a handful of realistic, varied cases into a demo tenant's review queue (dev/demo ONLY).

Gives a reviewer real fodder to clear when measuring review time (the ≤30s gate) — a spread of clean vs
flagged, anchored (resolves against the seeded order book → Moment 3) vs open, calm vs angry, and one
too-sparse-to-act case that routes to elicitation. Runs through the REAL HTTP intake path (`POST
/api/ingest`) against the running engine, so every case goes through ingest → normalise → extract →
decide → elicit exactly as a stranger's would.

Prereq: the engine must be UP on :8000 and the order book seeded (`seed_portal_orders.py`) so the anchored
cases resolve. Run:
    uv run python scripts/seed_review_cases.py "Portal Demo Co"
"""

from __future__ import annotations

import sys
import time

import httpx
from sqlalchemy import text

from app.config import settings
from app.store.db import admin_session

_ENGINE = "http://localhost:8000"

# Deliberately varied: category, emotion, anchor-present, and outcome-stated all differ across the set so
# the register shows a real spread (triage bands, priorities, the angry→human route, a sparse case).
_CASES: list[str] = [
    # anchored delivery, clear outcome, frustrated — resolves against BK-1004 (very late) → Moment 3
    (
        "Hi, order BK-1004 was meant to arrive by 2pm for my daughter's birthday and it turned up after "
        "7pm completely ruined. This is the second time this has happened. I want a full refund."
    ),
    # billing, specific amounts, calm-ish — a clear charge dispute
    (
        "I've been charged twice for the same subscription — 14.99 on the 3rd and again on the 5th of "
        "this month. Please refund the duplicate charge, I only signed up once."
    ),
    # staff conduct, angry, no anchor → should route to a human, not get interrogated
    (
        "absolutely disgusted with how your staff spoke to me on the phone today. rude, dismissive and "
        "unhelpful. someone senior needs to hear about this because it is not acceptable."
    ),
    # too sparse to act → elicitation (anchor + what happened)
    "i'm really not okay with how this whole thing has been handled and i need someone to sort it out",
    # product/fulfilment, anchored BK-1003 (wrong item), outcome replacement
    (
        "The cabinets you installed are the wrong colour — I ordered walnut and received oak. This is "
        "order BK-1003. I'd like them replaced with the correct ones as soon as possible."
    ),
    # record accuracy — the ask is correct the record, not money or conduct
    (
        "Your records still show my address as 14 Elm Street but I moved months ago and told you twice. "
        "I keep getting other people's post and mine goes elsewhere. Please update it."
    ),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if settings.app_env.strip().lower() in ("prod", "production"):
        print("REFUSING: seed_review_cases is a dev/demo tool; APP_ENV is prod.", file=sys.stderr)
        return 2
    name = sys.argv[1] if len(sys.argv) > 1 else "Portal Demo Co"

    with admin_session() as s:
        tid = s.execute(
            text("SELECT id FROM tenant WHERE name = :n ORDER BY id LIMIT 1"), {"n": name}
        ).scalar()
    if tid is None:
        print(f'tenant "{name}" not found', file=sys.stderr)
        return 1

    headers = {"X-Tenant-Id": str(tid)}
    ok = 0
    for i, body in enumerate(_CASES, 1):
        t0 = time.monotonic()
        try:
            r = httpx.post(
                f"{_ENGINE}/api/ingest", headers=headers, data={"text": body}, timeout=120
            )
            r.raise_for_status()
            ids = r.json().get("case_ids", [])
            dt = time.monotonic() - t0
            print(
                f"  [{i}/{len(_CASES)}] {dt:5.1f}s  case {ids[0][:8] if ids else '—'}  {body[:56]}…"
            )
            ok += 1
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            # A demo seeder: report each failure and carry on — never half-fail the batch silently.
            print(f"  [{i}/{len(_CASES)}] FAILED: {exc}", file=sys.stderr)

    print(f'seeded {ok}/{len(_CASES)} cases into "{name}" ({tid})')
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
