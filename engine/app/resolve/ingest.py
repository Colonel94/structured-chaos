"""Object-store ingest — self-serve, schema-agnostic, idempotent (Phase 5, EDD §16.1).

``ingest_object_collection`` takes a tenant's uploaded objects (a list of dicts — parsed from CSV/JSON
by the upload adapter) and lands them resolvable:

  profile identifier fields (deterministic)  →  for each object: content-hash (idempotent) →
  store the object_record → index each identifier value into object_key (normalised + hashed) →
  optionally embed a descriptive rendering for the fuzzy fallback (batched, off the hot path).

Idempotent by construction: an object's ``content_hash`` (sha256 of its canonical payload) is UNIQUE
per tenant, so re-uploading the same export is a no-op, never a duplicate — the pipeline's replay
guarantee extends to object ingest. All writes are RLS-scoped to the caller's tenant.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from ..store import api
from .keys import normalised_hash
from .profile import is_contact_field, profile_key_fields


class _Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class IngestResult:
    object_type: str
    ingested: int  # new objects stored
    duplicates: int  # objects already present (idempotent no-op)
    keys_indexed: int  # object_key rows written
    embedded: int  # objects given a fuzzy-match embedding
    key_fields: list[str]  # identifiers the profiler chose


def _content_hash(attributes: Mapping[str, object]) -> str:
    canonical = json.dumps(dict(attributes), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pick_external_id(attributes: Mapping[str, object], key_fields: Sequence[str]) -> str | None:
    """The object's own display id: the most-selective NON-contact key (an order_id, not the phone),
    falling back to the first key present, else None."""
    for field in key_fields:
        if not is_contact_field(field) and attributes.get(field) not in (None, ""):
            return str(attributes[field]).strip()
    for field in key_fields:
        if attributes.get(field) not in (None, ""):
            return str(attributes[field]).strip()
    return None


def _render_for_embedding(attributes: Mapping[str, object]) -> str:
    """A text rendering for the fuzzy fallback: what a customer types when they have no order number —
    a name, the items. CONTACT identifiers (phone/email) are excluded (a hashed phone is not
    fuzzy-matchable text), but names are KEPT even when unique — a unique name is also an exact key,
    yet a customer may TYPO it, and the fuzzy layer is what still resolves the typo to its object.
    """
    parts = [
        str(v).strip()
        for k, v in attributes.items()
        if not is_contact_field(k) and v not in (None, "")
    ]
    return " ".join(parts)


async def ingest_object_collection(
    session: Session,
    *,
    object_type: str,
    objects: Sequence[Mapping[str, object]],
    embedder: _Embedder | None = None,
) -> IngestResult:
    """Ingest a batch of objects of one type for the current tenant. Deterministic + idempotent; the
    optional ``embedder`` adds the fuzzy-match vector (batched into a single call)."""
    key_fields = profile_key_fields(objects)
    ingested = duplicates = keys_indexed = 0
    to_embed: list[tuple[UUID, str]] = []  # (object_id, render_text) for newly-stored objects

    for obj in objects:
        content_hash = _content_hash(obj)
        object_id, created = api.upsert_object_record(
            session,
            object_type=object_type,
            external_id=_pick_external_id(obj, key_fields),
            content_hash=content_hash,
            attributes=obj,
            key_fields=key_fields,
        )
        if not created:
            duplicates += 1
            continue
        ingested += 1
        for field in key_fields:
            raw = obj.get(field)
            if raw in (None, ""):
                continue
            nh = normalised_hash(field, str(raw))
            if nh is None:
                continue
            _norm, vhash = nh
            api.add_object_key(
                session,
                object_id=object_id,
                key_field=field,
                key_value_hash=vhash,
                key_value=str(raw).strip(),
            )
            keys_indexed += 1
        render = _render_for_embedding(obj)
        if embedder is not None and render:
            to_embed.append((object_id, render))

    embedded = 0
    if embedder is not None and to_embed:
        vectors = await embedder.embed([text for _oid, text in to_embed])
        for (object_id, _text), vec in zip(to_embed, vectors):
            api.set_object_embedding(session, object_id=object_id, embedding=vec)
            embedded += 1

    return IngestResult(
        object_type=object_type,
        ingested=ingested,
        duplicates=duplicates,
        keys_indexed=keys_indexed,
        embedded=embedded,
        key_fields=list(key_fields),
    )
