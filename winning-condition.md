# The Winning Condition

*Staged acceptance criteria for Adaptive Intake.*
*Version 0.2 — owner-authorised correction, 26 August 2026.*

## Why this contract changed

Version 0.1 combined four different questions into one binary gate:

1. Is the system technically safe?
2. Can one organisation use it in a controlled pilot?
3. Is quality proven well enough for a broad launch?
4. Has the market shown buying intent?

Those are not the same decision. Requiring independent benchmark labels, three strangers, every “wow”
reaction, legal sign-off, and mature operations before learning with one bounded design partner prevents
the evidence the product needs. Conversely, passing a demo reaction must never excuse a security or
human-control failure.

The corrected contract uses staged gates. It does not erase failed metrics; it places them at the stage
where they are decision-relevant.

## 1. Product outcome

> **A complaint-handling team can turn messy customer evidence into a traceable case draft, review it
> faster than creating the case manually, and approve it without surrendering human control.**

The product is an assisted complaint-management system. It is not sold as autonomous adjudication,
perfect extraction, or a self-running replacement for complaint staff.

The customer promise is:

- customers can communicate naturally instead of completing a rigid form;
- the system creates a useful draft and shows exactly where each value came from;
- uncertainty and discrepancies remain visible;
- a person corrects and approves the record before a report or operational hand-off;
- corrections become measured improvement signals, not silent overwrites.

## 2. Non-negotiable safety gates

These block every environment that contains real customer data. No pilot scope, disclaimer, or human
evaluation can waive them.

- [x] Every extracted field can be traced to source evidence.
- [x] Originals are immutable and corrections are append-only.
- [x] The case exists and its SLA clock starts at first contact.
- [x] The question budget is enforced in code: anchor plus two, then human hand-off.
- [x] Reports and other consequential outputs require explicit per-case human approval.
- [x] Still-processing and failed cases cannot be approved.
- [x] Priority and SLA decisions are deterministic and explainable.
- [x] Tenant isolation is enforced by RLS and tested using a non-bypass runtime role.
- [x] Authentication secrets and live sessions are not bulk-readable by the runtime role.
- [x] Pipeline stages and outbound actions are idempotent.
- [x] Customer data is redacted from logs.
- [x] Public inputs are origin-, type-, rate-, and size-bounded.
- [x] Tenant deletion removes tenant data and orphaned reviewer identities.

Any regression here is a release blocker.

## 3. Gate A — engineering readiness

Gate A answers: “Is there a coherent product to put into a controlled evaluation?”

- [x] A reviewer can create a workspace and sign in.
- [x] Text and supported files create a durable case without model work inside the HTTP request.
- [x] Processing progress and failure are represented honestly.
- [x] A reviewer can inspect evidence, correct fields, approve, undo briefly, and produce outputs.
- [x] Object data can be uploaded without defining a schema; exact and guarded fuzzy resolution are wired.
- [x] Health checks, worker liveness, migrations, deployment configuration, and security scanning exist.
- [x] Automated backend, frontend, type, lint, build, migration, and browser checks pass for the release.

**Current status: PASS.** Gate A permits synthetic/redacted evaluation and pilot preparation. It is not
permission to process real customer data without Gate B.

## 4. Gate B — controlled design-partner pilot

Gate B answers: “Can one named organisation use this safely within a deliberately narrow envelope?”

| Pilot-entry gate | Status | Definition |
|---|---|---|
| 1. Complete complaint workflow | **CLEAN** | Intake → review → correction → approval → report works end to end. |
| 2. Mandatory human control | **CLEAN** | Every case is reviewed; autonomous approval/action is disabled. |
| 3. Trust and tenant boundary | **CLEAN** | Every non-negotiable control in §2 passes. |
| 4. Named pilot governance | **OPEN** | Scope, business policy and data authority are approved. |
| 5. Operational evidence | **PARTIAL** | Recovery/security drills and operating ownership are complete. |
| 6. Operator acceptance | **NOT RUN** | One non-builder operator completes a representative case. |

Gate 4 requires a named organisation, use case, intake channel, maximum volume, dates and success owner;
an approved/versioned category, priority, SLA, escalation, retention and deletion policy; and agreement on
lawful basis or consent, controller/processor roles, permitted data, residency, subprocessors, breach
contact and deletion.

Gate 5 requires a timestamped backup/restore drill, no unaccepted high/critical security result, tested
secret rotation, a named monitor/incident responder and a rehearsed manual fallback.

Gate 6 requires one operator who did not build the feature to complete a representative case end to end.
Confusion is recorded; it is not necessary to hide documentation or keep the builder silent.

