"""PROBE (not a proof): does handing the gray-band adjudicator a couple of representative example
values flip the real synonym pairs it currently rejects on bare names? If even obvious dollar values
can't merge amount/charged_amount, the example-values lever is dead and we don't pay for a
re-extraction. Values here are representative CFPB-style samples chosen only to test the mechanism —
the real proof runs on values captured from the actual extractor.

Usage:  uv run python eval/probe_values.py
"""

from __future__ import annotations

import asyncio

from app.backends.local.llm_ollama import OllamaLLM
from app.schema.dedup import _adjudicate

# (name_a, values_a, name_b, values_b) — representative values, for a mechanism probe only.
CASES = [
    ("amount", ["$1,250.00", "$49.99"], "charged_amount", ["$500.00", "$120.00"]),
    ("amount", ["$1,250.00", "$49.99"], "fraudulent_amount", ["$2,300.00", "$85.00"]),
    ("account_status", ["closed", "past due"], "payment_status", ["late", "unpaid"]),
    ("bank_name", ["Wells Fargo", "Chase"], "company_name", ["Capital One", "Citibank"]),
    (
        "customer_request",
        ["remove the late fee", "refund the charge"],
        "requested_actions",
        ["delete the account", "correct my credit report"],
    ),
    # NON-synonym control: must stay "different" even with values.
    ("account_number", ["4021-8837", "552019"], "account_status", ["closed", "delinquent"]),
]


async def main() -> int:
    llm = OllamaLLM()
    print(f"{'pair':<42} {'bare':<10} {'with values':<12}")
    for a, va, b, vb in CASES:
        bare = "SAME" if await _adjudicate(llm, a, b) else "different"
        withv = "SAME" if await _adjudicate(llm, a, b, values_a=va, values_b=vb) else "different"
        print(f"{a + ' | ' + b:<42} {bare:<10} {withv:<12}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
