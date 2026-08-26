# Market readiness

**Decision as of 26 August 2026: product experience ready for a controlled design-partner pilot; not
ready for a production launch.** The first-run and reviewer experience is coherent and operational
readiness is visible, but the evidence, identity, legal, and operating gates below remain binding. This
is a product-readiness decision, not a judgment on the amount of implemented code.

## Design hardening completed 26 August 2026

- Added a branded pilot entry experience with a plain-language product promise and four-step workflow.
- Moved tenant UUID plumbing out of the active reviewer header and renamed it as a workspace concept.
- Added client-side workspace-ID validation and a clear route back to switch workspaces.
- Added live API/worker readiness: review remains available while new intake is paused when processing
  is unavailable, preventing users from discovering an outage through a failed submission.
- Replaced blank and ambiguous states with loading, unavailable, empty-queue, and queue-overview states.
- Added visible case counts for attention, ready-to-check, and approved work.
- Improved responsive behavior, focus states, help-dialog semantics, product metadata, and brand identity.
- Added a root start page, user guide, and market-readiness gate so each audience has one clear entry.

## Evidence snapshot

| Area | Status | Evidence / gap |
|---|---|---|
| Core intake and review | Built | Intake, provenance, correction, approval, undo, reports and failed-case handling exist. |
| Tenant isolation and trust controls | Strong PoC evidence | RLS, immutability, idempotency, provenance and commit-gate tests exist. CI forces DB-backed tests. |
| Accuracy | Failing ship gate | Current tracker: category 77% vs 90%; zero-edit 28% vs 70%; desired outcome 56% vs 90%; severity 83% vs 95%. |
| Evaluation validity | Blocked | Labels are self-authored; an independent 60–80 case held-out slice is still required. |
| Review efficiency | Unmeasured | Review time is instrumented but the ≤30-second human median has not been run. |
| Schema convergence | Failing / unproven | Duplicate/synonym fields are 7.6% vs <5%; the new-field curve is not declining on real customer data. |
| Onboarding | Guided pilot only | A branded access screen validates the workspace ID and explains the workflow, but there is no account, invite, session or role experience. |
| External usability | Not run | The three-stranger, no-walkthrough test is still outstanding. |
| Deployment safety | Partial | TLS, secret checks, worker liveness and backup instructions exist; restore drills and full observability evidence do not. |
| Commercial/legal operations | Missing | No approved privacy notice, DPA, terms, retention schedule, support policy, incident process, pricing or buyer pack is present. |

## P0 — required before any real-customer pilot

1. **Independent truth set.** Have a non-owner label 60–80 blind cases. Lock the set, scorer version and
   acceptance criteria before tuning. Re-run all ship metrics and publish the signed result.
2. **Human review-time test.** Run at least three cold reviewers through representative cases. Record
   median and p90 review time, error rate, help requests, and abandonment. The committed median gate is
   ≤30 seconds.
3. **No-walkthrough onboarding test.** Give three strangers the product and their own messy input. Do not
   explain the UI. Capture time to first value, points of confusion, and whether they can complete intake,
   review, approval, and report.
4. **Authentication and authorisation.** Replace pilot workspace-ID access and free-text reviewer identity with
   authenticated sessions, workspace membership, reviewer/admin roles, logout, expiry, invite/revoke,
   and server-side audit identity. Header possession is not production authentication.
5. **Tenant policy sign-off.** Replace `assets/policy/default_policy.yaml` placeholder priority/SLA values
   with an explicit per-tenant policy that has an owner, version, approval date and rollback path.
6. **Data protection pack.** Define data controller/processor roles, purpose, subprocessors, residency,
   retention/deletion, data-subject requests, breach handling, and whether model inputs leave the tenant’s
   chosen boundary. Obtain jurisdiction-specific legal review rather than inferring compliance from code.
7. **Operational recovery.** Perform and timestamp a restore drill for Postgres and object storage; set
   RPO/RTO; verify worker restart, orphan reaping, failed-case handling and expired portal links.
8. **Production observability.** Add central error reporting, structured-log collection, latency/error/job
   backlog dashboards, storage/capacity alerts and paging ownership. `/health` alone is insufficient.
9. **Security release gate.** Threat-model portal, uploads, webhooks and reviewer API; test file validation,
   rate limits, tenant boundary, signed-link leakage, secrets rotation and dependency vulnerabilities.
10. **Support fallback.** Name the person/process that handles a failed case, bad extraction, outage,
    deletion request and customer escalation during the pilot. Publish response targets.

## P1 — required before a paid or wider launch

- Meet the committed accuracy and convergence thresholds on independent, representative customer data.
- Remove the long inline-processing wait through background intake with honest progress and retry state.
- Build a customer/workspace admin flow: organisation creation, invite, data connection, policy setup,
  reviewer management and audit export.
- Pin and routinely scan deployable images; avoid mutable `latest` tags in a release manifest.
- Add versioned release notes, migration/rollback procedure, staging promotion and a tested upgrade path.
- Define packaging, pricing, service limits, onboarding promise, support tier and pilot-to-paid conversion.
- Produce buyer-facing security, privacy, architecture, data-flow and business-continuity summaries.
- Establish product analytics for activation, time to first case, review effort, correction rate, failure
  rate, retention and cost per processed case.
- Test accessibility with keyboard-only and screen-reader users, not only responsive screenshots.

## Suggested market sequence

### Stage 1 — evidence sprint (1–2 weeks)

Run independent labelling, timed reviewer sessions and three-stranger onboarding. Freeze new feature work
unless it removes a failure observed in those tests. Exit only with a written scorecard and prioritised
usability findings.

### Stage 2 — design-partner hardening (2–4 weeks)

Implement authentication, approved tenant policy, privacy/retention controls, monitoring and restore
evidence. Select one narrow vertical and one intake path. Do not promise the six-vertical addressable
market as shipped capability.

### Stage 3 — controlled pilot

Use one named customer, a capped case volume, no autonomous routing, human approval on every case, and a
documented manual fallback. Review metrics and incidents weekly. Define stop conditions before launch.

### Stage 4 — paid launch

Proceed only when independent quality gates pass, onboarding works without the builder present, security
and legal sign-offs are recorded, operations meet the agreed service level, and a buyer can understand
scope, price, limits and support without reading internal engineering documents.

## Go/no-go record

For each release candidate, record: date, commit, environment, evidence links, metric results, open risks,
risk owner, expiry date, and the person who made the go/no-go decision. A green CI run is necessary but
is not a market-readiness approval.
