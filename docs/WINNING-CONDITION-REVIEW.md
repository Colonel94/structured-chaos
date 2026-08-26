# Winning-condition review

**Audit date:** 26 August 2026
**Contract:** `winning-condition.md` version 0.2
**Reviewed revision:** `0edfd47`

## Decision

Adaptive Intake is **engineering-ready and suitable for synthetic/redacted evaluation and controlled
pilot preparation**. It is not yet authorised for a real-customer pilot because three pilot-entry
controls require an owner and operating context rather than more speculative product code.

The previous 1/6 score is retired. It combined safety, pilot readiness, general-availability evidence,
and market reactions in a single binary gate. The corrected staged score is:

| Decision | Status |
|---|---|
| Engineering readiness | **PASS** |
| Controlled-pilot entry | **3/6 CLEAN** |
| Paid continuation | **NOT RUN** |
| General availability | **NOT READY** |

## Controlled-pilot scorecard

| Gate | Status | Evidence or remaining action |
|---|---|---|
| Complete complaint workflow | **CLEAN** | Durable intake, processing state, evidence review, correction, per-case approval, undo and reports are implemented. |
| Mandatory human control | **CLEAN** | No autonomous approval; processing/failed cases are locked; batch approval was removed. |
| Trust and tenant boundary | **CLEAN** | RLS, provenance, immutable originals, append-only corrections, idempotency, least-privilege auth, CORS and bounded inputs are implemented and tested. |
| Named pilot governance | **OPEN** | Record one organisation, narrow use case/channel, volume, dates, success owner, approved policy, retention and legal/data terms. |
| Operational evidence | **PARTIAL** | Health, worker liveness, backup/restore tooling, security workflows and runbooks exist. Run and timestamp restore/security drills; name monitoring and fallback owners. |
| Operator acceptance | **NOT RUN** | One non-builder operator must complete a representative case end to end and record confusion. Coaching/documentation are allowed at pilot entry. |

## What changed—and what did not

Independent labels, timed reviewers, representative sparse/voice sets, multi-user administration and
external usability remain important. They now support pilot learning, paid continuation and general
availability instead of blocking the first bounded learning engagement.

The following remain hard blockers for any real data:

- tenant-isolation or authentication failure;
- missing provenance or lost originals;
- approval bypass or autonomous consequential action;
- unapproved SLA/priority policy;
- no lawful data basis, retention/deletion route, recovery plan or named incident owner.

The current self-authored metrics remain diagnostic, not erased: category 77%, zero-edit 28%, desired
outcome 56%, duplicate/synonym fields 7.6%, and a flat new-field curve. They prevent broad accuracy or
“self-converging schema” marketing claims. They do not prove that a mandatory-human-review draft cannot
save time in a controlled pilot; Gate C measures that directly against the customer’s manual baseline.

## Next actions

1. Name one design partner, one complaint workflow, one intake channel and a capped case volume.
2. Approve that tenant’s category/SLA/escalation and data-retention policy.
3. Record the data basis, residency, subprocessors, deletion route, pilot owner and incident contact.
4. Run the restore and security release drills; assign monitoring and manual-fallback ownership.
5. Run one non-builder operator acceptance case.
6. Start the bounded pilot with human approval on every case and measure the Gate C continuation targets.

## Evidence index

- Acceptance contract: `winning-condition.md`
- Market and operating controls: `docs/MARKET-READINESS.md`
- Evidence procedures: `docs/EVIDENCE-RUNBOOK.md`
- Reviewer workflow: `docs/USER-GUIDE.md`
- Deployment and recovery: `docs/DEPLOY.md`, `docs/OPERATIONS-RUNBOOK.md`
- Automated verification: `TEST-PLAN.md`, `engine/tests/`
