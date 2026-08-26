# Phase 8 — winning-condition §4 scorecard (honest state)

*Regenerate the live numbers any time: `cd engine && uv run python eval/score_phase8.py` (deterministic,
$0, files-only). This doc is a dated snapshot + the interpretation; the script is the source of truth.*

**Snapshot: 2026-08-21.** Ground-truth set = **216 real cases** (cfpb 120 + multidomain 96), scored
against the current **v20** extractions + the shipped **calib-v2** calibration.

> **Read this first.** Every accuracy number below is measured against gold **Claude authored**, so it is
> *agreement-with-the-labeller, not agreement-with-reality* (longterm_context.md §0; CLAUDE.md §10
> CORRECTION 2026-08-19c). The number that turns these into real accuracy is the **independent held-out
> slice** — `eval/holdout_labels.csv` (66 blind cases, ready for an independent labeller). Until that
> comes back, treat these as an upper bound on my own consistency, not a ship number.

## Measured from the ground-truth set (self-labelled)

| Measure | Threshold | Measured | Status |
|---|---|---|---|
| Category classification accuracy | ≥90% | **77%** (167/216; cfpb 82%, md 71%) | ❌ FAIL |
| Cases requiring zero human edits | ≥70% | **28%** (cfpb, ~3.7 labelled fields/row) | ❌ FAIL |
| Desired outcome captured | ≥90% | **56%** (cfpb; md unlabelled for this field) | ❌ FAIL |
| Severity accuracy (governed core) | ≥95% | **83%** (cfpb; md unlabelled) | ❌ FAIL |
| Ambiguous cases correctly flagged | ≥90% | **100%** — but *trivially*: gate_met=False/τ=1.01 routes **everything** to review (it also flags 100% of correct cases). Passes on paper, means "no automation yet". | ⚠️ trivial PASS |
| Accuracy on auto-routed cases only | ≥98% | **VACUOUS** — 0 cases auto-route (gate_met=False). The gate is not yet exercised. | — N/A |

**Governed-core field accuracy (§4 ≥95%)** is the composite of category/outcome/severity above — all
under gate. The product is currently **assisted data entry, not automation**: with nothing auto-routing,
the ≤30s review target *is* the value proposition (owner framing, §0).

## Convergence — the moat (the core design claim)

| Measure | Threshold | Measured | Status |
|---|---|---|---|
| Duplicate/synonym fields after 200 | <5% | last live **7.6%** dup, ~90% hapax | ❌ FAIL |
| New-field creation rate declining | declining | composite curve **FLAT** (cfpb [37,27,23,29,27,20], md [68,27,29,23,11]); hapax 85–89% | ❌ FAIL |

The `<5%`-dup row needs the live embedding dedup (`uv run --group embed python
eval/run_column_convergence.py`); the retraction (2026-08-17) stands — convergence is **unproven on real
data** and needs richer recurring data + the dedup/mint proof to bend the composite curve.

## Diagnostic only (never a gate — §10)

- **Emotion accuracy** (not in §4): 73% (cfpb).
- **Confidence discrimination** (for review *ordering*, not accepted accuracy): low confidence does
  concentrate errors — `conf<0.8` catches **86%** of wrong cases vs **62%** correct-false-flagged;
  `conf<0.7` catches 61% vs 25%. Useful for triage, not for a per-case difficulty claim (per-class prior).

## Measured via a live run (2026-08-21) — checkable against source data, not my gold

These don't depend on the gold I authored: the drill length, whether the anchor resolved the right
order, whether it asked for something already stated — all checkable against the source data + the coded
policy. Regenerate: `uv run python eval/measure_elicit.py` (pure) and `uv run python
eval/measure_object_match.py` (live store, DB up).

**Elicitation — the anchor+2 drill, over the real 216 extracted states** (`measure_elicit.py`):

| Measure | Threshold | Measured | Status |
|---|---|---|---|
| Questions per case (median) — HEADLINE | ≤2 after anchor | **file-drop median 2** (0q×99, 2q×114), **WhatsApp median 1**; drills-after-anchor median **1**, max **1** | ✅ PASS (never even reaches 2 drills) |
| Asked for something already stated | 0% | **0/216** | ✅ PASS (by construction, verified) |
| Asked for something derivable from anchor | ≤5% | **0/216** | ✅ PASS |
| Sparse complaints reaching actionable | ≥80% | **UNMEASURED** — 0/216 are too-sparse (the 216 are full narratives; §4's ≥20 sparse cases are a separate population). The 2nd drill never fires here for the same reason — category+fault are ~always extracted. | — |

Terminal states: **192 actionable, 24 in_review** (angry/budget handoffs — correct, never interrogated).

**Object-match — the PAIR, over the live resolver + store** (`measure_object_match.py`, 600 cases/orders,
objective key ground truth):

| Measure | Threshold | Measured | Status |
|---|---|---|---|
| WRONG silent binds (the trust gate) | 0 | **0 / 311 silent matches** | ✅ PASS |
| Silent-match accuracy | ≥99% | **0/311 wrong → ≤1.0% error bound** (n≈311 just clears the ~300 rule-of-three floor; *bounds*, doesn't yet *claim*, ≥99%) | ✅ no defect |
| Recall on resolvable (resolver quality) | — | **311/311 = 100%** (binds every safely-resolvable case) | ✅ |
| Complaints matched w/o asking (RATE) | ≥60% | **52% on this mix** — but the mix **constructs 48% unresolvable** (typos/shared-phones/no-anchor). Rate is a property of the **input distribution**, not the resolver (recall=100% proves it's not the bottleneck); the real ≥60% needs a real anchored-complaint dataset (CFPB anchors are redacted `XXXX` — $0 gap). | ⚠️ mix-dependent |

The pair reads correctly: recall 100% means the 52% rate is **input-bound, not abstention-gaming** — and 0
wrong binds is the regression to fear, which holds. Moment-3 confirmation fires live ("We've found your
order BK-…: items …, customer name …").

## Not measurable from files or a live run yet — reported, never faked (§10 "no silent caps")

Needs **new data or a longer run**: end-to-end latency (~8–17s observed inline, confirm under load);
backfill correctness (re-extract vs retained originals); the real object-match RATE (a real
anchored-complaint distribution).

Needs **humans / new data**: median review time (human on the review UI); elicitation abandonment (real
customers); discrepancies-surfaced (cases labelled with a known complaint-vs-record discrepancy); emergent
attribute accuracy (labelled emergent gold).

**UNMEASURED:** voice-vs-text field-extraction parity — there is no paired set containing the same cases
spoken and typed. Arabic/code-switched coverage was suspended by owner decision on 2026-08-21; when it
returns to scope, the ≥30-case composition rule and Arabic parity gate return with it.

## Bottom line

**Two very different pictures.** The **drill + trust** side is genuinely strong and — crucially — measured
on numbers that *don't* inherit the gold ceiling: anchor+2 holds with a wide margin (median 1 drill), 0/216
asked-already-stated, 0 wrong object binds across 311 silent matches, recall 100%. The **accuracy** side is
under gate on every self-labelled row (category 77%, zero-edit 28%, outcome 56%, severity 83%) and
convergence FAILs — and those are exactly the numbers that need the independent labels to become real.

The two levers that move the accuracy side:

1. **Independent held-out labels** (`eval/holdout_labels.csv`, ready) — breaks the self-labelled ceiling
   on category/confidence/review-ordering. Owner recruits an independent labeller. *Binding constraint.*
2. **A live elicitation + object-match run** — turns ~8 of the 13 UNMEASURED rows into real numbers
   without any new data (needs DB + Ollama up).
