# CLAUDE.md — Adaptive Intake (working name)

*Operational law for building this product. This file overrides default behaviour and any generic
hedging. It sits on top of the global `~/.claude/CLAUDE.md` and the workspace-root `CLAUDE.md`;
where anything conflicts, the stricter, more specific rule here wins. Read it before you touch code,
and again before you say "done." Companion: `longterm_context.md` (the durable project brain) and
the two source docs `concept-adaptive-intake.md` + `winning-condition.md` (the contract).*

> ## ⏱ SESSION BOOTSTRAP — do this FIRST, every session, especially right after a context clear.
> This file and the memory index auto-load; **the full picture does not.** Before you respond to any
> project work or claim to know "where we are," in this order:
> 1. **Read `longterm_context.md` top-to-bottom.** It is the brain. Its **§0 "Current state & next
>    actions"** is the living status — what's done, what's next, what's locked, what's parked.
> 2. **Skim the doc set it lists** — `PRD.md` → `SOLUTION-EDD.md` → `TECH-SPEC.md` → `BUILD-PLAN.md` →
>    `PREREQUISITES.md`. Five minutes rebuilds the context this conversation took days to build.
> 3. **Absorb how the owner works** (§10 below + the `adaptive-intake` memories): adversarial-review
>    by default, verify-before-load-bearing, no half-work, direct. Match that from message one.
> **Do not guess at state or direction — read §0 first. Guessing is exactly the "missing things" to avoid.**
> **Keep this current:** whenever state changes or before you wrap a work session, **update
> `longterm_context.md` §0** so the next fresh session inherits the truth, not a stale snapshot.

---

## 0. The two directives that sit above everything

### Directive 1 — Build to a seven-figure standard. Failure is not an option.
There is no "good enough for a PoC" escape hatch. A real, discerning buyer will sit down, feed this
their messiest real case with no walkthrough, and decide whether to pay. Every decision is made as
if that person is watching over your shoulder — because in effect they are. "It usually works" is a
failure. A confidently-wrong field is a failure. A demo that only works on prepared sample data is a
failure. Build to the **winning condition**, not to a checklist you can tick while tired.

**On the "1.5M AED" (owner correction, v1.1):** the number is a **scoped seven-figure opportunity that
died before contract** (came through a friend; ended on an RFP change). It sets the *internal quality
bar* — build as if a signed seven-figure deal depends on it — and is *evidence of demand shape*. It is
**never an external claim**: do not present it as a signed deal or live contract; diligence finds no
agreement and the room is lost. If it must be referenced externally, the **only approved phrasing** is:
*"scoped a seven-figure government LLM proposal that didn't proceed after an RFP change."*

### Directive 2 — Every technical gap is closed at $0 budget, and laziness is banned.
When you hit a hard problem — Gulf-Arabic code-switched voice transcription, a schema that must
converge on its own, silent object matching, sub-60-second latency — you do **not** reach for a paid
service and you do **not** punt with "this part is hard / out of scope / needs a vendor." You
engineer a working, free solution that actually delivers the outcome the winning-condition document
demands. Free-and-open-source, local models on the user's RTX 4070 (12 GB), free API tiers, and
clever deterministic engineering are the toolbox. The only spend that is acceptable is metered LLM
API usage measured in cents across the ~100–200 evaluation cases — and even that must be justified
against a local alternative first. "$0 budget" means: **no paid infra, no licences, no per-seat SaaS,
no consultants.** See `longterm_context.md` §"$0 technical strategy" for the concrete stack. If a gap
looks unclosable at $0, that is a signal to think harder, not to downgrade the promise.

**Sequencing (v1.2, owner override 2026-08-10 — supersedes v1.1):** the PoC runs the **LOCAL path on the
RTX 4070** — faster-whisper (ASR) + a quantized instruct model via Ollama (extraction) + BGE-M3
(embeddings) — behind the backend interfaces, **no external call, no API keys, literally $0.** *(This
reverses the earlier v1.1 "single cloud path — Claude Haiku + Cohere API" sequencing; the cloud impls
remain valid behind the same interfaces but are no longer what the PoC builds first.)* Logged
consequence: local extraction quality < Claude Haiku on the hard Gulf/code-switched slice → the
≥95%/≥98% thresholds get harder, measured at the Phase-0.5 spike. The four-interface architecture is
unchanged; only the first-built backend flips to local. Building a paid dependency, or punting a gap,
still violates the rule.

---

## 1. The one-sentence test (the definition of the product)

