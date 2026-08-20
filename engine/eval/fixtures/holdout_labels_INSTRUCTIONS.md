# Independent labelling — held-out accuracy slice

**Who should fill this in:** someone who is **neither the system's author nor the project owner.** The whole point of this sheet is an *independent* second opinion; if the person who wrote the prompts or the existing labels fills it in, it measures nothing new.

**Do this blind.** Read ONLY the `narrative` column and decide the correct answer yourself. Do **not** look at any system output, any other label file, or discuss a row before labelling it. There is no answer key — your honest reading *is* the answer.

**66 real complaints**, held out from the cases the system was built on (sources: CFPB 36, NHTSA 14, Trustpilot 16). Fill the `gold_*` columns for each row. Leave a cell EMPTY only to skip that one field for that row (it won't be scored); an empty `gold_desired_outcome` is a REAL label meaning "the customer did not state what they want".

## Valid values (type the exact string)
- **gold_category** — the SINGLE best archetype: product_fault | service_fault | delivery_fulfilment | billing_charge | record_accuracy | access_availability | staff_conduct | safety_health | other | UNCLEAR
    - `product_fault` = a physical item is defective / poor quality (no safety hazard).
    - `service_fault` = the company mishandled, ignored, delayed, or botched something, and no other category's harm fits better (the conduct itself is the harm).
    - `delivery_fulfilment` = a shipping / delivery / fulfilment problem with goods (parcel late, lost, damaged, wrong item) — NOT any order-related complaint.
    - `billing_charge` = a specific charge, fee, amount, or balance is WRONG (the dispute is about the number / money back).
    - `record_accuracy` = a record the company holds/publishes ABOUT the customer is inaccurate / unverified / wrongly dated (a credit entry, a reported balance, a late marker) and the ask is verify / correct / delete — NOT money.
    - `access_availability` = an account, funds, or service is in a currently BLOCKED state (locked, frozen, closed, declined, withheld, unreachable).
    - `staff_conduct` = a specific person's behaviour is the complaint.
    - `safety_health` = a genuine physical safety or health hazard.
    - `other` = a real complaint fitting none of the above. `UNCLEAR` = too sparse to tell what kind of complaint it is at all (a true last resort).
- **gold_desired_outcome** — refund | replacement | repair_redo | acknowledgement | information | escalation | other | leave EMPTY for `null`
    - Pick a value ONLY if the customer explicitly asks for a remedy; if they state two, the one they say FIRST. A grievance about money is not by itself a request for a refund. `refund` = money back; `repair_redo` = redo the work OR correct a record; `information` = an answer / status / validation; `replacement` = a new item; `escalation` = a manager / formal escalation; `acknowledgement` = only an apology.
- **gold_severity_signal** — safety_health | vulnerable_party | financial_harm | none
    - `financial_harm` = monetary harm of any kind (disputed charge, fee, money taken/withheld/frozen, debt wrongly owed/reported, damaged credit, denied refund). `safety_health` = physical safety/health risk. `vulnerable_party` = a child/elderly/disabled person at risk. `none` = none of these.
- **gold_emotion_signal** — calm | frustrated | angry (from the tone).
- **gold_key_facts** (optional) — the concrete facts that SHOULD be captured, `;`-separated as `name=value`, e.g. `charged amount=$500; account status=closed`. Used for a soft recall check.
