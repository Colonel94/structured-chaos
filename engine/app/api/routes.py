"""Review-view HTTP routes — the engine's first client reads the assembled case (Phase 4.7).

Two read-only endpoints under ``/api``: a case register and one case's full review payload (governed
core + emergent + provenance + corrections + the normalised text that backs it). Everything is
RLS-scoped: the tenant comes from the ``X-Tenant-Id`` header and is set as the transaction GUC, so a
query can only ever read that tenant's rows — a wrong id reads nothing (fail-closed), never a leak.

The tenant header is the **PoC** convention (operator-facing review tool, manual tenant onboarding —
CLAUDE.md §9); real auth mapping a session→tenant is later. RLS, not the header, is the isolation
boundary. The session factory is a FastAPI dependency so tests can bind it to their per-test engine.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from ..store import api
from ..store.db import SessionFactory, tenant_session

router = APIRouter(prefix="/api")


def get_factory() -> sessionmaker[Session]:
    """The app-role session factory — overridden in tests to bind the per-test engine."""
    return SessionFactory


# FastAPI dependency aliases via Annotated (the B008-safe idiom — the marker lives in the type, not
# a mutable default). ``TenantHeader`` is required, so a missing header is a 422 before any DB touch.
TenantHeader = Annotated[str, Header(alias="X-Tenant-Id")]
FactoryDep = Annotated[sessionmaker[Session], Depends(get_factory)]


def _tenant(x_tenant_id: str) -> UUID:
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Tenant-Id is not a valid UUID") from None


@router.get("/cases")
def list_cases(x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """The register: recent cases for the tenant with a light summary."""
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        return {"cases": api.list_cases(s)}


@router.get("/cases/{case_id}")
def get_case(case_id: str, x_tenant_id: TenantHeader, factory: FactoryDep) -> dict[str, Any]:
    """One case's full review payload. 404 if the case is absent for this tenant (RLS fail-closed)."""
    try:
        cid = UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="case_id is not a valid UUID") from None
    with tenant_session(_tenant(x_tenant_id), factory=factory) as s:
        review = api.get_case_review(s, cid)
    if review is None:
        raise HTTPException(status_code=404, detail="case not found")
    return review