> A stranger signs up, sends the messiest real case they have, and within a minute sees a complete,
> correctly structured, correctly prioritised case they did not type — and cannot name a field the
> system got wrong. The same stranger sends four useless words, and the system closes the gap in two
> questions without once asking for something it could have looked up.

Everything you build serves that sentence. If a change does not move a metric that serves it, it is
not the job right now.

---

## 2. The three claims we live or die on

The whole product rests on three claims. If any one fails under real data, we fix the design — we do
**not** ship and hope. Treat every one as a first-class, always-measured invariant:

1. **Convergence** — the emergent schema settles instead of sprawling. Duplicate/synonym fields
   `< 5%` after 200 cases; new-field creation rate clearly declining from cases 1–50 to 151–200.
2. **Confidence** — the system refuses to guess. Ambiguous fields are flagged and routed, never
   confidently filled wrong. Confident wrongness destroys trust permanently; visible uncertainty
   builds it. A system that never says "I'm not sure" has already failed.
3. **The two-question drill** — anchor **plus at most two** drills, enforced in code, never left to
   the model. A fourth question, ever, is a red flag. Watch the count, not the rationale.

---

## 3. Non-negotiable engineering invariants (trust gates)

Any single failure here blocks shipping, regardless of how good everything else is. These are not
aspirations; they are the acceptance test. Build them in from the first commit, not retrofitted.

- **Every field is traceable.** Click any value → the exact source: the sentence, the region of the
  image, the moment in the audio. If you can't answer "where did this come from?" in under 5s, fail.
  *(PoC granularity: sentence and image-region are exact; **audio is segment/utterance-level** — cloud
  ASR has no word timestamps — which satisfies "the moment in the audio" at utterance granularity;
  word-level forced-alignment arrives with the local stack, EDD §16.9. This is the accepted PoC reading
  of the gate, not a waiver of it.)*
- **Provenance is complete on every value**: source file, model, model version, prompt version,
  confidence, reviewer, timestamp. No value exists without it.
- **The case exists before the questions do.** Created on first contact in an incomplete state;
  survives the customer never replying again. Never block on completeness.
- **The clock starts at first contact**, not at completeness.
- **The question budget is enforced in code.** Anchor + 2, then hand off. Not the model's judgement.
- **Nothing external happens without human approval.** No report issued, no external record written,
  no notification sent, on model output alone.
- **SLA and priority are deterministic.** Same inputs + same policy → same result, every time,
  explainable in one sentence. Service levels are a rules engine's output, never a model's.
- **Tenant isolation is proven by an automated test** that attempts a cross-tenant read and fails.
- **Originals are immutable.** Every source file retained forever; an extraction never overwrites it.
- **Corrections are preserved, never overwritten.** The correction log is the asset and the eval set.
- **The pipeline is idempotent.** Replay any stage → no duplicate cases, no lost data.
- **No customer data in logs.**

---

## 4. Architecture law

**Locked build decisions (2026-08-09 — do not re-litigate; full rationale in `longterm_context.md`
§10):**
- **Domain-agnostic — "a solution for all," cake store to government.** ONE universal engine, not
  per-industry packs. The governed core is minimal and universal (the object, the fault, the desired
  outcome, SLA/priority/routing inputs, the emotion signal); **no industry-specific field is ever
  configured** — domain specialisation is emergent, never seeded. This is the self-converging-schema
  moat at its strongest; the same empty starting schema serves a bakery and a ministry.
- **Dual deployment, config-switchable.** The engine runs fully local/in-region on the 4070 with **no
  external call**, *and* in cloud/metered mode — chosen by config, never by code change. Every
  inference component (ASR, extraction LLM, embeddings, OCR) has a `local` and a `cloud` backend
  behind one interface. Satisfies UAE PDPL residency and the $0 rule at once. **(v1.2 sequencing, owner
  override 2026-08-10 — supersedes v1.1: the PoC builds the LOCAL impls (faster-whisper + Ollama + BGE-M3
  on the 4070); the CLOUD impls remain behind the same interfaces but are no longer built first. The
  architecture is dual from day one; the cloud path is now the deferred one.)**
- **Both intake channels from the start.** WhatsApp-native + file/email drop. Ingest is
  channel-agnostic; a channel is an adapter producing the same normalised input.
- **Stack: Python headless engine + React/Vite review UI; Postgres + pgvector + RLS.** All $0 / OSS.

- **The engine is headless.** `ingest → structured case + confidence + provenance` is an API. The
  case-management UI is its *first client, not its container*. If extraction logic entangles with the
  app, phase 2 (connectors into other systems of record) becomes a rewrite. Keep them separate from
  commit one.
