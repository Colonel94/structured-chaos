#!/usr/bin/env bash
# Deploy the stack SAFELY past Docker's COPY-layer cache — the stale-image footgun that has shipped
# code older than the working tree here (a migrate container once ran without migrations 0011/0012).
# Always rebuild the code-bearing images WITHOUT cache before `up`, so what runs == what's committed.
#
# Usage:  scripts/deploy_rebuild.sh
set -euo pipefail

COMPOSE="deploy/docker-compose.yml"
cd "$(git rev-parse --show-toplevel)"

echo ">> building engine/migrate/worker images --no-cache (defeats the COPY-cache stale-image hazard)"
docker compose -f "$COMPOSE" build --no-cache engine migrate worker worker-backfill

echo ">> bringing the stack up"
docker compose -f "$COMPOSE" up -d

echo ">> waiting for the one-shot migrate gate to finish, then showing status"
docker compose -f "$COMPOSE" ps
echo ">> done. Verify migrations applied: docker compose -f $COMPOSE logs migrate | tail"
