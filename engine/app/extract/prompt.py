"""The extraction prompt — versioned (EDD §5, §7.3).

``PROMPT_VERSION`` is part of the idempotency key (§7.3) and stamped into every ``field_extraction``
row's provenance: bump it on ANY change to this text, so a re-extraction gets a fresh run and never
silently overwrites prior provenance. The instructions encode the Spike-4.0 corrections (strict
severity, stated-not-guessed outcome, closed-world grounding).
"""

from __future__ import annotations

from .head_nouns import HEAD_NOUNS

# Bump on any change to the prompt text below.
PROMPT_VERSION = "extract-v3"  # v3: head/qualifier/value emergent attributes (Path A)

_SYSTEM = """You extract a structured complaint case from a customer message. Extract ONLY what the \
message states or directly implies. NEVER invent facts, names, numbers, or outcomes.

Fields:
- category: the single best archetype. Use "UNCLEAR" if the message is too sparse to classify.
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
- emergent_attributes: specific facts worth structuring, each as {"head","qualifier","value"}:
    * head = the column this fact belongs in, chosen from this CLOSED list (pick the closest; use \
"other" only if nothing fits): <<HEADS>>.
    * qualifier = one or two words that make the fact specific, or null if the head alone is enough. \
The qualifier MUST be words taken from the message. Examples: for "$500 was charged" use \
head="amount", qualifier="charged"; for a pension deposit use head="amount", qualifier="pension"; for \
the box being crushed use head="condition", qualifier="packaging" (or "box"); for when it was \
delivered use head="time", qualifier="delivered".
    * value = the actual value from the message (the number, date, name, phrase).
  Put the SPECIFICITY in the qualifier, NOT in the head — do not invent new heads. Include ONLY facts \
actually present in the message; every qualifier and value must come from the text. No inferred or \
generic fields.

Return JSON only."""


def build_prompt(case_text: str) -> str:
    """The full extraction prompt for one case's normalised text."""
    system = _SYSTEM.replace("<<HEADS>>", ", ".join(HEAD_NOUNS))
    return f'{system}\n\nCustomer message:\n"""{case_text}"""'
