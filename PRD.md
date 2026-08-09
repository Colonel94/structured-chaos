# Product Requirements Document — Adaptive Intake

*The WHAT and the WHY. Pairs with `SOLUTION-EDD.md` (the HOW). Contract of record:
`winning-condition.md` (the ship gate) + `concept-adaptive-intake.md` (the concept). Governed by
`CLAUDE.md`; context in `longterm_context.md`.*

*Version 1.1 — 2026-08-09. PoC / Phase 1 scope. v1.1 adds FR-13/14/15 and open decisions 6–8 from the
review pass comparing v1.0 to the concept + winning condition.*

---

## 1. Product in one sentence

> The customer gives zero structure; the fulfiller receives complete structure; the system pays the
> entire cost of the translation.

A domain-agnostic complaint-intake engine — *a solution for all*, from a cake store to a government —
that turns messy, multilingual, multimodal complaint input into a complete, prioritised,
fully-traceable structured case with **no form, no category picker, no type selector**, and drills
**anchor + at most two questions** only when the input is too sparse to act on.

**Stakes:** build to a **seven-figure standard**, failure is not an option (the "1.5M AED" is a scoped
opportunity that ended on an RFP change — an internal quality bar and demand-shape evidence, **never an
external claim of a signed deal**; see `CLAUDE.md` Directive 1). **Build budget:** $0.

---

## 2. Problem & why now

Structured forms are abandoned or filled with garbage; free text collapses reporting; mandating fields
produces `N/A`, `.`, `asdf` — compliant-looking garbage everyone knows is worthless. The insight:
**structure should be derived, not demanded.** Modern LLMs can read a messy nine-message thread with a
voice note and two photos and produce the case — a capability that didn't exist when today's
form-ending systems were designed. Remove the form and the trade-off disappears; the interaction
becomes a **drill-down** that asks only for what it couldn't work out, only when it can't act, never
for something already said.

## 3. Users

- **End customer** — sends what they were going to send anyway (WhatsApp thread, voice note, photos,
  forwarded email/PDF). Never sees a form. Answers at most an anchor + two tappable questions.
- **Fulfiller / agent** — stops transcribing, starts resolving. Lives in the review screen: verifies a
  pre-structured case in < 30s, sees low-confidence fields first, every value traceable to its source.
- **Manager (the signer)** — gets **100% field completion with zero mandatory fields**, in a report
  where every value is traceable and provenanced.
- **Tenant admin** — connects the object store (file upload or API key) and supplies written policy
  (SLA/priority/escalation) in the 10-minute self-serve setup. No consultant, no integration project.

## 4. The two moats (what we sell; everything else is table stakes)

1. **A schema that converges on its own** — promotes recurring attributes, deduplicates synonyms,
   backfills history. Unbuilt commercially.
2. **Voice-first Gulf-Arabic, WhatsApp-native intake.** Underserved by every incumbent (Western,
   web-form-first, English-first).

Defensibility is the **correction log + promoted-field registry + external mappings** — never the
extraction. **Never pitch "we replace forms with a conversation"** (funded competitors already do).

*Regulator-shaped / regulated-artefact reporting is **PARKED by owner** — out of scope, not to be
discussed until re-raised (`_parked/regulator-shaped-output.md`). Focus: the industries in §4a.*

## 4a. Target industries — non-regulated service/delivery (v1.1 focus)
One universal engine, six verticals, four object archetypes. The **anchor is the same everywhere — the
sender's phone number** resolves to that tenant's object; only the *object* changes, which is exactly
the domain-agnostic proof. The governed core stays minimal/universal; each vertical's specifics land in
the emergent layer and converge (the moat, shown live).

