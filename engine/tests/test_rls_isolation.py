"""BLOCKING trust gate — tenant isolation is proven, not assumed (CLAUDE.md §3, EDD §7.1).

Runs entirely as the app role. If this passes, one tenant physically cannot read or write
another's rows, and an unset context reads nothing (fail-closed).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _now() -> datetime:
    return datetime.now(UTC)


def test_app_role_cannot_bypass_rls(app_factory: sessionmaker[Session]) -> None:
    """The whole gate is meaningless if the app connects as a superuser/BYPASSRLS role."""
    sess = app_factory()
    try:
        role, is_super, bypass = sess.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        assert role == "app_rw"
        assert is_super is False
        assert bypass is False
    finally:
        sess.close()


def test_cross_tenant_read_is_empty(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant_a = api.create_tenant(admin_session, "Tenant A")
    tenant_b = api.create_tenant(admin_session, "Tenant B")
    admin_session.commit()

    with tenant_session(tenant_a, factory=app_factory) as s:
        api.create_case(s, channel="file_drop", first_contact_at=_now())

    # Positive control: A sees its own case.
    with tenant_session(tenant_a, factory=app_factory) as s:
        seen_a = s.execute(text("SELECT count(*) FROM case_record")).scalar_one()
    assert seen_a == 1

    # Isolation: B sees zero of A's cases.
    with tenant_session(tenant_b, factory=app_factory) as s:
        seen_b = s.execute(text("SELECT count(*) FROM case_record")).scalar_one()
    assert seen_b == 0


def test_cross_tenant_write_is_rejected(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant_a = api.create_tenant(admin_session, "Write-A")
    tenant_b = api.create_tenant(admin_session, "Write-B")
    admin_session.commit()

    # In tenant B's context, try to plant a row stamped for tenant A → WITH CHECK must reject.
    with pytest.raises(DBAPIError), tenant_session(tenant_b, factory=app_factory) as s:
        s.execute(
            text(
                "INSERT INTO case_record (tenant_id, channel, first_contact_at) "
                "VALUES (:tid, 'file_drop', now())"
            ),
            {"tid": str(tenant_a)},
        )


def test_app_role_cannot_repoint_tenant_id(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """The column-scoped UPDATE grant excludes tenant_id, so a compromised app role cannot move a
    case to another tenant even within its own session."""
    tenant_a = api.create_tenant(admin_session, "Repoint-A")
    tenant_b = api.create_tenant(admin_session, "Repoint-B")
    admin_session.commit()
    with tenant_session(tenant_a, factory=app_factory) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=_now())
    with pytest.raises(DBAPIError), tenant_session(tenant_a, factory=app_factory) as s:
        s.execute(
            text("UPDATE case_record SET tenant_id = :b WHERE id = :case"),
            {"b": str(tenant_b), "case": case},
        )


def test_unset_context_reads_zero(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant_a = api.create_tenant(admin_session, "Fail-Closed")
    admin_session.commit()
    with tenant_session(tenant_a, factory=app_factory) as s:
        api.create_case(s, channel="file_drop", first_contact_at=_now())

    # A fresh connection with NO app.tenant_id set must see nothing (fail-closed default).
    sess = app_factory()
    try:
        n = sess.execute(text("SELECT count(*) FROM case_record")).scalar_one()
        assert n == 0
    finally:
        sess.close()
