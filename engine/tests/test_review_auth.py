from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import get_factory
from app.config import settings
from app.main import app
from app.review_auth import (
    hash_password,
    normalise_email,
    token_digest,
    validate_password,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable() -> None:
    salt_a, digest_a = hash_password("correct horse battery staple")
    salt_b, digest_b = hash_password("correct horse battery staple")

    assert salt_a != salt_b
    assert digest_a != digest_b
    assert verify_password("correct horse battery staple", salt_a, digest_a)
    assert not verify_password("wrong password", salt_a, digest_a)


def test_identity_input_validation_and_token_hashing() -> None:
    assert normalise_email("  Maya@Example.COM ") == "maya@example.com"
    assert token_digest("secret") != "secret"
    with pytest.raises(ValueError):
        normalise_email("not-an-email")
    with pytest.raises(ValueError):
        validate_password("too short")


def test_production_rejects_spoofed_tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    response = TestClient(app).get(
        "/api/cases", headers={"X-Tenant-Id": "00000000-0000-4000-8000-000000000001"}
    )
    assert response.status_code == 401


def test_signup_session_and_logout(app_factory: sessionmaker[Session]) -> None:
    app.dependency_overrides[get_factory] = lambda: app_factory
    try:
        client = TestClient(app)
        created = client.post(
            "/api/auth/signup",
            json={
                "email": "maya@example.com",
                "password": "correct horse battery staple",
                "display_name": "Maya",
                "workspace_name": "Northstar Support",
            },
        )
        assert created.status_code == 201
        assert created.json()["workspace"]["name"] == "Northstar Support"
        assert client.get("/api/cases").json() == {"cases": []}

        csrf = client.cookies.get("adaptive_intake_csrf")
        signed_out = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf or ""})
        assert signed_out.status_code == 200
        assert client.get("/api/cases").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_runtime_role_cannot_bulk_read_credentials(app_engine: Engine) -> None:
    """A compromised request path may use the exact-key auth RPCs, never dump credential/session tables."""
    with app_engine.connect() as connection, pytest.raises(ProgrammingError):
        connection.execute(text("SELECT password_hash FROM app_user"))
