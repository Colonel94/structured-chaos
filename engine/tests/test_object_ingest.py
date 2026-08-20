"""Phase 5 — object-store ingest + entity resolution (EDD §16.1). DB-backed.

Covers the trust-critical properties: schema-agnostic profiling, idempotent re-ingest, tenant
isolation on objects (a cross-tenant object lookup reads zero rows), the exact-key resolve policy
(silent only when unambiguous), the multi-anchor cross-check (a typo'd id colliding with another
object must NOT silently bind — the defect the resolver spike surfaced), and the fuzzy name fallback.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.resolve import ingest_object_collection, resolve_object
from app.resolve.profile import profile_key_fields
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

_DIM = 1024

ORDERS = [
    {
        "order_id": "BK-1",
        "phone": "+44 7700 900001",
        "customer_name": "Sarah Whitfield",
        "items": "cupcakes",
    },
    {
        "order_id": "BK-2",
        "phone": "+44 7700 900002",
        "customer_name": "James O'Connor",
        "items": "cupcakes",  # repeats BK-1 so `items` isn't unique → not profiled as a key
    },
    {
        "order_id": "BK-3",
        "phone": "+44 7700 900003",
        "customer_name": "Aisha Rahman",
        "items": "macarons",
    },
    {
        "order_id": "BK-4",
        "phone": "+44 7700 900003",
        "customer_name": "Aisha Rahman",
        "items": "eid box",
    },
]


def _zero() -> list[float]:
    return [0.0] * _DIM


def _axis(idx: int, cos: float, filler: int) -> list[float]:
    """Unit vector with cosine ``cos`` to basis vector ``idx`` (rest on a distinct filler axis)."""
    v = _zero()
    v[idx] = cos
    v[filler] = (1 - cos * cos) ** 0.5
    return v


class _FakeEmbedder:
    """Maps a text to a controlled vector by a marker substring (so cosines to the query are exact)."""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._m = mapping

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            vec = next((v for marker, v in self._m.items() if marker in t), _zero())
            out.append(vec)
        return out


# --------------------------------------------------------------------------- profiling + ingest


def test_profile_picks_identifiers_not_free_text() -> None:
    keys = profile_key_fields(ORDERS)
    assert "order_id" in keys  # unique → identifier
    assert "phone" in keys  # shared but a contact identifier
    assert "customer_name" not in keys  # repeats + free text → not a key
    assert "items" not in keys
    assert keys[0] == "order_id"  # most-selective first


def test_display_id_prefers_identifier_named_over_a_unique_timestamp() -> None:
    """With few rows a timestamp can be as unique as the order number; the display id must still be the
    id-NAMED column (else a confirmation reads "we've found your order 18:42"). Pure, no DB."""
    from app.resolve.ingest import _pick_external_id
    from app.resolve.profile import is_identifier_name

    assert is_identifier_name("order_id") and is_identifier_name("booking_ref")
    assert not is_identifier_name("delivered_at") and not is_identifier_name("slot")
    attrs = {"order_id": "BK-1", "delivered_at": "18:42", "slot": "17:00"}
    # key order puts the timestamp first (alphabetical tie-break) — the id name still wins the display id.
    assert _pick_external_id(attrs, ["delivered_at", "order_id", "slot"]) == "BK-1"


def test_ingest_indexes_keys_and_is_idempotent(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Bakery-Co")
    admin_session.commit()  # tenant must be visible to the RLS app-role session
    with tenant_session(tenant, factory=app_factory) as s:
        r1 = asyncio.run(ingest_object_collection(s, object_type="order", objects=ORDERS))
    assert r1.ingested == 4
    assert r1.duplicates == 0
    assert set(r1.key_fields) == {"order_id", "phone"}
    assert r1.keys_indexed == 8  # 4 order_id + 4 phone
    with tenant_session(tenant, factory=app_factory) as s:
        assert api.count_objects(s, object_type="order") == 4
    # Re-ingest the identical batch → a pure no-op (replay guarantee).
    with tenant_session(tenant, factory=app_factory) as s:
        r2 = asyncio.run(ingest_object_collection(s, object_type="order", objects=ORDERS))
    assert r2.ingested == 0 and r2.duplicates == 4
    with tenant_session(tenant, factory=app_factory) as s:
        assert api.count_objects(s) == 4  # still four, no duplicates


# ----------------------------------------------------------------------- exact-key resolve policy


def _ingest(tenant: object, factory: sessionmaker[Session], objects: object = ORDERS) -> None:
    with tenant_session(tenant, factory=factory) as s:  # type: ignore[arg-type]
        asyncio.run(ingest_object_collection(s, object_type="order", objects=objects))  # type: ignore[arg-type]


def _resolve(tenant: object, factory: sessionmaker[Session], **kw: object) -> object:
    with tenant_session(tenant, factory=factory) as s:  # type: ignore[arg-type]
        return asyncio.run(resolve_object(s, **kw))  # type: ignore[arg-type]


def test_resolve_exact_key_silent_confirm_elicit(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Resolve-Co")
    admin_session.commit()
    _ingest(tenant, app_factory)

    # unique order id → silent (casefold-insensitive)
    r = _resolve(tenant, app_factory, anchor_id="bk-1")
    assert r.mode == "silent" and r.object_id is not None
    # unique phone, formatting-insensitive (spaces/parens/dashes normalise away) → silent
    assert _resolve(tenant, app_factory, phone="+44 (7700) 900-001").mode == "silent"
    # shared phone → confirm with both candidates
    shared = _resolve(tenant, app_factory, phone="+44 7700 900003")
    assert shared.mode == "confirm" and len(shared.candidates) == 2
    # quoted id not found → confirm, never a fuzzy-bind of a typo
    assert _resolve(tenant, app_factory, anchor_id="BK-999").mode == "confirm"
    # no anchor at all → elicit (the no-object fallback never fails)
    assert _resolve(tenant, app_factory).mode == "elicit"


def test_multi_anchor_cross_check_contradiction(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "CrossCheck-Co")
    admin_session.commit()
    _ingest(tenant, app_factory)
    # id resolves to BK-1 but the sender phone belongs to BK-2 → contradiction → confirm, NOT silent.
    contra = _resolve(tenant, app_factory, anchor_id="BK-1", phone="+44 7700 900002")
    assert contra.mode == "confirm"
    # id + its own phone agree → silent.
    agree = _resolve(tenant, app_factory, anchor_id="BK-1", phone="+44 7700 900001")
    assert agree.mode == "silent"


# ------------------------------------------------------------------------------- tenant isolation


def test_object_store_tenant_isolation(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    a = api.create_tenant(admin_session, "Tenant-A")
    b = api.create_tenant(admin_session, "Tenant-B")
    admin_session.commit()
    _ingest(a, app_factory)
    # Tenant B sees none of A's objects, and cannot resolve A's anchor (its keys are invisible too).
    with tenant_session(b, factory=app_factory) as s:
        assert api.count_objects(s) == 0
    assert _resolve(b, app_factory, anchor_id="BK-1").mode == "confirm"  # not found in B
    assert _resolve(b, app_factory, phone="+44 7700 900001").mode == "elicit"  # no phone match in B


# ---------------------------------------------------------------------------- fuzzy name fallback


def test_fuzzy_name_silent_when_unique_confirm_when_ambiguous(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Fuzzy-Co")
    admin_session.commit()
    objs = [
        {
            "order_id": "O1",
            "phone": "P1",
            "customer_name": "MARK1",
            "items": "cake",
        },  # e0 axis, cos .95
        {
            "order_id": "O2",
            "phone": "P2",
            "customer_name": "MARK2",
            "items": "cake",
        },  # e0 axis, cos .10
        {
            "order_id": "O4",
            "phone": "P4",
            "customer_name": "MARK4",
            "items": "cake",
        },  # e2 axis, cos .90
        {
            "order_id": "O5",
            "phone": "P5",
            "customer_name": "MARK5",
            "items": "cake",
        },  # e2 axis, cos .88
    ]
    embedder = _FakeEmbedder(
        {
            "MARK1": _axis(0, 0.95, 1),
            "MARK2": _axis(0, 0.10, 1),
            "MARK4": _axis(2, 0.90, 3),
            "MARK5": _axis(2, 0.88, 3),
            "QUNIQUE": _axis(0, 1.0, 1),  # aligns with the e0 axis → O1 clearly nearest
            "QAMBIG": _axis(2, 1.0, 3),  # aligns with the e2 axis → O4/O5 within margin
        }
    )
    with tenant_session(tenant, factory=app_factory) as s:
        res = asyncio.run(
            ingest_object_collection(s, object_type="order", objects=objs, embedder=embedder)
        )
    assert res.embedded == 4

    # A name aligned to a single clear object → silent.
    uniq = _resolve(tenant, app_factory, name="QUNIQUE", embedder=embedder)
    assert uniq.mode == "silent"
    # A name near two objects within the margin → confirm, never a guess.
    amb = _resolve(tenant, app_factory, name="QAMBIG", embedder=embedder)
    assert amb.mode == "confirm" and len(amb.candidates) == 2
