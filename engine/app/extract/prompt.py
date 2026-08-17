"""The extraction prompt — versioned (EDD §5, §7.3).

``PROMPT_VERSION`` is part of the idempotency key (§7.3) and stamped into every ``field_extraction``
row's provenance: bump it on ANY change to this text, so a re-extraction gets a fresh run and never
silently overwrites prior provenance. The instructions encode the Spike-4.0 corrections (strict
severity, stated-not-guessed outcome, closed-world grounding).
"""

from __future__ import annotations

from collections.abc import Sequence

from .head_nouns import HEAD_NOUNS

# Bump on any change to the prompt text below.
PROMPT_VERSION = "extract-v20"  # v20 (STRUCTURAL FIX, owner directive): service_fault was defined by CONDUCT, and conduct is present in EVERY complaint, so it bled into every category (lowest recall while posing as a peer). Fix = make service_fault EXPLICITLY RESIDUAL ("mishandled AND no other category's primary harm applies; the conduct itself is the harm"), and add the dominance rule THE BLOCK WINS — access_availability is a checkable STATE (blocked/frozen/closed/declined/withheld) and beats arguable service conduct when both apply; pure refusal with no block -> service_fault. Right for the product too (a block drives SLA/priority regardless of conduct). INTEGRITY: this rule is defensible on its own terms and was fixed BEFORE re-scoring; it will TRADE errors — if accuracy drops it STAYS (reverting on a fallen score = the 7th cheap-path instance). This is the LAST category prompt change: the close-call gold is owner-authored, so further grinding optimises toward label inconsistency (a gold ceiling, not a model ceiling). Category work done-for-now -> Phase 5. v19 was the off-finance synthesis; the two boundaries proved independent — v17 fixed safety (recall 11->15/17) but v18's safety tightening over-corrected into under-firing (back to 10/17), while v18 fixed delivery (service->delivery errors 8->4) that v17 barely touched. v19 keeps v17's recall-preserving SAFETY block (+ a one-line scam/fraud carve-out that killed v17's worst false-positive) AND v18's strict goods-logistics-only DELIVERY block — the best-performing general rule for each. No eval-case-specific examples (no test-set overfitting). No enum change; finance boundaries unchanged. v18 fixed delivery/broke safety; v17 first off-finance probe; v16 tightened service↔record_accuracy; v15 added record_accuracy (owner R6-C).

