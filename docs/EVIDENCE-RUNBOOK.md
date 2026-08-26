# Product-evidence runbook

This pack makes pilot-learning and general-availability evidence repeatable without pretending it has
already passed. Independent labels and unassisted stranger sessions are not controlled-pilot entry gates
under winning-condition v0.2; they remain required before broad quality/onboarding claims. Copy templates
into a dated evidence directory and freeze the commit, model, policy, inputs and thresholds before a run.

## Independent holdout

Give only `engine/eval/fixtures/holdout_labels.csv` and its instructions to a non-builder labeller. Do not
show model outputs. A second person adjudicates uncertain rows. Hash/freeze the completed file, then run
`cd engine && uv run python eval/score_holdout.py`. Record disagreements as well as aggregate scores.

## Cold reviewer timing

Use at least three people who have not used the product. Give one sentence: “Review these cases and
approve only what matches the source.” **The system instruments the session itself** — every approval
writes an append-only `review_event` row carrying `review_ms` and `fields_edited`, and the live HUD
shows the running median. After the session, read `GET /api/review-stats` and record the commit SHA,
`count` (n), `median_ms` and `p90_ms`. Pass only if the representative-case median is at most 30
seconds. Do **not** hand-log per-case times into a spreadsheet — a reviewer using the product *is* the
measurement, and re-typing it back into a form is the exact thing this product exists to eliminate.
The only things the instrumentation cannot see are **help requests, abandonment, and observer notes**;
capture those three on a sticky note.

## Sparse and voice sets

- Sparse: collect at least 20 real complaints containing no more than one useful fact beyond intent. Freeze
  the input and label whether the final case became actionable, reused stated data, asked for derivable
  data, captured outcome and was abandoned. Synthetic cases may test code but cannot pass the market gate.
- Voice parity: record at least 30 paired cases where the same speaker provides the same facts in a typed
  and a natural voice version, over real phone containers/codecs/noise. Run both cases through extraction
  and score EACH against the frozen gold with the same scorer as the holdout (`eval/score_holdout.py`);
  the absolute field-accuracy gap is **computed by the scorer, not hand-counted**, and must be at most
  five percentage points. The recording conditions (container/codec/noise) are inputs you choose when you
  record, not measurements to log — so no per-pair spreadsheet is needed.

## Unassisted onboarding study

For each person: use their own messy input, provide no walkthrough, keep the builder silent, and record
time to first value plus exact unsolicited reactions in `evidence/stranger-session-template.csv`. Treat
price questions and feature requests as discovery signals, not pass/fail software criteria. Consent to
record and retention/deletion must be settled before the session.

## What the system already measures (do not re-capture by hand)

Before adding any capture template, check whether the product already instruments it. It does, for most
of this: `review_event` + `GET /api/review-stats` give count/median/p90 review time and average fields
edited; the append-only `field_correction` log + `GET /api/review-breakdown` give per-field correction
pressure; the eval scorer gives field/category accuracy against gold. **A reviewer using the product is
the measurement.** Only genuinely external observations justify manual capture — reactions, price
questions, help requests, abandonment, observer notes — and those are a sticky note, not a 14-column
spreadsheet. (The former `reviewer-session-template.csv` and `voice-pair-template.csv` were removed for
exactly this reason: they re-typed instrumented data into a form, the thing this product exists to kill.
Only `stranger-session-template.csv` remains, because reactions and price questions are not
instrumentable.)

## Evidence integrity

Every result records UTC date, commit SHA, environment, model/version, dataset hash, observer, participant
relationship, raw artifact links, exclusions and failures. A blank, coached, self-labelled, synthetic or
post-tuning holdout row is not independent GA evidence; it may still be clearly labelled engineering or
pilot-learning evidence.
