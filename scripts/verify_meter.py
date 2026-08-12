"""Live: a REAL local-LLM call's usage lands in the cost meter — closes the backend→meter loop
that the Phase 0-1-2 review flagged as open (`backend_call` was empty; the meter had only ever
seen synthetic data).

    uv run --project engine python scripts/verify_meter.py   (needs Ollama up + compose DB)
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from uuid import uuid4

sys.path.insert(0, "engine")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from app.backends.registry import get_llm
from app.store import api, meter
from app.store.db import admin_session, tenant_session


async def main() -> int:
    llm = get_llm()  # local → a fresh OllamaLLM (single-flight)
    reply = await llm.complete("Reply with exactly one word: ok")

    with admin_session() as adm:
        tenant = api.create_tenant(adm, f"Meter-Live-{uuid4().hex[:6]}")
    with tenant_session(tenant) as s:
        case = api.create_case(s, channel="file_drop", first_contact_at=datetime.now(UTC))
        # The exact call a Phase-3 stage will make, immediately after the awaited backend call.
        meter.meter_backend(
            s, backend=llm, interface="llm", backend_name="local", model="qwen3:14b", case_id=case
        )
        cost = meter.case_cost(s, case)

    print(f"real LLM reply={reply.strip()[:20]!r}")
    print(f"metered per-case cost={cost}")
    ok = cost["calls"] == 1 and cost["wall_ms"] > 0 and cost["tokens_out"] > 0
    print(("PASS" if ok else "FAIL"), "- a real inference was recorded to backend_call")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
