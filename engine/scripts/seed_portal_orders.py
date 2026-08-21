"""Seed a realistic ORDER collection for the portal demo tenant (dev/demo only).

The "it already knew" moments (winning-condition §3 Moments 2 & 3) need an object store to reason
against: without orders, every drill is an open question and the anchor is just text. A real bakery
would upload this same file / connect this same feed in the §2 setup gate; here we ingest it directly
through the REAL resolution path (`ingest_object_collection` → deterministic key profiling → the
exact-key index the resolver binds against), so a customer typing "BK-1001" resolves silently and the
elicitation can STATE what the record shows instead of asking.

Deliberately includes anomalies + contrasts so the analytical drill and the case synthesis have
something real to surface: a late delivery (17:00 slot, delivered 18:42), a much later one, a
wrong-item order, an undelivered one — against two clean on-time orders.

Run (host, groups synced, Ollama/embeddings up):
    POSTGRES_ADMIN_PASSWORD=change_me_admin_local uv run --group asr \
        python scripts/seed_portal_orders.py "Portal Demo Co"
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.resolve import ingest_object_collection
from app.store.db import admin_session, tenant_session

# A small, realistic bakery-order book. `order_id` is the anchor key (unique → identifier); `phone` is a
# contact key (resolves the sender even when they quote no number). `delivery_slot`/`delivered_at`/
# `items`/`status`/`customer_name` are DESCRIPTIVE — stated back as "what we found", never matched on.
ORDERS: list[dict[str, object]] = [
    {
        "order_id": "BK-1001",
        "customer_name": "Layla Hassan",
        "phone": "+971501112221",
        "items": "1x chocolate fudge cake (8in)",
        "delivery_slot": "17:00",
        "delivered_at": "18:42",
        "status": "delivered late",
    },
    {
        "order_id": "BK-1002",
        "customer_name": "Omar Farouk",
        "phone": "+971502223332",
        "items": "1x red velvet cake (10in)",
        "delivery_slot": "12:00",
        "delivered_at": "11:58",
        "status": "delivered on time",
    },
    {
        "order_id": "BK-1003",
        "customer_name": "Sara Khan",
        "phone": "+971503334443",
        "items": "12x vanilla cupcakes",
        "delivery_slot": "15:00",
        "delivered_at": "15:05",
        "status": "delivered — customer flagged wrong flavour",
    },
    {
        "order_id": "BK-1004",
        "customer_name": "Ahmed Nasser",
        "phone": "+971504445554",
        "items": "3-tier wedding cake",
        "delivery_slot": "10:00",
        "delivered_at": "13:20",
        "status": "delivered very late",
    },
    {
        "order_id": "BK-1005",
        "customer_name": "Mariam Saleh",
        "phone": "+971505556665",
        "items": "1x New York cheesecake",
        "delivery_slot": "14:00",
        "delivered_at": "14:00",
        "status": "delivered on time",
    },
    {
        "order_id": "BK-1006",
        "customer_name": "Yusuf Rahman",
        "phone": "+971506667776",
        "items": "1x box of 9 brownies",
        "delivery_slot": "16:00",
        "delivered_at": "",
        "status": "not delivered — parcel lost",
    },
]


async def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "Portal Demo Co"
    with admin_session() as a:
        tid = a.execute(
            text("SELECT id FROM tenant WHERE name = :n ORDER BY id LIMIT 1"), {"n": name}
        ).scalar()
    if tid is None:
        print(f'tenant "{name}" not found — run scripts/portal_enable.py "{name}" first')
        return 1

    # Optional embedder (fuzzy name fallback / Moment 2). Skip gracefully if the model isn't loaded —
    # exact-key resolution (order id / phone) does not need it.
    embedder: object | None = None
    try:
        from app.backends.registry import get_embedding

        embedder = get_embedding()
    except Exception as exc:  # noqa: BLE001 — a missing embed model must not block the seed
        print(f"(no embedder: {exc} — seeding exact-key resolution only)")

    with tenant_session(tid) as s:
        result = await ingest_object_collection(
            s, object_type="order", objects=ORDERS, embedder=embedder  # type: ignore[arg-type]
        )

    print(f"tenant   : {tid}  ({name})")
    print(
        f"orders   : ingested={result.ingested} duplicates={result.duplicates} "
        f"keys_indexed={result.keys_indexed} embedded={result.embedded}"
    )
    print(
        "anchors  : BK-1001 (late), BK-1004 (very late), BK-1003 (wrong item), "
        "BK-1006 (undelivered), BK-1002/BK-1005 (on time)"
    )
    print(
        'try      : submit a sparse case, answer the anchor "BK-1001" — it should STATE what it found.'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
