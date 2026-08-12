"""Content-addressed, write-once blob store over the S3 API (MinIO on-prem / S3 cloud).

Implements the ``BlobStore`` interface. Two trust properties (EDD §7.2):
- **Content-addressed** — the effective object key is the SHA-256 of the bytes, so identical
  originals coalesce and the key *is* the integrity check.
- **Write-once** — a key that already exists is never overwritten (immutable originals). Full
  object-lock/WORM is the on-prem clinic tier (EDD §16.9); content-addressing + no-overwrite is
  the PoC guarantee.

boto3 is synchronous; the async interface methods offload to a thread so they never block the
event loop.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from ...config import Settings, settings


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MinioBlob:
    def __init__(self, cfg: Settings = settings) -> None:
        self._bucket = cfg.minio_bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=cfg.minio_endpoint,
            aws_access_key_id=cfg.minio_access_key,
            aws_secret_access_key=cfg.minio_secret_key,
            region_name="us-east-1",
            config=BotoConfig(signature_version="s3v4"),
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
        self._bucket_ready = True

    def _exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def _put_sync(self, data: bytes, content_type: str) -> str:
        self._ensure_bucket()
        key = sha256_hex(data)  # content address — overrides any advisory key
        if not self._exists(key):  # write-once: never overwrite an existing original
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        return key

    async def put(self, key: str, data: bytes, *, content_type: str) -> str:
        """Store bytes under their content hash (idempotent, non-overwriting). Returns the
        effective key (the SHA-256). The advisory ``key`` argument is honoured only as intent;
        the content hash is authoritative."""
        return await asyncio.to_thread(self._put_sync, data, content_type)

    def _get_sync(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        body: bytes = obj["Body"].read()
        return body

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get_sync, key)
