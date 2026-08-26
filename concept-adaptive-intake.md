# Adaptive Intake — Product Concept

*Working name. Version 0.1 — August 2026.*

> **PARKED-TOPIC NOTICE (owner, 2026-08-09):** references in this founding document to
> **regulator-shaped / regulated-artefact output** (e.g. §7.3, §8, §13) are **PARKED — out of scope and
> not to be discussed until the owner re-raises it.** This source text is preserved unaltered for the
> record; the active decision lives in the governing docs and `_parked/regulator-shaped-output.md`.

---

## 1. The statement

> **The customer gives zero structure. The fulfiller receives complete structure. The system pays the entire cost of the translation.**

Every case management, CRM and service desk product on the market pushes the work of structuring onto a human. This product absorbs it.

---

## 2. The problem

Organisations capturing complaints, requests and incidents face a trade-off with no good side.

**If you use structured forms:**
- End users abandon them or fill them badly. Long forms are the single most common complaint from both sides of the desk.
- Asking the customer to pick a type or category adds friction they don't want, and they pick wrong anyway — which lands the cost back on the fulfiller.

**If you use a free-text field:**
- The fulfiller has to read, interpret and re-key everything before they can act.
- Reporting collapses, because nothing is queryable.

**Management responds by mandating fields**, which produces the worst outcome of all: `N/A`, `.`, `see details`, `asdf`. Mandatory fields do not produce complete data. They produce compliant-looking garbage, and everyone involved knows it.

**Underneath all of it:** organisations work in chaos, and they expect software to absorb that chaos rather than demand it be fixed first. Systems that require the organisation to change its process get abandoned. Churn follows the vendor that adapts.

---

## 3. The insight

Structure should be *derived*, not *demanded*.

Modern language models can read a messy nine-message thread with photos and a voice note and produce a structured case. That capability did not exist when today's case management systems were designed. Those systems are built around the assumption that a human types into fields — which is why every one of them, including the AI-enhanced ones, still ends at a form.

Remove the form and the trade-off in section 2 disappears.

This much is no longer contrarian — an entire vendor category now argues it, as section 7 sets out. What remains unbuilt is what happens to the *schema* once the form is gone.

And once structure is derived rather than demanded, the interaction stops being a form and becomes a **drill-down**. The system asks only for what it could not work out on its own, only when it cannot act without it, and never for something the customer has already said.

---

## 4. How it works

### 4.1 Intake

Input is whatever the customer already produces: a WhatsApp message thread, voice notes, photographs, screenshots, forwarded PDFs, an email. No portal, no form, no category selection, no type picker.

### 4.2 The pipeline

```
ingest → normalise → transcribe / OCR → extract → elicit (only if below
the actionable floor) → deduplicate → promote → structured case →
human review → commit → report
```

Each stage is independently testable, idempotent and retryable. The original input is immutable and retained permanently; extractions reference it and never replace it.

### 4.3 Drill-down elicitation

Extraction assumes the mess contains the answer. Sometimes it contains nothing — *"I'm very mad at your service"* is a real complaint with no extractable content. The system must be able to close that gap itself.

**Every complaint has an object, and the object already exists.** A complaint is always against something — an order, a booking, a delivery, an asset, a subscription, a service visit — and that thing is already recorded somewhere in the business's data. This is what bounds the conversation. Only three things genuinely cannot be looked up:

1. **Which object** this complaint concerns
2. **What specifically** was wrong with it
3. **What the customer wants** done about it

That is where the question budget comes from. It is not an arbitrary limit — it is the actual number of unknowns.

**Often even the first is free.** If the sender's number matches exactly one recent order, do not ask; state it. Ask only when it is genuinely ambiguous, and then as two or three tappable options rather than an open question. The best drill-down is the one that asks nothing at all.

**And the record can contradict the complaint.** If the customer reports a late delivery and the record shows on-time arrival, that discrepancy is surfaced to the agent — never argued with the customer. Over time it is also a fraud and pattern signal.

**Complaints with no matching object** — a walk-in, a prospect, a service never purchased — need a fallback path that degrades to open questions. Rare, but it must not fail.

**The actionable floor.** Each category defines the smallest set of facts required to route, prioritise and act — not every field, the floor. The system compares what it extracted against that floor and elicits only the difference. A form asks everyone for everything; this asks one person for the two things missing from their case.

**Two kinds of question, in this order.**

*The anchor* — one question that resolves identity or transaction: order number, or the phone number used to order. It is not a field, it is a key. Everything downstream is looked up rather than asked.

*The drill* — narrows the fault, and only covers what the anchor could not reveal.

