"""Phase 4.4 — two-dimensional promotion (Path A, owner constraint #2, 2026-08-14).

DB-backed (testcontainers). Attests emergent facts across distinct cases through the real store, then
asserts: a HEAD promotes at ``PROMOTE_HEAD_N`` (dimension 1); a QUALIFIER variant splits only at the
strictly-harder ``PROMOTE_QUALIFIER_M`` AND under a promoted head (dimension 2); a rare head does not
promote; a qualifier below M does not split even under a promoted head.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.extract.head_nouns import compose_name
from app.schema.promote import PROMOTE_HEAD_N, PROMOTE_QUALIFIER_M, promote
from app.store import api
from app.store.db import tenant_session

pytestmark = pytest.mark.usefixtures("pg")

_DT = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


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

        heads, quals = promote(s)

    promoted_heads = {h for h, _s in heads}
    split_names = {name for name, _head, _s in quals}
    assert "fee" in promoted_heads  # dim 1: recurring head
    assert "amount" in promoted_heads  # dim 1: recurring head across varied qualifiers
    assert "rating" not in promoted_heads  # below N → not promoted
    assert "overdraft_fee" in split_names  # dim 2: a qualifier at M under a promoted head splits
    # No amount qualifier reached M (each appears once) → none split, even though the head promoted.
    assert not any(head == "amount" for _n, head, _s in quals)

    # Idempotent: a second run promotes nothing new and does not error.
    with tenant_session(tenant, factory=app_factory) as s:
        heads2, quals2 = promote(s)
    assert {h for h, _s in heads2} == promoted_heads
    assert {n for n, _h, _s in quals2} == split_names