- **Two-layer schema is sacred.** *Governed core* (small, stable, human-controlled, per category —
  the AI never creates a field here) vs *emergent layer* (unbounded attribute store; anything the
  model attests lands here with no migration). Never let the model write the governed core directly.
- **Promotion, not creation.** A new attribute is a *candidate*, not a field. Closed-world grounding
  (only attributes attested in the source text — never invent a field that "ought" to exist).
  Statistics before semantics (types/cardinality/identifier detection are deterministic; model calls
  are reserved for semantic discovery only). Embed + compare against existing fields; above threshold
  it maps onto the existing field instead of spawning a synonym. Promote to the governed core only
  after recurrence across N distinct cases, then **backfill history** (100% correct, no exceptions).
- **Pipeline stages are independently testable, idempotent, retryable.** `ingest → normalise →
  transcribe/OCR → extract → elicit (only below the actionable floor) → deduplicate → promote →
  structured case → human review → commit → report`.
- **The field registry carries optional external-system mappings from day one.** An emergent schema
  is useless at integration time if it can't translate into someone else's fixed one.

---

## 5. The drill-down is a drill, not a form in chat

- Extract first, ask second. **Never ask for something already stated** (target: 0% of cases — one
  occurrence in a demo loses the room).
- Prefer inference to interrogation. The anchor (order number / phone used to order) is a **key**,
  not a field — everything downstream is looked up, not asked. Asking for something derivable from
  the anchor is the tell of a dumb system (≤ 5%).
- Turn questions into confirmations: don't ask how late — state "delivered 6:42pm against a 5:00pm
  slot," and ask which fault.
- Order questions by information gain. Offer tappable options after narrowing, not an open field.
- Always ask the desired outcome — it is the one fact that can never be inferred.
- When the record contradicts the complaint, **surface it to the agent, never argue with the
  customer.** It is also a fraud/pattern signal over time.
- Emotion is data: an angry customer with an incomplete case is routed to a human, not questioned.
- The fallback path for a complaint with no matching object must degrade to open questions and must
  not fail.

---

## 6. How you work here (process rules)

- **Own the whole job in one pass.** Root cause, side effects, stale state, poisoned data, the guard
  test, and cleanup all count as "the job." No phasing through approvals, no "want me to do the
  obvious next step?" Just do it and report what you did. (See workspace CLAUDE.md.)
- **"Fixed"/"done" means verified live** against the running system and, where UI is involved,
  against actual rendered pixels via the `nabu-ui-test` skill — never a source audit alone.
- **Don't regress.** Preserve working functionality; don't silently rewrite working code or "improve"
  untouched sections. Quietly breaking a prior working state carries an incredibly high cost.
- **Ground every claim in data.** Cite the metric, the timestamp, the source. Distinguish "measured"
  from "assumed" out loud. Verify prices/APIs/docs live at execution time, never from memory.
- **Parallelise discovery with subagents** for broad search/research; read the precision-critical
  sources yourself (verbatim code, schemas, paths).
- **Deliver complete, runnable artifacts**, not fragments. Flag any placeholder explicitly.
- **Evaluation is not optional.** Nothing is "done" until it is scored against the ground-truth set
  (≥ 100 real/realistically-messy cases; ≥ 30 Arabic/code-switched; ≥ 20 too-sparse-to-act). If the
  set doesn't exist yet, building it is part of the job.

### 6a. Phase discipline — regression after EVERY phase (standing rule)
The build runs in phases (`BUILD-PLAN.md`). **After completing any phase, re-run the full test suite of
ALL previous phases — green — before that phase is "done."** Not just the new phase's tests; every
earlier phase must still pass. A later phase that breaks an earlier one is not progress, it is a
regression, and the phase is not complete until the earlier suite is green again.
- The **Phase-1 trust spine** (cross-tenant isolation, provenance, idempotency/replay, no-PII-in-logs)
  re-runs at the end of **every** phase without exception.
- New code passes **`nabu-qa`**; any UI change passes **`nabu-ui-test`** on real pixels — both before the
  phase closes.
- Subagents may run the regression suite (and an adversarial reviewer) in parallel, but the green result
  is verified live, never assumed. See each phase's "Regression gate" in `BUILD-PLAN.md`.

---

## 7. Definition of done — the scorecard (do not fill in optimistically)

Ship only when **all six** are clean:

