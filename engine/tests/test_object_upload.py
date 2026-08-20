"""Phase 5 (sellability) — self-serve object-store upload, end-to-end (the §2 self-serve box).

The adapter parses a CSV/JSON/JSONL export into row dicts; ``POST /api/objects`` profiles + lands them
resolvable, idempotently, tenant-scoped. The payoff test: an uploaded order then RESOLVES the anchor on a
case (silent bind), which is what lets the drill look facts up instead of asking (Moment 3). Closes the
audit gap "object store = a test-only function; the upload adapter its docstring references doesn't exist."
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import get_factory
from app.main import app
from app.resolve import resolve_object
from app.resolve.upload import ObjectFileError, parse_object_file
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

# Free-text columns repeat (items, customer_name, status) so the profiler can tell them from the
# identifiers (order_id unique, phone a shared contact key) — with too few distinct rows everything
# looks unique. Mirrors the shape of the known-good ORDERS fixture.
_CSV = (
    "order_id,phone,customer_name,items,status\r\n"
    "BK-1,+44 7700 900001,Sarah Whitfield,cupcakes,delivered\r\n"
    "BK-2,+44 7700 900002,James O'Connor,cupcakes,delivered\r\n"
    "BK-3,+44 7700 900003,Aisha Rahman,macarons,delivered\r\n"
    "BK-4,+44 7700 900003,Aisha Rahman,macarons,late\r\n"
)


def test_adapter_parses_csv_json_jsonl_and_rejects_garbage() -> None:
    csv_rows = parse_object_file("orders.csv", _CSV.encode("utf-8"))
    assert len(csv_rows) == 4 and csv_rows[0]["order_id"] == "BK-1"
    # JSON array, JSON wrapper, and JSONL all normalise to the same shape.
    assert parse_object_file("o.json", b'[{"order_id":"A1"}]')[0]["order_id"] == "A1"
    assert parse_object_file("o.json", b'{"objects":[{"order_id":"A1"}]}')[0]["order_id"] == "A1"
    assert len(parse_object_file("o.jsonl", b'{"order_id":"A1"}\n{"order_id":"A2"}\n')) == 2
    with pytest.raises(ObjectFileError):
        parse_object_file("o.json", b"not json at all {[")


async def test_upload_route_ingests_is_idempotent_and_resolves_an_anchor(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Orders-Co")
    admin_session.commit()

    app.dependency_overrides[get_factory] = lambda: app_factory
    try:
        client = TestClient(app)
        headers = {"X-Tenant-Id": str(tenant)}

        # A stranger drops their orders export — no schema declared.
        r = client.post(
            "/api/objects",
            headers=headers,
            data={"object_type": "order"},
            files={"file": ("orders.csv", _CSV, "text/csv")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ingested"] == 4 and body["total"] == 4
        assert set(body["key_fields"]) == {"order_id", "phone"}  # profiler found the identifiers

        # Re-uploading the same export is a pure no-op (idempotent).
        again = client.post(
            "/api/objects",
            headers=headers,
            data={"object_type": "order"},
            files={"file": ("orders.csv", _CSV, "text/csv")},
        ).json()
        assert again["ingested"] == 0 and again["duplicates"] == 4 and again["total"] == 4

        # The payoff: a case quoting an uploaded order id resolves silently — the anchor is a KEY.
        with tenant_session(tenant, factory=app_factory) as s:
            res = await resolve_object(s, anchor_id="BK-1")
        assert res.mode == "silent" and res.object_id is not None

        # An empty file is rejected (400), never a silent no-op.
        bad = client.post(
            "/api/objects", headers=headers, files={"file": ("empty.csv", "", "text/csv")}
        )
        assert bad.status_code == 400
    finally:
        app.dependency_overrides.clear()
