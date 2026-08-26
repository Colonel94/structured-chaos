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
approve only what matches the source.” Start the clock when the queue appears; stop per case at approval
or abandonment. Record every correction, help request and error in `evidence/reviewer-session-template.csv`.
Pass only if the representative-case median is at most 30 seconds; report p90 and sample size too.

## Sparse and voice sets

- Sparse: collect at least 20 real complaints containing no more than one useful fact beyond intent. Freeze
  the input and label whether the final case became actionable, reused stated data, asked for derivable
  data, captured outcome and was abandoned. Synthetic cases may test code but cannot pass the market gate.
- Voice parity: record at least 30 paired cases where the same speaker provides the same facts in a typed
  and a natural voice version. Include real phone containers/codecs/noise. Score governed fields using
  `evidence/voice-pair-template.csv`; the absolute field-accuracy gap must be at most five percentage points.

## Unassisted onboarding study

For each person: use their own messy input, provide no walkthrough, keep the builder silent, and record
time to first value plus exact unsolicited reactions in `evidence/stranger-session-template.csv`. Treat
price questions and feature requests as discovery signals, not pass/fail software criteria. Consent to
record and retention/deletion must be settled before the session.

## Evidence integrity

Every result records UTC date, commit SHA, environment, model/version, dataset hash, observer, participant
relationship, raw artifact links, exclusions and failures. A blank, coached, self-labelled, synthetic or
post-tuning holdout row is not independent GA evidence; it may still be clearly labelled engineering or
pilot-learning evidence.
