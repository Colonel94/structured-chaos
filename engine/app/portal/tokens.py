"""Signed case tokens — the read-scoped capability for a customer to check their case (PORTAL.md §3).

A case token is ``b64url(payload) + "." + b64url(HMAC_SHA256(secret, payload))`` where
``payload = "{tenant_id}:{case_id}"``. It is unguessable without ``portal_secret`` (no login, no
enumerable ``/case/{uuid}``), and it carries the tenant so a handler sets the RLS GUC with no cross-tenant
lookup. Verification is a constant-time compare; a tampered signature, a wrong secret, or a malformed
token all return ``None`` (fail-closed). Rotating the secret invalidates outstanding links (documented).

This is a *capability*, not a session: it grants exactly read-status + submit-one-answer for one case.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from uuid import UUID

from ..config import settings


class PortalSecretMissing(RuntimeError):
    """No ``portal_secret`` configured — the portal must not mint or trust tokens without one."""


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _secret() -> bytes:
    if not settings.portal_secret:
        raise PortalSecretMissing(
            "portal_secret is not set — required to sign/verify case tokens (see PORTAL.md / .env)."
        )
    return settings.portal_secret.encode("utf-8")


def _sign(payload: bytes) -> str:
    return _b64e(hmac.new(_secret(), payload, hashlib.sha256).digest())


def sign_case_token(tenant_id: UUID | str, case_id: UUID | str) -> str:
    """Mint a signed, read-scoped token for one (tenant, case)."""
    payload = f"{tenant_id}:{case_id}".encode()
    return f"{_b64e(payload)}.{_sign(payload)}"


def verify_case_token(token: str) -> tuple[UUID, UUID] | None:
    """Return ``(tenant_id, case_id)`` iff the token is well-formed and its signature is valid, else
    ``None``. Constant-time signature compare; any error (bad base64, wrong shape, bad uuid) → None.
    """
    try:
        payload_b64, sig = token.split(".", 1)
        payload = _b64d(payload_b64)
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        tenant_s, case_s = payload.decode("utf-8").split(":", 1)
        return UUID(tenant_s), UUID(case_s)
    except (ValueError, PortalSecretMissing):
        return None
