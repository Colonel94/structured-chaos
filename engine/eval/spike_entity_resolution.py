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
MATCH_TAU = 0.72  # BGE cosine floor for a name to be a candidate at all
MARGIN = 0.06  # top candidate must beat the 2nd by this much to be SILENT on name alone


@dataclass
class Resolution:
    mode: str  # "silent" | "confirm" | "elicit"
    object_id: str | None = None  # the silently-bound order, if any
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
    # 1. order_id — the strongest key, BUT it must not contradict a second known anchor
    if order_id:
        hits = [o for o in store if o["order_id"].upper() == order_id.upper()]
        if len(hits) == 1:
            o = hits[0]
            # multi-anchor cross-check: a quoted id that resolves to a DIFFERENT order than the
            # sender's phone is a CONTRADICTION (a typo can collide with someone else's valid order)
            # -> never silent-bind; surface it (winning-condition: acting on the wrong order > asking).
            if phone and o["phone"] != phone:
                return Resolution(
                    "confirm",
                    candidates=[o["order_id"]],
                    reason="order_id and sender phone point to DIFFERENT orders — contradiction, do NOT silent-bind",
                )
            return Resolution(
                "silent",
                o["order_id"],
                reason="order_id exact & unique" + (", phone agrees" if phone else ""),
            )
        if len(hits) == 0:
            return Resolution(
                "confirm", reason=f"order_id '{order_id}' not found — do NOT fuzzy-bind a typo"
            )
        return Resolution(
            "confirm", candidates=[o["order_id"] for o in hits], reason="order_id non-unique"
        )
    # 2. phone
    if phone:
        hits = [o for o in store if o["phone"] == phone]
        if len(hits) == 1:
            return Resolution("silent", hits[0]["order_id"], reason="phone unique")
        if len(hits) > 1:
            return Resolution(
                "confirm",
                candidates=[o["order_id"] for o in hits],
                reason="phone shared by multiple orders",
            )
    # 3. name (fuzzy) — only if BGE scores were supplied
    if name and name_scores:
        ranked = sorted(name_scores.items(), key=lambda kv: kv[1], reverse=True)
        top_id, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        if top >= MATCH_TAU and (top - second) >= MARGIN:
            return Resolution(
                "silent", top_id, reason=f"name unique (cos={top:.2f}, margin={top-second:.2f})"
            )
        if top >= MATCH_TAU:
            near = [oid for oid, s in ranked if top - s < MARGIN]
            return Resolution(
                "confirm",
                candidates=near,
                reason=f"name ambiguous (cos={top:.2f}, 2nd={second:.2f})",
            )
    # 4. nothing to resolve on
    return Resolution("elicit", reason="no usable anchor — open elicitation")


# =========================================================================================
# SCORING (per owner, 2026-08-18): report the PAIR, never accuracy alone.
#   - silent-match RATE     = silent binds / all cases         (target >= 60%; abstention tanks this)
#   - silent-match ACCURACY = correct binds / silent binds     (target >= 99%)
#   accuracy UP while rate DOWN is a REGRESSION (abstention gaming), not progress.
#   Small-n zero-error is NOT the gate: rule-of-three 95% upper bound on error ~ 3/n, so a >=99%
#   claim needs ~300 clean binds with zero wrong. Report "no failures at n=X (<= ~Y% err)", not 100%.
# =========================================================================================


def rule_of_three_upper(n_binds: int, wrong: int) -> str:
    if wrong > 0:
        return f"err={wrong}/{n_binds}={wrong/n_binds:.1%} (measured)"
    if n_binds == 0:
        return "no binds"
    return f"0/{n_binds}, 95% upper bound on error ~= {3/n_binds:.1%}"


# ---- planted hard cases (a DEFECT PROBE, not the gate): (label, kwargs, expected_mode, expected_object) ----
CASES: list[tuple[str, dict, str, str | None]] = [
    ("exact order_id, unique", {"order_id": "BK-10236"}, "silent", "BK-10236"),
    ("exact order_id #2, unique", {"order_id": "BK-10239"}, "silent", "BK-10239"),
    ("phone unique", {"phone": "+447700900668"}, "silent", "BK-10236"),
    ("phone shared (2 orders)", {"phone": "+447700900112"}, "confirm", None),
    ("phone shared (2 orders) #2", {"phone": "+447700900447"}, "confirm", None),
    ("transposed-digit order_id", {"order_id": "BK-10321"}, "confirm", None),
    ("nonexistent order_id", {"order_id": "BK-99999"}, "confirm", None),
    ("no anchor at all", {}, "elicit", None),
    ("phone unique #2", {"phone": "+447700900995"}, "silent", "BK-10239"),
    ("order_id lowercase, unique", {"order_id": "bk-10242"}, "silent", "BK-10242"),
    # --- fuzzy name cases (need --fuzzy / BGE) ---
    ("name near-dup (Sarah/Sara)", {"name": "Sarah Whitfield"}, "confirm", None),
    ("name near-dup (Mohammed/Muhammad)", {"name": "Mohammed Ali"}, "confirm", None),
    ("name unique", {"name": "Priya Nair"}, "silent", "BK-10236"),
]


