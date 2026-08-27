"""The extraction prompt — versioned (EDD §5, §7.3).

``PROMPT_VERSION`` is part of the idempotency key (§7.3) and stamped into every ``field_extraction``
row's provenance: bump it on ANY change to this text, so a re-extraction gets a fresh run and never
silently overwrites prior provenance. The instructions encode the Spike-4.0 corrections (strict
severity, stated-not-guessed outcome, closed-world grounding).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from .head_nouns import HEAD_NOUNS

# Bump on any change to the prompt text below.
PROMPT_VERSION = "extract-v23"  # v23 (SEVERITY UNDER-CALL FIX, 2026-08-27, from the Catleen+Osman independent-consensus diagnostic): the model was dropping harm to "none" on 44/49 severity errors (29 financial_harm->none) because it COUPLED severity to the chosen category — a product/service/delivery/record/access complaint defaulted severity to none, blind to the money plainly at stake (a refund/compensation being sought, a paid-for service that failed, a wrong bill/balance/credit, damaged goods). Fix = state severity is judged INDEPENDENTLY of category, add an explicit most-severe-driver precedence (safety_health > vulnerable_party > privacy_security > financial_harm > none), and name the IMPLICIT-money patterns so financial_harm fires whenever money is genuinely at stake. General rule, no eval-case-specific examples (no test-set overfitting). No enum change. v22 (owner-approved OVERLAP TIE-BREAKS from the independent-labelling review, 2026-08-27): added decided tie-breaks where two categories overlap (product_fault<->safety_health hazard wins; record_accuracy<->fraud_security by unauthorised-vs-merely-wrong; billing_charge<->misleading_practice by wrong-amount-vs-deception), desired_outcome counts only a remedy requested IN THIS message (not one merely recounted as previously asked), financial_harm has NO minimum (any disputed sum, small fee included — kills the financial_harm/none ambiguity), and sharpened emotion adjacent-boundary rules (calm/concerned/frustrated/angry/distressed) — scale kept at 5 (collapsing would discard the owner+Osman emotion gold). These resolve the exact owner-vs-Osman disagreement clusters (product/safety x12, financial_harm/none x22, adjacent-emotion). v21 (owner GOVERNED-CORE EXPANSION, 2026-08-26): taxonomy widened 1:1 to the labelling workbook's Option Sets — +transaction_processing / fraud_security / privacy_data / misleading_practice (category), +correction / cancellation / restore_access / stop_contact / compensation / investigation (desired_outcome), +privacy_security (severity), +concerned / distressed (emotion). Definitions + boundary rules follow the owner's Option Sets. NB: the "LAST category change" note below (v20) was about GRINDING existing boundaries toward owner-authored close-call gold; THIS is a NEW governed-core decision to EXPAND the enum (CLAUDE.md §4, human-controlled), not boundary-grinding. Deliberate remaps vs v20: record-correction repair_redo->correction; validate/prove a debt information->investigation; unauthorised transaction billing_charge->fraud_security. v20 (STRUCTURAL FIX, owner directive): service_fault was defined by CONDUCT, and conduct is present in EVERY complaint, so it bled into every category (lowest recall while posing as a peer). Fix = make service_fault EXPLICITLY RESIDUAL ("mishandled AND no other category's primary harm applies; the conduct itself is the harm"), and add the dominance rule THE BLOCK WINS — access_availability is a checkable STATE (blocked/frozen/closed/declined/withheld) and beats arguable service conduct when both apply; pure refusal with no block -> service_fault. Right for the product too (a block drives SLA/priority regardless of conduct). INTEGRITY: this rule is defensible on its own terms and was fixed BEFORE re-scoring; it will TRADE errors — if accuracy drops it STAYS (reverting on a fallen score = the 7th cheap-path instance). This is the LAST category prompt change: the close-call gold is owner-authored, so further grinding optimises toward label inconsistency (a gold ceiling, not a model ceiling). Category work done-for-now -> Phase 5. v19 was the off-finance synthesis; the two boundaries proved independent — v17 fixed safety (recall 11->15/17) but v18's safety tightening over-corrected into under-firing (back to 10/17), while v18 fixed delivery (service->delivery errors 8->4) that v17 barely touched. v19 keeps v17's recall-preserving SAFETY block (+ a one-line scam/fraud carve-out that killed v17's worst false-positive) AND v18's strict goods-logistics-only DELIVERY block — the best-performing general rule for each. No eval-case-specific examples (no test-set overfitting). No enum change; finance boundaries unchanged. v18 fixed delivery/broke safety; v17 first off-finance probe; v16 tightened service↔record_accuracy; v15 added record_accuracy (owner R6-C).

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
    transaction_processing = a payment, transfer, refund, deposit, or withdrawal did NOT process, \
settle, reverse, or arrive correctly — the money-MOVEMENT itself failed (a transfer stuck, a refund that \
never landed, a payment that won't go through, a deposit not credited). Distinct from billing_charge: \
billing_charge is a WRONG amount; transaction_processing is a (possibly correct) amount that did not \
COMPLETE. "It didn't go through / didn't arrive / won't reverse" -> transaction_processing; "the number \
is wrong / I was overcharged" -> billing_charge;
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
    fraud_security = fraud, a scam, account takeover, unauthorized activity, or a security compromise — \
a charge or transaction the customer did NOT authorise, a scammer, a hacked/taken-over account, \
phishing, or stolen credentials. This is its OWN class: an UNAUTHORISED transaction is fraud_security, \
NOT billing_charge (billing_charge is a dispute over a KNOWN, authorised charge's amount);
    privacy_data = the collection, disclosure, retention, or EXPOSURE of personal/sensitive data — data \
shared or leaked without consent, a breach, or improper retention. Distinct from record_accuracy: \
record_accuracy = the record is WRONG; privacy_data = the data was improperly collected, disclosed, or \
exposed (it may be accurate, but should not have been shared);
    misleading_practice = the customer was materially MISLED by advertising, pricing, terms, promises, \
representations, or a bait-and-switch — deceived about what they would get. Distinct from billing_charge \
(a wrong number) and service_fault (poor handling): here the core grievance is the DECEPTION itself;
    other = a real complaint that genuinely fits none of the above.
  Pick the least-bad fit. Use "UNCLEAR" ONLY when the message is too sparse to tell what kind of \
complaint it is at all — a true last resort, NOT because the wording is unusual for the category.
  FRAUD SUB-RULE: an unauthorised transaction, scam, account takeover, or security compromise -> \
fraud_security (its OWN class). billing_charge is only for a KNOWN, authorised charge whose AMOUNT is \
disputed; transaction_processing is a legitimate payment that FAILED to complete.
  OVERLAP TIE-BREAKS (decided rules — apply in this order when two categories both seem to fit):
   1. product_fault vs safety_health: if a product/vehicle/item defect creates a PHYSICAL-SAFETY hazard \
in use, safety_health WINS (see the PRODUCT vs SAFETY_HEALTH rule below); a defect with no hazard is \
product_fault.
   2. record_accuracy vs fraud_security: if the customer alleges the entry, charge, or account is \
UNAUTHORISED, not theirs, identity misuse, or someone else's doing -> fraud_security; if they allege it \
is merely WRONG / inaccurate / unverified / wrongly-dated (but not fraudulent) -> record_accuracy.
   3. billing_charge vs misleading_practice: if the dispute is that the AMOUNT or fee is wrong -> \
billing_charge; if the grievance is that they were DECEIVED (misleading terms, hidden conditions, \
bait-and-switch) into the charge -> misleading_practice.
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
money loss is NEVER safety_health (that is fraud_security, or billing_charge for a disputed amount).
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
asking for a specific remedy, return null. ONLY a remedy the customer is requesting IN THIS message \
counts: if they merely RECOUNT a remedy they already asked for previously ("I asked for a refund last \
week") without restating it as their ask now, that is NOT a stated outcome — return null unless they are \
making the request again here. Do NOT infer the remedy from the KIND of problem: a \
grievance about money is not, by itself, a request for a refund; filing or writing a complaint is not \
a request for escalation. Only if a remedy IS stated, map it to one value:
    refund = MONEY returned or reimbursed already paid/charged; replacement = a new or remade item; \
repair_redo = repair the issue or REDO the failed work/service (NOT correcting a record); \
acknowledgement = only an apology, ownership, or formal acknowledgement, nothing more; information = \
explain, clarify, verify status, or answer a question (NOT investigate — see investigation); escalation \
= escalate to management, a regulator, a specialist, or disciplinary action; correction = CORRECT \
inaccurate records, balances, reports, or administrative data — fix, update, remove, or delete an \
inaccurate entry (e.g. "remove this from my credit report", "correct my balance"); cancellation = \
cancel an account, order, contract, transaction, booking, or subscription; restore_access = restore \
access to an account, funds, service, or blocked functionality (unlock, reopen, reinstate); \
stop_contact = stop calls, messages, collection attempts, or other unwanted contact; compensation = pay \
for consequential loss, inconvenience, or harm BEYOND a simple refund; investigation = INVESTIGATE or \
VALIDATE the complaint, debt, transaction, or suspected wrongdoing (e.g. "validate this debt", "look \
into this"); other = a stated request that fits none of these.
  Key distinctions (the model tends to over-pick "refund"): FIX / UPDATE / DELETE an inaccurate record \
-> correction; VALIDATE or INVESTIGATE a debt or claim -> investigation; UNLOCK / REOPEN a blocked \
account -> restore_access; CANCEL a subscription or order -> cancellation; STOP contacting me -> \
stop_contact; pay me for the loss or damage caused -> compensation. None of these is a refund unless \
the customer ALSO asks for money back. If they state alternatives, choose the one they state FIRST. The \
absence of a stated remedy is null, never a guessed value.
- emotion_signal: the WRITER'S TONE, labelled INDEPENDENTLY from severity — a calm message can carry a \
severe issue. calm (factual, neutral, restrained) | concerned (worried, uneasy, questioning, without \
strong anger) | frustrated (clear dissatisfaction, exasperation, repeated effort, loss of patience) | \
angry (strong blame, hostility, outrage, insults, demands) | distressed (fear, panic, shock, acute \
worry, or emotional strain is prominent).
  EMOTION BOUNDARIES (the adjacent tones are the hard calls — decide by these): calm vs concerned — calm \
is neutral/factual with NO worry; the moment unease or worry shows, it is concerned. concerned vs \
frustrated — concerned is worry about an outcome; frustrated adds DISSATISFACTION or exasperation \
(often at repeated effort or the company's handling). frustrated vs angry — angry adds HOSTILITY, blame, \
insults, or outrage aimed at the company. angry vs distressed — angry is hostility directed OUTWARD; \
distressed is fear, panic, or emotional strain felt INWARD (even with no blame). Pick the single \
dominant tone.
- severity_signal: the SINGLE main severity DRIVER, judged INDEPENDENTLY of the category and of how \
angry the writer sounds (do not upgrade normal inconvenience into severe harm). The category is NOT the \
severity: a product_fault, service_fault, delivery_fulfilment, record_accuracy or access_availability \
complaint very often ALSO carries a monetary driver — do NOT default such a case to "none" just because \
its category is not itself a "harm" bucket. When more than one driver is present, pick the most severe \
in this order: safety_health > vulnerable_party > privacy_security > financial_harm > none (money \
outranks "none" whenever any is at stake).
    safety_health = a genuine safety/health hazard (allergen, injury risk, food poisoning, gas/\
electrical/fire hazard, unsafe operation);
    vulnerable_party = the severity is materially driven by a child, elderly, disabled, or otherwise \
vulnerable person explicitly present;
    financial_harm = MONETARY harm of ANY kind, with NO minimum. It is present — not "none" — whenever \
money is genuinely at stake, INCLUDING when the money is IMPLICIT in another kind of complaint: an \
unauthorized/disputed charge, overcharge or fee; money taken/withheld/frozen/not-released; a debt \
wrongly owed or reported, or damaged credit; a denied or withheld refund; the customer PAID for goods or \
a service that were not delivered, failed, or must be redone; a refund, compensation, recalculation or \
fee-reversal is being SOUGHT; property or goods were damaged, lost, or broken; or a bill, balance, \
credit, or payment record is wrong. A small fee counts as much as a large one; never label "none" on a \
monetary grievance because the sum is small or because the headline complaint is a defect, delay, or \
wrong record;
    privacy_security = identity, account security, sensitive information, or privacy EXPOSURE is the \
main driver (a data breach, account-takeover risk, leaked or improperly disclosed personal data);
    none = NO safety, vulnerability, monetary, or privacy/security driver at all — only normal service \
inconvenience with nothing paid-for-and-lost, sought, damaged, or owed (e.g. a late item that arrived \
with no money at stake and no refund sought, or a plain information request).
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


# Reviewer-tuned additive clarifications — proposed via the tuning digest, opened as a PR
# (scripts/open_tuning_pr.py), and merged ONLY after the eval re-scores (tuning-eval; CLAUDE.md §10).
# The file is `[]` on main → zero behaviour change and the eval is unaffected. A merged addendum also bumps
# PROMPT_VERSION (part of the idempotency key) so it re-runs and never overwrites prior provenance.
_ADDENDA_PATH = Path(__file__).resolve().parent / "tuning_addenda.json"


def _load_tuning_addenda() -> list[str]:
    """Active addenda from ``tuning_addenda.json`` (a list of ``{delta, active, ...}``). Fail-safe: any
    missing/unreadable/malformed file → no addenda, so the hand-authored core prompt always stands alone.
    """
    try:
        data = json.loads(_ADDENDA_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [
        str(e["delta"]).strip()
        for e in data
        if isinstance(e, dict) and e.get("active", True) and str(e.get("delta", "")).strip()
    ]


_TUNING_ADDENDA: list[str] = _load_tuning_addenda()


def build_prompt(
    case_text: str,
    heads: Sequence[str] = HEAD_NOUNS,
    minted_glosses: dict[str, str] | None = None,
) -> str:
    """The full extraction prompt for one case's normalised text. ``heads`` is the tenant's effective
    head vocabulary (seed + minted); it defaults to the seed so existing callers are unchanged.
    ``minted_glosses`` (head → definition) is injected as explicit guidance — the enum alone does NOT
    make the model use a minted head; it needs to know what the column MEANS or it defaults to ``other``
    (2026-08-17c live finding). Each minted head is offered with its gloss so an emerged column is used.
    """
    system = _SYSTEM.replace("<<HEADS>>", ", ".join(heads))
    if minted_glosses:
        defs = "\n".join(f"    {h} = {g}" for h, g in minted_glosses.items())
        system += (
            "\n\nThis account has LEARNED additional columns from past cases. Use one of these when a "
            "fact clearly matches it, in preference to `other`:\n" + defs
        )
    if _TUNING_ADDENDA:
        addenda = "\n".join(f"- {a}" for a in _TUNING_ADDENDA)
        system += "\n\nADDITIONAL DISAMBIGUATION (reviewer-tuned):\n" + addenda
    return f'{system}\n\nCustomer message:\n"""{case_text}"""'
