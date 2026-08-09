# The Winning Condition

*Acceptance criteria and ship gate for the Adaptive Intake PoC.*
*Version 0.1 — August 2026.*

---

## Purpose of this document

This is written **before** the build, deliberately, so that "ready" is defined by evidence rather than by how tired you are of building.

The PoC is not a demo. It must behave as an MVP: something a real organisation could start using on Monday, with no implementation project, no consultant, and no phone call to you.

Read this document once before you start building, and once when you think you are finished. If the second reading is uncomfortable, you are not finished.

---

## 1. The one-sentence test

> **A stranger signs up, sends the messiest real case they have, and within a minute sees a complete, correctly structured, correctly prioritised case they did not type — and cannot immediately name a field the system got wrong.**

And the inverse, which is the harder half:

> **The same stranger sends four useless words, and the system closes the gap in two questions without once asking for something it could have looked up.**

Everything below is that sentence, made measurable.

---

## 2. Plug and play — the setup gate

The product is plug and play only if all of the following are true. These are binary. There is no partial credit.

- [ ] **Zero configuration to first value.** From account creation to a fully structured case, with no settings touched, no schema defined, no category list built.
- [ ] **Under 10 minutes** from signup to first processed case, measured with a timer, by someone who has never seen it.
- [ ] **No historical data required.** The system works on an empty database.
- [ ] **No training, tuning or model work** per customer.
- [ ] **No documentation needed** to complete the first case.
- [ ] **You are not in the room.** If you have to explain anything, it is not plug and play — it is a demo with a salesperson attached.
- [ ] Connecting the object store — orders, bookings, assets, customers — is **self-serve and inside the 10 minutes**, by file upload or API key. Extraction must work without it; short elicitation will not.

If any box is unticked, stop. Nothing in section 3 matters yet.

---

## 3. The wow moments

These are the specific, observable events during a live test that produce the reaction you are looking for. Each must happen without prompting, explanation or apology.

### Moment 1 — Nothing was typed
A messy nine-message thread, containing a voice note in Gulf Arabic and two photographs, becomes a complete structured case. No form was filled. No category was chosen. No type was picked.

**Watch for:** the tester scrolling back to check they really did not enter anything.

### Moment 2 — It knew something it was never told
The case contains a field the tester never configured and never expected — pulled from the body of the complaint and placed correctly.

**Watch for:** *"How did it know that?"*

### Moment 3 — It asked, then it already knew
A four-word complaint with nothing in it. The system asks one anchor question — order number, or the phone used to order — and then, instead of asking what went wrong in detail, states what it found: *"delivered 6:42pm against a 5:00pm slot. Was it the delay, the condition, or something else?"*

Two more exchanges and the case is complete, including the desired outcome.

**Watch for:** the tester noticing it never asked for anything it could have looked up — and never asked twice for something they had already said. The number they should not be able to fault is the count of questions.

### Moment 4 — The schema grew, visibly
A second case reuses an attribute first seen in an earlier case. It is promoted into the real schema, typed, and — critically — **backfilled onto the earlier cases**.

**Watch for:** the tester realising the system got better while they watched, without anyone configuring anything.

### Moment 5 — It refused to guess
A genuinely ambiguous field is flagged low-confidence and routed for review, instead of being confidently filled with something wrong.

This moment matters more than the four above it. Confident wrongness destroys trust permanently; visible uncertainty builds it. **A system that never says "I'm not sure" has already failed.**

### Moment 6 — The report was already done
A manager-facing report or register is produced with every field populated, every value traceable to its source, and no mandatory field ever having been imposed on anyone.

**Watch for:** *"So nobody had to fill anything in, and the report is still complete?"* That is the sentence that closes the sale.

### Moment 7 — Arabic was not a downgrade
A code-switched Gulf Arabic voice note produces output of the same quality as the English equivalent.

**Watch for:** nothing. The absence of a wince is the pass condition.

---

## 4. Quantitative thresholds

Measured against a hand-labelled ground-truth set of **at least 100 real or realistically messy cases**, at least 30 of them Arabic or code-switched, and at least 20 of them too sparse to act on without elicitation, before any claim of readiness.

| Measure | Ship threshold | Why this number |
|---|---|---|
| Governed-core field accuracy | **≥ 95%** | These drive SLA, routing and reports. Errors here are expensive |
| Emergent attribute accuracy | ≥ 85% | Lower stakes; reviewable before promotion |
| Category classification accuracy | ≥ 90% | Below this the fulfiller stops trusting routing |
| Accuracy on auto-routed cases only | **≥ 98%** | Anything the system routes without asking must be near-certain |
| Ambiguous cases correctly flagged rather than guessed | ≥ 90% | The trust metric. Weight it highest |
| Cases requiring zero human edits | ≥ 70% | Below this it feels like proofreading, not automation |
| Complaints matched to the right object without asking | ≥ 60% | The sender's number should usually be enough. Every match is a question saved |
| Object match accuracy when matched silently | **≥ 99%** | Acting on the wrong order is worse than asking |
| Discrepancies between complaint and record surfaced to the agent | 100% | Never argued with the customer, never silently ignored |
| Questions asked per case (median) | **≤ 2 after the anchor** | The line between a drill-down and a form in chat |
| Cases where the system asked for something already stated | **0%** | Unforgivable. One occurrence in a demo loses the room |
| Cases where it asked for something derivable from the anchor | ≤ 5% | Asking what you could look up is the tell of a dumb system |
| Sparse complaints reaching actionable state | ≥ 80% | Elicitation has to actually close the gap, not just try |
| Elicitation abandonment (customer stops replying) | ≤ 20% | Above this the drill is too long or too dull |
| Desired outcome captured | ≥ 90% | The one fact that can never be inferred |
| Median review time per case | ≤ 30 seconds | The fulfiller must feel faster, not busier |
| Time from message received to case ready | ≤ 60 seconds | Slower and it stops feeling live |
| Arabic **field-extraction** accuracy versus English | within 5 points (field-level, **not** transcript WER) | Measured on the structured case, not the transcript: a ~26% WER voice note can still yield ~95% correct fields because the anchor supplied most. Raw ASR WER is not a ship metric and must never appear in buyer material |
| Duplicate or synonym fields after 200 cases | **< 5%** of promoted fields | This is the convergence proof — the core claim of the design |
| New-field creation rate, cases 1–50 versus 151–200 | clearly declining | If it is flat, the schema is sprawling, not converging |
| Backfill correctness after promotion | 100% | No exceptions. Silent corruption of history is fatal |

