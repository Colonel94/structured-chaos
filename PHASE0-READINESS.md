# PHASE0-READINESS.md — Gate A status & the exact remaining steps

*Companion to `PREREQUISITES.md` §9. This is the live checklist: what is DONE (built + verified),
and the small set of items only you can do (external accounts, a Docker install, recording your own
voice). When Gate A is all green, run `BUILD-PLAN.md` Phase 0. Last updated: 2026-08-10.*

---

## TL;DR — what's left for you (≈30–45 min of mechanical work)
1. **Install Docker Desktop** (the only missing local tool besides cloudflared/gh).
2. **Get 5 API keys/accounts** (Anthropic, Cohere, Meta WhatsApp ×3 values, GitHub repo) → paste into `.env`.
3. **Record 5 things**: 3–5 Gulf voice notes in a noisy room + 1 photo of a stamped bilingual doc
   (see `docs/recording-guide.md`). This is the highest-leverage hour in the project.
4. Run the verify commands in §"Gate A commands" below. All green → start Phase 0.

Everything else — scaffold, config, containers definition, CI, smoke/verify scripts, sample data,
policy, taxonomy — is **built and, where runnable without keys/Docker, verified live** (see §"Verified").

---

## Verified live on this box (2026-08-10)
| Check | Result |
|---|---|
| `uv sync` engine core+dev | ✅ resolved + installed (`engine/uv.lock` written) |
| `pytest` (Phase-0 gate: `/health`, fake-backend load, local-stub raises, 1024-d embed) | ✅ **4 passed** |
| `ruff check` · `black --check` · `mypy app` (strict) | ✅ all clean, **19 files** typed strict |
| UI: `pnpm install` · `vitest` · `vite build` (pnpm 9) | ✅ **1 test passed**, build 26 modules |
| Toolchain present | ✅ Python 3.12.10, uv 0.11.6, Node 24, pnpm 9 (pinned), ffmpeg 8.1 |

**Cannot be verified here without your action:** Anthropic/Cohere 200 (need keys), `docker compose up`
+ Postgres/MinIO (Docker not installed), BGE-M3/PaddleOCR (run in container), WhatsApp webhook (Meta
account + tunnel), spike recordings (your voice/environment).

---

## Gate A — blocking to START Phase 0