_FIRST = [
    "Sarah",
    "Sara",
    "James",
    "Aisha",
    "Tom",
    "Priya",
    "Daniel",
    "Emily",
    "Mohammed",
    "Muhammad",
    "Grace",
    "Liam",
    "Olivia",
    "Noah",
    "Fatima",
    "Henry",
    "Chloe",
    "Jack",
    "Isabella",
    "William",
    "Sophia",
    "Ava",
    "Ethan",
    "Mia",
    "Omar",
    "Layla",
    "Yusuf",
    "Zara",
    "Ryan",
    "Nina",
]
_LAST = [
    "Whitfield",
    "O'Connor",
    "Rahman",
    "Baker",
    "Nair",
    "Cohen",
    "Clarke",
    "Ali",
    "Thompson",
    "Murphy",
    "Bennett",
    "Williams",
    "Khan",
    "Scott",
    "Evans",
    "Robinson",
    "Ward",
    "Hughes",
    "Turner",
    "Mitchell",
    "Patel",
    "Ahmed",
    "Foster",
    "Brooks",
    "Reed",
]


def _synth_store(n_orders: int, rng) -> tuple[list[dict], set[str]]:
    """A larger synthetic store with CONTROLLED ambiguity. Returns (store, set_of_shared_phones).
    ~18% of orders share a phone with another (repeat customers -> phone is ambiguous)."""
    store: list[dict] = []
    phones: list[str] = []
    for i in range(n_orders):
        oid = f"BK-{20000 + i}"
        # 18% of the time, reuse a recent phone (a repeat customer) -> ambiguity
        if phones and rng.random() < 0.18:
            phone = rng.choice(phones[-40:])
        else:
            phone = f"+4477009{rng.randint(0, 999999):06d}"
        phones.append(phone)
        name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        store.append(
            {
                "order_id": oid,
                "phone": phone,
                "customer_name": name,
                "items": "order",
                "slot": "2026-08-18 15:00",
                "delivered_at": "2026-08-18 15:30",
            }
        )
    shared = {p for p in phones if phones.count(p) > 1}
    return store, shared


def _synth_cases(store: list[dict], shared: set[str], rng, *, include_name: bool):
    """Realistic WhatsApp-channel case mix with OBJECTIVE ground truth.
    Yields (kwargs, gt_mode, gt_object). The sender phone is (almost) always known on this channel.
    """
    by_phone: dict[str, list[dict]] = {}
    for o in store:
        by_phone.setdefault(o["phone"], []).append(o)
    cases = []
    for o in store:
        r = rng.random()
        uniq = o["phone"] not in shared
        if r < 0.45:  # phone-only (the WhatsApp default anchor)
            if uniq:
                cases.append(({"phone": o["phone"]}, "silent", o["order_id"]))
            else:
                cases.append(({"phone": o["phone"]}, "confirm", None))
        elif r < 0.62:  # quotes the order id (+ phone) -> strong
            cases.append(
                ({"order_id": o["order_id"], "phone": o["phone"]}, "silent", o["order_id"])
            )
        elif r < 0.72:  # typo'd order id -> must NOT bind
            typo = o["order_id"][:-1] + str((int(o["order_id"][-1]) + 5) % 10)
            cases.append(({"order_id": typo, "phone": o["phone"]}, "confirm", None))
        elif r < 0.82:  # unknown sender, no id -> elicit
            cases.append(({"phone": f"+4477000{rng.randint(0,999999):06d}"}, "elicit", None))
        elif include_name:  # name-only (web form; the fuzzy path)
            cases.append(({"name": o["customer_name"]}, "silent", o["order_id"]))
        else:
            cases.append(
                (
                    {"phone": o["phone"]},
                    "silent" if uniq else "confirm",
                    o["order_id"] if uniq else None,
                )
            )
    rng.shuffle(cases)
    return cases


async def _bge_scores(store: list[dict], name: str) -> dict[str, float]:
    """Cosine of the query name against every stored customer_name via BGE-M3 (in-memory, numpy)."""
    import numpy as np  # local import so the deterministic core needs no numpy/GPU

    from app.backends.registry import get_embedding

    embedder = get_embedding()
    names = [o["customer_name"] for o in store]
    vecs = await embedder.embed([name] + names)
    q = np.array(vecs[0])
    mat = np.array(vecs[1:])
    q = q / (np.linalg.norm(q) + 1e-9)
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    sims = mat @ q
    # best score per order_id
    return {store[i]["order_id"]: float(sims[i]) for i in range(len(store))}