The two bolded convergence rows are the ones to be honest about. If the schema does not visibly settle, the central idea in the concept document is wrong, and you need to know that before you sell anything.

---

## 5. Trust gates — non-negotiable

Failure of any single item here blocks shipping regardless of how well everything else performs.

- [ ] **Every field is traceable.** Click any value, see the exact source — the sentence, the region of the image, the moment in the audio.
- [ ] **Provenance is complete.** Source, model, model version, prompt version, confidence, reviewer, timestamp — on every value.
- [ ] **The case exists before the questions do.** A case is created on first contact in an incomplete state, and survives the customer never replying again.
- [ ] **The clock starts at first contact**, not at completeness.
- [ ] **The question budget is enforced in code**, not left to the model's judgement. Anchor plus two, then hand off.
- [ ] **Nothing external happens without approval.** No report issued, no record written elsewhere, no notification sent, on model output alone.
- [ ] **SLA and priority are deterministic.** Same inputs, same policy, same result, every time, and explainable in one sentence.
- [ ] **Tenant isolation is proven by an automated test** that attempts a cross-tenant read and fails.
- [ ] **Originals are immutable.** Every source file retained, never overwritten by an extraction.
- [ ] **Corrections are preserved, never overwritten.** This is the asset.
- [ ] **The pipeline is idempotent.** Replay any stage; no duplicate cases, no lost data.
- [ ] **No customer data in logs.**

---

## 6. What is allowed to be missing

Being ready to ship does not mean being complete. These absences are acceptable at ship:

- Only one or two intake channels
- One case category, done properly, rather than several done shallowly
- No dashboards beyond a register view and one report
- No mobile application
- No customer-facing portal
- No integrations with other systems
- No resolution suggestions or automation
- A hand-seeded drill tree rather than a learned one — convergence of the question set is a later phase, the budget and the anchor are not
- Rough visual design, provided the review screen is fast
- Manual tenant onboarding behind the scenes

**Do not delay shipping for anything on this list. Do not ship without anything in sections 2, 3 or 5.**

---

## 7. Red flags — you are not ready

Any one of these means stop, regardless of the metrics:

- You find yourself explaining what the tester should have expected
- The demo only works with the sample data you prepared
- You feel a need to say "it usually handles that better"
- The tester's first instinct is to look for the form
- The bot asks a fourth question, ever
- It asks for something the customer already told it, or something the order record already contains
- Elicitation reads like a survey rather than a conversation — the customer can feel the field list underneath it
- An angry customer with an incomplete case gets questioned instead of handed to a human
- Fields keep appearing that mean the same thing as existing fields
- You cannot answer "where did this value come from?" in under five seconds
- The review screen is slower than typing the case manually would have been
- It works in English and is a different product in Arabic
- Anything requires you to touch a database, a config file or a prompt to make a customer's case work

That last one is the most common failure mode, and it disqualifies the product entirely. If serving a customer requires you, it is a service business wearing a product costume.

---

## 8. The external gate

Internal testing does not decide this. Three people who did not build it do.

Give three strangers — ideally people who handle real cases for a living — access with no walkthrough, and their own messy real inputs. Watch, and say nothing.

You have won when:

- [ ] All three complete a case without asking you a question
- [ ] At least two ask **how** it did something, unprompted
- [ ] At least one asks whether they can use it for something you had not thought of
- [ ] None of them asks for a feature before asking about price
- [ ] At least one asks what it costs

**That last one is the actual winning condition.** Everything else in this document is a proxy for it. When someone asks the price before asking for a feature, you have built something people want.

---

## 9. Scorecard

Fill this in the day you think you are finished. Do not fill it in optimistically.

| Gate | Status | Evidence |
|---|---|---|
| Setup gate (section 2) — all boxes | | |
| Seven wow moments (section 3) | | |
| Quantitative thresholds (section 4) | | |
| Trust gates (section 5) — all boxes | | |
| No red flags present (section 7) | | |
| External gate with 3 strangers (section 8) | | |

**Ship when all six rows are clean. Not before, and not one week after.**

---

## 10. The honest reminder

The temptation will be to ship on section 3 alone, because the wow moments are the fun part and they arrive early.

Wow gets you a meeting. Sections 4, 5 and 7 are what stop the product falling apart in the second week, in front of the person who was going to pay you.

Convergence, confidence and a two-question drill are the three claims this product is built on. If any of them fails to hold under real data, the right decision is to fix the design, not to ship and hope.

The drill is the one most likely to rot quietly. Every question feels justified on the day it is added, and no single addition looks like a mistake. Watch the count, not the rationale.
