# Product-evidence runbook

This pack makes pilot-learning and general-availability evidence repeatable without pretending it has
already passed. Independent labels and unassisted stranger sessions are not controlled-pilot entry gates
under winning-condition v0.2; they remain required before broad quality/onboarding claims. Freeze the
commit, model, policy, inputs and thresholds before a run. There are **no session-capture spreadsheets**:
a person using the product is measured by the product (see the last section); the only labelling artifact
is the workbook `engine/eval/fixtures/holdout_labels.xlsx` (exported to `holdout_labels_<name>.csv` for
scoring). Help requests, abandonment, and observer notes are the only things the instrumentation cannot
see — they are recorded out-of-band as a short free-text note, never inferred from a successful
`review_event` row.

## Independent holdout

Give only `engine/eval/fixtures/holdout_labels.xlsx` to a non-builder labeller — the **Cases** sheet is
filled, **Option Sets** defines the allowed values (dropdown-validated) and their manager rules, and
**QA Summary** tracks distribution. Do not show model outputs. A second person adjudicates uncertain rows.
Export the completed Cases sheet to `engine/eval/fixtures/holdout_labels_<name>.csv` (e.g.
`holdout_labels_owner.csv`), hash/freeze it, then run `cd engine && uv run python eval/score_holdout.py`.
Record disagreements as well as aggregate scores. The gold taxonomy is a **superset** of the extractor's
enums, so category/outcome accuracy is honestly capped until the governed enum is expanded and history
re-extracted — that gap is the signal, not something to hide by collapsing gold.

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

For each person: use their own messy input, provide no walkthrough, keep the builder silent. **They use
the same product a reviewer does, so the session instruments itself** — the case lifecycle records intake
→ review → approval → report and `review_event` records the time; read it off the API the same way (`GET
/api/review-stats`, the case record), not a spreadsheet. The only things worth capturing by hand are the
conversational signals the software cannot see — an unsolicited reaction, a price or feature question,
whether they needed help or gave up — and those are a free-text note. Treat price questions and feature
requests as discovery signals, not pass/fail software criteria. Consent to record and retention/deletion
must be settled before the session.

## What the system already measures (do not re-capture by hand)

Before adding any capture template, check whether the product already instruments it. It does, for most
of this: `review_event` + `GET /api/review-stats` give count/median/p90 review time and average fields
edited; the append-only `field_correction` log + `GET /api/review-breakdown` give per-field correction
pressure; the eval scorer gives field/category accuracy against gold. **A reviewer using the product is
the measurement** — and so is a stranger onboarding, because they run the same product. Only genuinely
external observations justify manual capture — reactions, price questions, help requests, abandonment,
observer notes — and those are a free-text note, not a spreadsheet. (All three session templates —
`reviewer-session-template.csv`, `voice-pair-template.csv` and `stranger-session-template.csv` — were
removed for exactly this reason: a person using the self-instrumenting product never needs a structured
capture form. The mechanical parts are in the API; the handful of external observations are a note.)

## Evidence integrity

Every result records UTC date, commit SHA, environment, model/version, dataset hash, observer, participant
relationship, raw artifact links, exclusions and failures. A blank, coached, self-labelled, synthetic or
post-tuning holdout row is not independent GA evidence; it may still be clearly labelled engineering or
pilot-learning evidence.
