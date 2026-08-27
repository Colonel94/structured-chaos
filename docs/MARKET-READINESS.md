# Market readiness

**Decision as of 27 August 2026 (reviewed revision `10b95cf`):** engineering readiness passes. Controlled-pilot entry is **3/6
clean**. The product can be evaluated with synthetic/redacted data and prepared for one narrow design
partner; real customer data waits for the three remaining pilot-control bundles below.

This decision follows the staged contract in [The Winning Condition](../winning-condition.md). It
replaces the retired 1/6 all-or-nothing score, which incorrectly mixed engineering safety, pilot entry,
general-availability evidence and market reactions.

## What is ready

- Account and workspace creation, secure sessions and server-derived reviewer identity.
- Durable text/file intake with honest processing, failure and worker-readiness states.
- Evidence-linked case review, correction, deterministic SLA/priority, per-case approval and undo.
- Commit-gated PDF/CSV outputs; processing and failed cases cannot be approved.
- Self-serve CSV/JSON object data with exact and guarded fuzzy matching.
- RLS tenant isolation, immutable originals, append-only corrections and idempotent stages.
- Least-privilege authentication functions, tenant-enforced portal origins, formula-safe CSV and bounded
  public uploads.
- Health checks, worker liveness, deployment configuration, backup/restore tooling, incident/deletion
  runbooks and automated security workflows.
- A tested, responsive reviewer experience with explicit loading, empty, unavailable, processing and
  failure states.
- Independent quality evidence from two domain experts over all 200 holdout cases. Human agreement is
  92% category, 91% desired outcome, 94% severity and 83% emotion; this closes the self-grading gap.
- `calib-v3` confidence reliability is fitted from the two-expert consensus; it supports review ordering
  while autonomous routing remains disabled.

## Controlled-pilot scorecard

| Gate | Status | Evidence or action |
|---|---|---|
| Complete complaint workflow | **CLEAN** | Intake → review → correction → approval → report is implemented. |
| Mandatory human control | **CLEAN** | Every consequential output is individually approved; autonomous action remains off. |
| Trust and tenant boundary | **CLEAN** | Provenance, RLS, immutability, idempotency and least-privilege controls exist and are tested. |
| Named pilot governance | **OPEN** | Name the organisation, workflow, channel, volume, dates and owner; approve policy and data terms. |
| Operational evidence | **PARTIAL** | Run the restore/security drills and name monitoring, incident and manual-fallback owners. |
| Operator acceptance | **NOT RUN** | One non-builder operator completes a representative case end to end and records confusion. |

## Required before real customer data

### 1. Named pilot and approved policy

Record the design partner, exact complaint workflow, supported channel, maximum case volume, pilot dates,
success owner and stop conditions. Replace illustrative priority/SLA defaults with an approved,
versioned tenant policy covering categories, escalation, retention and deletion.

### 2. Data and operating authority

Agree controller/processor roles, lawful basis or consent, permitted data types, residency, subprocessors,
retention, deletion requests, breach contact and pilot termination handling. Obtain jurisdiction-specific
legal review; code controls are not legal approval.

Run and timestamp backup/restore and security-release drills. Confirm there is no unaccepted high or
critical security result, secrets can be rotated, and named people own monitoring, incidents, failed
cases, support and the manual fallback.

### 3. Operator acceptance

Have one complaint operator who did not build the feature complete a representative case from intake to
approved output. Documentation and normal onboarding help are allowed. Record time, corrections,
confusion, errors and any point that required engineering intervention. Fix blockers, then sign the pilot
entry record.

## What the pilot must measure

Freeze the continuation targets with the partner before the first case. The defaults are:

- at least 95% of cases process without engineering intervention;
- zero tenant, approval or provenance safety incidents;
- median review time at most 60 seconds and at least 25% faster than the team’s measured manual baseline;
- zero cases exceed the anchor-plus-two question budget;
- zero silent object matches are later found wrong;
- reviewers can locate supporting evidence for every approved case;
- the organisation makes an explicit continue/pay/stop decision.

Also record p90 review time, field corrections, processing latency, abandonment, support load and cost per
case. These are learning signals unless frozen as partner-specific gates before the run.

## Required before broader or self-serve launch

- Independent labelling of the current 200-case holdout is complete. Before GA, confirm that at least
  100 cases represent the chosen launch market and publish the frozen metric definitions and results.
- Validate the workflow with at least two organisations and three operators.
- Complete invitations, membership revocation, password recovery, shared rate limiting, audit export and
  workspace administration.
- Establish central logs, dashboards, backlog/capacity alerts, paging, release/rollback and recurring
  restore evidence.
- Finalise privacy/security buyer materials, pricing, limits, support terms and business continuity.
- Test onboarding without developer intervention and accessibility with keyboard and screen-reader users.
- Do not market “self-converging schema,” cross-domain parity or other experimental claims until their
  representative evidence thresholds pass.

Independent holdout labelling is complete. Current model agreement on the independent-consensus subsets
is 143/185 category (77%), 147/182 desired outcome (81%), 139/188 severity (74%) and 125/166 emotion
(75%). Cold reviewer sessions, chosen-market representativeness, sparse/voice sets and unassisted
onboarding remain GA evidence and pilot-learning tools, not blockers to the first bounded,
human-controlled engagement.

## Market sequence

1. **Pilot preparation:** close the three open Gate B control bundles.
2. **Controlled design-partner pilot:** one customer, one workflow, capped volume, human approval on every
   case and a documented manual fallback.
3. **Continuation decision:** compare measured value against the frozen Gate C targets; extend, pay, stop
   or narrow the product based on evidence.
4. **Repeatability:** close team/operations gaps and validate with a second organisation.
5. **General availability:** proceed only when independent quality, repeatable operations, legal terms,
   pricing and support are ready.

## Go/no-go record

For each release or pilot, record the date, commit, environment, model and policy versions, scope, evidence
links, metric results, open risks, owners, expiry date and decision-maker. Green CI proves engineering
health; the named pilot record authorises real-world use.
