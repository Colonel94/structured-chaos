"""Object-snapshot-on-bind — freeze the record a case was resolved against (Phase 5, §5, trust gate).

When a case binds to an object, the live object can later change (an order is refunded, an address is
corrected). Provenance must survive that: the moment of binding, we snapshot the object's CURRENT state
as an immutable, content-addressed ``source_document`` (``doc_kind='object_snapshot'``, the seam
reserved in migration 0004). A value the case draws from the record can then cite the snapshot
(``derived_from``); a value the record DISAGREES with cites it ``contradicts`` — so a discrepancy
between the complaint and the record is STORED and surfaced to the agent, never argued with the
customer and never silently lost (§5).

Idempotent: the snapshot's sha256 is the hash of the object's canonical state, so binding twice against
the same object state snapshots once; if the object changed, a new state → a new snapshot.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from ..store import api


class _Blob(Protocol):
    async def put(self, key: str, data: bytes, *, content_type: str) -> str: ...


async def snapshot_object(
    session: Session, *, case_id: UUID, object_id: UUID, blob: _Blob
) -> UUID | None:
    """Freeze ``object_id``'s current state as an immutable ``object_snapshot`` source document tied to
    the case. Returns the snapshot's ``source_document`` id (or None if the object is absent).
    Content-addressed + idempotent — the same object state never duplicates."""
    obj = api.get_object(session, object_id)
    if obj is None:
        return None
    object_type, external_id, attributes = obj
    payload = json.dumps(
        {"object_type": object_type, "external_id": external_id, "attributes": attributes},
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    sha = hashlib.sha256(payload).hexdigest()
    await blob.put(sha, payload, content_type="application/json")

    channel = api.get_case_channel(session, case_id)
    if channel is None:
        return None
    return api.add_source_document(
        session,
        case_id=case_id,
        sha256=sha,
        blob_key=sha,  # content-addressed: blob_key == sha256 (migration 0003)
        mime="application/json",
        channel=channel,
        byte_size=len(payload),
        received_at=datetime.now(UTC),
        doc_kind="object_snapshot",
    )
