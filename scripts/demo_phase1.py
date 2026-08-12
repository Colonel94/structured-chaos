"""Hands-on Phase-1 trust-spine demo — run it yourself, read the plain-English PASS/FAIL.

This is the human-testable counterpart to the automated suite (`cd engine && uv run pytest`). It
drives the LIVE compose Postgres (localhost) through every Phase-1 trust invariant and prints what
happened, so you can see with your own eyes that isolation / immutability / provenance / idempotency
hold — not just trust a green test count.

Prereqs: `docker compose --env-file .env -f deploy/docker-compose.yml up -d db` and the migration
applied (`cd engine && uv run alembic upgrade head`). Then:

    uv run --project engine python scripts/demo_phase1.py

It creates two throwaway tenants (unique names each run) and never deletes originals (they're
immutable by design), so re-running just adds fresh demo tenants.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, "engine")

# Windows consoles default to cp1252; force UTF-8 so output never dies on a glyph.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from app.store import api
from app.store.db import SessionFactory, admin_session, tenant_session
from sqlalchemy import text

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _results.append(ok)
    print(f"  {_PASS if ok else _FAIL}  {label}" + (f"  - {detail}" if detail else ""))


def blocked(fn) -> tuple[bool, str]:  # type: ignore[no-untyped-def]
    """Return (was_blocked, error-class-name) for an operation that MUST raise."""
    try:
        fn()
        return False, "no error (LEAK!)"
    except Exception as e:  # noqa: BLE001 - the whole point is to catch the block
        return True, type(e).__name__


def _now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> int:
    suffix = uuid4().hex[:8]
    print(f"\n=== Phase-1 trust-spine demo (run {suffix}) ===\n")

    # --- Setup: two tenants (a bakery and a ministry — same engine, isolated) --------------
    with admin_session() as adm:
        tenant_bakery = api.create_tenant(adm, f"Demo Bakery {suffix}")
        tenant_ministry = api.create_tenant(adm, f"Demo Ministry {suffix}")
    print(f"Created tenants: bakery={tenant_bakery}  ministry={tenant_ministry}\n")

    # --- 1. A case + a value drawn from MANY sources (provenance is a bridge) ---------------
    print("1. Case creation + multi-source provenance (citations, with roles)")
    with tenant_session(tenant_bakery) as s:
        case = api.create_case(s, channel="whatsapp", first_contact_at=_now())
        voice = api.add_source_document(
            s, case_id=case, sha256="d" * 64, blob_key="d" * 64, mime="audio/ogg",
            channel="whatsapp", byte_size=2048, received_at=_now(), doc_kind="message",
        )
        order = api.add_source_document(  # object-store row, snapshotted + content-hashed
            s, case_id=case, sha256="a1" * 32, blob_key="a1" * 32, mime="application/json",
            channel="file_drop", byte_size=128, received_at=_now(), doc_kind="object_snapshot",
        )
        # "delivered 102 min late" is DERIVED from the order's promised time + the complaint;
        # the voice note is the primary source. One value, three citations, distinct roles.
        ext = api.record_extraction(
            s, case_id=case, field_path="fault", value="cake arrived melted, 102 min late",
            model="qwen3:14b", model_version="q4_k_m", prompt_version="p1", run_id=uuid4(),
            confidence=0.82,
            citations=[
                api.Citation(voice, "primary", {"t_start": 3.2, "t_end": 6.8}, 0.9),
                api.Citation(order, "derived_from", {"field": "promised_time"}, 0.6),
                api.Citation(order, "contradicts", {"field": "status=on_time"}, None),
            ],
        )
        api.rebuild_field_current(s, case)
        row = s.execute(
            text("SELECT value, source_kind, confidence FROM field_current "
                 "WHERE case_id=:c AND field_path='fault'"),
            {"c": case},
        ).one()
        cites = s.execute(
            text("SELECT c.role, sd.doc_kind FROM extraction_citation c "
                 "JOIN source_document sd ON sd.id = c.source_document_id "
                 "WHERE c.extraction_id = :e ORDER BY c.role"),
            {"e": ext},
        ).all()
    roles = {r for r, _ in cites}
    check("case created immediately", case is not None)
    check("value projected into field_current", row[0].startswith("cake arrived melted"))
    check(
        "value traces to MANY sources with roles",
        roles == {"primary", "derived_from", "contradicts"},
        f"citations={[(r, k) for r, k in cites]}",
    )
    check(
        "a looked-up value cites an object-store snapshot, not a message",
        any(k == "object_snapshot" for _, k in cites),
    )

    # --- 2. Tenant isolation ----------------------------------------------------------------
    print("\n2. Tenant isolation (RLS)")
    with tenant_session(tenant_bakery) as s:
        seen_own = s.execute(text("SELECT count(*) FROM case_record")).scalar_one()
    with tenant_session(tenant_ministry) as s:
        seen_other = s.execute(text("SELECT count(*) FROM case_record")).scalar_one()
    check("tenant sees its own case", seen_own >= 1, f"{seen_own} case(s)")
    check("other tenant sees ZERO of it", seen_other == 0, f"{seen_other} case(s)")

    def _cross_write() -> None:
        with tenant_session(tenant_ministry) as s:
            s.execute(
                text("INSERT INTO case_record (tenant_id, channel, first_contact_at) "
                     "VALUES (:t, 'email', now())"),
                {"t": str(tenant_bakery)},
            )

    ok, why = blocked(_cross_write)
    check("cross-tenant write rejected (WITH CHECK)", ok, why)

    sess = SessionFactory()  # a fresh connection with NO app.tenant_id set
    try:
        unset_n = sess.execute(text("SELECT count(*) FROM case_record")).scalar_one()
    finally:
        sess.close()
    check("unset context reads zero (fail-closed)", unset_n == 0, f"{unset_n} rows visible")

    # --- 3. Immutability of originals & provenance -----------------------------------------
    print("\n3. Immutability (append-only originals + provenance)")
    with admin_session() as adm:  # even the superuser cannot mutate
        ok_u, why_u = blocked(
            lambda: adm.execute(text("UPDATE field_extraction SET value='\"x\"'::jsonb WHERE id=:e"),
                                {"e": ext})
        )
    with admin_session() as adm:
        ok_t, why_t = blocked(lambda: adm.execute(text("TRUNCATE source_document")))
    check("UPDATE on extraction blocked (even superuser)", ok_u, why_u)
    check("TRUNCATE on originals blocked (even superuser)", ok_t, why_t)

    # --- 4. Corrections are preserved and win over extractions ------------------------------
    print("\n4. Corrections (never overwrite; correction beats extraction)")
    with tenant_session(tenant_bakery) as s:
        api.record_correction(
            s, case_id=case, field_path="fault", prev_value="cake arrived melted",
            new_value="cake arrived melted AND late", based_on_extraction_id=ext,
            reviewer_id=f"demo-{suffix}",
        )
        api.rebuild_field_current(s, case)
        after = s.execute(
            text("SELECT value, source_kind FROM field_current "
                 "WHERE case_id=:c AND field_path='fault'"),
            {"c": case},
        ).one()
        extractions_still_there = s.execute(
            text("SELECT count(*) FROM field_extraction WHERE case_id=:c"), {"c": case}
        ).scalar_one()
    check("correction now shown", after[0] == "cake arrived melted AND late" and after[1] == "correction")
    check("original extraction still preserved", extractions_still_there >= 1)

    # --- 5. Idempotency: replay skips, crash is retryable ----------------------------------
    print("\n5. Idempotency (replay skips; crash is retryable)")
    key = api.compute_idempotency_key(
        source_sha256="d" * 64, stage="extract", model_version="q4_k_m",
        prompt_version="p1", code_version="0.1.0",
    )
    with tenant_session(tenant_bakery) as s:
        first = api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case)
        api.complete_stage(s, idempotency_key=key)
    with tenant_session(tenant_bakery) as s:
        replay = api.claim_stage(s, stage="extract", idempotency_key=key, case_id=case)
    check("first claim does the work", first is True)
    check("completed stage skipped on replay", replay is False)

    key2 = api.compute_idempotency_key(
        source_sha256="d" * 64, stage="normalise", model_version="q4_k_m",
        prompt_version="p1", code_version="0.1.0",
    )
    with tenant_session(tenant_bakery) as s:
        api.claim_stage(s, stage="normalise", idempotency_key=key2, case_id=case)  # "crash" (no complete)
    with tenant_session(tenant_bakery) as s:
        retry = api.claim_stage(s, stage="normalise", idempotency_key=key2, case_id=case)
    check("crashed stage is re-claimable (no lost work)", retry is True)

    # --- Verdict ----------------------------------------------------------------------------
    passed, total = sum(_results), len(_results)
    print(f"\n=== {passed}/{total} checks passed — "
          f"{'ALL TRUST GATES HELD' if passed == total else 'SEE FAILURES ABOVE'} ===\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
