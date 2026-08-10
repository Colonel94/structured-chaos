# PHASE0-READINESS.md — Gate A status & the exact remaining steps

*Companion to `PREREQUISITES.md` §9. This is the live checklist: what is DONE (built + verified),
and the small set of items only you can do (external accounts, a Docker install, recording your own
voice). When Gate A is all green, run `BUILD-PLAN.md` Phase 0. Last updated: 2026-08-10.*

---

## TL;DR — what's left for you (mostly done; ~1 hour of your own recording + one reboot)
1. ✅ **GitHub repo** created + pushed (`Colonel94/structured-chaos`). ✅ **Docker Desktop** installed (v4.85.0).
2. **One reboot:** enable WSL2 — `wsl --install --no-distribution` in an **admin** PowerShell, then reboot
   (Docker's engine backend; the assistant runs non-elevated, so this step is yours).
3. **~~5 API keys~~ → none for the LLM.** Owner override 2026-08-10: the PoC runs the LLM **local on the
   4070** — no Anthropic/Cohere keys. Only WhatsApp (Meta) is still a key, and only *if/when* the WhatsApp
   channel is built (file/email drop is the $0 day-one channel).
4. **Record 5 things**: 3–5 Gulf voice notes in a noisy room + 1 photo of a stamped bilingual doc
   (see `docs/recording-guide.md`). Highest-leverage hour in the project.
5. After the reboot the assistant brings up the containers, pulls the local models, and runs the verify
   commands. All green → Phase 0 → Phase 0.5.

Everything else — scaffold, config, containers definition, CI, smoke/verify scripts, sample data,
policy, taxonomy — is **built and, where runnable without Docker, verified live** (see §"Verified").

---

## Verified live on this box (2026-08-10)
| Check | Result |
|---|---|
| `uv sync` engine core+dev | ✅ resolved + installed (`engine/uv.lock` written) |
| `pytest` (Phase-0 gate: `/health`, fake-backend load, local-stub raises, 1024-d embed) | ✅ **4 passed** |
| `ruff check` · `black --check` · `mypy app` (strict) | ✅ all clean, **19 files** typed strict |
| UI: `pnpm install` · `vitest` · `vite build` (pnpm 9) | ✅ **1 test passed**, build 26 modules |
| Toolchain present | ✅ Python 3.12.10, uv 0.11.6, Node 24, pnpm 9 (pinned), ffmpeg 8.1 |

**Cannot be verified here without your action:** `docker compose up` + Postgres/MinIO (**needs the WSL2
reboot** — Docker itself is now installed), local models on the 4070 (faster-whisper / Ollama / BGE-M3 /
PaddleOCR — pulled + run after WSL2 is up), WhatsApp webhook (only if that channel is built), spike
recordings (your voice/environment). **No Anthropic/Cohere step — the LLM path is local now.**

---

## Gate A — blocking to START Phase 0

### A1 · Source control + config (no LLM API keys — local flip)
- [x] **GitHub private repo** created + scaffold pushed — `Colonel94/structured-chaos`, `origin` wired.
- [x] `.env.example` template written; `.gitignore` protects `.env` (done).
- [ ] ~~Anthropic / Cohere keys + smoke calls~~ — **removed** (owner override 2026-08-10). The PoC LLM
      path is local on the 4070; see **A4** for the local-model load check that replaces the smoke calls.

### A2 · `docker compose up` → Postgres+pgvector + MinIO; SELECT 1 + bucket write
- [x] **Docker Desktop installed** (v4.85.0, CLI `docker 29.6.2`).
- [ ] **Enable WSL2 (admin + reboot):** `wsl --install --no-distribution`, reboot, launch Docker Desktop.
- [x] `deploy/docker-compose.yml` (pgvector/pgvector:pg16 + minio) + `deploy/Dockerfile` written.
- **Do (assistant runs this after your reboot):**
  ```
  docker compose -f deploy/docker-compose.yml up -d db minio
  uv run --project engine python scripts/verify_infra.py      # expect PASS(pg) + PASS(minio)
  ```

### A3 · WhatsApp test number → tunnelled webhook  *(now OPTIONAL / parallel-track — file/email drop is the $0 day-one channel; do this only if building WhatsApp for the PoC)*
- [ ] **Meta developer account + WhatsApp Business app** → https://developers.facebook.com/apps
      (add WhatsApp product; note the **test number**, add ≤5 verified recipients).
- [ ] Generate a **permanent System-User token** (System Users → Generate token), not the 24h temp
      token → `WHATSAPP_TOKEN`; copy the phone-number id → `WHATSAPP_PHONE_NUMBER_ID`; invent a
      `WHATSAPP_VERIFY_TOKEN` string; copy the App Secret → `WHATSAPP_APP_SECRET`.
- [ ] **Install cloudflared** → https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
      then `cloudflared tunnel --url http://localhost:8000`, register that URL as the webhook.
- *Note:* the webhook route itself is Phase 3 — this box only proves the tunnel + number receive.
      **Production** WhatsApp needs Meta **Business verification** (track T2) — start it now, it's slow.

### A4 · Local models load on the 4070 (replaces the old Anthropic/Cohere smoke)
- [x] `scripts/test_embed.py` + `scripts/test_ocr.py` written (container-only, §3 caution honoured).
- [ ] **faster-whisper** transcribes a test clip · **Ollama** returns a completion (extraction model) —
      pulled/run after the WSL2 reboot; **needs CUDA 12 + cuDNN 9** on the 4070.
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

## Repo topology — RESOLVED (2026-08-10)
Dedicated private repo, `git init`ed on `main` **before any keys touched the tree**, first commit =
scaffold. Now pushed to the GitHub private remote **`Colonel94/structured-chaos`** (`origin`, `main`
tracking). History verified clean (no `.env` ever committed; only `.env.example` templates tracked). The
parent `…/Projects` tree is isolated via its local `.git/info/exclude`. Nothing left to decide here.

---

## What Phase 0 then is (mostly pre-satisfied here)
Phase 0's exit gate is *"`docker compose up` healthy; CI green on an empty test; config loads a fake
backend."* The scaffold above already delivers the CI + fake-backend halves (verified) and the repo is
pushed. Phase 0 proper becomes: **WSL2 reboot → `docker compose up` healthy end-to-end → pull the local
models to the 4070** (GitHub Actions already runs on push) — then straight into **Phase 0.5 de-risk
spike** with your recordings.
