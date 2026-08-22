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

# PREFLIGHT (R1): does the WORKER CONTAINER actually reach Ollama and have the model? This exercises the
# exact OLLAMA_HOST + extra_hosts path the worker uses, so it catches the container→Ollama bind trap that
# breaks on a native Linux host (host-gateway → a 127.0.0.1-bound Ollama = connection refused → every
# case silently ends up processing_failed). Fail LOUD here rather than discover it one dead case at a time.
echo ">> preflight: worker container -> Ollama reachability + model (catches the Linux bind trap)"
if ! docker compose -f "$COMPOSE" run --rm --no-deps worker python /app/scripts/preflight_ollama.py; then
  echo "!! PREFLIGHT FAILED: the stack is UP but extraction will fail. Fix per the message above" >&2
  echo "   (docs/DEPLOY.md §Ollama) BEFORE sending real cases — do not treat this deploy as ready." >&2
  exit 1
fi

echo ">> done. Verify migrations applied: docker compose -f $COMPOSE logs migrate | tail"
