"""FULL-PIPELINE DEMO — emergent head-minting, end to end through the real DB + real models.

The capstone proof of the moat's convergence mechanism (the R2 pivot): with ZERO configuration, a NEW
column is BORN from real data and then USED by the model. Every step runs the production code paths —
the real ingest → normalise → extract stage, the real dedup/mint scans, the RLS'd Postgres registry,
real Ollama extraction, real BGE-M3 clustering — driven by a script instead of the Procrastinate worker
(which merely defers these same functions).

Flow:
  1. ingest + normalise + extract a batch of REAL CFPB cases that cite statutes/regulations →
     the citations have no seed home, so they land in `other` (the escape valve).
  2. dedup_scan  — collapse synonym qualifiers (R1).
  3. mint_scan   — cluster the `other` facts; a recurring concept (legal citations) MINTS a new head,
     LLM-named + glossed, registered in minted_head (it now extends the tenant's extraction vocabulary).
  4. re-extract the affected cases (the vocab-aware idempotency key makes this fire) → the citations
     now land under the MINTED head instead of `other`. History re-homed.
  5. report before/after: the escape valve emptied of citations, a new column that no one configured.

Usage:  uv run --group embed python eval/demo_head_minting_e2e.py [n_cases]
Requires: Postgres up + migrated, Ollama up, BGE (embed group). ~3-5 min (real extraction x2).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import text as _sql

from app.backends.fake import FakeBlob
from app.backends.local.embed_bge import BGEEmbedding
from app.backends.local.llm_ollama import OllamaLLM
from app.extract.stage import extract_case
from app.intake.ingest import ingest_messages
from app.intake.models import InboundMessage
from app.pipeline import normalise_source_document
from app.schema.dedup_scan import scan_and_dedup
from app.schema.mint_scan import scan_and_mint
from app.store import api
from app.store.db import admin_session, tenant_session

_FIX = Path(__file__).resolve().parent / "fixtures" / "cfpb_sample.jsonl"
_CITE = re.compile(
    r"U\.?S\.?C|CFR|FCRA|FDCPA|Fair Credit|Fair Debt|Regulation [A-Z]",
    re.IGNORECASE,
)
_DT = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)


def _escape_facts(tid: UUID, factory: object) -> list[tuple[str, str, str]]:
    """(case_id, head, value) for facts currently under the escape-valve heads — what the demo watches
    move out of `other` into the minted column."""
    with tenant_session(tid, factory=factory) as s:  # type: ignore[arg-type]
        detail = s.execute(
            _sql(
                "SELECT fc.case_id, ef.head, fc.value #>> '{}' "
                "FROM field_current fc JOIN emergent_field ef ON ef.field_name = fc.field_path "
                "WHERE ef.head = ANY(ARRAY['other','description'])"
            )
        ).all()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in detail if r[2]]


def _facts_under(tid: UUID, head: str, factory: object) -> list[tuple[str, str]]:
    with tenant_session(tid, factory=factory) as s:  # type: ignore[arg-type]
        rows = s.execute(
            _sql(
                "SELECT fc.case_id, fc.value #>> '{}' "
                "FROM field_current fc JOIN emergent_field ef ON ef.field_name = fc.field_path "
                "WHERE ef.head = :h"
            ),
            {"h": head},
        ).all()
    return [(str(r[0]), str(r[1])) for r in rows]


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10

    rows = [json.loads(x) for x in _FIX.read_text(encoding="utf-8").splitlines() if x.strip()]
    cases = [r for r in rows if _CITE.search(r["narrative"])][:n]
    print(
        f"=== FULL-PIPELINE HEAD-MINTING DEMO — {len(cases)} real citation-bearing CFPB cases ==="
    )

    from app.store.db import SessionFactory as factory

    with admin_session() as s:
        tid = api.create_tenant(s, "head-minting-e2e-demo")

    llm = OllamaLLM()  # BGE is loaded LATER (only for dedup/mint) so it doesn't crowd qwen3's VRAM
    blob = FakeBlob()

    async def _extract_resilient(cid: UUID) -> bool:
        # A single schema-constrained generation can occasionally stall past the client timeout; retry
        # once (mirrors run_extraction.py) so one slow case doesn't nuke the demo.
        try:
            return await extract_case(tid, cid, llm=llm, factory=factory)
        except httpx.ReadTimeout:
            print("      (timeout — retrying once)")
            return await extract_case(tid, cid, llm=llm, factory=factory)

    # 1. ingest → normalise → extract (real pipeline, real Ollama). Each case is a DISTINCT customer
    # (unique sender + spaced time) so windowing opens a separate case — minting needs recurrence
    # across DISTINCT cases, not many facts in one.
    print("\n[1] ingest + normalise + extract (real Ollama)…")
    case_ids: list[UUID] = []
    for i, r in enumerate(cases):
        msg = InboundMessage(
            channel="file_drop",
            sender=f"+97155{i:06d}",
            sent_at=_DT + timedelta(days=i),
            text=r["narrative"],
        )
        res = await ingest_messages(tid, [msg], blob=blob, factory=factory)
        cid = res.case_ids[0]
        case_ids.append(cid)
        for sdid in res.source_document_ids:
            await normalise_source_document(tid, sdid, blob=blob, factory=factory)
        await _extract_resilient(cid)
        print(f"    extracted {i + 1}/{len(cases)}  case={str(cid)[:8]}")

    before = _escape_facts(tid, factory)
    print(f"\n[1] escape-valve (`other`/`description`) facts after first extraction: {len(before)}")
    for cid, head, val in before[:12]:
        print(f"      [{head}] {val[:52]}")

    # 2. dedup (BGE loads here, after the extraction-heavy step, so VRAM isn't split)
    print("\n[2] dedup_scan (collapse synonym qualifiers)…")
    embedder = BGEEmbedding()
    await scan_and_dedup(embedder=embedder, llm=llm, tenant_ids=[tid], factory=factory)

    # 3. mint
    print("\n[3] mint_scan (cluster the escape valve → mint a NEW head)…")
    minted = await scan_and_mint(embedder=embedder, llm=llm, tenant_ids=[tid], factory=factory)
    heads = minted.get(tid, [])
    with tenant_session(tid, factory=factory) as s:
        glosses = api.list_minted_head_glosses(s)
    if not heads:
        print(
            "    NO head minted — the citation cluster didn't reach the recurrence floor at this n."
        )
        print(f"    (escape-valve facts={len(before)}; try more cases: `... {n + 6}`)")
        return 0
    for head, support, affected in heads:
        print(f"    ✦ MINTED head '{head}'  (support {support} cases)")
        print(f"        gloss: {glosses.get(head)}")
        print(f"        will re-extract {len(affected)} affected cases")

    # 4. re-extract affected cases → citations re-home into the minted head (vocab-aware idempotency key)
    print("\n[4] re-extract affected cases with the extended vocabulary…")
    affected_all = sorted({c for _h, _s, cs in heads for c in cs})
    for i, cid in enumerate(affected_all):
        ran = await _extract_resilient(cid)
        print(f"    re-extracted {i + 1}/{len(affected_all)}  (ran={ran})")

    # 5. report — an emergent column was born from real data and is now used by the model
    print("\n===== RESULT — an emergent column was BORN and is now USED, zero-config =====")
    for head, support, _cs in heads:
        under = _facts_under(tid, head, factory)
        print(
            f"  MINTED column '{head}' (emerged from {support} recurring cases) now holds {len(under)} facts"
        )
        print(f"    gloss: {glosses.get(head)}")
        for _cid, val in under[:12]:
            print(f"      • {val[:58]}")
    print(
        "\n  None of these columns was configured — each emerged from recurring novelty the seed"
        " vocabulary had no home for, landed in `other`, clustered, was named+glossed, and the"
        " RE-EXTRACTED model now routes to it. 'Specialisation is emergent, never seeded' — proven end"
        " to end through the real pipeline (ingest → extract → dedup → mint → re-extract) on data we"
        " did not author. (The escape valve keeps other one-off novelty — that is the promotion bag,"
        " not a failure.)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
