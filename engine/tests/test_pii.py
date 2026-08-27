"""R5 — the PII / sensitivity gate. Unit (the deterministic classifier) + integration (a protected
cluster is recorded but BARRED from the extraction vocabulary; a sensitive qualifier does not promote).
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.extract.head_nouns import HEAD_NOUNS, compose_name
from app.schema import pii
from app.schema.mint_scan import mint_for_tenant
from app.schema.promote import PROMOTE_HEAD_N, PROMOTE_QUALIFIER_M, promote
from app.store import api
from app.store.db import tenant_session

_DT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_DIM = 1024


def test_classifier_flags_protected_and_spares_every_seed_head() -> None:
    assert pii.classify_sensitivity("diagnosis") == "health"
    assert pii.classify_sensitivity("ssn") == "government_id"
    assert pii.classify_sensitivity("card_number") == "payment_card"
    assert pii.classify_sensitivity("fingerprint") == "biometric"
    assert pii.classify_sensitivity("password") == "credentials"
    assert pii.classify_sensitivity("account", ["123-45-6789"]) == "government_id"  # SSN in a value
    assert (
        pii.classify_sensitivity("payment", ["4111 1111 1111 1111"]) == "payment_card"
    )  # Luhn card
    # A long NON-card number (fails Luhn) is not a card.
    assert pii.classify_sensitivity("identifier", ["1234567890123"]) == pii.NONE
    # No seed head is ever mis-flagged (that would break the universal vocabulary).
    assert [h for h in HEAD_NOUNS if pii.classify_sensitivity(h) != pii.NONE] == []


# ---- integration (DB-backed) ----
pytestmark_note = "the two tests below need the pg fixture"


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


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


class _NameLLM:
    def __init__(self, name: str, protected_category: str = "none") -> None:
        self._name = name
        self._cat = protected_category

    async def complete(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        import json

        return json.dumps(
            {
                "head": self._name,
                "gloss": "g",
                "protected": self._cat != "none",
                "protected_category": self._cat,
            }
        )


def _attest_other(session: Session, *, value: str, case_id: object) -> None:
    name = compose_name("other", None)
    doc = api.add_source_document(
        session,
        case_id=case_id,  # type: ignore[arg-type]
        sha256=_h(str(case_id)),
        blob_key=_h(str(case_id)),
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
    api.register_emergent_field(session, field_name=name, field_name_hash=_h(name), head="other")
    api.register_emergent_head(session, head="other")
    api.rebuild_field_current(session, case_id)  # type: ignore[arg-type]


@pytest.mark.usefixtures("pg")
async def test_protected_cluster_is_recorded_but_barred_from_vocabulary(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "PII-Mint-Co")
    admin_session.commit()
    vals = [
        "condition A concrete",
        "condition B concrete",
        "condition C detail",
        "condition D detail",
    ]
    with tenant_session(tenant, factory=app_factory) as s:
        cases = [
            api.create_case(s, channel="file_drop", first_contact_at=_DT)
            for _ in range(PROMOTE_HEAD_N)
        ]
        for c, v in zip(cases, vals, strict=True):
            _attest_other(s, value=v, case_id=c)
        emb = _FakeEmbedder({v: _vec(1.0) for v in vals})
        # The LLM names it `diagnosis` (deterministic health hit) — must NOT enter the vocabulary.
        minted = await mint_for_tenant(s, embedder=emb, llm=_NameLLM("diagnosis", "health"))

    assert minted == []  # blocked → not returned as a usable minted head
    with tenant_session(tenant, factory=app_factory) as s:
        assert "diagnosis" not in api.list_minted_heads(
            s
        )  # excluded from the extraction vocabulary
        detail = {d[0]: d[3] for d in api.list_minted_heads_detail(s)}  # (head → sensitivity)
        assert detail.get("diagnosis") == "health"  # but RECORDED with its sensitivity (audit)


@pytest.mark.usefixtures("pg")
async def test_sensitive_qualifier_does_not_promote(
    admin_session: Session, app_factory: sessionmaker[Session]
) -> None:
    tenant = api.create_tenant(admin_session, "PII-Promote-Co")
    admin_session.commit()
    with tenant_session(tenant, factory=app_factory) as s:
        cases = [
            api.create_case(s, channel="file_drop", first_contact_at=_DT)
            for _ in range(PROMOTE_QUALIFIER_M)
        ]
        # A `ssn_identifier` qualifier recurs enough to split — but it's protected → must not promote.
        for c in cases:
            name = compose_name("identifier", "ssn")
            doc = api.add_source_document(
                s,
                case_id=c,
                sha256=_h(str(c)),
                blob_key=_h(str(c)),
                mime="text/plain",
                channel="file_drop",
                byte_size=1,
                received_at=_DT,
            )
            api.record_extraction(
                s,
                case_id=c,
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
            api.register_emergent_field(
                s, field_name=name, field_name_hash=_h(name), head="identifier"
            )
            api.register_emergent_head(s, head="identifier")
        concepts = promote(s)

    variants = {c.concept_key for c in concepts if c.kind == "variant"}
    assert "ssn_identifier" not in variants  # protected qualifier barred from the governed layer
