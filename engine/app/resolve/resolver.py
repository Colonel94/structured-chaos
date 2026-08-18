"""Entity resolution — bind a case to its object, or ask (Phase 5, EDD §16.1).

The proven policy from the ``eval/spike_entity_resolution.py`` de-risk spike, now running against the
live object store. It encodes one principle: a CHECKABLE identifier binds; an arguable one asks —
and a silent bind fires ONLY when the evidence is unambiguous (winning-condition §4: object-match
accuracy when matched silently ≥99%, because acting on the wrong order is worse than asking).

  1. quoted id present:
       - resolves to exactly ONE object, and (if the sender phone is known) that object's phone is
         NOT contradicted  -> SILENT
       - id + phone point to DIFFERENT objects (a typo can collide with someone else's valid order)
         -> CONFIRM (contradiction; the seam contradiction-detection later surfaces, never argues)
       - id not found -> CONFIRM (never fuzzy-bind a mistyped id); id non-unique -> CONFIRM
  2. else sender phone: one object -> SILENT; many -> CONFIRM (list); none -> fall through
  3. else a name + embedder: a SINGLE fuzzy hit above MATCH_TAU with margin >= MARGIN over the
     runner-up -> SILENT; otherwise CONFIRM. A name alone is weak, so the bar is deliberately high.
  4. else -> ELICIT (open questions; the no-object fallback must never fail).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from ..store import api
from .keys import hash_key, normalise_key_value

MATCH_TAU = 0.72  # BGE cosine floor for a name to be a fuzzy candidate at all
MARGIN = 0.06  # the top fuzzy hit must beat the runner-up by this to be SILENT on a name alone


class _Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class Resolution:
    mode: str  # "silent" | "confirm" | "elicit"
    object_id: UUID | None = None  # the silently-bound object, if any
    candidates: list[UUID] = field(default_factory=list)
    reason: str = ""


def _key_hash(value: str, *, as_phone: bool) -> str:
    return hash_key(normalise_key_value("phone" if as_phone else "id", value))


async def resolve_object(
    session: Session,
    *,
    anchor_id: str | None = None,
    phone: str | None = None,
    name: str | None = None,
    object_type: str | None = None,
    embedder: _Embedder | None = None,
) -> Resolution:
    """Resolve a case to one object for the current tenant, or return confirm/elicit. RLS-scoped:
    every lookup only sees this tenant's objects."""
    phone_ids = (
        [
            h.object_id
            for h in api.resolve_object_by_key(
                session, key_value_hash=_key_hash(phone, as_phone=True)
            )
        ]
        if phone
        else []
    )

    # 1. quoted id — the strongest key, cross-checked against the sender phone
    if anchor_id:
        hits = api.resolve_object_by_key(
            session, key_value_hash=_key_hash(anchor_id, as_phone=False)
        )
        if len(hits) == 1:
            oid = hits[0].object_id
            if phone_ids and oid not in phone_ids:
                return Resolution(
                    "confirm",
                    candidates=[oid],
                    reason="quoted id and sender phone point to DIFFERENT objects — contradiction, do not silent-bind",
                )
            return Resolution(
                "silent",
                oid,
                reason="id exact & unique" + (", phone agrees" if oid in phone_ids else ""),
            )
        if len(hits) == 0:
            return Resolution(
                "confirm", reason=f"quoted id '{anchor_id}' not found — do not fuzzy-bind a typo"
            )
        return Resolution(
            "confirm",
            candidates=[h.object_id for h in hits],
            reason="quoted id resolves to multiple objects",
        )

    # 2. sender phone
    if phone:
        if len(phone_ids) == 1:
            return Resolution("silent", phone_ids[0], reason="sender phone resolves to one object")
        if len(phone_ids) > 1:
            return Resolution(
                "confirm", candidates=phone_ids, reason="sender phone shared by multiple objects"
            )

    # 3. name — fuzzy fallback (needs an embedder); silent only on a clear, high-margin single hit
    if name and embedder is not None:
        vec = (await embedder.embed([name]))[0]
        near = api.nearest_objects(session, embedding=vec, k=2, object_type=object_type)
        if near:
            top_id, _ext, top = near[0]
            second = near[1][2] if len(near) > 1 else 0.0
            if top >= MATCH_TAU and (top - second) >= MARGIN:
                return Resolution(
                    "silent",
                    top_id,
                    reason=f"name unique (cos={top:.2f}, margin={top - second:.2f})",
                )
            if top >= MATCH_TAU:
                nearby = [oid for oid, _e, s in near if top - s < MARGIN]
                return Resolution(
                    "confirm",
                    candidates=nearby,
                    reason=f"name ambiguous (cos={top:.2f}, 2nd={second:.2f})",
                )

    # 4. nothing to resolve on
    return Resolution("elicit", reason="no usable anchor — open elicitation")