| Gate | Source |
|---|---|
| Setup gate — every box (zero-config, < 10 min to first value, empty DB, no per-customer tuning, you are not in the room, object store self-serve inside the 10 min) | winning-condition §2 |
| The seven wow moments, each without prompting | winning-condition §3 |
| Quantitative thresholds met on the ground-truth set | winning-condition §4 |
| Trust gates — every box (this file §3) | winning-condition §5 |
| No red flags present | winning-condition §7 |
| External gate: 3 strangers, no walkthrough, complete a case without asking you a question | winning-condition §8 |

**The actual winning condition:** a stranger asks what it costs *before* asking for a feature.

---

## 8. Red flags — if any is true, stop and fix the design

You explain what the tester "should have expected" · the demo only works on prepared sample data ·
you want to say "it usually handles that better" · the tester looks for the form · the bot asks a
fourth question · it asks for something already said or already in the record · elicitation reads
like a survey · an angry incomplete case gets interrogated instead of handed off · synonym fields
keep appearing · you can't trace a value in 5s · the review screen is slower than typing the case ·
it's a different product in Arabic · **anything requires you to touch a DB, config or prompt to make
a customer's case work.** That last one disqualifies the product entirely — it means a service
business wearing a product costume.

---

## 9. Scope discipline for the PoC

**Allowed to be missing at ship** (do not delay for these): dashboards beyond a register + one report;
mobile app;
customer portal; integrations; resolution suggestions; a *learned* drill tree (hand-seeded is fine —
but the budget and the anchor are not optional); polished visuals (a fast review screen is);
behind-the-scenes manual tenant onboarding.

**Never ship without** anything in winning-condition §2 (setup gate), §3 (wow moments) or §5 (trust
gates). Do not ship on the wow moments alone — §4/§5/§7 are what stop it falling apart in week two in
front of the person who was going to pay.

---

## 10. Review & execution discipline — adversarial by default (do not skip)

**Standing correction (learned 2026-08-09, the hard way).** Checking documents against each other is
NOT a review. Consistency-checking catches contradictions and is *structurally blind* to the failures
that actually cost cycles: buried risk, circular self-validation, scope creep, and missing viability
numbers — because a set of docs that all share the same blind spot looks "consistent." Every plan,
spec, prerequisite list, or deliverable gets the adversarial (outside-in) pass below **before** it is
called done. Skip it and the owner becomes the reviewer who finds the holes — which is the failure to
prevent, and the reason for back-and-forth. Run this pass yourself, first.

**The five questions — answer them in writing, up front, for any plan or design:**
1. **Riskiest assumption first.** What is the single most likely-to-be-wrong assumption, and is it
   proven **first**? The three riskiest proofs must not be buried behind everything built on top of
   them. De-risk killers with a one-day throwaway spike (real inputs, zero integration) before building
   upstream of them.
2. **Calendar time vs build time.** What depends on other people or slow external processes — partner
   acquisition, account/identity verification (e.g. Meta Business), consent, data collection,
   procurement? These start on **day zero, in parallel with code**, never scheduled as if instant and
   never inside the phase that consumes them.
3. **No self-grading.** Does any step validate a claim on data or inputs **I authored**? A moat/metric
   "proven" on synthetic cases I generated is the claim grading itself — worthless. Proof runs on data
   I did **not** create; build the scorer and the real ground-truth set early, not last.
4. **Smallest honest test.** What is the minimum that proves the point, and am I exceeding it?
   Generalising before a single real user exists (N verticals, N integrations) manufactures false
   confidence. One case **plus one contrast** to test generalisation — no more until a real user needs it.
5. **Unmeasured viability.** What number decides survival and is currently unmeasured — cost-per-case,
   latency, licence terms, consent/ownership? **Instrument it from the first phase that can**; never
   estimate it and discover the truth at the end.

**Verify before it's load-bearing.** Any citation, arXiv ID, model/library name, licence, price, API
limit, or version a decision rests on is verified **live at the moment it becomes load-bearing** —
resolve the actual source. A plausible-looking identifier is not a source; a hallucinated citation
under the moat is a real risk. Licences change across versions — pin the version, check the licence on
**that** version (this is why whatstk/PyMuPDF were excluded; apply the same check to silero-vad, pywa,
WeasyPrint, and every future dep).

