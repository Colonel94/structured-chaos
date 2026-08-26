# Winning-condition review

**Audit date:** 26 August 2026  
**Reviewed revision:** release hardening candidate based on `0acf5bf`
**Decision:** **NO-GO for production launch.** The product is suitable for a controlled design-partner
pilot, but only one of the six ship-scorecard rows is fully clean under the evidence rules in
`winning-condition.md`.

This review distinguishes three different claims:

- **Built:** code and automated tests exist.
- **Measured:** the committed metric was evaluated on an appropriate population.
- **Proven:** the result passed with independent or external evidence where the condition requires it.

Built is not treated as proven. Self-authored labels are not treated as independent truth. A threshold
is not relaxed because the product is otherwise impressive.

## Executive scorecard

| Ship gate | Status | Why it is not clean |
|---|---|---|
| Setup gate (§2) | **PARTIAL / FAIL** | Self-serve account/workspace creation and file upload exist, but signup-to-value has not been timed by a stranger. |
| Seven wow moments (§3) | **PARTIAL** | The mechanisms exist for most moments, but none has passed the required unprompted external observation; Arabic is formally suspended and voice parity is unmeasured. |
| Quantitative thresholds (§4) | **FAIL** | Accuracy and convergence gates miss; several human, sparse-case, discrepancy, voice, and latency rows are unmeasured. |
| Trust gates (§5) | **MET IN CODE** | The automated trust spine is strong. Human speed-to-source still belongs in the external usability run, but no missing code gate was found. |
| No red flags (§7) | **NOT CLEAN** | Accuracy, convergence, external usability, review speed, and no-builder-dependency are not proven. |
| External gate (§8) | **NOT RUN** | No three-stranger, own-data, silent-observer session has been recorded. |

**Ship rule:** all six rows must be clean. Current clean rows: **1/6**. The trust row is technically met,
but it cannot rescue failures elsewhere.

## Section 1 — the one-sentence test

**Status: UNPROVEN.**

The code can ingest unstructured content, create a structured case, resolve objects, elicit missing
information, and present a review queue. The statement requires a stranger, their messiest real case,
correct structure and priority within one minute, plus the inverse four-word case closing in two
questions. Those conditions have not been observed together in an independent session.

Evidence in favour:

- Portal, file intake and WhatsApp paths exist.
- Historical processing was approximately 8–17 seconds; intake is now durable/asynchronous, but the
  message-to-ready interval has not been formally load-tested on the new path.
- The elicitation measurement reports median one drill after anchor and a hard maximum below budget.
- Object resolution produced zero wrong silent binds across 311 measured silent matches.

Missing proof:

- independent correctness;
- a qualifying sparse-case population;
- timed end-to-end stranger use;
- no-help completion.

## Section 2 — plug-and-play setup gate

Every item is binary in the source contract. A partial result therefore leaves the section failed.

| Criterion | Status | Evidence and remaining gap |
|---|---|---|
| Zero configuration to first value | **PARTIAL** | Account creation provisions a private workspace without schema/category configuration or a workspace UUID; the external timed proof is still missing. |
| Under 10 minutes, timed by a new user | **UNMEASURED** | No external timed run exists. |
| No historical data required | **MET IN CODE** | Intake and extraction operate without object-store history; elicitation is the fallback. |
| No per-customer training/tuning | **MET IN DESIGN** | Tenant configuration is policy/data, not model training. Independent use has not tested whether exceptions force manual prompt work. |
| No documentation needed for first case | **UNMEASURED** | The UI now explains the workflow, but only a silent stranger test can pass this item. |
| Builder absent | **NOT RUN** | The external silent-observer session is outstanding. |
| Self-serve object store inside 10 minutes | **PARTIAL** | CSV/JSON/JSONL upload and profiling exist and are tested. Timing is absent and API-key connection is not implemented. |

**Section verdict: FAIL until one timed external setup session passes every item, then repeat with three
strangers for §8.**

## Section 3 — seven wow moments

