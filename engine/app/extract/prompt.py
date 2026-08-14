"""The extraction prompt — versioned (EDD §5, §7.3).

``PROMPT_VERSION`` is part of the idempotency key (§7.3) and stamped into every ``field_extraction``
row's provenance: bump it on ANY change to this text, so a re-extraction gets a fresh run and never
silently overwrites prior provenance. The instructions encode the Spike-4.0 corrections (strict
severity, stated-not-guessed outcome, closed-world grounding).
"""

from __future__ import annotations

from .head_nouns import HEAD_NOUNS

# Bump on any change to the prompt text below.
PROMPT_VERSION = (
    "extract-v6"  # v6: category definitions + least-bad-fit policy (was 8% -> 65% on gold)
)

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
- desired_outcome: what the customer explicitly asks for, mapped to one value:
    refund = money back; replacement = a new/remade item; repair_redo = redo/revisit/fix the work \
again; escalation = warranty honoured, manager, or formal escalation; information = an answer/status; \
acknowledgement = only an apology/recognition, nothing more; other = none of these.
  If they state alternatives, choose the one they state FIRST. If they do NOT say what they want, \
return null — do NOT default to "acknowledgement".
- emotion_signal: calm | frustrated | angry, from the tone.
- severity_signal: use "safety_health" ONLY for a genuine safety/health hazard (allergen, injury \
risk, food poisoning, gas/electrical/fire hazard). Use "financial_harm" for a disputed charge/\
overcharge. Use "vulnerable_party" only if a child/elderly/disabled person is at risk. Otherwise \
"none". A late or damaged product with no hazard is "none".
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
complaint. If a fact would land in "description" as a whole clause, drop it instead.
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