| Industry | Object (anchor→) | Typical complaints | Example emergent fields |
|---|---|---|---|
| **F&B / bakery** *(headline demo)* | order (order #/phone) | wrong/missing item, late, quality/freshness, allergen | flavour, delivery_slot, driver, temp_on_arrival |
| **E-commerce / retail delivery** | order / shipment (order #/tracking/phone) | damaged, wrong item, not delivered, refund/return | sku, courier, tracking_no, packaging_condition, refund_method |
| **Home maintenance / facilities** *(headline demo)* | job visit / work order (job #/phone/unit) | no-show, poor workmanship, recurring fault, overcharge | technician, trade, parts_used, warranty_status, unit_no |
| **Automotive service / garages** | service job / vehicle (job #/plate/VIN) | fault not fixed, overcharge, delay, damage in service | plate, make_model, mileage, parts, symptom |
| **Hospitality (hotel / F&B dine-in)** | booking / stay (booking ref/room/phone) | room not ready, cleanliness, billing, service, noise | room_no, stay_dates, channel, loyalty_tier, area |
| **Salon / spa / fitness** | appointment / membership (appt id/phone) | no-show/cancellation, service quality, staff conduct, billing | service_type, staff, appt_time, membership_plan |

**Scope (v1.2, owner review):** this table is the **addressable market**, not the build list. The PoC
**builds and evaluates TWO** — bakery (order) + home maintenance (job-visit) — which is enough to prove
the object model generalises (order-shaped vs visit-shaped). The other four are added **when a real
customer needs one**, not as synthetic dev data — six synthetic verticals would only *manufacture* the
look of a proven moat. Convergence is graded on **real collected cases, never on cases we authored**.

## 5. Scope

### 5.1 In scope (Phase 1 PoC — one universal engine, cloud path only)
Intake (WhatsApp + file/email drop) · zero-shot extraction to a structured case · two-layer schema
(governed core + emergent) with embedding dedup, recurrence promotion, and retroactive backfill ·
drill-down elicitation (anchor + 2, enforced in code) · deterministic priority/SLA/routing rules
engine · per-value provenance · keyboard-driven review screen · one queue · one SLA clock · one
generated manager report (a **universal register**). Headline demos = bakery (order) + home maintenance
(job-visit); the eval set spans all **six §4a verticals / four object archetypes** to prove
domain-agnosticism. **Runs on the cloud path only (EDD §16.9)** — the four backend interfaces exist with
cloud impls + local stubs; the local build waits for clinic #1.

### 5.1a Explicitly deferred to a later milestone (clinic customer #1)
The four **local backend implementations** (Qwen3-14B/Ollama, self-hosted Cohere + word-level
forced-alignment, MinIO object-lock) · the **strict PHI-at-promotion gate** · a **separate local-stack
eval bar + run** · the **on-prem test-matrix target**. Not the PoC — a large architecture tax for a
segment (health) that is the opposite end of the market from the bakery/home-maintenance PoC.

### 5.2 Out of scope (deliberately, per winning-condition §6)
Dashboards beyond a register + one report · mobile app · customer portal · integrations with other
systems · resolution suggestions/automation · a *learned* drill tree (hand-seeded is fine; the budget
and anchor are not optional) · polished visuals (a fast review screen is required). Manual
behind-the-scenes tenant onboarding is acceptable. **Phase 2** = connectors into existing systems of
record; **Phase 3** = resolution intelligence from accumulated history.

---

## 6. Functional requirements

**FR-1 Zero-config first value.** Account → fully structured case with no settings touched, no schema
defined, no category list built. < 10 min signup→first processed case, empty DB, no per-customer
training. Object store connectable self-serve (file upload or API key) inside the 10 min.

**FR-2 Multimodal, multilingual intake.** Accept WhatsApp text/voice/image/PDF and file/email drops;
transcribe Gulf-Arabic + code-switched voice; OCR images/PDFs. Original input immutable and retained.

**FR-3 Zero-shot extraction.** From the mess, produce a structured case (governed-core fields +
emergent attributes) with no cold start, on the first case, on an empty schema.

**FR-4 Emergent schema + promotion + backfill.** New attested attributes land in the emergent layer
immediately; recurring ones (≥ N distinct cases) promote into the governed core, acquire type/unit/
validation, and **backfill history 100% correctly**. Synonyms dedupe before storage (< 5% duplicates
after 200 cases). New-field creation rate declines over time.

**FR-5 Drill-down elicitation.** When below the actionable floor: one anchor (order#/phone = a key),
then ≤ 2 drills, turning lookups into confirmations, always capturing desired outcome. **Budget
enforced in code.** Never ask for something already said (0%) or derivable from the anchor (≤ 5%).
Case created immediately in incomplete state; never blocked on completeness; angry + incomplete →
routed to a human.

**FR-6 Deterministic priority/SLA/routing.** From the tenant's written policy; reproducible,
explainable in one sentence; never model output. Clock starts at first contact.

**FR-7 Refuse to guess.** Ambiguous fields flagged low-confidence and routed for review, never
confidently filled wrong. Discrepancies between complaint and record surfaced to the agent (100%),
never argued with the customer.

**FR-8 Provenance & traceability.** Every value → exact source (sentence / image region / audio
moment) in < 5s, carrying source/model/model-version/prompt-version/confidence/reviewer/timestamp.
*(PoC: sentence + image-region exact; audio at segment/utterance granularity — word-level deferred with
the local stack, EDD §16.9.)*

**FR-9 Review screen.** Source vs fields, low-confidence first, keyboard-driven, < 30s/case.
Corrections stored append-only against the original extraction, never overwritten.

**FR-10 One manager report.** Every field populated, every value traceable, no mandatory field ever
imposed. Nothing external (report/record/notification) emitted without human approval.

**FR-11 Multi-tenant.** Tenant isolation proven by an automated cross-tenant-read-fails test.

**FR-12 Dual-deployment *architecture* (interfaces now, local built at clinic #1).** (Refined v1.1; EDD
§16.9.) The four backend interfaces (ASR/LLM/embeddings/blob) ship from day one so a tenant *can* run
fully-local/in-region (no external call) or cloud, switchable by config. **The PoC builds only the
cloud implementations; the local implementations ship as stubs and are built when a clinic is customer
#1** — the module hedge is kept, the local architecture tax is deferred to the segment that needs it.

**FR-13 Object store & entity resolution.** (Closes review gap G3/G4; EDD §16.1.) Tenant connects an
arbitrary-schema object store self-serve (upload or read-only API key) inside setup. The engine infers
its schema (no config), matches a complaint to its object silently only when the match is unique
(≥ 99% accuracy), asks the anchor otherwise, converts lookups to confirmations, surfaces any
complaint-vs-record contradiction to the agent (100%), and degrades to open questions for a
walk-in/prospect with no record (must not fail).

**FR-14 Emergent categories & derived floor — discovery auto, activation human-gated.** (Closes
G1/G2/G11; EDD §16.2.) Cases are zero-shot-assigned into a universal starter taxonomy so zero-config
yields value immediately; tenant-specific categories are *discovered* automatically but **never
auto-activated** — a wrong category is a wrong deadline. A candidate category goes live only on **a
human click + recurrence across ≥15 distinct cases + a mandatory mapping to an existing SLA policy**;
until then the case sits in its nearest parent with the candidate recorded. The actionable floor is
derived (three unknowns day one, growing per category as fields promote). A universal default SLA
policy ships; the tenant's written policy is optional override, not a setup gate.

**FR-15 Human-approval commit gate.** (Closes G6; EDD §16.4.) No report, external record, or
notification/template fires on model output alone — a reviewer's approval transitions the case to
committed first. Auto-routed cases still pass this gate for any external action.

**FR-16 Sensitive-data governance at promotion.** (New, v1.1; EDD §16.2.) A self-creating schema can
invent a field holding PII/PHI. Every candidate field passes a sensitivity classifier + redaction gate
before promotion, recorded in provenance. **Light PII tier ships in the PoC** (PDPL); the **strict PHI
tier is a hard prerequisite before any health/clinic tenant** (built with the local stack).

---

## 7. Non-functional requirements
Setup is zero-configuration for the customer's *schema/categories* (FR-14), needs **no documentation
to complete the first case**, and the customer is **not in the room** — the only setup inputs are the
object-store connection (FR-13) and optional written policy text.
Latency: message → case ready ≤ 60s. Idempotent pipeline (replay → no dupes/loss). No customer data
in logs. Immutable originals; append-only corrections. Deployable on RTX 4070-class hardware fully
local. $0 stack (OSS + local models; metered LLM only in cents for the eval). Residency: default to the
strict UAE reading (health/payment data must stay in-country; DIFC/ADGM are separate regimes).

---

## 8. The winning condition (acceptance) — the ship gate

Ship only when **all six** are clean (winning-condition §9):

1. **Setup gate** — every box in winning-condition §2 (binary, no partial credit).
2. **Seven wow moments** (§3), each without prompting: nothing was typed · it knew something it was
   never told · it asked then already knew · the schema grew and backfilled visibly · it refused to
   guess · the report was already done · Arabic was not a downgrade.
3. **Quantitative thresholds** (§10 below) met on the ground-truth set.
4. **Trust gates** — every box (winning-condition §5 / EDD §7).
5. **No red flags** (winning-condition §7) — above all: *nothing requires you to touch a DB, config or
   prompt to make a customer's case work.*
6. **External gate** — 3 strangers, no walkthrough, own messy inputs: all three complete a case
   without asking you a question; ≥ 2 ask *how* it did something; ≥ 1 asks if they can use it for
   something you hadn't thought of; none asks for a feature before price; **≥ 1 asks what it costs.**

> **The actual winning condition:** a stranger asks the price before asking for a feature.

---

## 9. Success metrics (ground-truth set: ≥100 cases, ≥30 Arabic/code-switched, ≥20 too-sparse)

Full table in `winning-condition.md` §4 and `longterm_context.md` §6. The load-bearing ones:
governed-core accuracy ≥ 95% · auto-routed accuracy ≥ 98% · ambiguous-correctly-flagged ≥ 90% (the
trust metric — weight highest) · questions after anchor median ≤ 2 · asked-for-already-stated 0% ·
silent object-match accuracy ≥ 99% · duplicate fields after 200 cases < 5% · new-field rate clearly
declining · backfill correctness 100% · message→ready ≤ 60s.

---

## 10. Spec deltas — ACCEPTED (owner, v1.1), with one hard rule

**Hard rule: neither number below is ours. Both are published-research feasibility evidence, never a
promise. They must NOT appear in buyer material, a pitch deck, or as a target/threshold in the winning
condition.**

- **Δ1 — Arabic metric re-anchored to field-level extraction accuracy, not transcript WER.** WER parity
  "within 5 points" is unachievable and irrelevant: best-in-class open ASR is ~26% WER on hard
  conversational Arabic (Cohere 25.87 / OmniASR-LLM-7B 28.32 / Whisper Large V3 36.86 — ~1 word in 4
  wrong), yet a 26% WER transcript still yields ~95% correct *fields* because the anchor supplied most.
  **Winning-condition §4 row updated** to field-level parity backed by mandatory audio provenance. This
  makes the promise both honest and *more favourable*. Wow Moment 7 is measured at the case level.
- **Δ2 — "~200 attributes @ 0.95 precision" is feasibility evidence from KG schema-induction research,
  not a target.** Internally cite **AutoSchemaKG 92%** / **AutoPKG WKE 0.953**; keep "0.90–0.95 field
  precision" and "<5% duplicates" as **internal SLOs only**.
- **Δ3 — Any cloud LLM/ASR call is a cross-border transfer**, categorically prohibited for
  health-/payment-adjacent tenants. Those tenants run the LOCAL backend end-to-end. The dual-mode
  design exists for exactly this.
- **Δ4 — Accuracy thresholds are PER-DEPLOYMENT, not one number (new, v1.1).** A local 14B is not
  Claude; the local stack extracts materially worse. The winning-condition thresholds are validated on
  the **cloud path** (the PoC deployment); the local deployment needs its **own eval run and its own,
  lower bar** — built at clinic #1 (EDD §16.9). One number across both is a promise met on only one.

---

## 11. Key risks (product-level; mitigations in EDD)
Schema fails to converge (→ two-threshold dedup + nightly re-cluster + convergence monitor) ·
misclassification becomes invisibly the vendor's fault (→ confidence routing, never auto-route
ambiguous) · managers distrust AI reports (→ per-field provenance) · case-boundary detection is hard
(→ hybrid time-gap + state + LLM new-vs-follow-up classifier; budget more effort here than extraction) ·
Arabic ASR ceiling (Δ1) · elicitation becomes an interrogation (→ hard budget + questions-per-case as a
first-class regression metric) · residency (→ local-first default).

---

## 12. Decisions — RESOLVED (owner, v1.1)
The four architecture decisions stay **locked** (`longterm_context.md` §10): domain-agnostic · dual
local+cloud · both intake channels · Python + React/Vite. The v1.1 review's open items are now settled:

1. **ASR — start Cohere Transcribe Arabic (Apache-2.0). RESOLVED.** Best clean-license accuracy; Audar
   is ahead on WER but ships weights under a non-Apache AudarAI licence — read before it's load-bearing.
   **Design consequence:** Cohere has **no native timestamps/diarization**, which breaks "click a field →
   exact audio moment," so word-level provenance comes from **mandatory forced-alignment** (wav2vec2/
   faster-whisper), with **segment-level as the accepted fallback** (EDD §4).
2. **Spec deltas — ACCEPTED, with a hard rule. RESOLVED.** Neither the ASR-WER nor the 200@0.95 figure
   is ours; both are feasibility evidence and **must never appear in buyer material or as a winning-
   condition target**. Arabic re-anchored to field-level extraction accuracy (winning-condition §4
   updated). See §10.
3. **"1.5M AED" — none of contract/budget/valuation. RESOLVED.** It was a scoped opportunity that died
   before contract (RFP change). Internal quality bar + demand-shape evidence only; the sole approved
   external line is *"scoped a seven-figure government LLM proposal that didn't proceed after an RFP
   change."* (`CLAUDE.md` Directive 1.)
4. **Demo domains — bakery + home maintenance. RESOLVED.** Bakery (object = order) + home maintenance
   (object = job visit) for maximal contrast; the eval spans all six §4a verticals.
5. **Regulator-shaped / regulated-artefact reporting — PARKED by owner.** Out of scope and **not to be
   discussed until the owner re-raises it.** The PoC ships a **universal manager register** (§4a).
   Archived: `_parked/regulator-shaped-output.md`.
6. **Emergent categories — CONFIRMED with a gate. RESOLVED.** Discovery is automatic; **activation is
   human-gated** (a click + ≥15 cases + a mandatory SLA-policy mapping) because a wrong category is a
   wrong deadline. Until activated, a case sits in its nearest parent (FR-14 / EDD §16.2).
7. **Eval data — owner supplies and owns it in writing. RESOLVED.** ~10–15 design-partner real
   complaints under a written DPA (anonymised) + ~15–20 self-recorded (8–10 Gulf speakers, scenario
   cards, WhatsApp capture) + synthetic to fill; public corpora for calibration only (EDD §16.7).
9. **Report form type — MOOT.** The PoC report is a **universal register = our layout carrying the
   tenant's data → WeasyPrint** (no stamped-form question).
10. **Cloud-first scope — SETTLED (owner, v1.1; EDD §16.9 / PRD §5.1a).** PoC = cloud path only; the
    four local backends, the strict PHI gate, the separate local eval bar, and the on-prem test target
    are deferred to clinic customer #1. Recorded here so it isn't re-opened.

**Still open (build-time measurement, not a decision):**

8. **≤60s latency on the target 4070 (EDD §16.3).** Applies to the *local* stack (clinic #1); the PoC
   cloud path (Haiku) is comfortably within budget. Live benchmark decides Qwen3-14B vs 8B then.