| Moment | Status | Evidence and remaining gap |
|---|---|---|
| 1. Nothing was typed | **PARTIAL** | Multimodal normalisers and attachment intake exist. A single real nine-message, Gulf-voice, two-photo case has not been externally demonstrated; Arabic is paused. |
| 2. It knew something unconfigured | **BUILT / UNOBSERVED** | Governed plus emergent extraction exists. The required spontaneous user reaction has not been observed. |
| 3. It asked, then already knew | **BUILT / PARTLY MEASURED** | Object-bound confirmation and anchor-plus-two enforcement are tested; WhatsApp median is one question. The four-word stranger test is not recorded. |
| 4. Schema grew visibly | **BUILT / CLAIM FAILING** | Promotion, dedup and backfill code/tests exist. Real-data convergence fails: 7.6% duplicates and a flat new-field curve. |
| 5. It refused to guess | **BUILT / TRIVIAL PASS** | Review routing and amber uncertainty are visible, but the current threshold sends everything to review. This proves abstention safety, not useful calibration. |
| 6. Report already done | **BUILT / UNOBSERVED** | Commit-gated PDF/CSV and provenance exist. The unprompted manager reaction has not been observed. |
| 7. Arabic not a downgrade | **SUSPENDED / UNMEASURED** | Owner formally suspended Arabic and replaced the current parity metric with voice-vs-text parity. The original wow moment cannot be marked passed. |

## Section 4 — quantitative thresholds

Source of current figures: `engine/eval/PHASE8_SCORECARD.md` (21 August snapshot). Accuracy labels were
authored by Claude and are agreement-with-labeller figures, not independent ship evidence.

| Measure | Threshold | Current evidence | Status |
|---|---:|---:|---|
| Governed-core field accuracy | ≥95% | Composite components below gate | **FAIL** |
| Emergent attribute accuracy | ≥85% | No labelled emergent gold | **UNMEASURED** |
| Category accuracy | ≥90% | 77% (167/216) | **FAIL** |
| Auto-routed accuracy | ≥98% | 0 auto-routed cases | **VACUOUS / UNMEASURED** |
| Ambiguous cases flagged | ≥90% | 100%, because all cases route to review | **TRIVIAL PASS** |
| Zero-edit cases | ≥70% | 28% | **FAIL** |
| Matched to object without asking | ≥60% | 52% on a mix constructed with 48% unresolvable | **NOT PROVEN** |
| Silent object-match accuracy | ≥99% | 0 wrong / 311 silent matches | **MET** |
| Discrepancies surfaced | 100% | No labelled discrepancy set | **UNMEASURED** |
| Questions per case, median | ≤2 after anchor | File median 2; WhatsApp median 1; post-anchor drill median 1 | **MET** |
| Asked for already-stated data | 0% | 0/216 | **MET** |
| Asked for anchor-derivable data | ≤5% | 0/216 | **MET** |
| Sparse complaints actionable | ≥80% | No qualifying sparse cases in the 216 set | **UNMEASURED** |
| Elicitation abandonment | ≤20% | No real-customer run | **UNMEASURED** |
| Desired outcome captured | ≥90% | 56% | **FAIL** |
| Median review time | ≤30s | Instrumented and seeded; no human result | **UNMEASURED** |
| Message-to-ready latency | ≤60s | Durable worker path built; historical 8–17s samples, no formal/load result on current path | **PARTIAL** |
| Voice-vs-text parity | within 5 points | No paired voice/text evaluation set | **UNMEASURED** |
| Duplicate/synonym fields | <5% | 7.6% | **FAIL** |
| New-field creation rate | declining | Flat composite curve | **FAIL** |
| Backfill correctness | 100% | Idempotent automated tests; no real-history measurement | **PARTIAL** |

**Section verdict: FAIL.** Four rows are substantively met, one passes only trivially, six fail or miss,
and the remainder are partial or unmeasured. Independent labels may change the accuracy numbers but do
not erase the need to meet the thresholds.

## Section 5 — non-negotiable trust gates

