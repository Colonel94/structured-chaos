"""Trust gate — originals and provenance are immutable (CLAUDE.md §3, EDD §7.2).

The block is enforced by a trigger, so it holds even for the **superuser** (admin engine),
not merely because the app role lacks the grant. An extraction can never overwrite an original;
a correction can never overwrite an extraction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _now() -> datetime:
    return datetime.now(UTC)


def _seed(admin_session: Session, app_factory: sessionmaker[Session]) -> tuple[UUID, UUID, UUID]:
    """Create a case with one source doc, one extraction, one correction. Return their ids."""
    tenant = api.create_tenant(admin_session, "Immutable-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
        doc = api.add_source_document(
            s,
            case_id=case,
            sha256="a" * 64,
            blob_key="a" * 64,
            mime="image/png",
            channel="file_drop",
            byte_size=10,
            received_at=_now(),
        )
        ext = api.record_extraction(
            s,
            case_id=case,
            field_path="fault",
            value="cake was stale",
            model="fake",
            model_version="v1",
            prompt_version="p1",
            run_id=uuid4(),
            confidence=0.9,
            citations=[
                api.Citation(
                    source_document_id=doc,
                    role="primary",
                    locator={"page": 1, "bbox": [0, 0, 10, 10]},
                )
            ],
        )
        corr = api.record_correction(
            s,
            case_id=case,
            field_path="fault",
            prev_value="cake was stale",
            new_value="cake was mouldy",
            based_on_extraction_id=ext,
            reviewer_id="reviewer-1",
        )
    return doc, ext, corr


def _expect_blocked(engine: Engine, sql: str, params: dict[str, object]) -> None:
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(text(sql), params)


def test_append_only_tables_reject_update_and_delete(
    admin_session: Session, app_factory: sessionmaker[Session], admin_engine: Engine
) -> None:
    doc, ext, corr = _seed(admin_session, app_factory)

    _expect_blocked(admin_engine, "UPDATE source_document SET mime='x' WHERE id=:id", {"id": doc})
    _expect_blocked(admin_engine, "DELETE FROM source_document WHERE id=:id", {"id": doc})

    _expect_blocked(
        admin_engine,
        "UPDATE field_extraction SET value='\"tampered\"'::jsonb WHERE id=:id",
        {"id": ext},
    )
    _expect_blocked(admin_engine, "DELETE FROM field_extraction WHERE id=:id", {"id": ext})

    _expect_blocked(
        admin_engine,
        "UPDATE field_correction SET new_value='\"tampered\"'::jsonb WHERE id=:id",
        {"id": corr},
    )
    _expect_blocked(admin_engine, "DELETE FROM field_correction WHERE id=:id", {"id": corr})


def test_append_only_tables_reject_truncate(
    admin_session: Session, app_factory: sessionmaker[Session], admin_engine: Engine
) -> None:
    """TRUNCATE fires no row triggers — a statement-level guard must still block a wholesale wipe,
    even for the superuser."""
    _seed(admin_session, app_factory)
    for tbl in ("source_document", "field_extraction", "field_correction"):
        _expect_blocked(admin_engine, f"TRUNCATE {tbl}", {})


def test_app_role_denied_update_delete_on_append_only(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """Defence in depth: beyond the trigger, app_rw simply lacks UPDATE/DELETE on the logs."""
    doc, ext, _ = _seed(admin_session, app_factory)
    tenant_row = admin_session.execute(
        text("SELECT tenant_id FROM source_document WHERE id=:id"), {"id": doc}
    ).one()
    tenant = tenant_row[0]
    with pytest.raises(DBAPIError), tenant_session(tenant, factory=app_factory) as s:
        s.execute(text("DELETE FROM field_extraction WHERE id=:id"), {"id": ext})


def test_confidence_is_required(admin_session: Session, app_factory: sessionmaker[Session]) -> None:
    """An extracted value must carry a confidence (NOT NULL) — the schema refuses a value the model
    gave no confidence for (CLAUDE.md §3). (Source provenance is now the citation bridge — its
    "≥1 citation" invariant is proven in test_trust_coverage.)"""
    tenant = api.create_tenant(admin_session, "Provenance-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
    # A raw insert with NULL confidence must fail the NOT NULL constraint.
    with pytest.raises(DBAPIError), tenant_session(tenant, factory=app_factory) as s:
        s.execute(
            text(
                "INSERT INTO field_extraction "
                "(tenant_id, case_id, field_path, value, model, model_version, prompt_version, "
                " confidence, run_id) "
                "VALUES (NULLIF(current_setting('app.tenant_id', true),'')::uuid, :c, 'fault', "
                " '\"x\"'::jsonb, 'm', 'v', 'p', NULL, gen_random_uuid())"
            ),
            {"c": case},
        )
