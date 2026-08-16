# Structured Chaos — Repository Analysis & Remediation

*Read of `Colonel94/structured-chaos` @ clone 2026-08-16. 172 files, ~10k lines of Python, 3.8 MB — the 3 GB was untracked working tree, so repo hygiene is clean.*

---

## Verdict up front

The engineering is genuinely good. Trust spine, RLS, transactional enqueue, immutable log, real re-extraction backfill, debounced promotion — all built, all matching their specs. Several things I flagged in earlier sessions were implemented properly rather than fudged.

**But the convergence proof is invalid, and it is invalid in a way that cannot be fixed by tuning.**

Path A did not solve the convergence problem. It renamed it. The measured curve now converges because it is mathematically incapable of doing anything else, and the sprawl it was supposed to eliminate moved into a space that is not measured and not deduplicated.

---

## FINDING 1 — Convergence is guaranteed by construction (CRITICAL)

### The claim

`eval/run_extraction.py`, docstring:

> "Convergence is therefore achieved AT EXTRACTION TIME (the head space is bounded by construction + extended only by promotion), so this harness IS the Path-A proof — no downstream embedding-dedup pass is needed for the column gate."

### What the numbers actually show

Measured over the 120-case CFPB extraction fixture:

```
new-HEAD per 20-case bucket:      [15, 4, 4, 1, 1, 1]     ← "converges"
distinct heads reached:            26  (of 31 seeded)
```

That curve is not evidence of a self-converging schema. `HEAD_NOUNS` is a **closed tuple of 31 hand-written values**, enforced as an enum in the extraction schema. The curve is the enumeration of a fixed list. It would produce the same declining shape on random noise, on a single repeated sentence, or on data from any domain whatsoever.

**A gate that cannot fail is not a gate.** Winning-condition §4 asks whether *the schema settles*. This measures whether *a list is finite*.

### Where the sprawl actually went

Same fixture, same run, composite (`qualifier_head`) space:

```
new-COMPOSITE per bucket:         [46, 38, 54, 45, 51, 41]   ← FLAT
distinct composites:               275
hapax (appear exactly once):       245 = 89%
```

Compare the pre-Path-A full-name curve this was meant to fix: `[48, 52, 74, 64, 77, 63]`.

**It is the same curve.** Same magnitude, same flatness, same ~90% hapax rate. The compound names did not stop being minted — they were split into two columns and only one of them is being counted.

The `amount` head alone carries **68 distinct qualifiers** across 94 attestations, including:

`charged` · `totaling` · `total` · `paid` · `owed` · `owed_them` · `settled_for` · `partial_payment_of` · `incurred_expenses_totaling` · `medical_procedure_balances_are` · `couple_xxxx_dollars` · `credit_score_dropped`

`total` and `totaling` are the same qualifier. `owed` and `owed_them` are the same qualifier. `credit_score_dropped` under head `amount` is a mis-extraction. This is exactly the synonym sprawl dedup exists to collapse — and dedup is not running on it.

### Why the harness cannot detect this

The same docstring labels the composite count *"DIAGNOSTIC ONLY (qualifiers are data and are EXPECTED to proliferate); not the gate."*

The one number that would have exposed the problem was pre-emptively excluded from the gate, in the same file that declares the gate satisfied.

### The pattern

This is the sixth occurrence of a specific failure mode across this project:

| # | Cheap path taken | Substance dropped |
|---|---|---|
| 1 | Concept curve as pass/fail | Full-name curve |
| 2 | Re-projection as "backfill" | Re-extraction *(caught, fixed — backfill.py is real)* |
| 3 | Claude-labelled gold set | Human labels |
| 4 | Subagent-generated convergence data | Data the author didn't write |
| 5 | "Unproven off finance" | *Failing* on finance |
| 6 | Closed head list as convergence proof | Actual convergence |

Every one looked equivalent from inside the code. That is what makes it dangerous: it is not carelessness, it is the natural gradient when the person checking the work is the person doing it.

---

## FINDING 2 — Dedup is built, tested, and never runs (CRITICAL)

`app/schema/dedup.py` is well-designed: two-threshold gate, asymmetric gray band, LLM adjudication framed as a column question, fail-safe to *not* merging, HNSW index in migration 0008.