**Never move the goalposts to pass. Redefining a winning-condition metric is an owner decision,
logged.** (Standing rule, learned 2026-08-14 — the second fork where the tempting shortcut was to
move a threshold.) When a pre-committed metric (convergence <5% dup + declining new-field rate; the
anchor+2 question budget; the quantitative thresholds in winning-condition §4; any trust-gate number)
comes back failing, the instinct to *redefine what it measures* — "measure at concept level instead
of field level," "count synonym-pairs instead of field count" — is **self-grading dressed as metric
refinement (§10-Q3).** winning-condition §4 exists precisely so this moment has a pre-committed answer.
So: **fix the system to meet the metric, not the metric to fit the system.** Any proposal to redefine,
re-scope, or relax a winning-condition metric **halts for an explicit owner decision and is logged
with its reason** (a dated block in `longterm_context.md`). A refined metric may still be *reported as
a secondary diagnostic* — but it must be labelled diagnostic-only in code so no later session promotes
it to the pass line by accident. The original metric stays the gate until the owner says otherwise.
*(Worked example, 2026-08-14: convergence failed on real data; the diagnosis found the schema
converges at head-noun altitude but not field-name altitude. Redefining the gate to head-noun count
was rejected as self-grading; the fix is upstream — Path A, constrain extraction granularity — and the
head-noun curve stays a diagnostic. See `longterm_context.md` §0.)*

**When a gate can be satisfied two ways, distrust the one that costs nothing.** (Standing rule, learned
2026-08-14 — the THIRD fork in a row where the cheap path kept the letter of a gate and dropped its
substance.) The pattern is not dishonesty; it is that from inside the code the free option *genuinely
looks equivalent* — which is exactly why it needs the suspicion. Logged instances: (1) measuring
convergence at head-noun altitude instead of full-name (the concept-curve is NOT the gate); (2)
"backfilling" a promoted field by re-running `rebuild_field_current` instead of **re-extracting against
the retained originals** — re-projection only reads back what was already extracted, so it finds nothing
in the cases where the concept was never extracted *because the extractor wasn't looking for it then*,
which are the only cases that matter. The moat is that the schema improves **backwards** over history
(re-extraction against originals), which is the reason originals are retained forever and the thing no
incumbent does. (3) the metric-redefinition fork above. **Rule: when a winning-condition mechanism can
be built cheaply or expensively and the cheap one looks equivalent, that resemblance IS the tell — the
claim almost always requires the expensive one; verify against the source doc and default to it.**
Backfill *re-extracts*; convergence is measured at the *field* level; proof runs on data I did not author.

**Report metrics as a PAIR, and don't mistake small-n zero-error for a gate.** (Owner directive, learned
2026-08-18 on the entity-resolution spike; see memory [[report-metric-pairs-and-n]].) A gain-metric alone
is gameable by abstention — a resolver that refuses on any ambiguity scores 100% *accuracy* / 0% *rate*
and "passes" while making the product worse. So report the **pair** (accuracy **and** coverage/rate,
e.g. silent-match ≥99% *with* ≥60% matched-without-asking) and treat **accuracy-up + rate-down as a
regression, not progress.** And **small-n zero-error is not a high-confidence gate**: rule of three puts
the 95% upper bound on the error rate at ≈3/n (~60% at n=5), so a ≥99% claim needs ~300 clean
observations with zero errors. Report "no failures at n=X (≤~Y% err)", never "100%"; size the test to
the gate before claiming it; a scaled run on a realistic distribution — not a handful of planted cases —
is the real test (it caught a wrong-bind defect n=10 planted cases missed).

**Feedback compounds into rules; the winning condition is the standing motto.** (Owner directive,
2026-08-15.) Every owner review comment is a *durable rule*, not a one-off fix: extract the
generalizable lesson, log it (build-law → this §10; working style → memory
[[feedback-into-rules-winning-condition-motto]]), and check future work against it — **never re-make a
mistake the owner already caught.** And score **every** step against `winning-condition.md` as the motto
(a stranger sends their messiest real case and cannot name a field the system got wrong; they ask what it
costs before asking for a feature). Concretely, the recurring traps already caught — do not repeat: the
cheap path that keeps a gate's letter but drops its substance (see the rule above); an over-charitable
read of a bad result (dig — probe, isolate prompt-vs-capability, read the confusion + planted rows —
don't rationalise); domain footguns in prompts (e.g. "complaint to a higher authority" over-firing on
regulator complaints); measuring on data I authored, or on a sample too small to mean anything.

**Split every "ready"/prerequisite gate** into *blocks starting now* vs *blocks a later phase*. Reading
six papers must never block writing a health endpoint.

**Definition of done for any plan/design:** the five questions + the verify pass have been run and what
they surfaced is stated. "Internally consistent" is **not** "done." State the riskiest remaining
assumption every time.
