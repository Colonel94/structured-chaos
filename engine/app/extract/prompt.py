"""The extraction prompt — versioned (EDD §5, §7.3).

``PROMPT_VERSION`` is part of the idempotency key (§7.3) and stamped into every ``field_extraction``
row's provenance: bump it on ANY change to this text, so a re-extraction gets a fresh run and never
silently overwrites prior provenance. The instructions encode the Spike-4.0 corrections (strict
severity, stated-not-guessed outcome, closed-world grounding).
"""

from __future__ import annotations

from .head_nouns import HEAD_NOUNS

# Bump on any change to the prompt text below.
PROMPT_VERSION = "extract-v12"  # v12: capture the named organization (bank/agency/collector) as a structured `organization` fact — the model was putting it only in `fault`, missing ~30/51 org key-facts. Outcome block unchanged from v11.

_SYSTEM = """You extract a structured complaint case from a customer message. Extract ONLY what the \
message states or directly implies. NEVER invent facts, names, numbers, or outcomes.

Fields:
- category: the SINGLE best archetype (universal, domain-agnostic — the same list serves a bakery \
and a bank). Definitions:
    product_fault = a physical item/product is defective or poor quality;
    service_fault = a service was done wrong, mishandled, delayed by the provider, or not as promised \
(includes a company mishandling a dispute, request, claim, or account);
    delivery_fulfilment = a problem with delivery, shipping, or fulfilment of an order;
    billing_charge = a disputed charge, fee, overcharge, debt, refund, or billing/payment/reporting \
problem;
    access_availability = trouble accessing or using an account, funds, or service (locked, frozen, \
closed, blocked, unavailable);
    staff_conduct = the behaviour/conduct of a specific person or agent is the complaint;
    safety_health = a genuine safety or health hazard;
    other = a real complaint that genuinely fits none of the above.
  Pick the least-bad fit. Use "UNCLEAR" ONLY when the message is too sparse to tell what kind of \
complaint it is at all — a true last resort, NOT because the wording is unusual for the category.
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
SPECIFIC head that fits: a money value → amount/fee/rate/balance; a calendar date → date; a clock time \
→ time; a state like open/closed/declined → status; a company/bank/agency → organization; a person → \
person; an id/reference number → identifier; a count → count; how long → duration. Use "description" \
or "other" ONLY as a last resort when NO specific head fits — never as a place to dump a sentence or a \
complaint. If a fact would land in "description" as a whole clause, drop it instead. ALWAYS capture \
the named organization the complaint is about or names — the company, bank, agency, lender, or debt \
collector — as an "organization" fact, whenever a real name is given (skip a fully-redacted XXXX).
    * qualifier = a SHORT phrase (1-3 words) COPIED VERBATIM from the message — the exact words as \
they appear, contiguous — that makes the fact specific, or null if the head alone is enough. Do NOT \
paraphrase, reword, reorder, or summarise: if you cannot copy a contiguous phrase straight from the \
message, use null. Examples: for "$500 was charged" use head="amount", qualifier="charged"; for "my \
pension was deposited" use head="amount", qualifier="pension"; for "the box was crushed" use \
head="condition", qualifier="box"; for "delivered at 6pm" use head="time", qualifier="delivered".
    * value = the specific value from the message (the number, date, name, or short phrase — not a \
sentence).
  Put the SPECIFICITY in the qualifier, NOT in the head — do not invent new heads. Include ONLY facts \
actually present in the message; every qualifier and value must come from the text. No inferred or \
generic fields. Prefer FEWER, cleaner structured facts over many narrative ones.

Return JSON only."""


def build_prompt(case_text: str) -> str:
    """The full extraction prompt for one case's normalised text."""
    system = _SYSTEM.replace("<<HEADS>>", ", ".join(HEAD_NOUNS))
    return f'{system}\n\nCustomer message:\n"""{case_text}"""'