`grep` for callers across `engine/app/`:

```
app/schema/dedup.py      (itself)
eval/run_convergence.py  ("the PRE-Path-A convergence proof (historical)")
eval/diag_pairs.py, eval/probe_values.py  (diagnostics)
```

**Zero callers in the live pipeline.** `extract/stage.py` calls `register_emergent_field` and `register_emergent_head` and stops. Nothing embeds. Nothing merges. The moat has never executed end-to-end on real data.

And the file that would have called it is marked *historical*, on the grounds established in Finding 1.

---

## FINDING 3 — The escape valve is closed, so promotion can never fire

```
head 'other' used:  3 times out of 450 attributes  (0.7%)
```

`other` is documented as *"the ESCAPE valve so the model is never forced to mis-map a genuinely-new concept — those `other` heads are exactly the promotion candidates."*

At 0.7%, the model is force-fitting nearly everything into the 31 seeded heads instead of flagging novelty. Which means:

- **Head promotion (STAGE 4, dimension 1) will essentially never trigger on a new concept.** The only path by which domain specialisation is supposed to emerge is closed.
- Force-fitting is silent information loss. `credit_score_dropped` landing under `amount` is that loss, visible.
- The §4 claim — *"no industry-specific field is ever configured; specialisation is emergent, never seeded"* — is not being met in practice. Specialisation is 100% seeded and 0.7% emergent.

Related: **18 of 94 `amount` attributes have `qualifier: null`** — a bare head with no specificity, i.e. the exact information loss Path A was designed to prevent. Overall qualifier retention is 0.658, so a third of attributes are carrying no specificity at all.

---

## FINDING 4 — Multi-domain run inherits the same invalid gate

```
multidomain new-HEAD per bucket:  [15, 3, 2, 3, 0]    total heads 23
96 cases across 9 domains
```

Same shape, same reason, same non-result. Standing up the multi-domain set was the right move and the domain spread is good (motor vehicle, health, retail, electronics, home service, restaurant, travel, utility, legal). But it is currently measuring the same tautology in nine places instead of one.

The composite curve for this set has not been reported at all.

---

## FINDING 5 — Confirmed sound (no action needed)

Stated plainly because the remediation below is heavy and these should not be re-opened:

- **Backfill is real re-extraction**, bounded batches, self-re-enqueueing on `BACKFILL_QUEUE`, with a `backfill_attempt` marker (migration 0010) for idempotency. This matches the spec exactly.
- **Promotion is debounced** via `promote_scan`, not per-case, with transactional defer so promote+enqueue commit together.
- **Two-dimensional promotion** with `M > N` and head-before-qualifier ordering is implemented as specified.
- **Extraction chains transactionally** off normalisation — no manual trigger, no orphan/phantom.
- **Prompt version is in the idempotency key**, so a prompt bump re-extracts history rather than silently skipping. That was a real hole and it was closed.
- **Cost meter exists** (`store/meter.py`, migration 0002, `eval/measure_backfill_cost.py`) — GAP-1 addressed.
- **Spike scripts exist** (`spike1_asr`, `spike2_doc`, `spike3_rtl_pdf`) — the de-risk step was taken.
- **`field_validity` mean 0.976** — grounding is holding well on real messy text.

---

## FINDING 6 — Still outstanding from the previous gap list

- **Statistics-before-semantics (§4.2) not built.** The deterministic type/cardinality/identifier pass doesn't exist; the LLM does all of it. This is the published remedy for exactly the failure mode in Finding 3.
- **PII gate at promotion (§4.5) not built.** Nothing prevents a health condition or ID number being promoted into the durable governed schema.
- **Grounding not re-measured on the qualifier slot** specifically. 0.976 is value-level.
- **All accuracy numbers are near majority-class baseline** — severity 66% vs 62% baseline is +4 points of real signal.
- **No real voice data through the pipeline.** Voice is now the entire behavioural wedge.
- **No design partner, no customer, no human-labelled eval.**

---

# REMEDIATION

Ordered. Do not proceed to Phase 5 until R1–R3 are done.

## R0 — Retract the claim (today, 10 minutes)

Edit the `run_extraction.py` docstring and any `longterm_context` entry that asserts Path A proved convergence. Replace with:

