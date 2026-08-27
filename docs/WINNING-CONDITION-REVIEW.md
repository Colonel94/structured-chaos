# Winning-condition review

**Audit date:** 27 August 2026
**Contract:** `winning-condition.md` version 0.2
**Reviewed revision:** `10b95cf`

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
| General availability | **NOT READY — quality measured, objectives not yet met** |

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

Independent labelling is **complete**: Osman and Catleen each reviewed all 200 holdout cases. Their
pairwise agreement is category **185/200 (92%)**, desired outcome **182/200 (91%)**, severity
**188/200 (94%)**, and emotion **166/200 (83%)**. This closes the self-grading evidence gap; it is not an
open pilot blocker.

The official consensus read scores the model only where both independent reviewers agree, with no
adjudication of disagreements: category **143/185 (77%)**, desired outcome **147/182 (81%)**, severity
**139/188 (74%)**, and emotion **125/166 (75%)**. These results establish a real extractor-quality gap,
but they do not block a bounded pilot in which every case is reviewed and autonomous routing is off.
Representative chosen-market evidence, timed reviewers, sparse/voice sets, multi-user administration
and external usability support pilot learning, paid continuation and general availability.

Confidence calibration has also been refit as `calib-v3` on the two-expert consensus. It remains a
review-ordering reliability estimate; autonomous routing stays disabled.

The following remain hard blockers for any real data:

- tenant-isolation or authentication failure;
- missing provenance or lost originals;
- approval bypass or autonomous consequential action;
- unapproved SLA/priority policy;
- no lawful data basis, retention/deletion route, recovery plan or named incident owner.

The independent consensus metrics replace the old self-authored accuracy headline. They prevent broad
accuracy or autonomous-routing claims at current quality. Duplicate/synonym fields of 7.6% and a flat
new-field curve also keep “self-converging schema” experimental. None proves that a mandatory-human-review
draft cannot save time in a controlled pilot; Gate C measures that directly against the customer's
manual baseline.

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
- Independent pairwise and consensus scoring: `engine/eval/score_holdout.py`
