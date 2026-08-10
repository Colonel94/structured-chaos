# Technical Specification — Adaptive Intake

*The build bill-of-materials: every functionality mapped to the concrete language, product, and library
that covers it, with the local ($0/in-region) and cloud backends called out. Implements `SOLUTION-EDD.md`
(the design) and `PRD.md` (the requirements). Governed by `CLAUDE.md`.*

*Version 1.0 — 2026-08-09. Pin exact versions to latest-stable at build time; minimums shown as "X+".*

> **⚠ OWNER OVERRIDE — 2026-08-10 (authoritative: `longterm_context.md` §0).** The PoC's LLM path is now
> **LOCAL, on the owner's RTX 4070 — not cloud.** Wherever this document says *cloud-first PoC*, *Claude
> Haiku* (extraction), *Cohere Transcribe* (ASR), or *Anthropic/Cohere API keys*, read instead:
> **faster-whisper** (ASR) · **a quantized instruct model via Ollama** (extraction) · **BGE-M3**
> (embeddings) — all local, no external call, no API keys, literally $0. The four-interface architecture
> is unchanged; only which backend the PoC builds first flips to local. Logged consequence (§0): local
> extraction quality < Haiku on the hard Gulf/code-switched slice, so the ≥95%/≥98% thresholds get harder
> — measured at the Phase-0.5 spike. Substantive section rewrites below are deferred to the phase that
> builds each component; **until then this banner overrides any cloud-first text that follows.**

---

## 0. Principles this stack obeys
- **$0 build budget** — OSS + local models on the RTX 4070 (12 GB); the only metered spend is Claude
  Haiku in *cents* across the eval, and only in CLOUD mode.
- **Dual deployment, config-switchable** — every inference/storage component sits behind an interface
  with a `local` and a `cloud` implementation, chosen by config, never by a code change.
- **Headless engine** — Python API is the product; the React UI is its first client.
- **Commercial-license-clean** — permissive licences only in the shipped path; every copyleft (AGPL/GPL)
  trap is flagged in §6 and designed around.

---

## 0.1 Scope decision (v1.1, owner) — cloud-first PoC, local deferred to clinic #1
The first market is any service/delivery business down to a cake shop — the *opposite* end of the
market from a health tenant. Standing up four local backends on the 4070 (Qwen3-14B, self-hosted
Cohere, MinIO, forced-alignment) is a large architecture tax paid for a segment not yet chosen. So:
- **Keep all four backend interfaces (§3) — they are the module hedge and they are cheap.**
- **Build ONLY the cloud implementation of each for the PoC; ship the local impls as stubs.**
- **Trigger the local build when a clinic is customer #1**, not before.
- The PoC cloud path stays at **cents (~$0)**: **Cohere Transcribe Arabic API** (ASR), **Claude
  Haiku 4.5** (extraction), **BGE-M3 self-hosted** (embeddings are trivial and CPU-capable — they stay
  self-hosted either way), Postgres, S3/MinIO.
- **PoC provenance is segment-level** (jump to the VAD utterance) — cloud ASR returns no word
  timestamps; word-level forced-alignment is deferred with the rest of the local stack.
- **Deferred *with* local** (so their costs are deferred too): the separate **local-stack eval bar**,
  the strict **PHI-at-promotion governance** for health tenants (§2.6a), and the **two-target test
  matrix**. The PoC ships a **universal manager register** (same report across the six §4a verticals).
- **Reconciles `CLAUDE.md` Directive 2:** "$0 local on the 4070" is the *clinic-#1* engineering, not
  the PoC. The PoC closes every gap on a single cloud path at cents; laziness is still banned.

---

## 1. Languages & why

