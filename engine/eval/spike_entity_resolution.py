"""PHASE 5 — riskiest-assumption spike: is SILENT object-match safe?

Winning-condition §4: object-match accuracy when matched silently >= 99% ("acting on the wrong order
is worse than asking"), and >= 60% of complaints matched to the right object WITHOUT asking. This spike
proves the resolver NEVER silently binds the wrong object, on PLANTED hard cases with objective ground
truth (transposed-digit id, shared-phone ambiguity, near-duplicate names, no-anchor). Throwaway, zero
pipeline integration (per CLAUDE.md §10: de-risk the killer before building elicitation on top).

Policy (encodes "a checkable identifier beats an arguable one", mirroring the v20 taxonomy rule):
  1. stated order_id present:
       - exact & unique in store  -> SILENT (strong key)
       - stated but NOT found     -> CONFIRM (never fuzzy-bind a mistyped id to a different order)
  2. else stated phone present:
       - exactly one order         -> SILENT (strong key)
       - more than one             -> CONFIRM (list candidates)
       - none                      -> fall through
  3. else stated name (fuzzy, BGE): a SINGLE candidate above MATCH_TAU with margin >= MARGIN over the
     2nd -> SILENT; otherwise CONFIRM. Name alone is weak, so the bar is deliberately high.
  4. else -> ELICIT (open questions; the no-object fallback must never fail).

Run: deterministic core (no GPU) ->  uv run python eval/spike_entity_resolution.py
     with BGE fuzzy-name layer     ->  uv run --group embed python eval/spike_entity_resolution.py --fuzzy
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

_STORE = Path(__file__).resolve().parent / "fixtures" / "spike_bakery_objects.jsonl"
MATCH_TAU = 0.72   # BGE cosine floor for a name to be a candidate at all
MARGIN = 0.06      # top candidate must beat the 2nd by this much to be SILENT on name alone


@dataclass
class Resolution:
    mode: str                       # "silent" | "confirm" | "elicit"
    object_id: str | None = None    # the silently-bound order, if any
    candidates: list[str] = field(default_factory=list)
    reason: str = ""


def _load_store() -> list[dict]:
    return [json.loads(l) for l in _STORE.read_text(encoding="utf-8").splitlines() if l.strip()]


def resolve(
    store: list[dict],
    *,
    order_id: str | None = None,
    phone: str | None = None,
    name: str | None = None,
    name_scores: dict[str, float] | None = None,
) -> Resolution:
    """Deterministic exact-key core + optional pre-computed BGE name_scores (order_id -> cosine)."""
    # 1. order_id — the strongest key
    if order_id:
        hits = [o for o in store if o["order_id"].upper() == order_id.upper()]
        if len(hits) == 1:
            return Resolution("silent", hits[0]["order_id"], reason="order_id exact & unique")
        if len(hits) == 0:
            return Resolution("confirm", reason=f"order_id '{order_id}' not found — do NOT fuzzy-bind a typo")
        return Resolution("confirm", candidates=[o["order_id"] for o in hits], reason="order_id non-unique")
    # 2. phone
    if phone:
        hits = [o for o in store if o["phone"] == phone]
        if len(hits) == 1:
            return Resolution("silent", hits[0]["order_id"], reason="phone unique")
        if len(hits) > 1:
            return Resolution("confirm", candidates=[o["order_id"] for o in hits], reason="phone shared by multiple orders")
    # 3. name (fuzzy) — only if BGE scores were supplied
    if name and name_scores:
        ranked = sorted(name_scores.items(), key=lambda kv: kv[1], reverse=True)
        top_id, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        if top >= MATCH_TAU and (top - second) >= MARGIN:
            return Resolution("silent", top_id, reason=f"name unique (cos={top:.2f}, margin={top-second:.2f})")
        if top >= MATCH_TAU:
            near = [oid for oid, s in ranked if top - s < MARGIN]
            return Resolution("confirm", candidates=near, reason=f"name ambiguous (cos={top:.2f}, 2nd={second:.2f})")
    # 4. nothing to resolve on
    return Resolution("elicit", reason="no usable anchor — open elicitation")


# ---- planted hard cases: (label, kwargs, expected_mode, expected_object_or_None) ----
CASES: list[tuple[str, dict, str, str | None]] = [
    ("exact order_id, unique",        {"order_id": "BK-10236"},           "silent",  "BK-10236"),
    ("exact order_id #2, unique",     {"order_id": "BK-10239"},           "silent",  "BK-10239"),
    ("phone unique",                  {"phone": "+447700900668"},         "silent",  "BK-10236"),
    ("phone shared (2 orders)",       {"phone": "+447700900112"},         "confirm", None),
    ("phone shared (2 orders) #2",    {"phone": "+447700900447"},         "confirm", None),
    ("transposed-digit order_id",     {"order_id": "BK-10321"},           "confirm", None),
    ("nonexistent order_id",          {"order_id": "BK-99999"},           "confirm", None),
    ("no anchor at all",              {},                                 "elicit",  None),
    ("phone unique #2",               {"phone": "+447700900995"},         "silent",  "BK-10239"),
    ("order_id lowercase, unique",    {"order_id": "bk-10242"},           "silent",  "BK-10242"),
    # --- fuzzy name cases (need --fuzzy / BGE) ---
    ("name near-dup (Sarah/Sara)",    {"name": "Sarah Whitfield"},        "confirm", None),
    ("name near-dup (Mohammed/Muhammad)", {"name": "Mohammed Ali"},       "confirm", None),
    ("name unique",                   {"name": "Priya Nair"},             "silent",  "BK-10236"),
]


async def _bge_scores(store: list[dict], name: str) -> dict[str, float]:
    """Cosine of the query name against every stored customer_name via BGE-M3 (in-memory, numpy)."""
    import numpy as np  # local import so the deterministic core needs no numpy/GPU

    from app.backends.registry import get_embedding

    embedder = get_embedding()
    names = [o["customer_name"] for o in store]
    vecs = await embedder.embed([name] + names)
    q = np.array(vecs[0]); mat = np.array(vecs[1:])
    q = q / (np.linalg.norm(q) + 1e-9)
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    sims = mat @ q
    # best score per order_id
    return {store[i]["order_id"]: float(sims[i]) for i in range(len(store))}


async def main() -> int:
    fuzzy = "--fuzzy" in sys.argv
    store = _load_store()
    silent_total = silent_correct = wrong_silent = 0
    resolvable = 0            # cases that SHOULD resolve silently (have a strong/unique anchor)
    behaviour_correct = 0
    total_scored = 0
    print(f"Object store: {len(store)} bakery orders.  Fuzzy name layer: {'ON (BGE)' if fuzzy else 'OFF (deterministic core only)'}\n")
    for label, kw, exp_mode, exp_obj in CASES:
        is_name_case = "name" in kw
        if is_name_case and not fuzzy:
            print(f"  [skip] {label:34s} (needs --fuzzy)")
            continue
        name_scores = await _bge_scores(store, kw["name"]) if (is_name_case and fuzzy) else None
        r = resolve(store, name_scores=name_scores, **kw)
        total_scored += 1
        if exp_mode == "silent":
            resolvable += 1
        ok_behaviour = (r.mode == exp_mode) or (exp_mode in {"confirm", "elicit"} and r.mode in {"confirm", "elicit"})
        # trust gate: any silent bind to the WRONG object
        if r.mode == "silent":
            silent_total += 1
            if r.object_id == exp_obj and exp_mode == "silent":
                silent_correct += 1
            elif exp_mode != "silent" or r.object_id != exp_obj:
                wrong_silent += 1
        if ok_behaviour and not (r.mode == "silent" and exp_mode != "silent"):
            behaviour_correct += 1
        flag = "OK " if (ok_behaviour and not (r.mode == "silent" and exp_mode != "silent")) else "XX "
        got = f"{r.mode}" + (f"->{r.object_id}" if r.object_id else (f"?{r.candidates}" if r.candidates else ""))
        print(f"  {flag}{label:34s} expect={exp_mode:7s}{('/'+exp_obj) if exp_obj else '':10s} got={got:22s} — {r.reason}")

    print("\n--- METRICS (winning-condition §4) ---")
    print(f"  silent-match accuracy   : {silent_correct}/{silent_total}"
          + (f" = {silent_correct/silent_total:.0%}" if silent_total else "")
          + "   (target >= 99%)")
    print(f"  WRONG silent matches    : {wrong_silent}   (MUST be 0 — the trust gate)")
    cov = silent_total / resolvable if resolvable else 0
    print(f"  coverage (silent/should): {silent_total}/{resolvable} = {cov:.0%}   (target >= 60% of resolvable)")
    print(f"  behaviour correct       : {behaviour_correct}/{total_scored}")
    verdict = "PASS" if (wrong_silent == 0 and silent_total and silent_correct == silent_total) else "FAIL"
    print(f"\n  RISKIEST-ASSUMPTION VERDICT: {verdict} — "
          + ("silent match never bound a wrong object; safe to build elicitation on top."
             if verdict == "PASS" else "silent match is UNSAFE; fix the resolver before building upstream."))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
