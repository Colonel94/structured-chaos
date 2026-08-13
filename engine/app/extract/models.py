"""Extraction result types (EDD §5–6)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmergentAttribute:
    """One candidate attribute the model attested — a *candidate*, not a promoted field (§6). ``name``
    is normalised snake_case; ``grounded`` is whether ``value`` traces back to the source text
    (closed-world grounding — an ungrounded candidate is a hallucination and is dropped/flagged)."""

    name: str
    value: str
    grounded: bool


@dataclass(frozen=True)
class ExtractionResult:
    """A case's extraction: the governed-core Block-B values (the model may not create fields here),
    the emergent candidates, and ``field_validity`` = grounded fraction of emergent attributes.
    ``field_validity < 1.0`` means the model referenced something not in the source → flag for repair
    (EDD §6.2 STAGE 2 anti-hallucination gate)."""

    governed: dict[str, object]
    emergent: list[EmergentAttribute]
    field_validity: float
    prompt_version: str
    raw: str = field(repr=False, default="")

    @property
    def grounded_emergent(self) -> list[EmergentAttribute]:
        """Only the emergent candidates that are grounded in the source (the ones we keep)."""
        return [e for e in self.emergent if e.grounded]
