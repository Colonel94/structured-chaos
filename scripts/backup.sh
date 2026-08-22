#!/usr/bin/env bash
# Backups (R8) — you are about to hold other people's complaint data; a lost DB is a lost business.
#
# Two things need backing up:
#   1. Postgres — the case records, extractions, provenance, corrections (the correction log IS the asset).
#   2. MinIO/S3 originals — the immutable source files (CLAUDE.md §3 "originals are immutable, retained
#      forever"). Extractions can be re-derived from originals; originals cannot be re-derived. Back them up.
#
# This script dumps Postgres (custom format, compressed) and mirrors the MinIO originals bucket, both to a
# timestamped directory, and prunes dumps older than RETENTION_DAYS. Idempotent, safe to cron.
#
# Usage:   scripts/backup.sh                 # writes to ./backups/<UTC-timestamp>/
#          BACKUP_DIR=/mnt/backups scripts/backup.sh
# Restore: see docs/DEPLOY.md §Backups (pg_restore + mc mirror back).
set -euo pipefail

COMPOSE="deploy/docker-compose.yml"
cd "$(git rev-parse --show-toplevel)"

# .env carries the creds; source it so this works unattended (cron) without an interactive shell.
[ -f .env ] && set -a && . ./.env && set +a
DB_USER="${POSTGRES_ADMIN_USER:-intake_admin}"
DB_NAME="${POSTGRES_DB:-adaptive_intake}"
BUCKET="${MINIO_BUCKET:-originals}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR:-./backups}/${STAMP}"
mkdir -p "$OUT"
echo ">> backup -> $OUT"

# 1. Postgres — custom format (-Fc) so restore is selective + parallelisable. -T through the container.
echo ">> dumping Postgres ($DB_NAME)"
docker compose -f "$COMPOSE" exec -T db pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$OUT/postgres.dump"
echo "   $(du -h "$OUT/postgres.dump" | cut -f1) written"

# 2. MinIO originals — mirror the bucket into the backup dir via a one-off mc container on the compose net.
echo ">> mirroring MinIO bucket '$BUCKET'"
if docker compose -f "$COMPOSE" run --rm --no-deps -T \
     -v "$(cd "$OUT" && pwd):/backup" --entrypoint sh minio -c "
        mc alias set local http://minio:9000 '${MINIO_ACCESS_KEY:-minioadmin}' '${MINIO_SECRET_KEY:-}' >/dev/null 2>&1 &&
        mc mirror --overwrite --remove local/${BUCKET} /backup/minio-${BUCKET}
     "; then
  echo "   originals mirrored"
else
  echo "   !! MinIO mirror failed (bucket empty or creds?) — Postgres dump still succeeded" >&2
fi

# 3. Prune old backups.
if [ -d "${BACKUP_DIR:-./backups}" ]; then
  echo ">> pruning backups older than ${RETENTION_DAYS} days"
  find "${BACKUP_DIR:-./backups}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" \
    -exec rm -rf {} + 2>/dev/null || true
fi

echo ">> backup complete: $OUT"
