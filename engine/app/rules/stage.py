"""The rules pipeline stage — governed core → deterministic priority/SLA/routing decision (Phase 6, §8).

Chains off extraction (parallel to elicit): the moment a case's governed core is (re-)extracted, this
loads the tenant's policy (its override, else the universal default), evaluates the category/severity/
emotion signals through the pure :func:`app.rules.engine.evaluate`, computes the SLA deadline from
``first_contact_at`` (the clock starts at first contact, not completeness), and writes the disposable
``case_decision`` projection.

No model call — this is deterministic by construction: same inputs + same policy version → the identical
row, every time, explainable in one sentence (the matched rule's rationale). Idempotent on the EXTRACTED
inputs + the policy version (the stage-ledger key), so a replay with unchanged inputs is a no-op and a
re-extraction that changes a signal — or a policy change — recomputes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ..config import settings
from ..obs.logging import get_logger
from ..store import api
from ..store.db import SessionFactory, tenant_session
from .engine import evaluate, evaluated_inputs, load_policy

log = get_logger(__name__)

_STAGE = "rules"


def decide_case(
    tenant_id: str | UUID,
    case_id: UUID,
    *,
    factory: sessionmaker[Session] | None = None,
) -> bool:
    """Compute and persist the deterministic decision for one case. Returns True if a decision was
    (re)computed, False if skipped (case absent, or these inputs+policy were already decided)."""
    with tenant_session(tenant_id, factory=factory or SessionFactory) as session:
        row = api.get_case_decision_inputs(session, case_id)
        if row is None:
            log.info("rules.skip_absent", case_id=str(case_id))
            return False
        first_contact_at, governed = row
        policy = load_policy(api.get_tenant_policy_yaml(session))
        inputs = evaluated_inputs(governed)

        # Idempotent on (inputs snapshot + policy version): unchanged → a replay is a no-op; a
        # re-extraction that moves a signal, or a policy change, yields a new key → recompute.
        material = json.dumps({"inputs": inputs, "policy": policy.version}, sort_keys=True)
        key = api.compute_idempotency_key(
            source_sha256=hashlib.sha256(f"{case_id}\x1f{material}".encode()).hexdigest(),
            stage=_STAGE,
            model_version="-",
            prompt_version=policy.version,
            code_version=settings.code_version,
        )
        if not api.claim_stage(session, stage=_STAGE, idempotency_key=key, case_id=case_id):
            log.info("rules.skip_done", case_id=str(case_id))
            return False

        decision = evaluate(governed, policy)
        due_at = first_contact_at + timedelta(hours=decision.sla_target_hours)
        api.upsert_case_decision(
            session,
            case_id,
            priority=decision.priority,
            routing=decision.routing,
            sla_target_hours=decision.sla_target_hours,
            sla_response_due_at=due_at,
            matched_rule_id=decision.matched_rule_id,
            rationale=decision.rationale,
            policy_version=decision.policy_version,
            inputs=inputs,
        )
        api.complete_stage(session, idempotency_key=key)
        log.info(
            "rules.done",
            case_id=str(case_id),
            priority=decision.priority,
            routing=decision.routing,
            rule=decision.matched_rule_id,
            sla_due_at=due_at.isoformat(),
        )
        return True