| Trust gate | Status | Repository evidence |
|---|---|---|
| Every field traceable | **MET IN CODE** | Review payload citations plus text, audio-segment and image-region viewers in `ui/src`; provenance route tests. |
| Complete provenance | **MET IN CODE** | Required citation/source constraints, immutable citation tests, extraction metadata surfaced in review. |
| Case exists before questions | **MET** | Intake persists the case before the elicitation stage; ingest and elicitation tests. |
| Clock starts at first contact | **MET** | `test_stage_writes_the_decision_and_clock_runs_from_first_contact`. |
| Anchor plus two enforced in code | **MET** | `test_hard_cap_blocks_even_the_anchor_at_three_questions`; live measurement stays below cap. |
| No external action without approval | **MET** | Commit gate refuses reports before approval; still-processing cases cannot be approved; channel dispatch is explicit and idempotent. |
| Deterministic SLA/priority | **MET** | Rules-stage repeat/idempotency and policy-version tests. |
| Tenant isolation automated | **MET** | Cross-tenant read/write/repoint/unset-context tests using the non-bypass app role. |
| Originals immutable | **MET** | Database triggers/grants plus content-addressed blob verification. |
| Corrections append-only | **MET** | Append-only triggers and correction/commit tests. |
| Pipeline idempotent | **MET** | Stage ledger, ingest, object-store, dispatch, snapshot and backfill idempotency tests. |
| No customer data in logs | **MET** | Nested/list PII-redaction tests. |

**Section verdict: technically clean.** Before production, authentication, security review, restore
evidence and operational monitoring remain market-readiness requirements even though they are not listed
in the original §5 contract.

## Section 6 — allowed omissions

The build stays within the permitted scope: a limited channel set, a register plus report, no native
mobile app, limited integrations and human-gated action. The customer portal is extra, not required.
Manual tenant provisioning is allowed behind the scenes. None of these allowances waives §§2, 3 or 5.

## Section 7 — red-flag audit

**Status: NOT CLEAN.**

Confirmed absent in code/evidence:

- the hard question cap prevents a fourth question;
- already-stated and anchor-derivable questions measured at zero in the current set;
- angry/incomplete cases hand off rather than being interrogated;
- values have source citations;
- cross-tenant access fails closed;
- external reports are commit-gated.

Still present or unproven:

- duplicate/synonym fields exceed the committed limit and the curve is flat;
- review speed versus manual typing is unmeasured;
- own-data, no-explanation behavior is not externally tested;
- accuracy is low enough that “it usually handles that better” remains a material demo risk;
- self-serve identity/workspace creation exists, but team invitation/reset/revocation is incomplete;
- Arabic is suspended, so the original cross-language red flag cannot be declared absent.

## Section 8 — external gate

**Status: NOT RUN.** No evidence records three independent people using their own messy inputs with the
builder silent. Therefore all five external outcomes remain unchecked, including the actual winning
condition: at least one person asking the price before asking for a feature.

## What to do next, in order

1. **Run the staged 20-minute cold reviewer session now.** Record median and p90 time, edits, errors and
   help requests. This is unblocked and determines whether assisted review has value at 28% zero-edit.
2. **Get the 66-case blind holdout independently labelled.** Freeze labels before tuning; publish the
   scorer output and disagreements. Do not tune on this set.
3. **Build a qualifying sparse set of at least 20 cases.** Measure actionable rate, question reuse,
   derivable questions, abandonment and desired-outcome capture.
4. **Use recurring real cases from one narrow vertical to attack convergence.** Demonstrate <5%
   duplicates, a declining new-field curve and 100% backfill on retained originals. Until then, do not
   sell “self-converging schema” as proven.
5. **Create paired voice/text cases.** Measure field-level parity within five points and formalise
   end-to-end latency under representative load.
6. **Close team identity and operations.** Add invitation acceptance, password reset and membership
   revocation to the authenticated workspace; complete privacy, retention, monitoring, restore and support gates from
   `docs/MARKET-READINESS.md`.
7. **Only then run the three-stranger gate.** Use their data, provide no walkthrough, say nothing, and
   record the five outcomes verbatim. Do not count a coached design-partner demo.

## Evidence index

- Contract: `winning-condition.md`
- Threshold snapshot: `engine/eval/PHASE8_SCORECARD.md`
- Build/test claims: `TEST-PLAN.md`, `engine/tests/`
- Live readiness summary: `docs/tracker.html`
- Market/operational gates: `docs/MARKET-READINESS.md`
- Reviewer workflow: `docs/USER-GUIDE.md`
- Product requirements: `PRD.md`
