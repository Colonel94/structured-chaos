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

from collections.abc import Sequence

from .head_nouns import HEAD_NOUNS

# Universal starter taxonomy (GOVERNED-CORE-SCHEMA §2) — hierarchical archetypes + UNCLEAR.
# `record_accuracy` added 2026-08-17 (owner decision R6, option C): a record the company holds/publishes
# about the customer is inaccurate/unverified/improperly disclosed/improperly dated — the ask is
# verify/correct/delete, not money (billing) or conduct (service). 15 of 23 boundary errors were this
# missing third thing.
#   GENERALISATION VERDICT (owner requirement, measured 2026-08-17): FINANCE-WEIGHTED, not universal-
#   frequency. It occurs off finance (real analogues exist → NOT a seeded industry field, §4-safe: a
#   wrong house-number held on record, a booking confirmation with wrong dates) but is RARE there — the
#   96-row multi-domain gold has 2/96 = 2% record_accuracy vs 29/100 = 29% on CFPB. So it earns its
#   place in the universal core (genuine cross-domain concept) but is concentrated in record-keeping-
#   heavy domains (finance, credit). Treat as universal-but-finance-weighted, never as finance-only.
# TAXONOMY v0.2 (owner governed-core expansion, 2026-08-26): the taxonomy was deliberately WIDENED so
# complaints are not forced into coarser buckets, aligned 1:1 with the independent-labelling workbook's
# "Option Sets" sheet (eval/fixtures/holdout_labels.xlsx). Four categories added — transaction_processing
# (a payment/transfer/refund/deposit/withdrawal did not process/settle/reverse/arrive, distinct from a
# WRONG amount = billing_charge), fraud_security (fraud/scam/account-takeover/unauthorized activity — now
# its OWN class, superseding the old "unauthorised charge → billing_charge" sub-rule), privacy_data
# (collection/disclosure/exposure of personal data, distinct from an INACCURATE record = record_accuracy),
# and misleading_practice (materially misled by advertising/pricing/terms/bait-and-switch). The prompt
# (extract-v21) carries the owner's definitions + boundary rules.
TAXONOMY: tuple[str, ...] = (
    "product_fault",
    "service_fault",
    "delivery_fulfilment",
    "billing_charge",
    "transaction_processing",
    "record_accuracy",
    "access_availability",
    "staff_conduct",
    "safety_health",
    "fraud_security",
    "privacy_data",
    "misleading_practice",
    "other",
    "UNCLEAR",
)

# desired_outcome vocabulary (GOVERNED-CORE-SCHEMA §1 Block B) — nullable at extraction. v0.2 adds the
# remedies the old 7-value set collapsed: correction (fix a record — was folded into repair_redo),
# cancellation, restore_access, stop_contact, compensation (consequential loss beyond a refund), and
# investigation (validate/investigate — was folded into information).
DESIRED_OUTCOMES: tuple[str, ...] = (
    "refund",
    "replacement",
    "repair_redo",
    "acknowledgement",
    "information",
    "escalation",
    "correction",
    "cancellation",
    "restore_access",
    "stop_contact",
    "compensation",
    "investigation",
    "other",
)

# v0.2: emotion adds concerned/distressed (a 5-point tone scale); severity adds privacy_security.
EMOTIONS: tuple[str, ...] = ("calm", "concerned", "frustrated", "angry", "distressed")
SEVERITIES: tuple[str, ...] = (
    "safety_health",
    "vulnerable_party",
    "financial_harm",
    "privacy_security",
    "none",
)

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
def build_extraction_schema(heads: Sequence[str] = HEAD_NOUNS) -> dict[str, object]:
    """The extraction JSON schema for a given head vocabulary. ``heads`` is the tenant's EFFECTIVE head
    set = seed ``HEAD_NOUNS`` + any minted heads (head-minting) — so once a tenant mints a ``regulation``
    column the grammar lets the model emit it directly. Defaults to the seed so every existing caller is
    unchanged. The head enum is what enforces the closed-then-emergent column space in code, not prose.
    """
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": list(TAXONOMY)},
            "fault": {"type": "string"},
            # nullable → the model must NOT invent an outcome the customer didn't state.
            "desired_outcome": {"type": ["string", "null"], "enum": [*DESIRED_OUTCOMES, None]},
            "emotion_signal": {"type": "string", "enum": list(EMOTIONS)},
            "severity_signal": {"type": "string", "enum": list(SEVERITIES)},
            "anchor_value": {"type": ["string", "null"]},
            # Path A: an emergent attribute is {head, qualifier, value}. The HEAD is grammar-constrained
            # to ``heads`` (seed + minted). The QUALIFIER is open free text carrying specificity; it may
            # be null. Both qualifier and value are grounded against the source (closed-world grounding).
            "emergent_attributes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "head": {"type": "string", "enum": list(heads)},
                        "qualifier": {"type": ["string", "null"]},
                        "value": {"type": "string"},
                    },
                    "required": ["head", "qualifier", "value"],
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


# The seed-vocabulary schema (backward-compatible constant for callers that don't mint heads).
EXTRACTION_SCHEMA: dict[str, object] = build_extraction_schema()
