"""Extraction result types (EDD §5–6)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .head_nouns import compose_name


@dataclass(frozen=True)
class EmergentAttribute:
    """One candidate attribute the model attested — a *candidate*, not a promoted field (§6). Path A
    (2026-08-14): ``head`` is the column (from the closed vocabulary), ``qualifier`` is the open
    specificity token (may be ``None``), ``value`` is the attested value. ``grounded`` is whether the
    attribute traces back to the source text — the qualifier AND the value are each checked
    independently (owner constraint #3: the qualifier is a second free-text slot = a second place to
    hallucinate), so ``grounded`` is True only when both hold. An ungrounded candidate is dropped.
    """

    head: str
    qualifier: str | None
    value: str
    grounded: bool

    @property
    def name(self) -> str:
        """The composite column display-name (``qualifier_head``) recorded in the log — preserves
        within-case multiplicity while the head is the convergence unit."""
        return compose_name(self.head, self.qualifier)


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
