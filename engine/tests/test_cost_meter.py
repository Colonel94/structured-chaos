"""Phase-2 gate — the cost-per-case meter aggregates usage per case and stays tenant-isolated."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.store import api, meter
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")


def _now() -> datetime:
    return datetime.now(UTC)


def test_case_cost_aggregates_backend_calls(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Meter-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        case = api.create_case(s, channel="whatsapp", first_contact_at=_now())
        # An ASR call, then two LLM calls — the shape a real ingest produces.
        meter.meter_usage(
            s,
            interface="asr",
            backend="local",
            model="large-v3",
            usage={"audio_seconds": 12.0, "wall_ms": 800.0},
            case_id=case,
        )
        meter.meter_usage(
            s,
            interface="llm",
            backend="local",
            model="qwen3:14b",
            usage={"tokens_in": 300, "tokens_out": 120, "wall_ms": 5200.0},
            case_id=case,
        )
        meter.meter_usage(
            s,
            interface="llm",
            backend="local",
            model="qwen3:14b",
            usage={"tokens_in": 50, "tokens_out": 40, "wall_ms": 1100.0},
            case_id=case,
        )
        cost = meter.case_cost(s, case)

    assert cost["calls"] == 3
    assert cost["tokens_in"] == 350  # 300 + 50
    assert cost["tokens_out"] == 160  # 120 + 40
    assert cost["audio_seconds"] == pytest.approx(12.0)
    assert cost["wall_ms"] == pytest.approx(7100.0)  # 800 + 5200 + 1100 — the per-case GPU time
    assert cost["cost_usd"] == 0.0  # local path is $0; wall_ms is the real figure


def test_meter_is_tenant_isolated(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant_a = api.create_tenant(admin_session, "Meter-A")
    tenant_b = api.create_tenant(admin_session, "Meter-B")
    admin_session.commit()
    with tenant_session(tenant_a, factory=app_factory) as s:
        case = api.create_case(s, channel="email", first_contact_at=_now())
        meter.meter_usage(
            s,
            interface="llm",
            backend="local",
            model="qwen3:14b",
            usage={"tokens_in": 100, "wall_ms": 500.0},
            case_id=case,
        )
    # Tenant B, reading A's case_id, sees nothing (RLS).
    with tenant_session(tenant_b, factory=app_factory) as s:
        cross = meter.case_cost(s, case)
    assert cross["calls"] == 0
    assert cross["wall_ms"] == 0.0
