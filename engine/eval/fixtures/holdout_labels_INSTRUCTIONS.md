# Independent labelling — held-out accuracy slice

**You have been given `holdout_labels_blank.xlsx`.** Fill the **Cases** sheet. The **Option Sets** sheet
is the authoritative definition of every allowed value (definition + manager rule); the gold columns are
dropdown-validated to those values. Do **not** hand-type values — pick from the dropdown.

**Who should fill this in:** someone who is **neither the system's author nor the project owner.** The
whole point is an *independent* second opinion; if the person who wrote the prompts or the existing
labels fills it in, it measures nothing new.

**Do this blind.** Read ONLY the `narrative` column and decide the correct answer yourself. Do **not**
look at any system output, the owner's labels, or any other label file, and do not discuss a row before
labelling it. There is no answer key — your honest reading *is* the answer.

**200 cases** (66 real complaints — CFPB 36, NHTSA 14, Trustpilot 16 — plus 134 additional harder
cases). Label every row. Leave a cell EMPTY only to skip that one field for that row; an empty
`gold_desired_outcome` is a REAL label meaning "the customer did not state what they want".

## The four scored columns (pick from the dropdown; see Option Sets for each value's meaning)

- **gold_category** — the SINGLE best archetype. 14 values:
  `product_fault | service_fault | delivery_fulfilment | billing_charge | transaction_processing |
  record_accuracy | access_availability | staff_conduct | safety_health | fraud_security | privacy_data |
  misleading_practice | other | UNCLEAR`. Choose the one primary complaint, not every issue mentioned.
  `UNCLEAR` is for positive/neutral entries, hearsay, or genuinely insufficient information — never
  invent a complaint.
- **gold_desired_outcome** — the remedy the customer EXPLICITLY asks for, else leave EMPTY (= null). 13
  values: `refund | replacement | repair_redo | acknowledgement | information | escalation | correction |
  cancellation | restore_access | stop_contact | compensation | investigation | other`. Pick a value
  ONLY if a remedy is explicitly requested; if two are stated, the one said FIRST. Dissatisfaction alone
  is **not** a request for a refund. (Note the fine distinctions in Option Sets: correcting a record =
  `correction`; validating/investigating a debt = `investigation`; unlocking a blocked account =
  `restore_access`; cancelling = `cancellation`; stopping contact = `stop_contact`; paying for
  consequential loss beyond a refund = `compensation`.)
- **gold_severity_signal** — the MAIN harm driver, judged by the harm and **not** by how angry the writer
  sounds. 5 values: `safety_health | vulnerable_party | financial_harm | privacy_security | none`. Do not
  upgrade normal inconvenience into severe harm.
- **gold_emotion_signal** — the writer's TONE, labelled INDEPENDENTLY of severity (a calm message can
  carry a severe issue). 5 values: `calm | concerned | frustrated | angry | distressed`.

## Optional

- **gold_key_facts** — the concrete facts that SHOULD be captured, `;`-separated as `name=value`, e.g.
  `charged amount=$500; account status=closed`. NOT scored (a soft recall check) — you may skip it.

## Labelling principles (the ones that make the two-annotator agreement meaningful)

1. Desired outcome is populated ONLY when the customer explicitly asks for something; the first requested
   remedy wins when several are mentioned; an empty cell is the real label "no remedy stated".
2. Severity is the main harm driver, not the writer's anger.
3. Emotion (tone) is judged independently of severity.
4. `UNCLEAR` is for positive/neutral/hearsay/insufficient cases, not for wording that is merely unusual.

When it comes back, the owner exports your file to `holdout_labels_<yourname>.csv` and scores it — your
labels become the independent accuracy number (model vs you) and the human ceiling (owner vs you).
