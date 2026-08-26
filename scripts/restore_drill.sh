#!/usr/bin/env bash
# Restore a backup into isolated drill targets, verify it, and remove only those drill targets.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: scripts/restore_drill.sh backups/<UTC-stamp>" >&2
  exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
BACKUP="$(cd "$1" && pwd)"
COMPOSE="$ROOT/deploy/docker-compose.yml"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

DB_USER="${POSTGRES_ADMIN_USER:-intake_admin}"
DRILL_DB="${RESTORE_DRILL_DB:-adaptive_intake_restore_drill}"
BUCKET="${MINIO_BUCKET:-originals}"
DRILL_BUCKET="${BUCKET}-restore-drill"

case "$DRILL_DB" in
  *_restore_drill) ;;
  *) echo "RESTORE_DRILL_DB must end in _restore_drill" >&2; exit 2 ;;
esac
[ -s "$BACKUP/postgres.dump" ] || { echo "missing postgres.dump in $BACKUP" >&2; exit 2; }

cleanup() {
  docker compose -f "$COMPOSE" exec -T db dropdb -U "$DB_USER" --if-exists "$DRILL_DB" >/dev/null 2>&1 || true
  docker compose -f "$COMPOSE" run --rm --no-deps -T --entrypoint sh minio -c "
    mc alias set local http://minio:9000 '${MINIO_ACCESS_KEY:-minioadmin}' '${MINIO_SECRET_KEY:-}' >/dev/null 2>&1 &&
    mc rb --force local/${DRILL_BUCKET} >/dev/null 2>&1 || true
  " >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
docker compose -f "$COMPOSE" exec -T db createdb -U "$DB_USER" "$DRILL_DB"
docker compose -f "$COMPOSE" exec -T db pg_restore -U "$DB_USER" -d "$DRILL_DB" < "$BACKUP/postgres.dump"

TABLES="$(docker compose -f "$COMPOSE" exec -T db psql -U "$DB_USER" -d "$DRILL_DB" -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
CASES="$(docker compose -f "$COMPOSE" exec -T db psql -U "$DB_USER" -d "$DRILL_DB" -Atc \
  "SELECT count(*) FROM case_record")"
[ "$TABLES" -gt 0 ] || { echo "restore has no public tables" >&2; exit 1; }

OBJECTS="not-present"
if [ -d "$BACKUP/minio-${BUCKET}" ]; then
  OBJECTS="$(docker compose -f "$COMPOSE" run --rm --no-deps -T \
    -v "$BACKUP:/backup:ro" --entrypoint sh minio -c "
      mc alias set local http://minio:9000 '${MINIO_ACCESS_KEY:-minioadmin}' '${MINIO_SECRET_KEY:-}' >/dev/null 2>&1 &&
      mc mb --ignore-existing local/${DRILL_BUCKET} >/dev/null &&
      mc mirror /backup/minio-${BUCKET} local/${DRILL_BUCKET} >/dev/null &&
      mc ls --recursive local/${DRILL_BUCKET} | wc -l
    ")"
fi

echo "RESTORE DRILL PASS backup=$BACKUP tables=$TABLES cases=$CASES objects=$OBJECTS"
