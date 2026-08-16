# Labeling instructions — multidomain accuracy slice

96 real complaints (up to 30 per sector), of which 0 are already labelled from a prior pass (leave those rows as they are). Fill the `gold_*` columns for the REMAINING blank rows with the CORRECT answer — what a careful human says the case is, reading only the narrative. Leave a cell EMPTY to skip that field for that row (it won't be scored). Do not look at the model output first.

## Valid values (exact strings)
- **gold_category**: product_fault | service_fault | delivery_fulfilment | billing_charge | access_availability | staff_conduct | safety_health | other | UNCLEAR
  - Pick the SINGLE least-bad archetype. Use `UNCLEAR` only if the narrative is genuinely too sparse/ambiguous to classify at all — not just because the wording is unusual for the category. `service_fault` = the provider mishandled/delayed/botched a service; `product_fault` = a physical item is defective; `delivery_fulfilment` = a shipping/delivery/fulfilment problem.
- **gold_desired_outcome**: refund | replacement | repair_redo | acknowledgement | information | escalation | other | `null`
  - `null` = the customer did NOT state what they want. Pick the value only if they explicitly ask for it; if they state two, the one they say FIRST.
- **gold_severity_signal**: safety_health | vulnerable_party | financial_harm | none
  - `financial_harm` = MONETARY harm of any kind (unauthorized/disputed charge, overcharge or fee, money taken/withheld/frozen, a debt wrongly owed or reported, damaged credit, a denied/withheld refund). `none` = no monetary/safety/vulnerability harm (e.g. a plain information request, or a late/damaged item with no hazard).
- **gold_emotion_signal**: calm | frustrated | angry
- **gold_key_facts** (optional): the specific facts that SHOULD be captured, `;`-separated, as `name=value` — e.g. `charged amount=$500; account status=closed`. Used for a soft recall check (did the system capture what matters).

Then run: `uv run python eval/score.py`