**Pilot score:** three of six top-level gates are clean: product workflow, human control, and trust/data
boundary. The remaining work is pilot-specific governance, operational evidence, and one operator
acceptance run. Independent benchmark labels and three-stranger sessions do not block starting a bounded
pilot; the pilot is how representative evidence is collected.

## 5. Gate C — pilot success and paid continuation

Gate C answers: “Did the product create enough operational value to continue or pay for?” Agree the
numeric targets with the pilot organisation before the first live case. Default targets are:

| Measure | Default continuation target |
|---|---:|
| Cases processed without engineering intervention | ≥95% |
| Confirmed tenant/approval/provenance safety incidents | 0 |
| Median review time | ≤60 seconds and ≥25% faster than that team’s measured manual baseline |
| Cases exceeding the anchor-plus-two budget | 0 |
| Silent object matches later found wrong | 0 |
| Cases where the reviewer can locate supporting evidence | 100% |
| Pilot users who want to continue using the workflow | Named decision, not inferred sentiment |

Measure correction rate, p90 review time, abandonment, processing latency, support load, and cost per case
as diagnostics. They guide prioritisation; they are not retroactively turned into pass/fail gates.

The commercial winning condition is an explicit decision: a signed extension, paid pilot, purchase
process, or documented “no” with reasons. Someone asking the price is useful discovery evidence, not a
software acceptance test.

## 6. Gate D — general availability

Gate D answers: “Can the product be offered repeatedly without founder-dependent operation?” Before a
broad or self-serve launch:

- independent evaluation covers at least 100 representative cases from the chosen market;
- governed-field, category, ambiguity, desired-outcome, voice/text, object-match, and question-reuse
  claims have frozen definitions and published results;
- at least two organisations and three operators have completed representative workflows;
- invitation, membership revocation, password recovery, shared rate limiting, audit export, and workspace
  administration are complete;
- central monitoring, capacity alerts, restore evidence, release/rollback, support ownership, privacy
  terms, pricing, limits, and buyer documentation are operational;
- onboarding succeeds without developer intervention for the supported deployment model.

Recommended GA quality objectives—not pilot-entry gates—are:

| Measure | GA objective |
|---|---:|
| Governed-field accuracy | ≥90% on independently labelled, representative data |
| Category accuracy | ≥90% |
| Ambiguous cases correctly flagged | ≥90% |
| Stated desired outcome captured correctly | ≥95% |
| Silent object-match accuracy | ≥99% |
| Asked for already-stated information | 0% |
| Questions after anchor, median | ≤2 |
| Median review time | ≤30 seconds or ≥50% faster than the customer baseline |
| Message-to-ready latency | p95 ≤60 seconds for the supported workload |

Zero-edit rate is reported, but it is not the product’s primary success metric: a human-reviewed draft can
be valuable even when corrected. Auto-route accuracy is not a launch metric while autonomous routing is
disabled.

## 7. Experimental claims

Schema emergence, automatic promotion/backfill, cross-domain generality, voice parity, and fuzzy object
resolution remain valuable differentiators. They must be demonstrated before being sold as claims, but
they do not block a narrow human-reviewed pilot whose contract does not promise them.

In particular, “self-converging schema” may be marketed only after representative recurring data shows
fewer than 5% duplicate/synonym promoted fields and a declining new-field curve after 200 cases. Until
then, describe the capability as captured emergent attributes with human-gated promotion.

## 8. Stop conditions

Pause intake and return to manual handling when any of these occurs:

- a cross-tenant access, approval-bypass, lost-original, or untraceable-output incident;
- repeated processing failure without an honest visible hand-off;
- a policy/SLA decision cannot be explained or is using an unapproved default;
- the pilot exceeds its agreed data types, channel, volume, support capacity, or residency boundary;
- reviewers are approving without checking evidence, or the workflow is slower than their baseline with
  no compensating quality benefit;
- the customer asks for autonomous action before the evidence supports it.

## 9. Current scorecard

| Decision | Status | Meaning |
|---|---|---|
| Engineering readiness (Gate A) | **PASS** | The coherent, human-controlled product and testable deployment path exist. |
| Controlled-pilot entry (Gate B) | **3/6 CLEAN** | Code gates pass; governance, operational proof, and an operator acceptance run remain. |
| Paid continuation (Gate C) | **NOT RUN** | Must be measured with the first named design partner. |
| General availability (Gate D) | **NOT READY** | Independent quality, multi-user operations, and repeatable commercial delivery remain. |

The next correct move is not more speculative feature breadth. It is to name a narrow pilot, close its
three entry controls, run it with mandatory human approval, and let real correction/time/value evidence
decide the roadmap.
