"""Database engine + the tenant-scoped session (RLS context).

The engine connects as the least-privilege ``app_rw`` role (EDD §7.1). Every unit of work
runs inside :func:`tenant_session`, which sets the ``app.tenant_id`` GUC **transaction-locally**
(``set_config(..., is_local => true)``) so Row-Level Security scopes every query to one tenant
and an unset context reads zero rows (fail-closed). We use ``set_config`` rather than a literal
``SET LOCAL`` so the tenant id is a bound parameter, never string-interpolated SQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings, settings


def make_engine(cfg: Settings = settings, *, admin: bool = False) -> Engine:
    """Create an Engine. ``admin=True`` connects as the superuser (migrations/tests only)."""
    url = cfg.admin_database_url if admin else cfg.database_url
    # future=True → SQLAlchemy 2.0 semantics; pool_pre_ping avoids stale-conn errors after
    # the Postgres container restarts.
    return create_engine(url, future=True, pool_pre_ping=True)


# Import-time app-role engine + session factory. Cheap (no connection made until first use).
engine: Engine = make_engine()
SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)


@contextmanager
def tenant_session(
    tenant_id: UUID | str, *, factory: sessionmaker[Session] = SessionFactory
) -> Iterator[Session]:
    """Yield a session bound to one tenant for the life of a single transaction.

    Commits on clean exit, rolls back on exception. The ``app.tenant_id`` GUC is set with
    ``is_local => true`` so it is scoped to this transaction only — critical under any
    transaction-pooling proxy (PgBouncer), where a plain ``SET`` would leak the tenant
    context to the next checkout.
    """
    session = factory()
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def admin_session(cfg: Settings = settings) -> Iterator[Session]:
    """Yield a superuser session (no RLS context). For migrations/tests/bootstrap only —
    never on the request path."""
    admin_engine = make_engine(cfg, admin=True)
    session = Session(bind=admin_engine, future=True)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        admin_engine.dispose()
