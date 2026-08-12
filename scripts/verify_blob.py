"""Live check for the content-addressed, write-once blob store (EDD §7.2).

Runs against the compose MinIO (localhost:9000). Kept out of the hermetic pytest suite so CI
does not need MinIO; this is the live trust-gate proof for immutable originals.

  uv run --project engine python scripts/verify_blob.py
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "engine")

from app.backends.cloud.blob_minio import sha256_hex  # noqa: E402
from app.backends.registry import get_blob  # noqa: E402


async def main() -> int:
    blob = get_blob()  # BLOB_BACKEND=local → MinioBlob
    data = b"hello immutable original \xf0\x9f\x94\x92"

    key = await blob.put("advisory-key", data, content_type="application/octet-stream")
    assert key == sha256_hex(data), "key must be the content hash"

    # Same bytes, different advisory key → same content address (idempotent, coalesced).
    key2 = await blob.put("a-totally-different-advisory-key", data, content_type="text/plain")
    assert key2 == key, "content-addressing must coalesce identical bytes"

    got = await blob.get(key)
    assert got == data, "roundtrip must return the exact bytes"

    print(f"PASS blob: content-addressed + write-once + roundtrip (key={key[:12]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
