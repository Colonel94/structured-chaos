"""Isolate WHY governed `category` scored 8%: prompt/policy gap, or model capability? (2026-08-15)

The main extraction prompt lists the category enum with NO definitions and tells the model to abstain
to UNCLEAR when unsure — while the human labeller was told to pick the least-bad fit. This re-runs
category-only on the 40 gold cases with the SAME policy the human had (least-bad fit, UNCLEAR only when
genuinely too sparse) PLUS a one-line definition per category. Domain-neutral glosses — no case-specific
hints, so it's not teaching-to-the-test — scored against the human gold. If accuracy jumps, the 8% was
mostly the prompt; if it stays low, the taxonomy/model is the problem.

Usage:  uv run python eval/category_probe.py
"""

from __future__ import annotations

import asyncio
import csv
import json
from collections import Counter
from pathlib import Path

from app.backends.local.llm_ollama import OllamaLLM
from app.extract.schema import TAXONOMY

_DIR = Path(__file__).resolve().parent / "fixtures"
_SHEET = _DIR / "cfpb_labels.csv"
_SAMPLE = _DIR / "cfpb_sample.jsonl"

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"category": {"type": "string", "enum": list(TAXONOMY)}},
    "required": ["category"],
}

_PROMPT = """Classify this customer complaint into ONE category. Definitions:
- product_fault: a physical item or product is defective / poor quality.
- service_fault: a service was done wrong, mishandled, delayed by the provider, or not as promised \
(includes a company mishandling a dispute, request, or account).
- delivery_fulfilment: a problem with delivery, shipping, or fulfilment of an order.
- billing_charge: a disputed charge, fee, overcharge, debt, refund, or billing/payment/reporting problem.
- access_availability: trouble accessing or using an account, funds, or service (locked, frozen, \
closed, blocked, unavailable).
- staff_conduct: the behaviour or conduct of a specific person/agent is the complaint.
- safety_health: a genuine safety or health hazard.
- other: a real complaint that genuinely fits none of the above.
- UNCLEAR: ONLY if the message is too sparse to tell what kind of complaint it is at all.
Pick the SINGLE best fit. Use UNCLEAR only as a true last resort — NOT because the wording is unusual \
for the category. Return JSON only.

Message:
\"\"\"{msg}\"\"\""""


async def main() -> int:
    narr = {
        str(json.loads(x)["id"]): json.loads(x)["narrative"]
        for x in _SAMPLE.read_text(encoding="utf-8").splitlines()
        if x
    }
    with _SHEET.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if str(r.get("gold_category", "")).strip()]

    llm = OllamaLLM()
    correct = 0
    confusion: Counter[tuple[str, str]] = Counter()
    unclear = 0
    for r in rows:
        gold = str(r["gold_category"]).strip().lower()
        raw = await llm.complete(_PROMPT.format(msg=narr[str(r["id"])]), schema=_SCHEMA)
        try:
            pred = str(json.loads(raw).get("category", "")).strip().lower()
        except json.JSONDecodeError:
            pred = ""
        unclear += int(pred == "unclear")
        correct += int(pred == gold)
        confusion[(gold, pred)] += 1

    n = len(rows)
    print(f"===== CATEGORY PROBE (aligned policy + definitions) vs {n} gold labels =====")
    print(f"accuracy : {correct}/{n} = {correct / n:.0%}   (was 8% under the shipped prompt)")
    print(f"UNCLEAR calls : {unclear}/{n} (was ~90% under the shipped prompt)")
    print("\n-- confusion (gold -> model), top 15 --")
    for (g, m), c in confusion.most_common(15):
        mark = "OK " if g == m else "XX "
        print(f"  {mark} gold={g:<20} model={m:<20} x{c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