| Language | Where | Why it (and not the alternative) |
|---|---|---|
| **Python 3.12+** | Headless engine, pipeline, all ML/inference, rules engine, eval | The entire local-model + ASR + embeddings ecosystem is Python-native; nothing else gives $0 access to Whisper/Cohere/BGE/Qwen locally |
| **TypeScript 5+** | React/Vite review UI | Type safety across the provenance-heavy UI; shares generated types with the engine's OpenAPI schema |
| **SQL (PostgreSQL dialect)** | Schema, RLS policies, migrations, the `field_current` projection | RLS + pgvector + append-only integrity must live in the DB, not the app |
| **GBNF grammar** | Constrained-decoding grammars for the local LLM | Guarantees valid JSON / one-of-N category labels at sampling time |
| **Bash + PowerShell** | Ops scripts (dev is on Windows 11; prod deploys Linux) | Cross-platform because the owner's box is Windows, deploy targets are Linux |

---

## 2. Master traceability matrix — functionality → stack

*Grouped by pipeline stage + cross-cutting concern. "Local" = in-region/$0 on the 4070; "Cloud" = metered/eval.
Every row traces to an EDD section.*

### 2.1 Engine core & API
| Functionality | Language | Product / Library (pick) | Backend split | EDD |
|---|---|---|---|---|
| Headless REST API (the engine) | Python | **FastAPI** + **Uvicorn** (ASGI) | n/a | §1 |
| Schemas, validation, structured-output contracts | Python | **Pydantic v2** | n/a | §5 |
| Pipeline orchestration (idempotent, retryable, replayable stages) | Python + SQL | **Procrastinate** (Postgres-backed) — the real reason is **transactional enqueue**: the job is enqueued in the *same transaction* as the row write, so a partial failure can't orphan a job or leave a phantom case (Redis can't do this) | both | §2, §7.3 |
| **Backfill isolation** (promotion re-extracts history → burst of model calls) | Python + SQL | Dedicated **low-priority Procrastinate queue + separate worker pool** so a promotion event can't starve live intake | both | §6, §16 |
| Config + the local/cloud backend switch | Python | **pydantic-settings** + `.env` | n/a | §3 |

### 2.2 Intake adapters (both channels, self-serve)
| Functionality | Language | Product / Library | Backend split | EDD |
|---|---|---|---|---|
| WhatsApp inbound (text/voice/image/PDF) + 2-step media fetch | Python | **Meta WhatsApp Cloud API** (Graph API) via **pywa** + **httpx**; PoC on Meta **free test number** | cloud channel only | §11 |
| WhatsApp media download (5-min URL, bearer header) | Python | **httpx** (async, stream to object store on receipt) | — | §11 |
| File drop: WhatsApp chat-export `.zip`/`.txt` parse | Python | **in-house parser** (iOS/Android grammar) — *not* whatstk as a lib (GPL, §14); stdlib `zipfile` | local | §11 |
| Email drop (residency-safe) | Python | **aiosmtpd** or **Postfix** on a UAE VPS; **imap_tools** for poll; stdlib `email` for MIME | local | §11 |
| Email drop (demo shortcut only) | TypeScript | **Cloudflare Email Workers** + `postal-mime` | cloud (demo) | §11 |
| Conversation windowing / new-case-vs-follow-up | Python | **in-house** hybrid: 24h idle gap + resolve/close state + LLM classifier (§2.4) — no Chatwoot dep (AGPL) | both | §11 |