def _score(cases, results):
    """Return the PAIR + trust counts over (gt_mode, gt_object) vs Resolution results."""
    total = len(cases)
    silent = [(c, r) for c, r in zip(cases, results) if r.mode == "silent"]
    correct = sum(
        1 for (_, _, gt_obj), r in silent if r.object_id == gt_obj
    )  # gt_obj is 3rd of case tuple
    wrong = len(silent) - correct
    should_silent = sum(1 for _, m, _ in cases if m == "silent")
    got_when_should = sum(
        1
        for (_, m, gt_obj), r in zip(cases, results)
        if m == "silent" and r.mode == "silent" and r.object_id == gt_obj
    )
    return {
        "total": total,
        "silent": len(silent),
        "correct": correct,
        "wrong": wrong,
        "rate": len(silent) / total if total else 0,
        "accuracy": correct / len(silent) if silent else 0,
        "should_silent": should_silent,
        "recall": got_when_should / should_silent if should_silent else 0,
    }


async def _run(store, cases, *, fuzzy):
    results = []
    for kw, _, _ in cases:
        ns = await _bge_scores(store, kw["name"]) if ("name" in kw and fuzzy) else None
        results.append(resolve(store, name_scores=ns, **kw))
    return results


async def main() -> int:
    import random

    fuzzy = "--fuzzy" in sys.argv

    # ---- 1. DEFECT PROBE (hand-authored planted cases; NOT the gate — reported as "no failures at n") ----
    store = _load_store()
    probe = [(kw, m, o) for _, kw, m, o in CASES if fuzzy or "name" not in kw]
    labels = [lbl for lbl, kw, _, _ in CASES if fuzzy or "name" not in kw]
    res = await _run(store, probe, fuzzy=fuzzy)
    binds = [(c, r) for c, r in zip(probe, res) if r.mode == "silent"]
    wrong = sum(1 for (_, _, gt), r in binds if r.object_id != gt or gt is None)
    behaviour_ok = sum(
        1
        for (_, m, gt), r in zip(probe, res)
        if (r.mode == m) or (m in {"confirm", "elicit"} and r.mode in {"confirm", "elicit"})
    )
    print(f"DEFECT PROBE — {len(probe)} planted hard cases (fuzzy={'ON' if fuzzy else 'OFF'}):")
    for lbl, (_, m, gt), r in zip(labels, probe, res):
        got = r.mode + (
            f"->{r.object_id}" if r.object_id else (f"?{r.candidates}" if r.candidates else "")
        )
        ok = (r.mode == m) or (m in {"confirm", "elicit"} and r.mode in {"confirm", "elicit"})
        print(f"  {'OK ' if ok else 'XX '}{lbl:34s} expect={m:7s} got={got}")
    print(
        f"  -> behaviour {behaviour_ok}/{len(probe)}; silent binds {rule_of_three_upper(len(binds), wrong)}"
    )
    print("  (this is DEFECT DETECTION at small n, NOT a 99% claim.)\n")

    # ---- 2. GATE MEASUREMENT (scaled synthetic, objective ground truth; report the PAIR) ----
    rng = random.Random(42)
    n_orders = (
        60 if fuzzy else 700
    )  # fuzzy embeds every name (GPU) -> smaller; deterministic -> big n (>=300 clean binds for a real >=99% bound)
    sstore, shared = _synth_store(n_orders, rng)
    scases = _synth_cases(sstore, shared, rng, include_name=fuzzy)
    sres = await _run(sstore, scases, fuzzy=fuzzy)
    m = _score(scases, sres)
    print(
        f"GATE MEASUREMENT — {m['total']} synthetic cases over {n_orders} orders "
        f"({len(shared)} shared phones; name-only path {'ON' if fuzzy else 'OFF'}):"
    )
    print(
        f"  silent-match RATE     : {m['silent']}/{m['total']} = {m['rate']:.0%}   (target >= 60%; abstention tanks this)"
    )
    print(
        f"  silent-match ACCURACY : {rule_of_three_upper(m['silent'], m['wrong'])}   (target >= 99%)"
    )
    print(f"  WRONG silent binds    : {m['wrong']}   (the trust gate — must be 0)")
    print(f"  recall on resolvable  : {m['recall']:.0%}  (of cases that SHOULD silently resolve)")
    print("\n  READ THE PAIR TOGETHER: high accuracy + low rate = abstention gaming = regression.")
    if m["silent"] < 300:
        print(
            f"  NOTE: {m['silent']} clean binds < ~300, so this run cannot yet CLAIM >=99% — it bounds error at ~{3/max(m['silent'],1):.1%}."
        )
    verdict = "no-defect" if m["wrong"] == 0 else "FAIL"
    print(
        f"\n  VERDICT: {verdict} — "
        + (
            f"0 wrong binds across {m['silent']} silent matches; rate {m['rate']:.0%}. "
            + ("Fuzzy layer is the real rate test." if not fuzzy else "Name-only path priced in.")
            if m["wrong"] == 0
            else "silent match bound a WRONG object — unsafe."
        )
    )
    return 0 if m["wrong"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