### A1 · Keys 1–5 in `.env`; gitignored; Anthropic + Cohere smoke = 200
- [ ] **Anthropic key** → https://console.anthropic.com/settings/keys — paste `ANTHROPIC_API_KEY`.
- [ ] **Cohere key** → https://dashboard.cohere.com/api-keys — paste `COHERE_API_KEY`.
- [ ] **GitHub private repo** → create, then see §"Repo topology" below (there's a decision to make).
- [x] `.env.example` template written; `.gitignore` protects `.env` (done).
- **Do:** `cp .env.example .env`, fill keys, then:
  ```
  uv run --project engine python scripts/smoke_anthropic.py   # expect PASS
  uv run --project engine python scripts/smoke_cohere.py      # expect PASS
  ```

### A2 · `docker compose up` → Postgres+pgvector + MinIO; SELECT 1 + bucket write
- [ ] **Install Docker Desktop** → https://www.docker.com/products/docker-desktop/ (WSL2 backend).
- [x] `deploy/docker-compose.yml` (pgvector/pgvector:pg16 + minio) + `deploy/Dockerfile` written.
- **Do:**
  ```
  docker compose -f deploy/docker-compose.yml up -d db minio
  uv run --project engine python scripts/verify_infra.py      # expect PASS(pg) + PASS(minio)
  ```

### A3 · WhatsApp test number → tunnelled webhook receives a message
- [ ] **Meta developer account + WhatsApp Business app** → https://developers.facebook.com/apps
      (add WhatsApp product; note the **test number**, add ≤5 verified recipients).
- [ ] Generate a **permanent System-User token** (System Users → Generate token), not the 24h temp
      token → `WHATSAPP_TOKEN`; copy the phone-number id → `WHATSAPP_PHONE_NUMBER_ID`; invent a
      `WHATSAPP_VERIFY_TOKEN` string; copy the App Secret → `WHATSAPP_APP_SECRET`.
- [ ] **Install cloudflared** → https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
      then `cloudflared tunnel --url http://localhost:8000`, register that URL as the webhook.
- *Note:* the webhook route itself is Phase 3 — this box only proves the tunnel + number receive.
      **Production** WhatsApp needs Meta **Business verification** (track T2) — start it now, it's slow.

### A4 · BGE-M3 embeds a test string; PaddleOCR reads a test image (in the container)
- [x] `scripts/test_embed.py` + `scripts/test_ocr.py` written (container-only, §3 caution honoured).
- **Do (after A2, in-container so Windows stays clean):**
  ```
  docker compose -f deploy/docker-compose.yml build engine
  docker compose -f deploy/docker-compose.yml run --rm engine python scripts/test_embed.py
  docker compose -f deploy/docker-compose.yml run --rm engine python scripts/test_ocr.py <a-test-image>
  ```

### A5 · De-risk spike inputs recorded (3–5 Gulf voice notes + 1 stamped bilingual doc)
- [ ] Record them per **`docs/recording-guide.md`**. These feed Phase 0.5; without them the spike
      proves nothing. ~1 hour, do it yourself.

---

## Gate B — needed before Phase 4/5 (NOT before Phase 0; runs on calendar tracks meanwhile)
- [x] **Two sample object stores** — `assets/objectstores/bakery_orders.csv` +
      `home_maintenance_jobs.csv` (order-shaped vs visit-shaped; phone-anchor resolves against them).
- [x] **Default policy YAML** — `assets/policy/default_policy.yaml` (priority/SLA/routing + severity
      escalation + emotion→human routing).
- [x] **Starter taxonomy** — `assets/taxonomy/starter_taxonomy.yaml` (8 archetypes + `UNCLEAR`).
- [ ] **Read the six schema-induction papers** (PREREQUISITES §7) + absorb the two citation caveats.
- [ ] **T1 design-partner outreach live**; **T3 recording kit with signed consent + ownership**
      (consent one-pager draft in `docs/recording-guide.md`).
- [ ] **T2 Meta Business verification** submitted.

---

## Repo topology — the one decision I did NOT make for you
This folder currently lives inside a **single shared git repo rooted at `…/Projects`**, on branch
`realestate-intelligence`, alongside NextLife, Project X, etc. `PREREQUISITES.md` wants a **dedicated
private repo, branched off `main`, that never commits `.env`**. The `.gitignore` here already protects
`.env` even inside the shared repo, so nothing leaks meanwhile — but this project should get its own
repo before Phase 0 commits start. Options, my recommendation first:

1. **(Recommended) Dedicated repo for `Structured Chaos/`.** `cd "Structured Chaos" && git init`, add a
   GitHub private remote, first commit = this scaffold. Clean history, clean CI, true project isolation
   (CLAUDE.md §5). The parent repo should then ignore this subtree.
2. Keep it in the shared repo on a dedicated branch — simplest, but bleeds unrelated history/CI and
   muddies the "private repo" trust boundary. Not advised for a seven-figure-standard build.

Tell me which and I'll wire it (init, remote, `.gitignore` in the parent, first commit).

---

## What Phase 0 then is (mostly pre-satisfied here)
Phase 0's exit gate is *"`docker compose up` healthy; CI green on an empty test; config loads a fake
backend."* The scaffold above already delivers the CI + fake-backend halves (verified). Phase 0 proper
becomes: flip Docker on, drop in keys, confirm `docker compose up` healthy end-to-end, push so GitHub
Actions runs green — then straight into **Phase 0.5 de-risk spike** with your recordings.
