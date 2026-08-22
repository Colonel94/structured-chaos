"""R5 — fail-closed on default/placeholder secrets in prod.

A real deployment holding complaint data must never boot with ``change_me_*`` or the PoC portal secret.
This is gated on ``app_env`` so dev / test / the local PoC are untouched; only prod refuses to start.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

_REAL = {
    "postgres_password": "s3cr3t-app-rw-pw",
    "postgres_admin_password": "s3cr3t-admin-pw",
    "minio_secret_key": "s3cr3t-minio-key",
    "portal_secret": "s3cr3t-portal-hmac",
}


def test_prod_refuses_default_postgres_secret() -> None:
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        Settings(app_env="prod", **{**_REAL, "postgres_password": "change_me_local"})


def test_prod_refuses_poc_portal_secret_when_portal_enabled() -> None:
    with pytest.raises(ValidationError, match="PORTAL_SECRET"):
        Settings(
            app_env="prod",
            portal_enabled=True,
            **{**_REAL, "portal_secret": "poc-portal-secret-2026"},
        )


def test_prod_allows_real_secrets() -> None:
    s = Settings(app_env="prod", portal_enabled=True, **_REAL)
    assert s.app_env == "prod"


def test_dev_is_not_gated() -> None:
    # The committed local PoC default: dev with placeholder secrets must still boot (zero regression).
    s = Settings(
        app_env="dev",
        postgres_password="change_me_local",
        portal_enabled=True,
        portal_secret="",
    )
    assert s.app_env == "dev"


def test_prod_ignores_disabled_portal_secret() -> None:
    # portal off → its secret is irrelevant, must not block boot even if empty.
    s = Settings(app_env="prod", portal_enabled=False, **{**_REAL, "portal_secret": ""})
    assert s.portal_enabled is False