### 2.3 Normalisation — audio, ASR, timestamps, OCR
| Functionality | Language | Product / Library | Backend split | EDD |
|---|---|---|---|---|
| Audio decode (opus/m4a/ogg) | — | **ffmpeg** (invoked by the ASR libs) | local | §11 |
| Voice-activity detection / chunking | Python | **silero-vad** | local | §4 |
| ASR — Gulf-Arabic + code-switch (transcript) | Python | **PoC: Cohere Transcribe Arabic API** (best clean-licence Arabic). **Local (deferred): same weights self-hosted** via transformers/vLLM. Groq Whisper-v3 / Deepgram credit = eval baseline only | **cloud built; local deferred** | §4 |
| Provenance timestamps | Python | **PoC: segment-level** (VAD utterance boundaries — cloud ASR has no word ts). **Deferred: word-level forced-alignment** (WhisperX / ctc-forced-aligner + wav2vec2-Arabic) with the local stack | cloud built; local deferred | §4, §16.1 |
| OCR — images / scanned PDF (Arabic) | Python | **PaddleOCR (PP-OCRv6)** (Apache-2.0) | self-hosted (CPU-capable) | §11 |
| PDF digital **text** + layout/bbox | Python | **pdfplumber** (MIT) — **never PyMuPDF (AGPL)** | self-hosted | §11 |
| PDF **page → image** (rasterise photographed/stamped/angled PDFs for the vision path) | Python | **pypdfium2** (BSD/Apache — PyMuPDF's rendering value, without AGPL). pdfplumber for text, pdfium for pixels | self-hosted | §11 |
| ML runtime under the above | Python | **PyTorch** (CUDA 12 + cuDNN 9), **CTranslate2** | local | §3 |

### 2.4 Extraction, classification, semantic discovery
| Functionality | Language | Product / Library | Backend split | EDD |
|---|---|---|---|---|
| LLM extraction / category / semantic discovery | Python | **PoC: Claude Haiku 4.5** (`claude-haiku-4-5`) via **anthropic** SDK. **Local (deferred): Qwen3-14B Q4_K_M** via **Ollama**; ALLaM-7B/Falcon-Arabic specialists | **cloud built; local deferred** | §5 |
| Guaranteed-valid JSON / one-of-N labels | Python + GBNF | **Ollama `format=json_schema`** (→ GBNF); **xgrammar** via vLLM if throughput needs it | local; Haiku `output_config.json_schema` | §5 |
| Unified LLM abstraction (backend switch) | Python | **in-house `LLMClient`** interface (local_ollama / cloud_haiku), Pydantic schema shared both paths | both | §3 |

### 2.5 Confidence & "refuse to guess"
| Functionality | Language | Product / Library | Backend split | EDD |
|---|---|---|---|---|
| Self-consistency (sample-N agreement — primary signal) | Python | **in-house** sampler over the `LLMClient` | both | §10, §16.3 |
| Token-logprob confidence | Python | Ollama/llama.cpp logprobs (local); Haiku → self-report + verifier | local strong / cloud weak | §10 |
| Calibration + abstention threshold | Python | **scikit-learn** (Platt/isotonic/temperature scaling) over the labeled dev set | n/a | §10 |

### 2.6 Self-converging schema (the moat)
| Functionality | Language | Product / Library | Backend split | EDD |
|---|---|---|---|---|
| Statistics-before-semantics profiling (type/cardinality/identifier) | Python | **pandas** + **numpy** (deterministic, no LLM) | local | §6, §16.1 |
| Field/name embeddings | Python | **BGE-M3** via **FlagEmbedding** (or sentence-transformers) | local (same model anywhere) | §6 |
| Vector store + similarity (dedup, convergence, object match) | SQL | **PostgreSQL + pgvector** (HNSW `m=16, ef_construction=200`) | both | §6, §7 |
| Batch re-cluster (nightly, complete-linkage HAC) | Python | **scikit-learn** `AgglomerativeClustering` / **scipy** | local | §6 |
| Promotion + backfill jobs (idempotent, bounded) | Python + SQL | **Procrastinate** (dedicated low-priority queue, §2.1) + Alembic-managed nullable-column adds | both | §6, §16 |

**§2.6a — Emergent-field governance at promotion (a self-creating schema can invent a field holding
PII/PHI).** Before any candidate field is promoted, it passes a **PII/PHI classifier + redaction gate**:
tag the field's sensitivity (deterministic patterns for phone/ID/address + an LLM check for free-text
health content), block or redact per tenant sensitivity, and record the classification in provenance.
Light version (PII, e.g. a phone in a bakery complaint) applies to **every** tenant under PDPL; the
**strict PHI version is a hard requirement before a health/clinic tenant** and is what a health-sector
audit looks for. Deferred to the clinic-#1 build for the strict tier; the light PII tier ships in the PoC.

