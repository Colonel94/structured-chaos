# Prerequisite Setup — Adaptive Intake (PoC, LOCAL-first on the 4070)

*Setup for the **local-first PoC** (owner override 2026-08-10, `longterm_context.md` §0): the LLM path
runs **on the owner's RTX 4070** behind the four backend interfaces — faster-whisper (ASR) + a quantized
instruct model via Ollama (extraction) + BGE-M3 (embeddings), **no external call, no API keys, $0.** The
cloud impls stay valid behind the same interfaces but are no longer what the PoC builds first. The heavy
on-prem/residency extras (WORM, UAE VPS, PHI gate) remain **deferred to clinic customer #1** (§8).*

*Version 1.2 — 2026-08-09 (owner adversarial review). **Readiness is TWO gates (§9), not one:** a small
start-blocking set gets Phase 0 moving; the heavier items (object stores, papers, data, verifications)
block Phases 4/5 and run on parallel calendar tracks meanwhile — so reading six papers never blocks
writing a health endpoint. $0 rule holds. Verify latest-stable versions live at install time and pin
them; verify licences per pinned version (§3).*

---

## 1. Accounts & API keys (put every key in a gitignored `.env`)
| # | Account / key | For | Cost | Notes |
|---|---|---|---|---|
| 1 | **GitHub private repo** | source, CI | free | ✅ **DONE** — `Colonel94/structured-chaos` (private), `origin` wired, scaffold pushed |
| 2 | *(only if building the WhatsApp channel)* **Meta developer account + WhatsApp Business app** | WhatsApp channel (dev) | free **test number** | ≤5 verified recipients; **permanent System-User token**. Production needs Meta **Business verification** — long-lead track (T2). **Not day-one: file/email drop is the $0 self-serve channel; WhatsApp is parallel-track.** |
| 3 | *(with #2)* **A public webhook URL for dev** | WhatsApp inbound webhook | free | **cloudflared** tunnel (or ngrok free) → local FastAPI |
| 4 | *(optional, eval only)* **Groq** / **Deepgram** | ASR baseline comparator | free tier / $200 credit | measures faster-whisper against a hosted baseline; **never the product path** |

> **~~Anthropic + Cohere API keys are GONE~~** (owner override 2026-08-10). Extraction runs on a local
> Ollama model, ASR on local faster-whisper — **no metered LLM spend in the PoC**, so the old "~$1.30 /
> 200 cases" cost line is moot. The cost-per-case meter now tracks **GPU time/throughput on the 4070**;
> if a cloud backend is ever switched on later, **instrument cost from that point** rather than estimating.

**Do NOT create now (deferred to clinic #1, §8):** any UAE VPS, on-prem S3, or GPU cloud.

---

## 2. Local software (dev box — owner's Windows 11; Docker gives parity with Linux deploy)
- **Docker Desktop + Docker Compose** — runs Postgres, MinIO, and the app uniformly.
- **PostgreSQL 16+ with the `pgvector` extension** — via the `pgvector/pgvector` Docker image.
- **MinIO** (Docker) — local S3-compatible blob store ($0; object-lock available for the immutability gate).
- **Python 3.12+** via **uv** (fast, lockfile-based).
- **Node 20+** via **pnpm**.
- **ffmpeg** — audio decode (opus/m4a/ogg) for the ASR path.
- **cloudflared** (or ngrok) — expose the local webhook for the WhatsApp test number.
- Quality gates installed up front: **ruff · black · mypy · pytest (+ pytest-asyncio, testcontainers, pgrls)** ·
  **ESLint · Prettier · Vitest · Playwright**.

---

## 3. Model & library assets to pull once
- **The local LLM path (NOW primary — owner override 2026-08-10; was §8-deferred):**
  - **faster-whisper large-v3** (int8/fp16 on the 4070) — Gulf-Arabic ASR; segment timestamps are native,
    word-level provenance via optional **WhisperX / wav2vec2 forced-alignment**. **Needs CUDA 12 + cuDNN 9.**
  - **Ollama** + a **quantized instruct model** (e.g. Qwen3-14B-Instruct GGUF, Q4 ≈ 9 GB — fits the 12 GB
    4070) — the extraction / semantic-discovery LLM. Reserve model calls for *semantic* work only.
  - These replace the Anthropic/Cohere cloud backends for the PoC; the cloud impls stay behind the
    interfaces for later (dual architecture unchanged).
- **BGE-M3** embeddings (via **FlagEmbedding** or sentence-transformers) — ~1.1 GB, **CPU-capable**;
  runs on the owner's box (faster on the 4070 if present, not required).
- **PaddleOCR (PP-OCRv6)** weights — Arabic OCR for images/scanned PDFs.
- **silero-vad** — voice-activity detection / chunking (gives segment-level provenance timestamps).
- Python libs (locked via uv): FastAPI, Uvicorn, Pydantic v2, pydantic-settings, **Procrastinate**,
  SQLAlchemy 2 + psycopg 3, Alembic, **anthropic**, httpx, **pywa**, pdfplumber, **pypdfium2**,
  PaddleOCR, FlagEmbedding, scikit-learn, pandas, numpy, WeasyPrint, structlog, boto3/minio, Authlib,
  argon2 (passlib). *(Note the licence ledger — TECH-SPEC §6: no PyMuPDF, no whatstk-as-a-library.)*
- **Licence-pin check (one minute each, before load-bearing):** **silero-vad**'s licence changed across
  major versions (GPL-3.0 → MIT) — **pin the version and confirm the licence *on that version*.** Same
  quick check for **pywa** and **WeasyPrint**. This is the same distribution-triggered discipline that
  excluded PyMuPDF/whatstk (we ship on-prem).
- **Windows caution:** **WeasyPrint and PaddleOCR are painful to install natively on Windows** (GTK/Pango,
  build deps). **Run them only inside the Docker container — never on the host** — or you'll lose a day.

---

## 4. Repo & config scaffolding (created in Phase 0, but decided now)
- Monorepo layout per TECH-SPEC §4 (`engine/`, `ui/`, `deploy/`, `tests/`).
- `deploy/docker-compose.yml` (Postgres + pgvector + MinIO + app) and `Caddyfile`.
- `.env.example` (keys from §1) + `pydantic-settings` config carrying the **backend switch**
  (`local` | `cloud`) per interface — **PoC runs all-LOCAL on the 4070**; the cloud impls stay behind the
  interfaces (owner override 2026-08-10).
- CI (GitHub Actions): ruff/black/mypy + pytest (Postgres via testcontainers) + Vitest/Playwright.

---

## 5. Data & policy assets to prepare (not code — inputs the engine needs; NOT a Phase-0 blocker, §9)
- **Two sample object stores only** — **bakery orders + home-maintenance jobs** (order-shaped vs
  visit-shaped) as **CSV/JSON**, so the phone-anchor has something to resolve against. Two is enough to
  prove the object model generalises; the other four §4a verticals are added when a *real* customer needs
  one — not synthetic breadth. (BUILD-PLAN Phase 5.)
- **Universal default policy YAML** — priority/SLA/routing defaults so a zero-config tenant gets value;
  the rules engine reads this (EDD §8 / §16.2).
- **Universal starter category taxonomy** — the ~6–8 hierarchical archetypes + `UNCLEAR` (EDD §16.2).

---

## 6. Evaluation & legal prerequisites (calendar time — START NOW, in parallel with Phase 0)
- **De-risk spike inputs (day-one — record yourself in an hour):** **3–5 genuine Gulf voice notes
  recorded in a noisy real environment** (kitchen/street) + **1 photographed, stamped, bilingual
  document** (angled). Without these, Phase 0.5 proves nothing. These are the highest-leverage hour
  in the project.
- **Design-partner OUTREACH starts now** (track T1) — there is no partner yet and acquiring one is a
  sales cycle. The **DPA is drafted the day someone says yes**, not "before Phase 8." The DPA is the
  legal spine; no real complaint data is touched without it (EDD §16.7).
- **Self-recording kit** — recruit **8–10 Gulf-Arabic speakers**, scenario cards (not scripts) for the
  **two built verticals** (bakery orders, home-maintenance jobs), capture through WhatsApp (~15–20 cases).
  **Consent + ownership (required, not a handshake):** a **one-page written consent** — voice is personal
  (biometric-adjacent) data — that **assigns the recordings AND the resulting eval set to us**. That set
  is the asset; don't build it on trust.
- **Synthetic generation** fills edge slices (sparse/injection) toward ≥100 total, each validated by a
  native speaker. Public corpora (SADA/MASC) = **calibration only**, never the case set. **Convergence is
  proven on the real cases, never on synthetic ones we authored** (BUILD-PLAN Phase 4).

---

## 7. Knowledge prerequisites (read before Phase 4 — the moat)
Read the schema-induction sources so the convergence engine mirrors proven work, not guesswork:
**Executable Schema Contracts** (arXiv:2606.05415 — the reference; τ=0.85/0.70), **EDC** (2404.03868),
**CESI** (1902.00172), **ZOES** (2506.04458), **AutoSchemaKG** (2505.23628), **PG-HIVE** (2512.01092).
Summarised in EDD §6.
- **Citations VERIFIED (2026):** all six arXiv IDs resolve to the real papers (checked against the arXiv
  API, not model summaries). **But two honesty caveats:** (a) the **τ=0.85/0.70 thresholds are one lab's
  chosen defaults with NO published sensitivity sweep** (Jonnalagedda et al. 2026) — cite them as
  "adopted defaults, unvalidated," and **tune on our scored set**, don't treat as field-standard;
  (b) "closed-world grounding" and "statistics before semantics" are **our paraphrases** — the paper says
  "closed-world constrained discovery / field catalog" and "statistical-before-semantic ordering." Don't
  present the paraphrases as verbatim quotes.

---

## 8. DEFERRED prerequisites — do NOT set up now (trigger: clinic customer #1)
*(CUDA 12 + cuDNN 9 · Ollama + Qwen GGUF · faster-whisper are **no longer here** — the local flip promoted
them to §3 as the PoC's primary path.)* Still deferred: self-hosted Cohere weights (only if the cloud ASR
backend is ever wanted) · MinIO object-lock/WORM on-prem · UAE VPS + Postfix (residency-safe email) · the
strict PHI-at-promotion gate · the separate local-stack eval bar (a local 14B ≠ Claude → its own threshold
set). These are the on-prem/residency milestone (EDD §16.9), not the PoC.

---

## 9. Definition of ready — TWO gates (don't let a paper block a health endpoint)

**Gate A — blocking to START Phase 0 (must be true before the first commit):**
- [x] GitHub private repo created + scaffold pushed (`Colonel94/structured-chaos`).
- [x] Docker Desktop installed (v4.85.0). **Pending:** WSL2 backend — `wsl --install --no-distribution`
      (admin) + reboot; then `docker compose up` brings up Postgres+pgvector + MinIO (`SELECT 1` + bucket
      write succeed).
- [ ] **Local models load on the 4070:** faster-whisper transcribes a test clip · Ollama returns a
      completion · BGE-M3 embeds a test string · PaddleOCR reads a test image (**in the container**, §3).
      *(Replaces the old "Anthropic/Cohere smoke = 200" — no API keys in the local PoC.)*
- [ ] *(only if building WhatsApp now)* test number receives a message to the tunnelled webhook —
      otherwise file/email drop is the day-one channel and this moves to a parallel track.
- [ ] De-risk spike inputs recorded (3–5 Gulf voice notes + 1 stamped bilingual doc, §6) — for Phase 0.5.

**Gate B — needed before Phase 4/5 (NOT before Phase 0; runs on calendar tracks meanwhile):**
- [ ] **Two** sample object stores (bakery orders + home-maintenance jobs) + default policy YAML +
      starter taxonomy exist as files.
- [ ] The six schema-induction papers read; the two citation caveats (§7) understood.
- [ ] Design-partner outreach live (T1); recording kit with **signed consent + ownership** lined up (T3).
- [ ] Meta Business verification for production submitted (T2).

**Started day-zero, done on calendar time (not a code gate):** T1 outreach, T2 verification, T3 data.

When all boxes are ticked, start `BUILD-PLAN.md` Phase 0.
