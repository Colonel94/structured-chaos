"""Phase 4.3 — dedup mechanism (EDD §6.2 STAGE 3). DB-backed; controlled cosines via a fake embedder
so the τ gate + gray-band adjudication are tested deterministically (no model)."""

from __future__ import annotations

import math

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.schema.dedup import dedup_field
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

_DIM = 1024


def _vec(cos: float) -> list[float]:
    """A unit vector whose cosine with e0=[1,0,...] is ``cos``."""
    v = [0.0] * _DIM
    v[0] = cos
    v[1] = math.sqrt(max(0.0, 1 - cos * cos))
    return v


class _FakeEmbedder:
    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._m = mapping

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._m[t] for t in texts]


class _LLM:
    def __init__(self, same: bool) -> None:
        self._same = same

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return '{"same": true}' if self._same else '{"same": false}'


async def _register_and_dedup(
    tenant: object, factory: sessionmaker[Session], name: str, embedder: object, llm: object
) -> str:
    h = api.compute_idempotency_key(
        source_sha256=name, stage="f", model_version="m", prompt_version="p", code_version="c"
    )
    with tenant_session(tenant, factory=factory) as s:  # type: ignore[arg-type]
        api.register_emergent_field(s, field_name=name, field_name_hash=h)
        canon, _method, _sim = await dedup_field(
            s, field_name=name, field_name_hash=h, llm=llm, embedder=embedder  # type: ignore[arg-type]
        )
    return canon + "|" + h  # canonical|self


async def test_high_similarity_merges_low_admits_gray_adjudicates(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Dedup-Co")
    admin_session.commit()
    emb = _FakeEmbedder(
        {
            "amount one": _vec(1.0),  # seed
            "amount two": _vec(0.90),  # cos 0.90 >= 0.85 -> merge into seed
            "status flag": _vec(0.05),  # cos ~0 < 0.70 -> admit new
            "gray field": _vec(0.78),  # 0.70-0.85 -> LLM decides
        }
    )
    llm_merge = _LLM(same=True)

    r1 = await _register_and_dedup(tenant, app_factory, "amount one", emb, llm_merge)
    r2 = await _register_and_dedup(tenant, app_factory, "amount two", emb, llm_merge)
    r3 = await _register_and_dedup(tenant, app_factory, "status flag", emb, llm_merge)
    r4 = await _register_and_dedup(tenant, app_factory, "gray field", emb, llm_merge)

    c1, self1 = r1.split("|")
    c2, _ = r2.split("|")
    c3, self3 = r3.split("|")
    c4, _ = r4.split("|")
    assert c1 == self1  # seed is its own canonical
    assert c2 == self1  # 0.90 merged into the seed
    assert c3 == self3  # distinct admitted as its own canonical
    assert c4 == self1  # gray band, LLM said same -> merged into the amount canonical

    with tenant_session(tenant, factory=app_factory) as s:
        canon = api.list_canonical_fields(s)
    # Two canonicals survive: the "amount" group (3 aliases) and "status flag".
    assert {name for _h, name, _p in canon} == {"amount one", "status flag"}


async def test_gray_band_llm_split_keeps_them_separate(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "Split-Co")
    admin_session.commit()
    emb = _FakeEmbedder({"amount one": _vec(1.0), "gray field": _vec(0.78)})
    await _register_and_dedup(tenant, app_factory, "amount one", emb, _LLM(same=True))
    await _register_and_dedup(tenant, app_factory, "gray field", emb, _LLM(same=False))
    with tenant_session(tenant, factory=app_factory) as s:
        canon = api.list_canonical_fields(s)
    assert len(canon) == 2  # LLM said different -> not over-merged


async def test_dedup_registry_is_head_scoped_and_idempotent(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """The live qualifier-space pass (remediation R1): synonyms under the SAME head merge; an identical
    embedding under a DIFFERENT head does NOT merge (the closed head is the anchor); re-running is a
    no-op (idempotent). This is the mechanism that turns qualifier sprawl into a converging schema."""
    from app.schema.dedup import dedup_registry

    tenant = api.create_tenant(admin_session, "Registry-Co")
    admin_session.commit()
    # `total_amount` and `total_fee` embed to the SAME vector — but different heads → must NOT merge.
    emb = _FakeEmbedder(
        {
            "total amount": _vec(1.0),
            "totaling amount": _vec(0.90),  # >=0.85, same head=amount -> merge into total_amount
            "owed amount": _vec(0.05),  # <0.70 -> admit new under amount
            "total fee": _vec(1.0),  # identical vector, head=fee -> head-scoped, must seed separately
        }
    )
    variants = [
        ("total_amount", "amount"),
        ("totaling_amount", "amount"),
        ("owed_amount", "amount"),
        ("total_fee", "fee"),
    ]
    with tenant_session(tenant, factory=app_factory) as s:
        for name, head in variants:
            h = api.compute_idempotency_key(
                source_sha256=name, stage="f", model_version="m", prompt_version="p", code_version="c"
            )
            api.register_emergent_field(s, field_name=name, field_name_hash=h, head=head)
        methods = await dedup_registry(s, embedder=emb, llm=_LLM(same=False))  # type: ignore[arg-type]

    # total_amount seeds amount; totaling_amount merges; owed_amount admits new (compared vs the amount
    # canonical, cos low); total_fee seeds fee. 3 canonicals created (2 seed + 1 admit_new), 1 merge.
    assert methods == {"seed": 2, "admit_new": 1, "merge": 1}
    with tenant_session(tenant, factory=app_factory) as s:
        canon = {name for _h, name, _p in api.list_canonical_fields(s)}
        # totaling_amount merged away; total_fee survives DESPITE the identical vector (head anchor).
        assert canon == {"total_amount", "owed_amount", "total_fee"}
        # Idempotent: everything is embedded now, so a second pass finds nothing to do.
        again = await dedup_registry(s, embedder=emb, llm=_LLM(same=False))  # type: ignore[arg-type]
    assert again == {}