### 2.7 Determinism, object store, tenancy, provenance
| Functionality | Language | Product / Library | Backend split | EDD |
|---|---|---|---|---|
| Priority / SLA / routing (deterministic, auditable) | Python + YAML | **in-house rules engine** driven by declarative **YAML** policy (universal defaults + tenant override) | n/a | §8, §16.2 |
| Object-store ingest (arbitrary tenant schema) + entity resolution | Python + SQL | FastAPI upload / read-only API key → §2.6 profiling → pgvector fuzzy + hashed exact-key match | both | §16.1 |
| Relational store, RLS multi-tenancy | SQL + Python | **PostgreSQL 16+**, **SQLAlchemy 2.0** + **psycopg 3**, **Alembic** migrations | both | §7.1 |
| RLS isolation test (blocking gate) | Python | **pytest** + **pgrls** (plugin + lint rules + CI policy-diff) | n/a | §7.1 |
| Immutable originals + append-only provenance/corrections | SQL | Postgres RULES/triggers; append-only tables; `field_current` view | both | §7.2 |
| Object storage (immutable blobs, WORM) | Python | **MinIO** (local, S3-compatible, object-lock) / **AWS S3** (cloud) via **boto3** | local / cloud | §7.2 |
| Idempotency keys | Python + SQL | version-hash key + `UNIQUE` constraint | both | §7.3 |
| Injection/adversarial-input defence | Python | closed-world grounding + GBNF bounds + templated (non-LLM) customer text | both | §16.6 |