_SYSTEM = """You extract a structured complaint case from a customer message. Extract ONLY what the \
message states or directly implies. NEVER invent facts, names, numbers, or outcomes.

Fields:
- category: the SINGLE best archetype (universal, domain-agnostic — the same list serves a bakery \
and a bank). Definitions:
    product_fault = a physical item/product is defective or poor quality;
    service_fault = the RESIDUAL class: the company mishandled, ignored, delayed, or botched something \
AND no other category's primary harm applies. Use ONLY when the CONDUCT ITSELF is the harm (jerked me \
around, never responded, refused to investigate, failed to act). It is NOT a peer category — if a \
concrete harm fits another class (a wrong charge, an inaccurate record, a currently blocked account, a \
failed delivery, a safety hazard, a specific person's behaviour), pick THAT, never service_fault;
    delivery_fulfilment = a problem with delivery, shipping, or fulfilment of an order;
    billing_charge = a specific CHARGE, fee, amount, or balance is WRONG. The dispute is about THE \
NUMBER (an overcharge, a fee, a debt wrongly owed, money to be returned);
    record_accuracy = a RECORD the company holds or publishes ABOUT THE CUSTOMER is inaccurate, \
unverified, improperly disclosed, or improperly dated — a credit file entry, a tradeline, a reported \
balance, a late marker, an account status. The ask is VERIFY / CORRECT / DELETE, not money. ("this is \
falsely reporting on my credit", "remove this inaccurate item", "validate this debt", "re-aged / wrong \
date opened");
    access_availability = an account, funds, or service is in a currently BLOCKED STATE — locked, \
frozen, closed, declined, withheld, restricted, or otherwise unreachable. This is a STATE (objectively \
checkable) and it WINS over service_fault when both apply: if anything is currently blocked / frozen / \
closed / declined / withheld, pick access_availability EVEN IF the company also mishandled it; only a \
pure refusal with NO actual block is service_fault;
    staff_conduct = the behaviour/conduct of a specific person or agent is the complaint;
    safety_health = a genuine safety or health hazard;
    other = a real complaint that genuinely fits none of the above.
  Pick the least-bad fit. Use "UNCLEAR" ONLY when the message is too sparse to tell what kind of \
complaint it is at all — a true last resort, NOT because the wording is unusual for the category.
  FRAUD SUB-RULE: an unauthorised transaction is a wrong charge -> billing_charge, UNLESS the \
customer's own framing is about the company's CONDUCT rather than the money (then service_fault).
  TIEBREAK (classify by the PRIMARY harm; service_fault is the RESIDUAL, chosen only when nothing else \
fits): a currently blocked / frozen / closed / declined / withheld account or funds -> \
access_availability (a checkable STATE beats arguable conduct); money back -> billing_charge; fix / \
correct / delete my file or record -> record_accuracy; pure runaround with no concrete harm above -> \
service_fault.
  SERVICE vs RECORD_ACCURACY (the common confusion — apply carefully): pick record_accuracy ONLY when \
the customer alleges a specific RECORD IS INACCURATE / unverified / wrongly-dated and asks to correct, \
verify, or delete IT. If the grievance is the company's CONDUCT — won't respond, keeps contacting me, \
refuses to act, WITHHOLDS documents or records, gives the runaround, cease-and-desist — pick \
service_fault EVEN IF an account, debt, credit, or report is mentioned. Merely mentioning "account", \
"credit", or "records" is NOT record_accuracy; the record itself must be alleged WRONG.
  PRODUCT vs SAFETY_HEALTH (apply carefully): if a product, vehicle, or item defect creates a \
PHYSICAL-SAFETY hazard in use — loss of control, cannot brake / steer / accelerate, stalls or loses \
power in traffic, fire / electrical / gas / smoke, allergen, injury or crash risk — pick safety_health, \
NOT product_fault, even though a product is involved. product_fault is a defect or poor quality with NO \
safety hazard (it simply doesn't work well, is worn, or underperforms). A financial scam, fraud, or \
money loss is NEVER safety_health (that is billing_charge or service_fault).
  DELIVERY vs SERVICE (apply carefully): delivery_fulfilment is STRICTLY the shipment / logistics of \
goods failing as the standalone grievance — a parcel that never arrived, arrived late, arrived damaged, \
or was the wrong item, with no larger complaint around it. It is NOT a catch-all for anything involving \
an order. A service performed poorly (a stay, a repair visit, a meal served, a booking), a venue or \
property problem (uncleaned, broken fixtures, a leak), a botched replacement or install, a returns / \
refund runaround, an unreachable company, or any dissatisfaction with the company's overall HANDLING is \
service_fault, NOT delivery_fulfilment, EVEN IF an order, booking, or delivery appears in the story.
- fault: one sentence — what specifically went wrong, grounded in the message.
- desired_outcome: what the customer wants done — but ONLY if they explicitly ask for it. Decide \
first: did they actually state a request or instruction (e.g. "I want a refund", "please reverse \
this", "I am requesting...")? If the message only describes or disputes the problem, or vents, without \
asking for a specific remedy, return null. Do NOT infer the remedy from the KIND of problem: a \
grievance about money is not, by itself, a request for a refund; filing or writing a complaint is not \
a request for escalation. Only if a remedy IS stated, map it to one value:
    refund = MONEY returned or reimbursed to the customer (a payment back); replacement = a new/remade \
item; repair_redo = redo or fix the work, OR CORRECT A RECORD — fix, update, remove, or delete an \
inaccurate entry, balance, or report item (e.g. "remove this from my credit report", "correct my \
balance"); this is NOT a refund; escalation = warranty honoured, a manager, or formal escalation; \
information = an answer, a status, or VALIDATION/PROOF/documentation of something (e.g. "validate this \
debt", "verify this account"); acknowledgement = only an apology/recognition, nothing more; other = a \
stated request that fits none of these.
  Key distinction (the model tends to over-pick "refund"): a request to FIX, UPDATE, or DELETE an \
inaccurate record/report is repair_redo, and a request to VALIDATE or PROVE a debt is information — \
neither is a refund unless the customer ALSO asks for money back. If they state alternatives, choose \
the one they state FIRST. The absence of a stated remedy is null, never "acknowledgement", \
"escalation", or "other".
- emotion_signal: calm | frustrated | angry, from the tone.
- severity_signal: pick the SINGLE most serious that applies.
    safety_health = a genuine safety/health hazard (allergen, injury risk, food poisoning, gas/\
electrical/fire hazard);
    vulnerable_party = a child, elderly, disabled, or otherwise vulnerable person is at risk;
    financial_harm = MONETARY harm of ANY kind — an unauthorized/disputed charge, an overcharge or \
fee, money taken/withheld/frozen, a debt wrongly owed or reported, damaged credit, or a denied/\
withheld refund or payment (not only a "charge");
    none = no safety, vulnerability, or monetary harm (e.g. a late/damaged item with no hazard, or a \
plain information request).
- anchor_value: any explicit key the customer stated (order #, job #, booking/tracking ref), else null.
- emergent_attributes: specific STRUCTURED facts worth putting in a table, each as \
{"head","qualifier","value"}. A fact is ONE concrete value — a number, amount, date, name, status, or \
short phrase — NOT a sentence, an opinion, an allegation, or a restatement of the complaint (the story \
is already captured in "fault"). If something is just narrative, leave it out.
    * head = the column this fact belongs in, chosen from this CLOSED list: <<HEADS>>. Choose the MOST \
SPECIFIC head that GENUINELY fits: a money value → amount/fee/rate/balance; a calendar date → date; a \
clock time → time; a state like open/closed/declined → status; a company/bank/agency → organization; a \
person → person; an id/reference number → identifier; a count → count; how long → duration. \
PREFER "other" to force-fitting a fact into a head that does not really match: a flagged new kind of \
thing is more useful than a wrong mapping, and "other" is how genuinely-new concepts are surfaced. For \
example, a CREDIT SCORE or its change is NOT an amount of money — it has no head in this list, so use \
"other", never "amount". Use "description" only for a single concrete value that fits no other head — \
NEVER for a sentence or a clause; if a fact would land in "description" as a whole clause, drop it. \
ALWAYS capture the named organization the complaint is about or names — the company, bank, agency, \
lender, or debt collector — as an "organization" fact, whenever a real name is given (skip a \
fully-redacted XXXX).
    * qualifier = a SHORT LABEL (1-3 words) that says WHICH KIND of this head the fact is — COPIED \
VERBATIM from the message (the exact contiguous words), or null if the head alone is enough. The \
qualifier is a category label, NEVER the value itself: do NOT put a number, amount, date, name, id, or \
the value's own content in the qualifier — those belong in "value". If the only phrase you could copy \
is the value itself, use null. Do NOT paraphrase, reword, reorder, or summarise; if you cannot copy a \
contiguous LABEL phrase, use null. Examples: for "$500 was charged" → head="amount", \
qualifier="charged", value="$500" (NOT qualifier="$500"); for "my pension was deposited" → \
head="amount", qualifier="pension"; for "the box was crushed" → head="condition", qualifier="box"; \
for "delivered at 6pm" → head="time", qualifier="delivered", value="6pm".
    * value = the specific value from the message (the number, date, name, or short phrase — not a \
sentence). If the value is entirely redacted (only XXXX with no real content), OMIT the whole fact.
  Put the SPECIFICITY in the qualifier LABEL, NOT in the head, and the CONTENT in the value — do not \
invent new heads. Include ONLY facts actually present in the message; every qualifier and value must \
come from the text. No inferred or generic fields. Prefer FEWER, cleaner structured facts over many \
narrative ones.

Return JSON only."""


def build_prompt(
    case_text: str,
    heads: Sequence[str] = HEAD_NOUNS,
    minted_glosses: dict[str, str] | None = None,
) -> str:
    """The full extraction prompt for one case's normalised text. ``heads`` is the tenant's effective
    head vocabulary (seed + minted); it defaults to the seed so existing callers are unchanged.
    ``minted_glosses`` (head → definition) is injected as explicit guidance — the enum alone does NOT
    make the model use a minted head; it needs to know what the column MEANS or it defaults to ``other``
    (2026-08-17c live finding). Each minted head is offered with its gloss so an emerged column is used."""
    system = _SYSTEM.replace("<<HEADS>>", ", ".join(heads))
    if minted_glosses:
        defs = "\n".join(f"    {h} = {g}" for h, g in minted_glosses.items())
        system += (
            "\n\nThis account has LEARNED additional columns from past cases. Use one of these when a "
            "fact clearly matches it, in preference to `other`:\n" + defs
        )
    return f'{system}\n\nCustomer message:\n"""{case_text}"""'
