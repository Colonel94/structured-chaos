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

## Not measurable from files — reported, never faked (§10 "no silent caps")

Needs a **live run** (DB/Ollama/pipeline): complaint→object match rate + silent-match accuracy (report as
a pair); questions-per-case + asked-already-stated + derivable-from-anchor + sparse→actionable
(elicitation budget); end-to-end latency (~8–17s observed inline, confirm under load); backfill
correctness (re-extract vs retained originals).

Needs **humans / new data**: median review time (human on the review UI); elicitation abandonment (real
customers); discrepancies-surfaced (cases labelled with a known complaint-vs-record discrepancy); emergent
attribute accuracy (labelled emergent gold).

**BLOCKED:** Arabic field-extraction parity — **0/216** Arabic in the set. The marquee differentiator is
unbuilt and unmeasured (separate project).

## Bottom line

**1 trivial PASS / 4 FAIL / 1 N/A measured, convergence FAIL, 13 rows unmeasured or blocked.** A sellable
*surface* is not a passing *scorecard*. The two levers that move this:

1. **Independent held-out labels** (`eval/holdout_labels.csv`, ready) — breaks the self-labelled ceiling
   on category/confidence/review-ordering. Owner recruits an independent labeller. *Binding constraint.*
2. **A live elicitation + object-match run** — turns ~8 of the 13 UNMEASURED rows into real numbers
   without any new data (needs DB + Ollama up).
