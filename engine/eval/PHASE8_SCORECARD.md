# Phase 8 — independent quality scorecard

*Snapshot: 27 August 2026 at revision `10b95cf`. The executable scorer is the source of truth.*

## Reproduce the results

From `engine/`, run the complete pairwise report:

```powershell
uv run python eval/score_holdout.py
```

Run the independent-consensus headline explicitly:

```powershell
uv run python eval/score_holdout.py --consensus `
  catleen=eval/fixtures/holdout_labels_catleen.csv `
  osman=eval/fixtures/holdout_labels_osman.csv
```

Consensus uses **no adjudication or invented tie-break**. For each field, a case enters the denominator
only when Catleen and Osman both labelled it and selected the same value. Human disagreements are
excluded for that field. A blank desired outcome is the explicit null label when both sources used the
column. The denominator therefore differs by field and must always be printed with the percentage.

## Evidence status

Independent labelling is **complete**, not outstanding:

- Osman, an independent complaints-resolution director, labelled all 200 cases.
- Catleen, an independent customer-care director, labelled all 200 cases.
- The owner labels remain development evidence and are not used in the independent-consensus headline.
- Model extractions cover all 200 labelled cases and use `extract-v22`.
- Confidence artifact `calib-v3` is fitted from the two-expert consensus for honest review ordering;
  autonomous routing remains disabled.

## Independent human agreement

| Field | Agreement | Rate |
|---|---:|---:|
| Category | 185/200 | **92%** |
| Desired outcome | 182/200 | **91%** |
| Severity | 188/200 | **94%** |
| Emotion | 166/200 | **83%** |
| All four fields on the same row | 134/200 | **67%** |

This establishes that the governed taxonomy is consistently usable by independent domain experts. The
owner's earlier labels, particularly emotion, are not the human ceiling.

## Model agreement with each independent reviewer

| Field | Model vs Catleen | Model vs Osman |
|---|---:|---:|
| Category | 147/200 (74%) | 153/200 (76%) |
| Desired outcome | 153/200 (76%) | 153/200 (76%) |
| Severity | 146/200 (73%) | 143/200 (72%) |
| Emotion | 139/200 (70%) | 142/200 (71%) |
| All four fields on the same row | 57/200 (28%) | 64/200 (32%) |

## Official independent-consensus headline

| Field | Model correct / independent-agreement subset | Rate |
|---|---:|---:|
| Category | **143/185** | **77%** |
| Desired outcome | **147/182** | **81%** |
| Severity | **139/188** | **74%** |
| Emotion | **125/166** | **75%** |

The extractor trails the independent human agreement level on every field. Severity has the largest
gap. The failed `extract-v23` severity experiment was reverted, and extractor prompt tuning is frozen at
`extract-v22`; additional prompt variants against these same labels would turn the holdout into training
data.

## Decision relevance

- **Controlled pilot:** these accuracy results do not block a narrow pilot because mandatory human
  review remains on for every case and autonomous routing remains disabled.
- **General availability:** current category, desired-outcome and governed-field quality remain below
  the objectives in `winning-condition.md`. Broader claims wait for chosen-market representativeness and
  stronger extraction quality.
- **Claims:** describe the product as human-supervised complaint drafting and evidence review, not
  autonomous complaint adjudication.

## Other measured trust and workflow evidence

The deterministic supporting evaluations remain reproducible through their own commands:

- `eval/measure_elicit.py`: the anchor-plus-two budget holds; the prior 216-case run asked for already
  stated information 0/216 times.
- `eval/measure_object_match.py`: the prior objective-key run recorded 0 wrong silent binds across 311
  silent matches and 311/311 recall on resolvable cases.
- `eval/score_phase8.py`: retains the older self-labelled development diagnostics; those numbers must not
  replace the independent results above.

## Remaining evidence work

- Confirm at least 100 cases represent the chosen GA launch market.
- Measure review time and correction pressure with real operators during the controlled pilot.
- Exercise sparse and voice/text populations before making claims about them.
- Keep `calib-v3` tied to the frozen extractor and label provenance; refit only when either changes.
