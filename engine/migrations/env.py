"""Alembic environment. Migrations run as the **superuser** (``intake_admin``); the URL comes
from app.config so no password is ever written into the repo. Schema is hand-authored (RLS
policies, immutability triggers, role bootstrap, grants) — autogenerate is intentionally unused.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.admin_database_url)

# Hand-written migrations only — no model metadata to diff against.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=settings.admin_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
