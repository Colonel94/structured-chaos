"""Cost-per-case meter (Phase 2). Records each inference call's usage against a case and reports
the aggregate, so per-case cost is measured as features land — not estimated at ship (BUILD-PLAN
Phase 2). On the local 4070 path the $ is zero; ``wall_ms`` (GPU/wall time) is the real figure.

Writes are tenant-stamped from the GUC and RLS-scoped, identical to the trust spine.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from .api import _GUC_TENANT

# Backends expose `last_usage` with a subset of these keys; map them onto the meter columns.
_USAGE_KEYS = ("tokens_in", "tokens_out", "audio_seconds", "wall_ms")


def record_backend_call(
    session: Session,
    *,
    interface: str,
    backend: str,
    model: str,
    case_id: UUID | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    audio_seconds: float = 0.0,
    wall_ms: float = 0.0,
    cost_usd: float = 0.0,
) -> None:
    """Log one inference call's usage for the current tenant, attributed to ``case_id`` if given."""
    session.execute(
        text(f"""
            INSERT INTO backend_call
                (tenant_id, case_id, interface, backend, model,
                 tokens_in, tokens_out, audio_seconds, wall_ms, cost_usd)
            VALUES ({_GUC_TENANT}, :case_id, :interface, :backend, :model,
                    :tokens_in, :tokens_out, :audio_seconds, :wall_ms, :cost_usd)
            """),
        {
            "case_id": case_id,
            "interface": interface,
            "backend": backend,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "audio_seconds": audio_seconds,
            "wall_ms": wall_ms,
            "cost_usd": cost_usd,
        },
    )


def meter_usage(
    session: Session,
    *,
    interface: str,
    backend: str,
    model: str,
    usage: dict[str, float],
    case_id: UUID | None = None,
    cost_usd: float = 0.0,
) -> None:
    """Convenience: record straight from a backend's ``last_usage`` dict (missing keys → 0)."""
    record_backend_call(
        session,
        interface=interface,
        backend=backend,
        model=model,
        case_id=case_id,
        tokens_in=int(usage.get("tokens_in", 0)),
        tokens_out=int(usage.get("tokens_out", 0)),
        audio_seconds=float(usage.get("audio_seconds", 0.0)),
        wall_ms=float(usage.get("wall_ms", 0.0)),
        cost_usd=cost_usd,
    )


def meter_backend(
    session: Session,
    *,
    backend: object,
    interface: str,
    backend_name: str,
    model: str,
    case_id: UUID | None = None,
    cost_usd: float = 0.0,
) -> None:
    """Record a backend's ``last_usage`` after a call — the seam that closes the loop
    backend-call → meter row. Call it **immediately after** the awaited backend call, on the same
    per-work-unit backend instance (see backends/local single-flight contract), so usage is not
    clobbered by a concurrent call. Real pipeline stages (Phase 3) call this after each backend."""
    usage = getattr(backend, "last_usage", {}) or {}
    meter_usage(
        session,
        interface=interface,
        backend=backend_name,
        model=model,
        usage=usage,
        case_id=case_id,
        cost_usd=cost_usd,
    )


def case_cost(session: Session, case_id: UUID) -> dict[str, float]:
    """Aggregate usage for a case: call count, tokens, audio-seconds, total wall/GPU time, and $.
    RLS scopes this to the current tenant — another tenant reading the same case_id gets zeros."""
    row = session.execute(
        text("""
            SELECT count(*)                     AS calls,
                   COALESCE(sum(tokens_in), 0)  AS tokens_in,
                   COALESCE(sum(tokens_out), 0) AS tokens_out,
                   COALESCE(sum(audio_seconds), 0) AS audio_seconds,
                   COALESCE(sum(wall_ms), 0)    AS wall_ms,
                   COALESCE(sum(cost_usd), 0)   AS cost_usd
            FROM backend_call
            WHERE case_id = :case_id
            """),
        {"case_id": case_id},
    ).one()
    return {
        "calls": float(row[0]),
        "tokens_in": float(row[1]),
        "tokens_out": float(row[2]),
        "audio_seconds": float(row[3]),
        "wall_ms": float(row[4]),
        "cost_usd": float(row[5]),
    }
