"""Object-store ingest + entity resolution + contradiction detection (Phase 5).

The anchor is a KEY, not a field: a case is bound to its object by LOOKUP, so the two-question drill
only has to ask what genuinely can't be looked up. ``ingest`` lands a tenant's objects resolvable
(schema-agnostic, idempotent, RLS'd); ``resolver`` binds a case to one — or asks — never silently
binding the wrong object.
"""

from __future__ import annotations

from .ingest import IngestResult, ingest_object_collection
from .profile import profile_key_fields
from .resolver import Resolution, resolve_object

__all__ = [
    "IngestResult",
    "Resolution",
    "ingest_object_collection",
    "profile_key_fields",
    "resolve_object",
]
