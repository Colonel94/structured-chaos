"""The governed-core extraction schema (GOVERNED-CORE-SCHEMA §1–2, EDD §5–6).

The LLM extracts INTO Block B (the universal content core) + the anchor hint + an open-ended list of
emergent attributes. It **never creates a governed-core field** — Block B is fixed here; anything
else the model attests lands in ``emergent_attributes`` and is a *candidate*, not a field (promotion
is §6, later units).

Spike-4.0 corrections baked in (the "refuse to guess" trust invariant, CLAUDE.md §2):
- ``desired_outcome`` is **nullable** — a customer who didn't state what they want yields ``null``,
  which routes to elicitation (Phase 5), rather than the model guessing ``acknowledgement``.
- ``category`` includes ``UNCLEAR`` so the model can abstain below the classification floor.
- ``severity_signal`` criteria are spelled out in the prompt so it stops firing ``safety_health`` on
  non-hazards (the spike's confident-wrong failure).
"""

from __future__ import annotations

# Universal starter taxonomy (GOVERNED-CORE-SCHEMA §2) — hierarchical archetypes + UNCLEAR.
TAXONOMY: tuple[str, ...] = (
    "product_fault",
    "service_fault",
    "delivery_fulfilment",
    "billing_charge",
    "access_availability",
    "staff_conduct",
    "safety_health",
    "other",
    "UNCLEAR",
)

# desired_outcome vocabulary (GOVERNED-CORE-SCHEMA §1 Block B) — nullable at extraction.
DESIRED_OUTCOMES: tuple[str, ...] = (
    "refund",
    "replacement",
    "repair_redo",
    "acknowledgement",
    "information",
    "escalation",
    "other",
)

EMOTIONS: tuple[str, ...] = ("calm", "frustrated", "angry")
SEVERITIES: tuple[str, ...] = ("safety_health", "vulnerable_party", "financial_harm", "none")

# The governed-core keys the extractor projects out of the model's JSON (Block A hint + Block B).
GOVERNED_KEYS: tuple[str, ...] = (
    "category",
    "fault",
    "desired_outcome",
    "emotion_signal",
    "severity_signal",
    "anchor_value",
)

# The JSON schema Ollama constrains the output to (llama.cpp GBNF). Guarantees valid, typed JSON so
# "refuse to guess" is a null, never a malformed field (EDD §5 — grammar-constrained decoding).
EXTRACTION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(TAXONOMY)},
        "fault": {"type": "string"},
        # nullable → the model must NOT invent an outcome the customer didn't state.
        "desired_outcome": {"type": ["string", "null"], "enum": [*DESIRED_OUTCOMES, None]},
        "emotion_signal": {"type": "string", "enum": list(EMOTIONS)},
        "severity_signal": {"type": "string", "enum": list(SEVERITIES)},
        "anchor_value": {"type": ["string", "null"]},
        "emergent_attributes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["name", "value"],
            },
        },
    },
    "required": [
        "category",
        "fault",
        "desired_outcome",
        "emotion_signal",
        "severity_signal",
        "anchor_value",
        "emergent_attributes",
    ],
}
