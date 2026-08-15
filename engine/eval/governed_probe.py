"""Isolate WHY severity (60%) and desired_outcome (58%) score middling: prompt gap or capability/
ambiguity? Same method as the category probe (2026-08-15).

The failure modes (confusion vs the 40 gold): severity systematically UNDER-calls financial_harm
(gold=financial_harm → model=none x12) — the shipped def is narrow ("a disputed charge/overcharge");
outcome errors are scattered boundary confusions (repair_redo→refund, refund→escalation, …).

These probes re-classify JUST that field on the gold cases with a PRINCIPLED improved definition —
broaden financial_harm to all monetary harm; sharpen the outcome boundaries — written as a reasonable
person would, NOT reverse-engineered from the 40 errors, then scored vs the human gold. If the number
jumps, it's the prompt; if it holds, it's capability/genuine ambiguity.

CAVEAT: probing on the same 40 we'd tune against is a mild self-grading risk — a real fix must be
validated on FRESH labels. Severity's fix (a too-narrow def) is principled + likely to generalise;
outcome's boundary-sharpening is more at risk of overfitting. Treated as a potential estimate.

Usage:  uv run python eval/governed_probe.py
"""

from __future__ import annotations

import asyncio
import csv
import json
from collections import Counter
from pathlib import Path

from app.backends.local.llm_ollama import OllamaLLM
from app.extract.schema import DESIRED_OUTCOMES, SEVERITIES

_DIR = Path(__file__).resolve().parent / "fixtures"
_SHEET = _DIR / "cfpb_labels.csv"
_SAMPLE = _DIR / "cfpb_sample.jsonl"

_SEVERITY_PROMPT = """Rate the SEVERITY signal of this complaint. Definitions:
- safety_health: a genuine safety or health hazard (injury, illness, allergen, fire/gas/electrical risk).
- vulnerable_party: a child, elderly, disabled, or otherwise vulnerable person is at risk or harmed.
- financial_harm: the customer suffered or is exposed to MONETARY harm of ANY kind — an unauthorized or \
disputed charge, an overcharge or fee, money taken/withheld/frozen, a debt wrongly owed or reported, \
damaged credit, or a denied/withheld refund or payment. Any real money-at-stake harm counts, not only a \
"charge".
- none: no safety, vulnerability, or monetary harm (e.g. a late/damaged item with no hazard, or a plain \
information request).
Pick the SINGLE most serious that applies. Return JSON only.

Message:
\"\"\"{msg}\"\"\""""

_OUTCOME_PROMPT = """What does the customer EXPLICITLY ask for? Map to ONE value:
- refund: money back, reverse a charge, or erase/zero a wrongful debt or balance.
- replacement: a new or remade item/product.
- repair_redo: fix, redo, or CORRECT the work or a record (e.g. correct or remove an inaccurate entry, \
fix an error) — without primarily asking for money back.
- escalation: a warranty honoured, a manager, a formal escalation, or that the company be compelled / \
held to account.
- information: an answer, status, explanation, or validation/proof.
- acknowledgement: only an apology or recognition, nothing more.
- other: a clear ask that fits none of these.
- null: the customer does NOT state what they want.
If they state more than one, pick the one they state FIRST. Do not invent an ask. Return JSON only.

Message:
\"\"\"{msg}\"\"\""""

_FIELDS = {
    "severity_signal": (_SEVERITY_PROMPT, list(SEVERITIES)),
    "desired_outcome": (_OUTCOME_PROMPT, [*DESIRED_OUTCOMES, None]),
}


def _norm(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    return "" if s in ("", "null") else s


async def _probe(field: str, prompt: str, enum: list[object]) -> None:
    narr = {
        str(json.loads(x)["id"]): json.loads(x)["narrative"]
        for x in _SAMPLE.read_text(encoding="utf-8").splitlines()
        if x
    }
    with _SHEET.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if str(r.get(f"gold_{field}", "")).strip()]
    schema: dict[str, object] = {
        "type": "object",
        "properties": {field: {"type": ["string", "null"], "enum": enum}},
        "required": [field],
    }
    llm = OllamaLLM()
    correct = 0
    conf: Counter[tuple[str, str]] = Counter()
    for r in rows:
        gold = _norm(r[f"gold_{field}"])
        raw = await llm.complete(prompt.format(msg=narr[str(r["id"])]), schema=schema)
        try:
            pred = _norm(json.loads(raw).get(field))
        except json.JSONDecodeError:
            pred = ""
        correct += int(pred == gold)
        conf[(gold or "null", pred or "null")] += 1
    n = len(rows)
    print(f"\n=== {field} probe: {correct}/{n} = {correct / n:.0%} ===")
    for (g, m), c in conf.most_common(12):
        print(("  OK " if g == m else "  XX ") + f"gold={g:<16} model={m:<16} x{c}")


async def main() -> int:
    print("===== GOVERNED PROBE (principled improved defs) vs gold =====")
    print("(shipped v6: severity 60%, desired_outcome 58%)")
    for field, (prompt, enum) in _FIELDS.items():
        await _probe(field, prompt, enum)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