**The anchor turns questions into confirmations.** Once the transaction is known, the system does not ask how late the delivery was. It knows, and says so: *"delivered at 6:42pm against a 5:00pm slot — was it the delay?"* Confirmations are cheap; questions are expensive. Every question converted into a confirmation is the moment the customer feels understood rather than processed.

**Rules that stop the drill becoming a form in chat.**

- Extract first, ask second. Never ask for something already stated.
- Prefer inference to interrogation. Phone number resolves to customer, contracts, assets, location, open cases. Most gaps are derivable.
- Order questions by information gain — what most narrows the case, first.
- Sometimes the right follow-up is evidence, not a question. Damage reported, photograph requested: more data, less effort.
- Offer tappable options rather than open questions. Choosing between three concrete options *after* the system has narrowed the case is not the same act as classifying a complaint before it starts.
- Always ask the desired outcome — refund, replacement or acknowledgement. It is the only thing that can never be inferred, and it determines the resolution path.
- **Budget: the anchor plus two drills.** Then act, or hand to a human. A fifth question means the form has been rebuilt in chat.
- Stop at actionable, not at complete.

**Never block on completeness.** The case is created immediately in an incomplete state and elicitation runs alongside it. A complaint is never lost because someone stopped replying.

**The clock starts at first contact**, not at completeness — that is how regulators and customers both count it. Slow elicitation consumes the response window, which is the structural reason to keep the budget at two.

**Emotion is data.** *"I'm very mad"* carries no case content but is a strong signal of severity, escalation and churn risk. It is stored as an attribute, and an angry customer with an incomplete case is routed to a human rather than questioned further.

**The question set converges like the schema does.** The drill tree is not hand-built. It is generated per category, then narrowed by evidence: questions that never change the resolution are dropped, and follow-ups agents keep asking manually are promoted into the tree. Which yields a metric for free — **questions per case should fall over time.**

### 4.4 Two-layer schema

This is the core design decision.

**Governed core** — small, stable, defined per case category. Drives SLA clocks, routing, escalation and any regulator-facing output. Humans control it. The AI never creates a field here.

**Emergent layer** — an unbounded attribute store. Anything the model observes in a case lands here immediately, with no schema change and no migration.

### 4.5 Promotion, not creation

A newly observed attribute is a *candidate*, not a field.

- **Closed-world grounding.** The model may only propose attributes that are attested in the source text. It never invents a field it thinks ought to exist. This is the single most important constraint in the promotion layer — unconstrained discovery produces schemas that cannot be executed.
- **Statistics before semantics.** Structural decisions — types, cardinality, whether a value is an identifier — are made by deterministic methods. Model calls are reserved for semantic discovery only.
- Every candidate is embedded and compared against existing fields and prior candidates. Above a similarity threshold it maps onto the existing field rather than spawning a synonym. This is what makes the schema converge instead of sprawling.
- A candidate is promoted into the governed core only after it recurs across N distinct cases within a category.
- On promotion it acquires a type, a unit and validation rules.
- History is then re-extracted and backfilled, because every original is retained. **The schema improves backwards as well as forwards.**

The rule this implements: *recurrence proves necessity; one-offs stay in the bag.* If an attribute never appears again, it was specific to that case and was never a field worth having.

### 4.6 Determinism where it matters

The model supplies inputs — category, severity signals, entities. A deterministic rules engine assigns priority, SLA and routing. Service levels must be reproducible and defensible in an audit; they cannot be model output.

### 4.7 Provenance

Every stored value carries its source file, model, model version, prompt version, confidence score and reviewer. Managers will not trust a report they cannot trace, and provenance becomes mandatory the moment a value feeds a regulatory return or writes into another system of record.

### 4.8 Human review

The review screen is the product's most important interface. Source on one side — audio with transcript, or the original image — extracted fields on the other. Low-confidence fields flagged and focused first. Keyboard-driven. A reviewer should clear a case in under thirty seconds.

Every correction a human makes is stored against the original extraction, never overwritten. That correction log is the evaluation dataset and, over time, the asset a competitor cannot copy.

---

## 5. Worked scenarios

**Scenario 1 — known fields.** A long WhatsApp complaint arrives. The system extracts to the governed core, classifies the case, and the rules engine assigns priority and starts the SLA clock. No human typing occurred at any point.

**Scenario 2 — unknown fields.** A longer complaint contains details with no existing placeholder. Those attributes are captured into the emergent layer with their values. If similar attributes recur across other cases, they are promoted into the governed core, typed, and backfilled across history. The schema grows to match what the business actually deals with.

