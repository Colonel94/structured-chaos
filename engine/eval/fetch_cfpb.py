"""Fetch a curated sample of REAL English complaints from the public CFPB Consumer Complaint
Database (https://www.consumerfinance.gov/data-research/consumer-complaints/) into a fixture.

Why this exists: the moat/extraction proof must run on data we did NOT author (CLAUDE.md §10-Q3,
GOVERNED-CORE-SCHEMA §0). CFPB narratives are real, human-written, already PII-scrubbed by CFPB
(names/accounts redacted as XXXX), public-domain US-government data, no auth. Financial-domain, not
bakery/home-maintenance — which makes it a *stronger* domain-agnostic test (the same universal engine
on real complaints from a domain we never designed for).

Reproducible: re-running regenerates ``fixtures/cfpb_sample.jsonl``. We pull across several
consumer-facing products for variety (credit-reporting complaints skew template-y, so they're
excluded), keep readable-length narratives, and drop near-duplicate boilerplate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

_API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
_PRODUCTS = [
    "Debt collection",
    "Credit card or prepaid card",
    "Checking or savings account",
    "Money transfer, virtual currency, or money service",
]
_PER_PRODUCT = 30
_MIN_CHARS, _MAX_CHARS = 120, 1400
_OUT = Path(__file__).resolve().parent / "fixtures" / "cfpb_sample.jsonl"


def _norm_key(text: str) -> str:
    """A coarse fingerprint to drop near-identical boilerplate submissions."""
    return re.sub(r"\s+", " ", re.sub(r"[Xx]{2,}|\d+", "", text)).strip().lower()[:200]


def _fetch_product(client: httpx.Client, product: str) -> list[dict[str, str]]:
    resp = client.get(
        _API,
        params={
            "product": product,
            "has_narrative": "true",
            "size": str(_PER_PRODUCT * 3),  # over-fetch; we filter for length + dedup
            "sort": "created_date_desc",
            "no_aggs": "true",
        },
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", {}).get("hits", [])
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for h in hits:
        src = h.get("_source", {})
        narrative = (src.get("complaint_what_happened") or "").strip()
        if not (_MIN_CHARS <= len(narrative) <= _MAX_CHARS):
            continue
        k = _norm_key(narrative)
        if k in seen:
            continue
        seen.add(k)
        out.append(
            {
                "id": str(src.get("complaint_id", "")),
                "product": product,
                "issue": src.get("issue", ""),
                "narrative": narrative,
            }
        )
        if len(out) >= _PER_PRODUCT:
            break
    return out


def main() -> int:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with httpx.Client(timeout=60.0, headers={"User-Agent": "adaptive-intake-eval/0.1"}) as client:
        for product in _PRODUCTS:
            got = _fetch_product(client, product)
            print(f"  {product}: {len(got)} narratives")
            rows.extend(got)
    with _OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} real complaints -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
