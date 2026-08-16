"""Fetch a MULTI-DOMAIN sample of REAL complaints — PRODUCT + SERVICE across many sectors — so the
domain-agnostic engine is finally measured OFF the financial domain (CFPB is one sector; §4 promises
"cake store to government"). Same fixture shape as ``fetch_cfpb.py`` → ``{id, product, issue,
narrative}`` (``product`` = the sector label), so the same eval harness scores it (``--dataset
multidomain``). NOT financial — that's the entire point.

Two real, human-authored, $0, no-auth sources — data we did NOT author (§10-Q3):

- **NHTSA vehicle complaints** (``api.nhtsa.gov``) — US-gov PUBLIC DOMAIN. Free-text ``summary`` +
  crash/fire/injury/death flags. Exercises product_fault + the safety_health class CFPB never did.

- **Trustpilot reviews** (``Kerassy/trustpilot-reviews-123k`` on HuggingFace, **MIT** licence — the one
  permissively-licensed multi-sector prose source; verified) — 22 balanced sectors. We keep only LOW-
  rated reviews (``stars <= 2`` — a low review IS a complaint) with a real narrative, sampled across a
  curated set of PRODUCT sectors (electronics, retail/fashion) and SERVICE/public sectors (restaurants,
  travel, utilities, home services, health, legal/government). Exercises service_fault, staff_conduct,
  delivery_fulfilment, billing_charge, access_availability, safety_health (food/health).
  *Provenance note:* MIT is the uploader's declared licence; the underlying text is user-generated
  reviews — clean enough as a PRIVATE internal eval fixture, not a first-party public-domain grant like
  CFPB/NHTSA. (NonCommercial airline/support-tweet corpora were rejected — can't ship in a commercial
  product; gov service DBs were rejected — structured category codes, no prose. See the licence ledger
  in the handoff.)

Reproducible: re-running regenerates ``fixtures/multidomain_sample.jsonl``, balanced per sector,
readable-length narratives, near-duplicate + single-company domination dropped.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import httpx
import pyarrow.parquet as pq

_OUT = Path(__file__).resolve().parent / "fixtures" / "multidomain_sample.jsonl"
_MIN_CHARS, _MAX_CHARS = 180, 1400
_UA = {"User-Agent": "adaptive-intake-eval/0.1"}

# --- PRODUCT (auto): NHTSA, a spread of makes/models/years so failure modes vary. ---
_NHTSA_API = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
_NHTSA_VEHICLES = [
    ("Honda", "Accord", 2019),
    ("Ford", "F-150", 2020),
    ("Tesla", "Model 3", 2021),
    ("Jeep", "Grand Cherokee", 2019),
    ("Toyota", "Camry", 2020),
    ("Nissan", "Altima", 2020),
    ("Chevrolet", "Silverado", 2019),
    ("Hyundai", "Elantra", 2021),
]
_NHTSA_TOTAL = 24

# --- PRODUCT + SERVICE + PUBLIC: Trustpilot sectors → a readable sector label for the fixture. ---
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
_PER_SECTOR = 9
_PER_COMPANY = 2  # spread across companies so one bad vendor doesn't dominate a sector


def _norm_key(text: str) -> str:
    """Coarse fingerprint to drop near-identical boilerplate."""
    return re.sub(r"\s+", " ", re.sub(r"[Xx]{2,}|\d+", "", text)).strip().lower()[:200]


def _ok_len(s: str) -> bool:
    return _MIN_CHARS <= len(s) <= _MAX_CHARS


def _fetch_nhtsa(client: httpx.Client) -> list[dict[str, str]]:
    """Real vehicle-defect complaints — product_fault + safety_health (crash/fire/injury)."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    per_vehicle = max(3, _NHTSA_TOTAL // len(_NHTSA_VEHICLES) + 1)
    for make, model, year in _NHTSA_VEHICLES:
        resp = client.get(_NHTSA_API, params={"make": make, "model": model, "modelYear": str(year)})
        if resp.status_code != 200:
            continue
        got = 0
        for c in resp.json().get("results", []):
            summary = (c.get("summary") or "").strip()
            if not _ok_len(summary) or _norm_key(summary) in seen:
                continue
            seen.add(_norm_key(summary))
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
            if got >= per_vehicle:
                break
        if len(out) >= _NHTSA_TOTAL:
            break
    return out[:_NHTSA_TOTAL]


def _fetch_trustpilot(client: httpx.Client) -> list[dict[str, str]]:
    """Real multi-sector service/product complaints — low-rated Trustpilot reviews, balanced by
    sector, spread across companies."""
    data = client.get(_TRUSTPILOT_PARQUET).content
    rows = pq.read_table(io.BytesIO(data)).to_pylist()

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    per_sector: dict[str, int] = {}
    per_company: dict[tuple[str, str], int] = {}
    for r in rows:
        category = r.get("category") or ""
        label = _TRUSTPILOT_SECTORS.get(category)
        if label is None:  # not a sector we sample
            continue
        try:
            if int(r.get("stars") or 5) > 2:  # keep only complaints (low rating), not praise
                continue
        except (TypeError, ValueError):
            continue
        review = (r.get("review") or "").strip()
        if not _ok_len(review) or _norm_key(review) in seen:
            continue
        if per_sector.get(category, 0) >= _PER_SECTOR:
            continue
        company = str(r.get("company") or "?")
        if per_company.get((category, company), 0) >= _PER_COMPANY:
            continue
        seen.add(_norm_key(review))
        per_sector[category] = per_sector.get(category, 0) + 1
        per_company[(category, company)] = per_company.get((category, company), 0) + 1
        out.append(
            {
                "id": f"trustpilot-{category.split()[0].lower()}-{len(out)}",
                "product": label,
                "issue": f"{category} — {company}",
                "narrative": review,
            }
        )
        if len(out) >= _PER_SECTOR * len(_TRUSTPILOT_SECTORS):
            break
    return out


def main() -> int:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with httpx.Client(timeout=120.0, headers=_UA, follow_redirects=True) as client:
        auto = _fetch_nhtsa(client)
        print(f"  Motor vehicle (NHTSA): {len(auto)}")
        rows.extend(auto)
        tp = _fetch_trustpilot(client)
        print(f"  Trustpilot sectors: {len(tp)}")
        rows.extend(tp)
    with _OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} real multi-domain complaints -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
