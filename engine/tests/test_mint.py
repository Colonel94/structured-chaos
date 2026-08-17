"""Head-minting — the emergent-column birth mechanism (remediation, the R2 pivot). DB-backed.

Proves end to end: escape-valve (`other`) facts that form ONE recurring concept across >=
PROMOTE_HEAD_N distinct cases MINT a new head (LLM-named), which registers and joins the tenant's
extraction vocabulary; a cluster below the floor does NOT mint; and a proposed name colliding with a
seed head is rejected (no duplicate columns). Controlled embeddings/LLM so the mechanism is
deterministic (real BGE/Ollama behaviour is a separate real-data spike)."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.extract.head_nouns import compose_name
from app.schema.mint_scan import mint_for_tenant
from app.schema.promote import PROMOTE_HEAD_N
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

_DT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_DIM = 1024


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _vec(cos: float, axis: int = 0) -> list[float]:
    v = [0.0] * _DIM
    v[axis] = cos
    v[(axis + 1) % _DIM] = math.sqrt(max(0.0, 1 - cos * cos))
    return v


class _FakeEmbedder:
    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._m = mapping

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._m[t] for t in texts]


class _NameLLM:
    def __init__(
        self, name: str, gloss: str = "a learned column", protected_category: str = "none"
    ) -> None:
        self._name = name
        self._gloss = gloss
        self._cat = protected_category

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        import json

        return json.dumps(
            {
                "head": self._name,
                "gloss": self._gloss,
                "protected": self._cat != "none",
                "protected_category": self._cat,
            }
        )


def _attest_other(session: Session, *, value: str, case_id: object, head: str = "other") -> None:
    """Record one grounded escape-valve fact and project it into field_current (what minting reads)."""
    name = compose_name(head, None)
    doc = api.add_source_document(
        session,
        case_id=case_id,  # type: ignore[arg-type]
        sha256=_h(f"{case_id}"),
        blob_key=_h(f"{case_id}"),
        mime="text/plain",
        channel="file_drop",
        byte_size=1,
        received_at=_DT,
    )
    api.record_extraction(
        session,
        case_id=case_id,  # type: ignore[arg-type]
        field_path=name,
        value=value,
        model="m",
        model_version="m",
        prompt_version="p",
        run_id=uuid4(),
        confidence=0.5,
        citations=[api.Citation(source_document_id=doc, role="primary")],
        layer="emergent",
    )
    api.register_emergent_field(session, field_name=name, field_name_hash=_h(name), head=head)
    api.register_emergent_head(session, head=head)
    api.rebuild_field_current(session, case_id)  # type: ignore[arg-type]


async def test_recurring_other_cluster_mints_a_new_head(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Mint-Co")
    admin_session.commit()
    citations = [
        "15 U.S.C. 1692c",
        "Fair Debt Collection Practices Act",
        "12 CFR 1006.34",
        "15 USC 1681i",
    ]
    with tenant_session(tenant, factory=app_factory) as s:
        cases = [
            api.create_case(s, channel="file_drop", first_contact_at=_DT)
            for _ in range(PROMOTE_HEAD_N)
        ]
        for c, val in zip(cases, citations, strict=True):
            _attest_other(s, value=val, case_id=c)
        # All citations embed to one cluster (same vector); the LLM names it `regulation`.
        emb = _FakeEmbedder({v: _vec(1.0) for v in citations})
        llm = _NameLLM("regulation", gloss="a cited law, statute, or regulation")
        minted = await mint_for_tenant(s, embedder=emb, llm=llm)

    assert len(minted) == 1
    head, support, affected = minted[0]
    assert head == "regulation"
    assert support == PROMOTE_HEAD_N
    assert len(affected) == PROMOTE_HEAD_N
    with tenant_session(tenant, factory=app_factory) as s:
        assert "regulation" in api.list_minted_heads(s)  # joins the extraction vocabulary
        glosses = api.list_minted_head_glosses(s)  # and carries its gloss for the prompt
        assert glosses["regulation"] == "a cited law, statute, or regulation"


async def test_cluster_below_floor_does_not_mint(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "NoMint-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        cases = [
            api.create_case(s, channel="file_drop", first_contact_at=_DT)
            for _ in range(PROMOTE_HEAD_N - 1)  # one short of the floor
        ]
        vals = [f"15 U.S.C. 169{i}" for i in range(len(cases))]
        for c, val in zip(cases, vals, strict=True):
            _attest_other(s, value=val, case_id=c)
        emb = _FakeEmbedder({v: _vec(1.0) for v in vals})
        minted = await mint_for_tenant(s, embedder=emb, llm=_NameLLM("regulation"))
    assert minted == []  # recurrence below PROMOTE_HEAD_N → stays in `other`
    with tenant_session(tenant, factory=app_factory) as s:
        assert api.list_minted_heads(s) == []


async def test_name_colliding_with_seed_head_is_rejected(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Collide-Co")
    admin_session.commit()
    vals = ["a1 concrete", "b2 concrete", "c3 concrete", "d4 concrete"]
    with tenant_session(tenant, factory=app_factory) as s:
        cases = [
            api.create_case(s, channel="file_drop", first_contact_at=_DT)
            for _ in range(PROMOTE_HEAD_N)
        ]
        for c, val in zip(cases, vals, strict=True):
            _attest_other(s, value=val, case_id=c)
        emb = _FakeEmbedder({v: _vec(1.0) for v in vals})
        # LLM proposes "amount" — an existing SEED head → must be rejected (no duplicate column).
        minted = await mint_for_tenant(s, embedder=emb, llm=_NameLLM("amount"))
    assert minted == []
    with tenant_session(tenant, factory=app_factory) as s:
        assert "amount" not in api.list_minted_heads(s)
