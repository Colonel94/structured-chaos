"""Test fixtures for the Phase-1 trust spine.

A real Postgres (pgvector image) is spun up once per session via testcontainers, the actual
Alembic migration is applied (so the tests exercise the real RLS/trigger/grant DDL, not a
hand-rolled copy), and two engines are handed out: an **admin** engine (superuser — creates
tenants) and an **app** engine that connects as the least-privilege ``app_rw`` role the
migration created. Tests that need the DB depend on these fixtures; locally they skip if Docker is
unavailable (so the non-DB suite runs anywhere), but under CI a missing DB is a HARD FAILURE — the
trust spine must never silently skip its way to green (see `_REQUIRE_DB`).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.store.db import make_engine

_ENGINE_DIR = Path(__file__).resolve().parents[1]

# In CI (GitHub sets CI=true) the trust-spine suite MUST run — a missing DB is a hard failure, not
# a silent skip. Otherwise a broken testcontainers import or a Docker hiccup would let an RLS /
# immutability / idempotency regression ship green, voiding CLAUDE.md §6a. Locally (no CI / no
# REQUIRE_DB) the DB tests still skip so the non-DB suite runs anywhere.
_REQUIRE_DB = os.environ.get("CI") == "true" or os.environ.get("REQUIRE_DB") == "1"


def _no_db(reason: str) -> None:
    if _REQUIRE_DB:
        pytest.fail(f"DB-backed trust tests are required here but the DB is unavailable: {reason}")
    pytest.skip(reason)


try:
    # Prefer the non-deprecated location; fall back to the classic one on older testcontainers.
    try:
        from testcontainers.community.postgres import (
            PostgresContainer,  # type: ignore[import-not-found]
        )
    except Exception:  # noqa: BLE001
        from testcontainers.postgres import PostgresContainer

    _HAS_TC = True
except Exception:  # noqa: BLE001  # pragma: no cover - import guard
    _HAS_TC = False


@pytest.fixture(scope="session")
def pg() -> Iterator[None]:
    """Start Postgres, point the global settings at it, and apply the migrations + queue schema."""
    if not _HAS_TC:
        _no_db("testcontainers not installed")

    try:
        container = PostgresContainer(
            "pgvector/pgvector:pg16",
            username="intake_admin",
            password="admin_pw_test",
            dbname="adaptive_intake",
        )
        container.start()
    except Exception as exc:  # noqa: BLE001  # Docker not running / image unavailable
        _no_db(f"Docker/Postgres unavailable: {exc}")

    # Repoint the global settings at the container so the migration + app engines all agree.
    settings.postgres_host = container.get_container_host_ip()
    settings.postgres_port = int(container.get_exposed_port(5432))
    settings.postgres_db = "adaptive_intake"
    settings.postgres_admin_user = "intake_admin"
    settings.postgres_admin_password = "admin_pw_test"
    settings.postgres_user = "app_rw"
    settings.postgres_password = "app_pw_test"

    # Apply the real migration in-process (programmatic Config → no ini/logging coupling).
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_ENGINE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.admin_database_url)
    command.upgrade(cfg, "head")

    # Procrastinate owns/versions its own schema — apply it (+ app_rw grants) alongside the
    # Alembic-managed trust spine, so the transactional-enqueue tests have a queue to defer into.
    from app.queue import admin_conninfo, apply_procrastinate_schema

    apply_procrastinate_schema(admin_conninfo())

    try:
        yield None
    finally:
        container.stop()


@pytest.fixture()
def admin_engine(pg: None) -> Iterator[Engine]:
    eng = make_engine(settings, admin=True)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def app_engine(pg: None) -> Iterator[Engine]:
    """Engine connecting as the RLS-enforced ``app_rw`` role."""
    eng = make_engine(settings, admin=False)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def app_factory(app_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=app_engine, class_=Session, expire_on_commit=False, future=True)


@pytest.fixture()
def admin_session(admin_engine: Engine) -> Iterator[Session]:
    sess = Session(bind=admin_engine, future=True)
    try:
        yield sess
        sess.commit()
    finally:
        sess.close()
