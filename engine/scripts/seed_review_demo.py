"""Seed the compose DB with real cases for a live review-UI check (Phase 7 — dev/demo only).

Drives the REAL pipeline (ingest → normalise → extract via Ollama → deterministic rules) on a handful
of real CFPB narratives we did NOT author + the audio smoke fixture, so the review screen renders a
genuine queue (governed core + calibrated confidence + priority/SLA + per-field provenance spans).
Prints the tenant UUID to open in the UI. Not a test; not wired into the app.

Run (host, groups synced, Ollama up):
  POSTGRES_ADMIN_PASSWORD=change_me_admin_local uv run --group asr python scripts/seed_review_demo.py
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from datetime import UTC, datetime, timedelta

from app.backends.registry import get_blob, get_llm
from app.extract.stage import extract_case
from app.intake.ingest import ingest_messages
from app.intake.models import InboundAttachment, InboundMessage
from app.pipeline import normalise_source_document
from app.rules.stage import decide_case
from app.store import api
from app.store.db import admin_session

ROOT = pathlib.Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "engine" / "eval" / "fixtures" / "cfpb_sample.jsonl"
AUDIO = ROOT / "data" / "smoke" / "asr_smoke.wav"
N_TEXT = 5


async def _drive(tenant: object, msg: InboundMessage, blob: object, llm: object) -> list[object]:
    res = await ingest_messages(tenant, [msg], blob=blob)
    for sdid in res.source_document_ids:
        await normalise_source_document(tenant, sdid, blob=blob)
    for cid in res.case_ids:
        await extract_case(tenant, cid, llm=llm)
        decide_case(tenant, cid)
    return list(res.case_ids)


async def main() -> None:
    with admin_session() as s:
        tenant = api.create_tenant(s, "Phase7 Review Demo")
    print(f"TENANT {tenant}")

    blob, llm = get_blob(), get_llm()
    base = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)

    lines = SAMPLE.read_text(encoding="utf-8").splitlines()[:N_TEXT]
    for i, line in enumerate(lines):
        rec = json.loads(line)
        msg = InboundMessage(
            channel="file_drop",
            sender=f"+97155501{i:02d}",
            sent_at=base + timedelta(hours=i),
            text=rec["narrative"],
        )
        cids = await _drive(tenant, msg, blob, llm)
        print(f"  text  {rec['id']} -> {cids}")

    if AUDIO.exists():
        att = InboundAttachment(filename="voice.wav", mime="audio/wav", data=AUDIO.read_bytes())
        msg = InboundMessage(
            channel="whatsapp",
            sender="+9715550199",
            sent_at=base + timedelta(hours=9),
            attachments=(att,),
        )
        cids = await _drive(tenant, msg, blob, llm)
        print(f"  audio voice.wav -> {cids}")

    print(f"TENANT {tenant}")


if __name__ == "__main__":
    asyncio.run(main())
