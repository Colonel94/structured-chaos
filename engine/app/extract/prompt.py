"""The extraction prompt — versioned (EDD §5, §7.3).

``PROMPT_VERSION`` is part of the idempotency key (§7.3) and stamped into every ``field_extraction``
row's provenance: bump it on ANY change to this text, so a re-extraction gets a fresh run and never
silently overwrites prior provenance. The instructions encode the Spike-4.0 corrections (strict
severity, stated-not-guessed outcome, closed-world grounding).
"""

from __future__ import annotations

# Bump on any change to the prompt text below.
PROMPT_VERSION = "extract-v2"

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
- emergent_attributes: specific facts worth structuring, each as {"name","value"} with a snake_case \
name (e.g. flavour, promised_time, actual_time, packaging_condition, technician, unit_no, \
charged_amount). Include ONLY facts actually present in the message. No inferred or generic fields.

Return JSON only."""


def build_prompt(case_text: str) -> str:
    """The full extraction prompt for one case's normalised text."""
    return f'{_SYSTEM}\n\nCustomer message:\n"""{case_text}"""'
