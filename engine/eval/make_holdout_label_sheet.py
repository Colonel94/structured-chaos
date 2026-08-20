"""Generate a BLIND, HELD-OUT label sheet for an INDEPENDENT human labeller (winning-condition §4).

Why this exists (the binding constraint, longterm_context.md §0 + CLAUDE.md §10 CORRECTION 2026-08-19c):
the confidence gate, the true category ceiling, and the review-UI ordering are ALL blocked on one thing —
an independent human-labelled held-out slice. The existing gold (``*_labels.csv``) was authored by *me*
(Claude), so every accuracy number currently measures "P(the model agrees with MY labels)", not
"P(correct)". A more accurate extractor can only raise agreement with the labeller, never past wherever
my own labelling was inconsistent (service↔access, billing↔record are exactly there). The only lever that
breaks that ceiling is labels produced by **someone who is neither the owner nor me, on cases neither the
prompt nor my labels have ever seen.**

This script produces exactly that sheet. Two properties make it valid:

1. **HELD-OUT.** Every case is fetched fresh from the same public $0 sources as the eval set
   (CFPB / NHTSA / Trustpilot) and then filtered against the EXISTING 216-case fixtures by content
   fingerprint + id, so nothing here overlaps the data the v20 prompt was tuned on or that I labelled.

2. **BLIND.** The sheet shows ONLY the narrative + the valid vocab. No model prediction, no gold, no
   hint — so the human's labels cannot anchor to the system's output (that would grade the labeller's
   agreement with the model, the very circularity we are trying to escape).

Stratified across finance (CFPB: billing / service / record / access boundaries) AND off-finance
(NHTSA product/safety, Trustpilot service/staff/delivery) so the slice stresses the SAME boundaries
that sit at the accuracy ceiling — not one easy domain.

Output: ``fixtures/holdout_labels.csv`` (blank ``gold_*`` columns for a human to fill) +
``fixtures/holdout_labels_INSTRUCTIONS.md``. Hand both to an independent labeller. When it comes back
filled, score the current v20 extractions against it the same way ``score.py`` does — that number is
the first honest, non-self-graded accuracy the project has.

Usage:  uv run python eval/make_holdout_label_sheet.py [target_total]   (default 70)
Requires network (public APIs, no auth, $0). Trustpilot pulls a parquet (~large); if any single source
fails the script proceeds with what it got and reports the shortfall rather than aborting.
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import httpx

from app.extract.schema import DESIRED_OUTCOMES, EMOTIONS, SEVERITIES, TAXONOMY

_DIR = Path(__file__).resolve().parent / "fixtures"
_EXISTING = [_DIR / "cfpb_sample.jsonl", _DIR / "multidomain_sample.jsonl"]
_OUT = _DIR / "holdout_labels.csv"
_INSTRUCTIONS = _DIR / "holdout_labels_INSTRUCTIONS.md"

_GOLD_COLS = [
    "gold_category",
    "gold_desired_outcome",
    "gold_severity_signal",
    "gold_emotion_signal",
    "gold_key_facts",
]

_MIN_CHARS, _MAX_CHARS = 120, 1400
_UA = {"User-Agent": "adaptive-intake-eval/0.1"}


def _norm_key(text: str) -> str:
    """Coarse content fingerprint (same shape as the fetchers) — strips digits/redactions so
    near-identical boilerplate and the exact existing cases are both excluded."""
    return re.sub(r"\s+", " ", re.sub(r"[Xx]{2,}|\d+", "", text)).strip().lower()[:200]


def _load_seen() -> tuple[set[str], set[str]]:
    """Ids + content fingerprints already in the 216-case eval set — the held-out exclusion set."""
    ids: set[str] = set()
    prints: set[str] = set()
    for path in _EXISTING:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            ids.add(str(r.get("id", "")))
            prints.add(_norm_key(r.get("narrative", "")))
    return ids, prints


def _ok_len(s: str) -> bool:
    return _MIN_CHARS <= len(s) <= _MAX_CHARS


# --- Source 1: CFPB (finance — the billing / service / record / access boundaries) ---
_CFPB_API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
_CFPB_PRODUCTS = [
    "Debt collection",
    "Credit card or prepaid card",
    "Checking or savings account",
    "Money transfer, virtual currency, or money service",
]


def _fetch_cfpb(
    client: httpx.Client, seen_ids: set[str], seen_prints: set[str], per_product: int
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for product in _CFPB_PRODUCTS:
        resp = client.get(
            _CFPB_API,
            params={
                "product": product,
                "has_narrative": "true",
                "size": str(per_product * 6),
                # oldest-first: deterministically disjoint from the eval set, which took newest-first.
                "sort": "created_date_asc",
                "no_aggs": "true",
            },
        )
        resp.raise_for_status()
        got = 0
        for h in resp.json().get("hits", {}).get("hits", []):
            src = h.get("_source", {})
            narrative = (src.get("complaint_what_happened") or "").strip()
            cid = str(src.get("complaint_id", ""))
            fp = _norm_key(narrative)
            if not _ok_len(narrative) or cid in seen_ids or fp in seen_prints:
                continue
            seen_ids.add(cid)
            seen_prints.add(fp)
            out.append(
                {
                    "id": cid,
                    "product": product,
                    "issue": src.get("issue", ""),
                    "narrative": narrative,
                }
            )
            got += 1
            if got >= per_product:
                break
    return out


# --- Source 2: NHTSA (off-finance product_fault + safety_health) ---
_NHTSA_API = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
_NHTSA_VEHICLES = [
    ("Subaru", "Outback", 2019),
    ("Ram", "1500", 2020),
    ("Kia", "Telluride", 2021),
    ("Volkswagen", "Jetta", 2019),
    ("Mazda", "CX-5", 2020),
    ("GMC", "Sierra", 2019),
]


def _fetch_nhtsa(client: httpx.Client, seen_prints: set[str], total: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    per_vehicle = max(2, total // len(_NHTSA_VEHICLES) + 1)
    for make, model, year in _NHTSA_VEHICLES:
        resp = client.get(_NHTSA_API, params={"make": make, "model": model, "modelYear": str(year)})
        if resp.status_code != 200:
            continue
        got = 0
        for c in resp.json().get("results", []):
            summary = (c.get("summary") or "").strip()
            fp = _norm_key(summary)
            if not _ok_len(summary) or fp in seen_prints:
                continue
            seen_prints.add(fp)
            comps = (c.get("components") or "").strip()
            out.append(
                {
                    "id": f"nhtsa-{c.get('odiNumber', '')}",
                    "product": "Motor vehicle",
                    "issue": f"{make} {model} {year} — {comps}" if comps else f"{make} {model}",
                    "narrative": summary,
                }
            )
            got += 1
            if got >= per_vehicle or len(out) >= total:
                break
        if len(out) >= total:
            break
    return out[:total]


# --- Source 3: Trustpilot (off-finance service / staff / delivery / billing) ---
_TRUSTPILOT_PARQUET = (
    "https://huggingface.co/datasets/Kerassy/trustpilot-reviews-123k/"
    "resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet"
)
_TRUSTPILOT_SECTORS = {
    "Electronics & Technology": "Electronics / tech product",
    "Shopping & Fashion": "Retail / fashion order",
    "Restaurants & Bars": "Restaurant / food service",
    "Travel & Vacation": "Travel / booking",
    "Utilities": "Utility service",
    "Home Services": "Home service / repair",
    "Health & Medical": "Health / medical service",
    "Legal Services & Government": "Legal / public service",
}


def _fetch_trustpilot(
    client: httpx.Client, seen_prints: set[str], per_sector: int, per_company: int
) -> list[dict[str, str]]:
    import pyarrow.parquet as pq  # lazy: only this source needs it

    data = client.get(_TRUSTPILOT_PARQUET).content
    rows = pq.read_table(io.BytesIO(data)).to_pylist()
    out: list[dict[str, str]] = []
    sector_n: dict[str, int] = {}
    company_n: dict[tuple[str, str], int] = {}
    # Walk from the END of the file so we land on different reviews than the eval fetch (which took
    # the first matches) — a second held-out guard on top of the fingerprint exclusion.
    for r in reversed(rows):
        category = r.get("category") or ""
        label = _TRUSTPILOT_SECTORS.get(category)
        if label is None:
            continue
        try:
            if int(r.get("stars") or 5) > 2:
                continue
        except (TypeError, ValueError):
            continue
        review = (r.get("review") or "").strip()
        fp = _norm_key(review)
        if not _ok_len(review) or fp in seen_prints:
            continue
        if sector_n.get(category, 0) >= per_sector:
            continue
        company = str(r.get("company") or "?")
        if company_n.get((category, company), 0) >= per_company:
            continue
        seen_prints.add(fp)
        sector_n[category] = sector_n.get(category, 0) + 1
        company_n[(category, company)] = company_n.get((category, company), 0) + 1
        out.append(
            {
                "id": f"tp-holdout-{category.split()[0].lower()}-{len(out)}",
                "product": label,
                "issue": f"{category} — {company}",
                "narrative": review,
            }
        )
        if len(out) >= per_sector * len(_TRUSTPILOT_SECTORS):
            break
    return out


def _write_instructions(n: int, by_source: dict[str, int]) -> None:
    src_line = ", ".join(f"{k} {v}" for k, v in by_source.items())
    _INSTRUCTIONS.write_text(
        "# Independent labelling — held-out accuracy slice\n\n"
        "**Who should fill this in:** someone who is **neither the system's author nor the project "
        "owner.** The whole point of this sheet is an *independent* second opinion; if the person who "
        "wrote the prompts or the existing labels fills it in, it measures nothing new.\n\n"
        "**Do this blind.** Read ONLY the `narrative` column and decide the correct answer yourself. "
        "Do **not** look at any system output, any other label file, or discuss a row before labelling "
        "it. There is no answer key — your honest reading *is* the answer.\n\n"
        f"**{n} real complaints**, held out from the cases the system was built on "
        f"(sources: {src_line}). Fill the `gold_*` columns for each row. Leave a cell EMPTY only to "
        "skip that one field for that row (it won't be scored); an empty `gold_desired_outcome` is a "
        'REAL label meaning "the customer did not state what they want".\n\n'
        "## Valid values (type the exact string)\n"
        f"- **gold_category** — the SINGLE best archetype: {' | '.join(TAXONOMY)}\n"
        "    - `product_fault` = a physical item is defective / poor quality (no safety hazard).\n"
        "    - `service_fault` = the company mishandled, ignored, delayed, or botched something, and no "
        "other category's harm fits better (the conduct itself is the harm).\n"
        "    - `delivery_fulfilment` = a shipping / delivery / fulfilment problem with goods (parcel "
        "late, lost, damaged, wrong item) — NOT any order-related complaint.\n"
        "    - `billing_charge` = a specific charge, fee, amount, or balance is WRONG (the dispute is "
        "about the number / money back).\n"
        "    - `record_accuracy` = a record the company holds/publishes ABOUT the customer is inaccurate "
        "/ unverified / wrongly dated (a credit entry, a reported balance, a late marker) and the ask is "
        "verify / correct / delete — NOT money.\n"
        "    - `access_availability` = an account, funds, or service is in a currently BLOCKED state "
        "(locked, frozen, closed, declined, withheld, unreachable).\n"
        "    - `staff_conduct` = a specific person's behaviour is the complaint.\n"
        "    - `safety_health` = a genuine physical safety or health hazard.\n"
        "    - `other` = a real complaint fitting none of the above. `UNCLEAR` = too sparse to tell what "
        "kind of complaint it is at all (a true last resort).\n"
        f"- **gold_desired_outcome** — {' | '.join(DESIRED_OUTCOMES)} | leave EMPTY for `null`\n"
        "    - Pick a value ONLY if the customer explicitly asks for a remedy; if they state two, the "
        "one they say FIRST. A grievance about money is not by itself a request for a refund. `refund` = "
        "money back; `repair_redo` = redo the work OR correct a record; `information` = an answer / "
        "status / validation; `replacement` = a new item; `escalation` = a manager / formal escalation; "
        "`acknowledgement` = only an apology.\n"
        f"- **gold_severity_signal** — {' | '.join(SEVERITIES)}\n"
        "    - `financial_harm` = monetary harm of any kind (disputed charge, fee, money "
        "taken/withheld/frozen, debt wrongly owed/reported, damaged credit, denied refund). "
        "`safety_health` = physical safety/health risk. `vulnerable_party` = a child/elderly/disabled "
        "person at risk. `none` = none of these.\n"
        f"- **gold_emotion_signal** — {' | '.join(EMOTIONS)} (from the tone).\n"
        "- **gold_key_facts** (optional) — the concrete facts that SHOULD be captured, `;`-separated as "
        "`name=value`, e.g. `charged amount=$500; account status=closed`. Used for a soft recall check.\n",
        encoding="utf-8",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 70
    seen_ids, seen_prints = _load_seen()
    print(f"held-out exclusion set: {len(seen_ids)} ids, {len(seen_prints)} fingerprints")

    # ~60% finance (the billing/service/record/access ceiling), ~40% off-finance (product/safety/service).
    cfpb_target = round(target * 0.55)
    per_product = max(1, cfpb_target // len(_CFPB_PRODUCTS))
    nhtsa_target = round(target * 0.2)
    tp_target = target - cfpb_target - nhtsa_target

    rows: list[dict[str, str]] = []
    by_source: dict[str, int] = {}
    with httpx.Client(timeout=120.0, headers=_UA, follow_redirects=True) as client:
        for name, fn in (
            ("CFPB", lambda: _fetch_cfpb(client, seen_ids, seen_prints, per_product)),
            ("NHTSA", lambda: _fetch_nhtsa(client, seen_prints, nhtsa_target)),
            (
                "Trustpilot",
                lambda: _fetch_trustpilot(client, seen_prints, max(1, tp_target // 8), 1),
            ),
        ):
            try:
                got = fn()
            except Exception as exc:  # noqa: BLE001 — a flaky source must not abort the whole sheet
                print(f"  {name}: FAILED ({type(exc).__name__}: {exc}) — proceeding without it")
                continue
            print(f"  {name}: {len(got)} held-out cases")
            by_source[name] = len(got)
            rows.extend(got)

    rows.sort(key=lambda r: str(r["id"]))  # deterministic order
    with _OUT.open("w", encoding="utf-8", newline="") as f:
        import csv

        w = csv.writer(f)
        w.writerow(["id", "product", "issue", "narrative", *_GOLD_COLS])
        for r in rows:
            w.writerow(
                [r["id"], r["product"], r.get("issue", ""), r["narrative"], "", "", "", "", ""]
            )

    _write_instructions(len(rows), by_source)
    print(f"\nwrote {len(rows)} blank held-out rows -> {_OUT}")
    print(f"instructions -> {_INSTRUCTIONS}")
    if len(rows) < target:
        print(
            f"NOTE: {len(rows)}/{target} — a source shortfall; re-run to top up (merge-safe by fp)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
