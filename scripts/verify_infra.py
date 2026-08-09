#!/usr/bin/env python
"""Gate A infra check: Postgres+pgvector reachable (SELECT 1, CREATE EXTENSION vector)
and MinIO bucket write/read round-trips.

Run AFTER `docker compose -f deploy/docker-compose.yml up -d`:
    uv run --project engine python scripts/verify_infra.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def check_postgres() -> bool:
    try:
        import psycopg
    except ImportError:
        print("SKIP(pg): psycopg not installed (uv sync the engine core).")
        return False
    dsn = (
        f"host={os.environ.get('POSTGRES_HOST', 'localhost')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} "
        f"dbname={os.environ.get('POSTGRES_DB', 'adaptive_intake')} "
        f"user={os.environ.get('POSTGRES_USER', 'app_rw')} "
        f"password={os.environ.get('POSTGRES_PASSWORD', '')}"
    )
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        print("PASS(pg): SELECT 1 ok; pgvector extension available.")
        return True
    except Exception as e:  # noqa: BLE001 - surface any connection/permission error
        print(f"FAIL(pg): {e}")
        return False


def check_minio() -> bool:
    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        print("SKIP(minio): boto3 not installed (uv sync the engine core).")
        return False
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    bucket = os.environ.get("MINIO_BUCKET", "originals")
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", ""),
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
        if bucket not in existing:
            s3.create_bucket(Bucket=bucket)
        s3.put_object(Bucket=bucket, Key="_smoke.txt", Body=b"ok")
        body = s3.get_object(Bucket=bucket, Key="_smoke.txt")["Body"].read()
        assert body == b"ok"
        s3.delete_object(Bucket=bucket, Key="_smoke.txt")
        print(f"PASS(minio): bucket '{bucket}' write/read/delete round-trip ok.")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"FAIL(minio): {e}")
        return False


def main() -> int:
    _load_env()
    ok_pg = check_postgres()
    ok_minio = check_minio()
    return 0 if (ok_pg and ok_minio) else 1


if __name__ == "__main__":
    sys.exit(main())
