"""Irreversibly erase one tenant after an approved data-deletion request.

Offline admin tool only. It requires an exact UUID plus a matching confirmation string, uses the admin
credential, removes every public table row carrying tenant_id (including immutable audit tables), removes
queued jobs for that tenant, then deletes now-unreferenced content-addressed objects. Never call this from
the request path.
"""

from __future__ import annotations

import argparse
from uuid import UUID

import boto3
from botocore.client import Config as BotoConfig
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.store.db import make_engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True, type=UUID)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    expected = f"DELETE-{args.tenant}"
    if args.confirm != expected:
        parser.error(f"confirmation must be exactly {expected}")

    engine = make_engine(settings, admin=True)
    blob_keys: list[str] = []
    try:
        with Session(bind=engine, future=True) as session, session.begin():
            exists = session.execute(
                text("SELECT name FROM tenant WHERE id = :tenant"), {"tenant": args.tenant}
            ).scalar_one_or_none()
            if exists is None:
                blob_keys = list(
                    session.execute(
                        text(
                            "SELECT blob_key FROM deletion_blob_pending WHERE deletion_id = :tenant"
                        ),
                        {"tenant": args.tenant},
                    ).scalars()
                )
                if not blob_keys:
                    raise SystemExit("tenant not found and no pending blob cleanup exists")
            else:
                blob_keys = list(
                    session.execute(
                        text(
                            "SELECT DISTINCT blob_key FROM source_document WHERE tenant_id = :tenant"
                        ),
                        {"tenant": args.tenant},
                    ).scalars()
                )
                for key in blob_keys:
                    session.execute(
                        text("""
                            INSERT INTO deletion_blob_pending (deletion_id, blob_key)
                            VALUES (:tenant, :key) ON CONFLICT DO NOTHING
                        """),
                        {"tenant": args.tenant, "key": key},
                    )
            if exists is None:
                tables = []
            else:
                tables = list(
                    session.execute(
                        text("""
                            SELECT table_name FROM information_schema.columns
                             WHERE table_schema = 'public' AND column_name = 'tenant_id'
                             ORDER BY table_name
                        """)
                    ).scalars()
                )
            session.execute(text("SET LOCAL session_replication_role = replica"))
            quote = engine.dialect.identifier_preparer.quote
            for table in tables:
                session.execute(
                    text(f"DELETE FROM {quote(table)} WHERE tenant_id = :tenant"),
                    {"tenant": args.tenant},
                )
            # Procrastinate stores task arguments as JSON rather than a tenant_id column.
            if session.execute(text("SELECT to_regclass('public.procrastinate_jobs')")).scalar():
                session.execute(
                    text("DELETE FROM procrastinate_jobs WHERE args->>'tenant_id' = :tenant"),
                    {"tenant": str(args.tenant)},
                )
            if exists is not None:
                session.execute(
                    text("DELETE FROM tenant WHERE id = :tenant"), {"tenant": args.tenant}
                )

        client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name="us-east-1",
            config=BotoConfig(signature_version="s3v4"),
        )
        with Session(bind=engine, future=True) as session:
            for key in blob_keys:
                referenced = session.execute(
                    text("SELECT 1 FROM source_document WHERE blob_key = :key LIMIT 1"),
                    {"key": key},
                ).scalar_one_or_none()
                if referenced is None:
                    client.delete_object(Bucket=settings.minio_bucket, Key=key)
                session.execute(
                    text("""
                        DELETE FROM deletion_blob_pending
                         WHERE deletion_id = :tenant AND blob_key = :key
                    """),
                    {"tenant": args.tenant, "key": key},
                )
            session.commit()
        print(
            f"deleted tenant {args.tenant}: database rows removed; {len(blob_keys)} blobs checked"
        )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
