"""Phase 4.4 — two-dimensional promotion (Path A, owner constraint #2, 2026-08-14).

DB-backed (testcontainers). Attests emergent facts across distinct cases through the real store, then
asserts: a HEAD promotes at ``PROMOTE_HEAD_N`` (dimension 1); a QUALIFIER variant splits only at the
strictly-harder ``PROMOTE_QUALIFIER_M`` AND under a promoted head (dimension 2); a rare head does not
promote; a qualifier below M does not split even under a promoted head.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.extract.head_nouns import compose_name
from app.schema.dedup import dedup_registry
from app.schema.promote import PROMOTE_HEAD_N, PROMOTE_QUALIFIER_M, promote
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

_DT = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
_DIM = 1024


def _vec(cos: float) -> list[float]:
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
    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return '{"same": false}'


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _attest(session: Session, *, head: str, qualifier: str | None, case_id: object) -> None:
    """Record one grounded emergent attestation for a case, exactly as the extract stage does."""
    name = compose_name(head, qualifier)
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
        value="v",
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


def test_two_dimensional_promotion(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    assert PROMOTE_QUALIFIER_M > PROMOTE_HEAD_N  # dimension 2 is strictly harder
    tenant = api.create_tenant(admin_session, "Promote-Co")
    admin_session.commit()

    with tenant_session(tenant, factory=app_factory) as s:
        cases = [
            api.create_case(s, channel="file_drop", first_contact_at=_DT)
            for _ in range(PROMOTE_QUALIFIER_M)
        ]

        # head "fee" via ONE qualifier "overdraft" across M cases → head promotes AND the qualifier
        # variant "overdraft_fee" splits.
        for c in cases[:PROMOTE_QUALIFIER_M]:
            _attest(s, head="fee", qualifier="overdraft", case_id=c)

        # head "amount" across exactly N cases, but spread over DIFFERENT qualifiers so no single
        # qualifier reaches M → head promotes (dim 1) but no qualifier splits (dim 2).
        amount_quals = ["charged", "refunded", "owed", "disputed"]
        for c, q in zip(cases[:PROMOTE_HEAD_N], amount_quals, strict=True):
            _attest(s, head="amount", qualifier=q, case_id=c)

        # head "rating" in only 2 cases → below N, must NOT promote.
        for c in cases[:2]:
            _attest(s, head="rating", qualifier=None, case_id=c)

        concepts = promote(s)

    heads = {c.head for c in concepts if c.kind == "head"}
    splits = {c.concept_key for c in concepts if c.kind == "variant"}
    assert "fee" in heads  # dim 1: recurring head
    assert "amount" in heads  # dim 1: recurring head across varied qualifiers
    assert "rating" not in heads  # below N → not promoted
    assert "overdraft_fee" in splits  # dim 2: a qualifier at M under a promoted head splits
    # No amount qualifier reached M (each appears once) → none split, even though the head promoted.
    assert not any(c.head == "amount" for c in concepts if c.kind == "variant")
    # The split variant recovers its qualifier for backfill re-extraction.
    overdraft = next(c for c in concepts if c.concept_key == "overdraft_fee")
    assert overdraft.qualifier == "overdraft" and overdraft.is_new is True

    # Idempotent: a second scan promotes the same set, but nothing is NEW (→ no re-backfill).
    with tenant_session(tenant, factory=app_factory) as s:
        concepts2 = promote(s)
    assert {c.head for c in concepts2 if c.kind == "head"} == heads
    assert {c.concept_key for c in concepts2 if c.kind == "variant"} == splits
    assert all(c.is_new is False for c in concepts2)  # already promoted → not re-enqueued


async def test_dedup_prevents_duplicate_promoted_columns(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    """The moat's convergence claim, end to end (remediation R1): two SYNONYM qualifiers
    (``total``/``totaling`` under ``amount``), each attested across enough cases to promote on their
    own, must NOT both promote as duplicate columns — dedup collapses them to one canonical whose
    POOLED support promotes a SINGLE column. Without the dedup pass this would split into two."""
    tenant = api.create_tenant(admin_session, "Dedup-Promote-Co")
    admin_session.commit()

    with tenant_session(tenant, factory=app_factory) as s:
        cases = [
            api.create_case(s, channel="file_drop", first_contact_at=_DT)
            for _ in range(PROMOTE_QUALIFIER_M)
        ]
        # Both synonyms attested across ALL M cases → each ALONE reaches the promotion floor. Pre-dedup
        # that is two duplicate columns; the whole point of R1 is that it becomes one.
        for c in cases:
            _attest(s, head="amount", qualifier="total", case_id=c)
            _attest(s, head="amount", qualifier="totaling", case_id=c)

        # Run the live dedup pass: totaling_amount ~ total_amount (cos 0.9) merges under head=amount.
        emb = _FakeEmbedder({"total amount": _vec(1.0), "totaling amount": _vec(0.90)})
        methods = await dedup_registry(s, embedder=emb, llm=_LLM())  # type: ignore[arg-type]
        assert methods.get("merge") == 1  # exactly one synonym merged away

        concepts = promote(s)

    amount_splits = [c for c in concepts if c.kind == "variant" and c.head == "amount"]
    # ONE column, not two: the canonical total_amount promotes; totaling_amount is an alias, excluded.
    assert len(amount_splits) == 1
    assert amount_splits[0].concept_key == "total_amount"
    assert not any(c.concept_key == "totaling_amount" for c in concepts)