> The head-space curve is bounded by construction (closed vocabulary) and is therefore NOT evidence of convergence. The gate is the composite (qualifier_head) curve after dedup. Currently unproven.

This matters more than it looks. Every subsequent decision inherits this claim, and future-you will trust the docstring.

## R1 — Wire dedup into the live pipeline, on qualifier space

In `extract/stage.py`, after `register_emergent_field`, call `dedup_field` — but **scoped within a head**, not across the global name space:

- The comparison universe for a new qualifier is the set of existing canonical qualifiers *under the same head*.
- Embed `f"{qualifier} {head}"` rather than the bare qualifier, so `total`/`totaling` under `amount` compare in context.
- Keep the existing τ=0.85 / 0.70 gate and the fail-safe-to-not-merging behaviour. Both are right.

Consider doing this off the hot path (a queued `dedup` stage) if latency matters — the registry is already designed for that ("embedded when the dedup unit runs (kept out of the hot extract path)").

## R2 — Fix the gate, then measure it

Replace the convergence gate with three numbers, all reported per run:

1. **Composite curve after dedup** — `new canonical (qualifier, head) pairs per bucket`. This is the gate. It must bend down.
2. **Duplicate rate** — `1 − (canonical composites / raw composites)`, target <5%. Currently unmeasurable because nothing merges.
3. **Hapax rate** — currently 89%. A converging schema drives this down.

Report the head curve as a diagnostic. Invert the current labelling exactly.

Run on both CFPB and multi-domain. If the composite curve does not bend after dedup, the concept is wrong and you need to know that before Phase 5.

## R3 — Reopen the escape valve

`other` at 0.7% means the promotion path is dead. Fix in the prompt, then verify:

- Instruct explicitly: *prefer `other` over a poor fit; a forced mapping is worse than a flagged novelty.*
- Add a negative example showing a bad force-fit (`credit_score_dropped` → `amount`) mapped to `other` instead.
- **Target: 5–15% `other`.** Below 3% the model is force-fitting; above 25% the seed vocabulary is wrong for the domain.
- Then confirm at least one head actually promotes out of `other` on the multi-domain set. If none does, emergent specialisation does not work and §4's central claim fails.

Also investigate the 18 null-qualifier `amount` attributes — a bare head is information loss, and 34% of attributes carry no qualifier at all.

## R4 — Build statistics-before-semantics (§4.2)

A deterministic pass over attested values before the LLM: type inference, cardinality, identifier detection, unit detection. This is the published fix for hallucinated/force-fitted fields and it directly attacks Finding 3. Cheap, and it reduces model calls.

## R5 — PII gate at promotion (§4.5)

Before a concept enters the durable governed schema, classify it. Health conditions, government IDs, payment card numbers, and the rest of the protected set never promote — they stay in the emergent bag with a sensitivity flag. Low urgency now, unbounded liability later; one promoted health attribute is a disclosure problem, not a bug.

## R6 — Adopt `record_accuracy` and re-label

Per the adjudication: 15 of 23 boundary errors were neither billing nor service, but record-accuracy disputes ("your file on me is wrong — verify, correct, or delete"). Add the third category, re-label, re-score.

Note this will *lower* the score until the prompt is updated. That direction is the correctness check.

Verify it generalises off finance before adopting — in a bakery the analogue is membership status, loyalty balance, warranty registration, service history.

## R7 — Determinism check (free, do it while running R2)

`24483813` and `24490268` are word-for-word identical narratives. `24506166`, `24509544`, `24525658` are near-identical templates. Identical input must produce identical extraction. If it doesn't, that is a determinism bug and it invalidates every measurement above.

---

## What this does to the score

Previous assessment: **5/10**, with engineering strong and evidence weak.

Revised: **4/10.** The engineering rating holds — arguably rises, given how much of the trust spine and backfill is correctly built. But the moat has now been measured, and the measurement was invalid in the one direction that mattered. That is worse than unmeasured, because it produced false confidence that three further phases were built on.

**What moves it back to 6:** R1–R3 done, and the composite curve reported honestly — *whatever it shows*.

**What moves it to 8:** the composite curve bends down after dedup on data you didn't author. That single result is the difference between a product with a moat and a well-engineered ticketing system.

It is one to two weeks of work and it is the only thing worth doing next.
