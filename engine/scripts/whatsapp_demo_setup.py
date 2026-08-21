"""Set up a tenant for the live WhatsApp end-to-end test, with an orders store that includes YOUR phone.

Why your phone: on WhatsApp the sender's number IS the anchor. If your number is on an order, a message
you send resolves that order SILENTLY and the reply CONFIRMS the record instead of asking (Moment 3). So
this seeds a small bakery order book with one row keyed to the number you'll message from.

Usage:
    uv run python scripts/whatsapp_demo_setup.py +447700900123
    #                                            ^ the phone you'll WhatsApp FROM, international format

It prints the tenant UUID — put it in .env as WHATSAPP_TENANT_ID, then restart the engine. Idempotent:
re-running reuses/creates cleanly (objects dedupe on content hash).
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.resolve import ingest_object_collection
from app.store import api
from app.store.db import admin_session, tenant_session

TENANT_NAME = "WhatsApp Live Demo"


async def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("usage: uv run python scripts/whatsapp_demo_setup.py <your-phone e.g. +447700900123>")
        return 1
    my_phone = sys.argv[1].strip()

    # Reuse an existing demo tenant of this name if present, else create one (manual onboarding is
    # allowed behind the scenes — winning-condition §6).
    with admin_session() as a:
        existing = a.execute(
            text("SELECT id FROM tenant WHERE name = :n ORDER BY id LIMIT 1"),
            {"n": TENANT_NAME},
        ).scalar()
        tenant = existing or api.create_tenant(a, TENANT_NAME)

    orders = [
        # YOUR order — the row your WhatsApp number resolves. Slot 17:00 vs delivered 18:42 makes the
        # lateness visible in the confirmation.
        {
            "order_id": "BK-1001",
            "phone": my_phone,
            "customer_name": "You",
            "slot": "17:00",
            "items": "chocolate birthday cake",
            "delivered_at": "18:42",
        },
        # a few others so the profiler treats phone/order_id as identifiers, name/items as descriptive
        {
            "order_id": "BK-1002",
            "phone": "+447700900002",
            "customer_name": "James Okafor",
            "slot": "12:30",
            "items": "two dozen cupcakes",
            "delivered_at": "12:25",
        },
        {
            "order_id": "BK-1003",
            "phone": "+447700900003",
            "customer_name": "Aisha Rahman",
            "slot": "09:00",
            "items": "wedding tier sample box",
            "delivered_at": "09:05",
        },
        {
            "order_id": "BK-1004",
            "phone": "+447700900004",
            "customer_name": "Tom Bennett",
            "slot": "15:15",
            "items": "gluten-free brownies",
            "delivered_at": "15:10",
        },
        {
            "order_id": "BK-1005",
            "phone": "+447700900005",
            "customer_name": "Priya Nair",
            "slot": "11:00",
            "items": "lemon drizzle loaf",
            "delivered_at": "11:02",
        },
    ]
    with tenant_session(tenant) as s:
        res = await ingest_object_collection(s, object_type="order", objects=orders)

    print("\n=== WhatsApp live-demo tenant ready ===")
    print(f"  tenant id : {tenant}")
    print(f"  orders    : {res.ingested} ingested, {res.duplicates} already present")
    print(f"  your order: BK-1001 keyed to {my_phone}")
    print("\nNext:")
    print(f"  1. put this in .env →  WHATSAPP_TENANT_ID={tenant}")
    print("  2. set CHANNEL_BACKEND=cloud + your WHATSAPP_* creds (docs/WHATSAPP-SETUP.md)")
    print("  3. restart the engine, start the tunnel, then WhatsApp the test number:")
    print('       "hey the birthday cake turned up really late and was all squashed"')
    print(f"  4. watch the case at  http://localhost:5173/?tenant={tenant}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
