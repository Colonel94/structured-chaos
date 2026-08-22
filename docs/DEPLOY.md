# DEPLOY.md — running the engine on a host that isn't your laptop

The honest checklist for a real deployment. The PoC has run all-local on the owner's RTX 4070 (Docker
Desktop, Windows); this doc is what changes when you put it on a Linux server holding real data. Each
section maps to a hardening item (R1–R8). Nothing here needs paid infra — it is $0 / OSS.

> **State of readiness (honest):** the repo is Linux-*ready* (compose, preflight, secret gate, backups,
> TLS template all in place and unit-tested). The one thing that can only be verified on an actual Linux
> host with a GPU is the container→Ollama path (§Ollama) — the preflight is built to catch it, but it has
> not yet been *run green on a Linux box* because there isn't one yet. Do that first on any new host.

---

## §Ollama — the one that breaks on Linux (R1)

The worker/engine containers reach the host GPU's Ollama over
`OLLAMA_HOST=http://host.docker.internal:11434` + `extra_hosts: host.docker.internal:host-gateway`
(already in `deploy/docker-compose.yml`).

- **Docker Desktop (Windows/Mac):** works out of the box — Docker proxies `host.docker.internal` to host
  loopback, so it reaches a `127.0.0.1`-bound Ollama.
- **Native Linux server:** `host-gateway` resolves to the docker *bridge* gateway (e.g. `172.17.0.1`),
  which does **not** reach an Ollama bound to `127.0.0.1`. Result: connection refused → every extract/
  elicit job retries, exhausts, and the case is honestly stamped `processing_failed`. Silent per-case,
  fatal for the product.

**Fix (on the host running the Ollama SERVER):**
1. Bind Ollama to all interfaces: set `OLLAMA_HOST=0.0.0.0:11434` in **Ollama's own** environment.
   ⚠ Same env var name, **opposite role**: on the host it is Ollama's *bind address*; in the container it
   is the *client target url*. Do not conflate them.
2. Restart Ollama; confirm from another host: `curl http://<host-ip>:11434/api/tags`.
3. Firewall port `11434` to the docker bridge subnet **only** — never the public internet.
4. Point the container at it (keep `host.docker.internal` once step 1 makes it reachable, or set
   `OLLAMA_HOST=http://<bridge-ip>:11434` in `.env`).

**Verify before trusting the deploy:** `scripts/deploy_rebuild.sh` runs the preflight automatically, or:

```bash
docker compose -f deploy/docker-compose.yml run --rm --no-deps worker python /app/scripts/preflight_ollama.py
```

Exit 0 = reachable + model present. Non-zero = the exact diagnosis + fix. (Alternative to hosting Ollama
on the box: a GPU host, or the deferred cloud-LLM backend — both are larger changes; the bind fix is $0.)

---

## §Secrets — no `change_me_*` on anything reachable (R5)

Set `APP_ENV=prod` in `.env`. The app then **refuses to boot** if any of these is empty or a
`change_me_*` / PoC placeholder (fail-closed, `app/config.py`):
`POSTGRES_PASSWORD`, `POSTGRES_ADMIN_PASSWORD`, `MINIO_SECRET_KEY`, and `PORTAL_SECRET` (when the portal
is enabled). Generate each: `openssl rand -hex 32`. This gate is off in dev/test so the local PoC is
unaffected.

---

## §Deploy safely — beat the stale-image cache (R7)

Docker's COPY-layer cache has shipped code older than the working tree here (a migrate container once ran
without two migrations). **Never** `docker compose up` after a code change — always:

```bash
scripts/deploy_rebuild.sh    # rebuilds engine/migrate/worker --no-cache, ups, then runs the Ollama preflight
```

---

## §Worker — exactly one, and liveness is visible (R2, R3)

- **One worker per queue-set, enforced.** `scripts/run_worker.py` takes a Postgres advisory lock keyed by
  its queues; a second `default` worker refuses to start (exit 3). Two workers racing the same jobs caused
  spurious failures before this. `default` (intake) and `backfill` take different keys, so compose runs
  both. Bypass only for a deliberate scale-out: `WORKER_ALLOW_MULTIPLE=1`.
- **Liveness.** Every worker heartbeats to `worker_heartbeat` (~15s). If the newest beat is older than
  `WORKER_LIVENESS_SECONDS` (default 60), a still-processing case shows honest handoff copy ("we've hit a
  snag — a person is taking over") instead of an open-ended spinner, and `/health` reports the worker
  `down`. Monitor `/health` → `.worker.status`.
- **Auto-restart.** `engine`, `worker`, and `worker-backfill` all carry `restart: unless-stopped` (R4).

---

## §TLS — real HTTPS with a domain (R6)

`deploy/Caddyfile` + the `caddy` compose service (profile `edge`) give automatic Let's Encrypt HTTPS:

```bash
# in .env:
SITE_ADDRESS=intake.example.com      # point its A record at this host; ":80" = plain HTTP, no domain
docker compose --profile edge -f deploy/docker-compose.yml up -d caddy
```

Caddy handles the cert, renewal, and HTTP→HTTPS redirect. (Local dev keeps using a cloudflared quick
tunnel instead — see longterm_context.md §0 RUN IT.)

---

## §Backups — you're holding other people's complaints (R8)

Two things: Postgres (the correction log is the asset) and the MinIO originals (immutable, un-re-derivable).

```bash
scripts/backup.sh                 # → ./backups/<UTC-stamp>/{postgres.dump, minio-originals/}
BACKUP_DIR=/mnt/backups RETENTION_DAYS=30 scripts/backup.sh   # cron this
```

**Restore:**
```bash
# Postgres (into a fresh/empty DB):
docker compose -f deploy/docker-compose.yml exec -T db \
  pg_restore -U intake_admin -d adaptive_intake --clean --if-exists < backups/<stamp>/postgres.dump
# MinIO originals:
docker compose -f deploy/docker-compose.yml run --rm --no-deps -v "$(pwd)/backups/<stamp>:/backup" \
  --entrypoint sh minio -c "mc alias set local http://minio:9000 <access> <secret> && \
                            mc mirror --overwrite /backup/minio-originals local/originals"
```

Test the restore on a throwaway DB before you rely on it — an untested backup is a hope, not a backup.

---

## First-boot order on a new host

1. `.env` from `.env.example`; set `APP_ENV=prod` + real secrets (§Secrets); set `OLLAMA_*`.
2. Fix + verify the Ollama bind (§Ollama) — `preflight_ollama.py` green.
3. `scripts/deploy_rebuild.sh` (builds --no-cache, ups, preflights).
4. Confirm `/health` → `status: ok`, `worker.status: alive`.
5. TLS (§TLS) if public; schedule `scripts/backup.sh` (§Backups).
6. Only then send a real case.