### 2.8 Review UI, reporting, auth
| Functionality | Language | Product / Library | Backend split | EDD |
|---|---|---|---|---|
| Review SPA | TypeScript | **React 18+** + **Vite 5+**; **Tailwind CSS**; **TanStack Query** | n/a | §12 |
| Audio provenance (waveform, seek, region highlight) | TypeScript | **wavesurfer.js v7** (+ Regions/Timeline) via **@wavesurfer/react** | n/a | §12 |
| Image OCR-region highlight | TypeScript | **in-house div-overlay** from bbox (rendered-dim coords) | n/a | §12 |
| PDF original render | TypeScript | **react-pdf** (pdf.js) | n/a | §12 |
| Keyboard-driven review (<30s/case) | TypeScript | **react-hotkeys-hook** | n/a | §12 |
| Typed API client (no drift) | TypeScript | **openapi-typescript** / **orval** from FastAPI's OpenAPI | n/a | §1 |
| Manager report + register (universal) | Python | **WeasyPrint** (HTML→PDF; our layout carrying the tenant's data; Pango/HarfBuzz handle Arabic RTL). CSV via stdlib | both | §16.8 |
| Auth + tenant context | Python | **Authlib**/**python-jose** (JWT), **argon2** (passlib) hashing; `SET LOCAL app.tenant_id` per request | both | §7.1 |

### 2.9 Deployment, observability, testing
| Functionality | Language | Product / Library | Backend split | EDD |
|---|---|---|---|---|
| Packaging / single-node deploy (local + cloud) | YAML | **Docker** + **Docker Compose** | both | §14 |
| GPU model serving | — | **Ollama** (bundles llama.cpp+CUDA); **vLLM** optional | local | §3 |
| TLS / reverse proxy | — | **Caddy** (auto-TLS) | both | §14 |
| Structured logging, PII-scrubbed (no customer data) | Python | **structlog** + in-house redaction filter | n/a | §14 |
| Metrics/convergence monitor (optional PoC) | Python | **Prometheus** + **Grafana**, or logged counters | n/a | §15 |
| Backend tests + Postgres in CI | Python | **pytest**, **pytest-asyncio**, **testcontainers**, **pgrls** | n/a | §15 |
| Eval harness (ground-truth scoring) | Python | **in-house** scorer + **pandas**; risk-coverage/calibration plots via **matplotlib** | n/a | §15 |
| Frontend tests | TypeScript | **Vitest** (unit) + **Playwright** (e2e) | n/a | §15 |

---

## 3. The four backend-switch interfaces (the heart of dual-mode)
Each is a Python `Protocol` selected by `pydantic-settings`. **Per §0.1, the PoC builds only the `cloud`
column; the `local` column ships as a stub and is built when a clinic is customer #1.**

| Interface | `cloud` impl (BUILT for PoC) | `local` impl (STUB — build at clinic #1) | Health/finance tenants |
|---|---|---|---|
| `ASRBackend` | **Cohere Transcribe Arabic API** (segment-level ts) | Cohere weights self-hosted + forced-align on the 4070 | **local only** |
| `LLMBackend` | **Claude Haiku 4.5** (SDK) | Qwen3-14B via Ollama (GBNF) | **local only** |
| `EmbeddingBackend` | **BGE-M3 self-hosted** (trivial, CPU-capable — same both modes) | same | either |
| `BlobStore` | **S3** (or MinIO) | MinIO (object-lock, on-prem) | **local only** |

When a clinic is customer #1, all four `local` impls are built and the tenant runs every interface in
`local` — no external call (health data, Federal Law 2/2019 Art. 13). Until then, no local build.

---

## 4. Repository / module layout (monorepo)
```
adaptive-intake/
  engine/                     # Python, FastAPI headless engine (the product)
    api/                      # routes, webhooks (WhatsApp), uploads
    intake/                   # channel adapters + chat-export parser + windowing
    normalise/               # ffmpeg, silero-vad, ASR, forced-align, OCR, pdf
    extract/                 # LLMClient, GBNF schemas, category, semantic discovery
    schema/                  # profiling, embeddings, dedup, promotion, backfill
    confidence/              # self-consistency, calibration, abstention
    resolve/                 # object-store ingest + entity resolution + contradiction
    rules/                   # deterministic priority/SLA/routing (YAML-driven)
    store/                   # SQLAlchemy models, RLS, provenance, blob store, Alembic
    report/                  # WeasyPrint templates (universal register), CSV
    backends/                # local/ vs cloud/ impls of the 4 interfaces
    eval/                    # ground-truth scorer + harness
  ui/                        # React + Vite + TS review SPA
  deploy/                    # docker-compose (local | cloud), Caddyfile, .env.example
  tests/                     # pytest (+ pgrls), Playwright
```

---

## 5. External services (the PoC cloud path — the only non-self-hosted pieces)
| Service | Used for | Mode | Cost |
|---|---|---|---|
| **Anthropic API** (Claude Haiku 4.5) | PoC extraction backend | cloud; never for residency-bound tenants | **floor ~$1.30/200; real cost MEASURED from Phase 2** (this ignores vision + self-consistency + backfill re-extraction) |
| **Cohere Transcribe Arabic API** | PoC ASR backend | cloud; self-hosted at clinic #1 | metered, cents at eval scale |
| **Meta WhatsApp Cloud API** | WhatsApp channel | PoC = free test number | free (service window) |
| **Groq / Deepgram** | ASR eval baseline only | eval | free tier / $200 credit |
| everything else (Postgres, BGE-M3, PaddleOCR, UI, engine) | — | self-hosted | **$0** |

---

## 6. License ledger (commercial-clean shipped path)
**The test that decides every dependency (corrected): the trigger is DISTRIBUTION, not use.** GPL-3.0
copyleft is *not* triggered by pure SaaS (that is exactly why AGPL exists) — so `whatstk` would be
legally fine for a hosted-only product. But **call §0.1/§3 says we ship on-prem to a clinic**, and
on-prem = *conveying* the software → GPL copyleft applies. So GPL deps are excluded because we
distribute, not because we import. AGPL is excluded even for SaaS (network use counts). Apply this
distribution test to every future dependency.

**Pin-then-verify (licences drift across versions):** confirm the licence *on the pinned version* for
**silero-vad** (was GPL-3.0 → MIT across majors — the pinned version's licence is what governs),
**pywa**, and **WeasyPrint**, before each is load-bearing. One-minute check; same distribution logic.

| Component | Licence | Action |
|---|---|---|
| FastAPI, Pydantic, SQLAlchemy, React, Vite, wavesurfer, pgvector, BGE-M3, PaddleOCR, pdfplumber, **pypdfium2**, faster-whisper, WhisperX, Ollama, MinIO, Cohere Transcribe Arabic | MIT / Apache-2.0 / BSD / MPL | ✅ ship as-is |
| **silero-vad** (+ pywa, WeasyPrint) | version-dependent | ⚠️ pin version, verify licence *on that version* first |
| **PyMuPDF** | **AGPL-3.0** | ❌ **excluded** — pdfplumber (text) + **pypdfium2 (rendering)** replace its two roles |
| **whatstk** (chat-export parser) | **GPL-3.0** | ⚠️ excluded because **we distribute on-prem** (not a SaaS/import issue) — reimplement the simple export grammar in-house |
| **Chatwoot** (windowing prior art) | **AGPL-3.0** | ⚠️ **not a dependency** — build windowing in-house |
| **Audar-ASR** weights | **non-Apache AudarAI licence** | ⚠️ Cohere (Apache-2.0) is the shipped ASR; only revisit Audar after a licence review |
| **Qwen3 / ALLaM / BGE-M3 / Falcon** weights | Apache-2.0 (Falcon: TII AUP) | ✅ check Falcon AUP if used |

---

## 7. Build order — PoC is CLOUD-PATH ONLY (see BUILD-PLAN for full phases/subagents/gates)
**Runs in parallel from day zero (calendar time):** T1 design-partner outreach · T2 Meta Business
verification · T3 ground-truth data collection (signed consent + eval-set ownership).
0. **Scaffold** — repo, docker-compose, CI, config, `/health`.
0.5. **De-risk spike (one day, throwaway)** — real noisy Gulf voice→transcript · stamped bilingual doc→fields · data→Arabic-RTL PDF. Red here changes the plan cheaply.
1. **Store + tenancy first** — Postgres + pgvector + RLS + the blocking cross-tenant test (nothing trusted until isolation is proven).
2. **Engine skeleton** — FastAPI + Procrastinate (transactional enqueue; dedicated backfill queue) + the 4 interfaces (cloud impls + local stubs) + config switch + **cost-per-case meter**.
3. **Ingest → normalise** — file drop first, then WhatsApp test number; **Cohere API ASR (segment-level ts) + PaddleOCR + pdfplumber/pypdfium2**.
4. **Extract + schema + the scorer + a JSON-diff view** — LLMClient (**Claude Haiku**), profiling, embeddings, dedup, promotion (**+ light PII gate**), backfill; **scorer runs on REAL collected data (never author-generated); convergence proven there, not on synthetic**.
5. **Elicit + resolve** — object-store ingest (**two verticals: bakery + home maintenance**), entity resolution, anchor+2 budget, contradiction detection.
6. **Confidence + rules** — self-consistency + calibration + abstention; deterministic SLA/priority/routing.
7. **Review UI + commit gate + report** — React SPA, approval gate, **universal manager register** (WeasyPrint, §16.8).
8. **Full threshold scoring** — the Phase-4 scorer over the matured real set (cloud-path bar) + per-case cost reported.
9. **External gate** — three strangers (from T1); the scorecard; ship.

**Deferred to clinic-#1 (a later milestone, NOT the PoC):** build the four `local` impls (Qwen3-14B/
Ollama, self-hosted Cohere + forced-alignment word-ts, MinIO object-lock); the **strict PHI-at-promotion
governance**; the **separate local-stack eval bar + run**; the **second (on-prem) test-matrix target**.

---

## 8. Hard dependencies to install once
**PoC (cloud path):** **PostgreSQL 16+ with pgvector**, **ffmpeg**, **Docker**, **BGE-M3** (CPU-capable)
+ **PaddleOCR**, Anthropic + Cohere API keys (in a gitignored `.env`). Python via **uv** (or Poetry);
Node 20+ via **pnpm**. Quality gates: **ruff** + **black** + **mypy** (Python); **ESLint** + **Prettier** (TS).
- **Deferred to clinic-#1 (the local stack):** CUDA 12 + cuDNN 9, **Ollama** (Qwen3-14B GGUF),
  self-hosted Cohere + forced-alignment, **MinIO** object-lock. None of this is needed for the PoC.