**Scenario 3 — nothing to extract.** *"The delivery was bad."* No order, no fault, no date. The system asks the anchor question — order number or the phone used to order — then, having looked up the transaction, confirms rather than interrogates: *"chocolate cake, delivered 6:42pm against a 5:00pm slot. Was it the delay, the condition, or something else?"* Damage reported, a photograph requested, desired outcome asked. Four exchanges, nothing typed into a field, and the case now holds the order, the customer, the items, promised versus actual delivery time, a 102-minute delay, two fault types, photographic evidence, the driver and the requested remedy.

---

## 6. What this is not

- **Not a CRM.** No pipelines, campaigns, quotes or forecasting. It does one job completely.
- **Not a chatbot.** It speaks to the customer only to close a gap it could not close itself, within a hard question budget, and it never attempts resolution. It does not converse; it drills.
- **Not autonomous.** Nothing reaches a report or an external system without human approval.
- **Not a reporting suite.** It produces the specific artefacts required, not a dashboard builder.

---

## 7. Prior art

Researched before committing. The intake half of this idea is a named category with funded players. The schema half is not yet a product.

### 7.1 What already exists

**Conversational intake is an established category in 2026.** Adoption is fastest in legal intake, insurance first-notice-of-loss and quoting, healthcare patient intake and B2B lead qualification, where form completion rates sit around 20–40%. Vendors fall into three camps: form builders with a chat skin (Typeform, Tally, Fillout), support chatbots repositioned as intake (Intercom, Drift, Ada), and AI-native intake platforms built around an interview model.

Their published reference architecture is close to identical to this one: an interviewer agent, a structured-output schema, a routing and escalation layer, and an analysis layer that turns transcripts into the same database rows a form would have produced.

**Adaptive drill-down is shipped.** Legal intake agents branch on each answer, asking only what a given matter requires — brief for clear non-fits, deeper for strong cases — and routinely surface details a form would never capture.

**The anchor-to-confirmation pattern is standard in insurance.** Claims systems already auto-create the record and populate policy and incident details from integrated systems, explicitly to eliminate repetitive questioning at intake. Coverage and exposure are pulled from policy systems and compared against what the claimant reported.

**WhatsApp-to-ticket exists.** Respond.io, Wati, Gorgias, Kustomer, eesel and others turn conversations into tickets with fields populated.

**Conclusion: "replace the form with a conversation" is not a novel insight.** It is a consensus position with vendors competing on execution. Any pitch resting on it alone will be met with a list of incumbents.

### 7.2 What does not exist as a product

**Self-converging schema.** Automatic schema induction is active research, not shipped software. Published frameworks perform extraction, definition and self-canonicalisation with online merging and dynamic schema extension for in-the-wild discovery, reporting schema sizes around 200 attributes at roughly 0.95 precision. No commercial intake or case management product ships a schema that promotes its own fields and backfills history.

The same literature names the failure mode this design must avoid, and the fix: LLM-based field discovery hallucinates fields that are absent from the data, producing schemas that cannot be executed. The remedy is **closed-world grounding** — restricting all model output to attested data fields — combined with **statistical inference before semantic inference**, delegating structural decisions to deterministic methods and reserving model calls for semantic discovery. Both are adopted into the promotion layer in section 4.5.

**Voice-first, Arabic, WhatsApp-native intake.** Every serious player in the category is Western, web-form-replacement and English-first. Practitioner commentary in adjacent markets is explicit that customers send voice notes for everything, and that platforms which display a speaker icon and do nothing with it are unusable — described as table stakes and still unmet.

### 7.3 Current product claim — corrected 26 August 2026

The first sellable claim is narrower and already supported by the product:

> **Messy complaint evidence becomes a traceable case draft that a human can review and approve faster,
> without forcing the customer through a form or surrendering control to automation.**

Self-converging schema, Arabic parity and regulator-shaped output remain research/product hypotheses, not
the controlled-pilot promise. They may become differentiators after representative evidence passes, but
the product does not need to pretend they are proven in order to learn whether its traceable drafting and
review workflow saves a complaint team time.

---

## 8. Positioning

**To the manager who signs:**

> 100% field completion. Zero mandatory fields.

Managers mandate fields because it is the only lever they have, and it produces unusable data. This product delivers the completeness they wanted by removing the mechanism they relied on.

**To the fulfiller:** stop transcribing, start resolving.

**To the end customer:** send what you were going to send anyway.

**And what must never be the pitch:** *"we replace forms with a conversation."* Section 7 explains why — a category of funded competitors already says exactly that, better rehearsed. Lead with the two claims they cannot match: a schema that grows and corrects itself, and voice-first Arabic intake producing the artefact a GCC regulator actually demands.

---

## 9. No cold start

Extraction is zero-shot. The system structures a complaint from a company it has never seen, on day one, with an empty database. The emergent schema bootstraps from the first case.

This removes the standard objection facing AI products in this category — *"give us six months of your history first"* — and neutralises incumbents' data advantage.

Two things are required at setup, and neither is historical data:

- **The object store, connected once**: orders, bookings, assets, service catalogue, customers. Extraction works without it, but elicitation does not stay short without it — this is the record that turns questions into confirmations. It must be connectable self-serve, by file upload or API key, inside the setup window. No consultant, no integration project.
- **Written policy**, supplied as text: escalation and priority rules, SLA definitions.

Note the distinction that matters: the system needs the customer's **current records**, never their **case history**. One is a connection made in minutes; the other is the six-month data dependency this product exists to avoid.

Historical data becomes necessary only when automating *resolution* — suggesting fixes, predicting root cause, identifying which data points predict fast closure. That is a later phase and deliberately out of scope for the proof of concept.

---

## 10. Architecture principle

**The engine is headless. The case management application is its first client, not its container.**

```
Engine (API):        ingest → structured case + confidence + provenance
Client A (PoC):      standalone case management UI
Client B (phase 2):  connectors writing into existing systems of record
```

If extraction logic is entangled with the case application, phase two is a rewrite. If the application merely consumes the engine's API, phase two is a connector.

Consequently, the field registry carries optional mappings to external system fields from the outset. An emergent schema is useless at integration time unless it can translate into someone else's fixed one.

---

## 11. Roadmap

**Phase 1 — Proof of concept.** Standalone case management. Intake, extraction, emergent schema with deduplication and promotion, the review screen, one queue, SLA clock, one generated report. Nothing else.

**Phase 2 — Integratable module.** The same engine, writing structured cases into existing platforms. No rip-and-replace, no process change demanded of the customer.

**Phase 3 — Resolution intelligence.** Using accumulated history: which attributes predict fast resolution, prompting agents for the specific missing data points that matter for that case type. A static form asks everyone for everything; this asks each case for what it is missing. The same evidence narrows the drill tree — questions that never change an outcome are retired, and follow-ups agents keep asking by hand are promoted into it.

---

## 12. The demonstration

Paste a messy nine-message thread with two photographs and a voice note.

Thirty seconds later: a fully populated case, priority and SLA assigned, three attributes the system had never encountered sitting in the emergent layer, one low-confidence field flagged for review.

Paste a second complaint that reuses one of those attributes, and watch it promote itself into the schema.

Then send the opposite extreme — four words, *"the delivery was bad"* — and watch it ask one question, look up the transaction, and confirm the delay rather than asking for it.

Ninety seconds, no configuration, empty database.

---

## 13. Known risks

| Risk | Mitigation |
|---|---|
| Schema fails to converge — synonym fields proliferate | Embedding-based deduplication before storage; promotion thresholds; admin merge tooling |
| Misclassification moves from customer to model, and becomes invisibly the vendor's fault | Confidence thresholds with a triage queue; never auto-route ambiguous cases |
| Managers distrust AI-populated reports | Per-field provenance and confidence, visible in every report |
| Case boundaries are hard — complaints arrive across many messages over time | Conversation windowing plus explicit new-case-versus-update classification. Budget more effort here than for extraction |
| The conversational-intake category already exists and will absorb this wedge | Compete first on traceable evidence, mandatory human control, fast complaint review and deployable data boundaries. Treat self-converging schema and voice/language breadth as evidence-gated future differentiators, not current promises. |
| Elicitation becomes an interrogation — the long form rebuilt in chat | Hard budget of anchor plus two drills; questions-per-case tracked as a first-class metric, with any rising trend treated as a regression |
| The system asks for something the customer already said, or could have been looked up | Extract before asking; infer from the anchor before asking; both enforced in the elicitation policy and measured |
| Customer abandons mid-elicitation | Case created immediately in an incomplete state; never blocked on completeness. Reengagement outside the messaging service window requires a template — designed for, not discovered later |
| Regulatory constraints cannot be emergent | Governed core is human-controlled; only the attribute layer adapts freely |

---

## 14. Open questions

1. **Which domain for the proof of concept** — facilities and property management (easiest to demonstrate convincingly) or complaints in a regulated sector (the more fundable story, where the output is a mandated artefact).
2. **Go-to-market.** A low-priced self-serve product cannot fund a salesperson; a sales-led product must be priced high enough to justify one. Pricing and channel must be decided together.
3. **Data residency.** Whether target buyers will accept a non-regional deployment, given UAE PDPL and sector-specific requirements.
