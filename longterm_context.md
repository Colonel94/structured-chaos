# longterm_context.md — Adaptive Intake

*The durable brain for this project. Anything a future session must know to build correctly without
re-reading everything lives here. `CLAUDE.md` is the law (how we build); this is the context (what
we're building and why, plus the settled technical strategy). Companion build docs:
`PRD.md` (what/why, requirements, acceptance), `SOLUTION-EDD.md` (how — verified models,
thresholds, schemas, URLs), `TECH-SPEC.md` (the build BOM — functionality→language→product/library
matrix, backend-switch interfaces, licence ledger, build order), `PREREQUISITES.md` (setup before
Phase 0), and `BUILD-PLAN.md` (Phase 0→ship, with per-phase subagent guidance + regression gates). Source of truth for the promise: `concept-adaptive-intake.md` +
`winning-condition.md` — when this file and those disagree, those win and this file is stale and must
be corrected (except the two research-backed spec deltas in §6, which supersede two of their numbers).*

*Last updated: 2026-08-09.*

---

## 0. Current state & next actions  ← read this first every session; keep it current

**UPDATE (2026-08-12) — ENGLISH-FIRST focus (owner directive).** For now, build/verify the **English
path only**; do **not** sink time into Arabic quality. This is a *sequencing* call, not a moat reversal:
the Gulf-Arabic voice moat (§3) stays locked and the **capability is retained in code** (faster-whisper
is multilingual; OCR is `OCR_LANG`-switchable, default `en`) — it's simply deprioritised until the owner
re-raises it. Concrete effects: **Gate-A5 Gulf recordings are deprioritised** (Phase-0.5 spikes #1/#2 can
run on English inputs meanwhile); **OCR default flipped to English** (`lang="en"` PP-OCRv5 — newer/better model;
`OCR_LANG=ar` still selects the Arabic path). *(Verified 2026-08-12: the paddle-3.x oneDNN workaround
is NOT Arabic-specific — English PP-OCRv5 hits the same bug, so `FLAGS_use_mkldnn=0` stays for both.)*
If this is meant as a permanent moat change (not just
"for now"), the owner will say so; until then it is treated as reversible focus.

**UPDATE (2026-08-12) — PHASE 1 (trust spine) BUILT + VERIFIED LIVE; Gate-A5 recordings PARKED
(owner directive this session).** The owner parked the ~1 hr voice/photo recording (the only
owner-keyboard item) — spikes #1/#2 stay STAGED, un-proven, deferred until re-raised — and directed
"work everything else." So Phase 0.5 does not fully close (spike #3 PASS; #1/#2 parked), and the build
proceeded to **Phase 1 — the trust spine**, which has zero dependency on the recordings. **Done +
verified live this session:**
- **RLS role footgun fixed.** The scaffold made the app's `app_rw` the DB **superuser** (would silently
  bypass RLS). Split into `intake_admin` (superuser; migrations/bootstrap only) + `app_rw`
  (`NOSUPERUSER NOBYPASSRLS`; the engine's runtime role). Verified live: `pg_roles` shows app_rw
  `rolsuper=f, rolbypassrls=f`. Required a one-time `docker compose down -v` (volume held only prior
  verification scratch — no real data). Compose superuser renamed → `intake_admin`; `.env`/`.env.example`
  carry `POSTGRES_ADMIN_USER/PASSWORD`; `config.py` has `admin_database_url`.
- **Alembic + migration `0001_trust_spine`** (hand-authored DDL — security objects can't be autogen'd):
  `tenant` + `case_record` + `source_document` + `field_extraction` + `field_correction` +
  `field_current` (projection) + `stage_execution` (idempotency ledger). **RLS** `ENABLE`+`FORCE`+
  fail-closed `NULLIF` policies (separate `USING`/`WITH CHECK`) on every tenant table; **append-only
  immutability triggers** (raise on UPDATE/DELETE) on the 3 logs; **least-privilege grants**
  (append-only tables get SELECT/INSERT only; case UPDATE is column-scoped, never `tenant_id`); a
  monotonic `seq` IDENTITY on the logs so "latest" is deterministic (fixed a real bug: `now()` is
  txn-constant → same-txn rows tie).
- **Store layer:** `store/db.py` (`tenant_session` → `set_config('app.tenant_id', …, true)`, txn-local
  so it can't leak under PgBouncer); `store/api.py` (create case, immutable content-addressed source
  doc, `record_extraction`/`record_correction` with full provenance, `rebuild_field_current`,
  `compute_idempotency_key`/`claim_stage`); MinIO content-addressed **write-once** blob store
  (`backends/cloud/blob_minio.py`, routed for BOTH local+cloud since blob is infra not a model);
  `obs/logging.py` structlog **PII-redaction** processor (no customer data in logs).
- **Trust gates GREEN (live, testcontainers Postgres):** cross-tenant read=0 + positive control +
  cross-tenant write rejected (`WITH CHECK`) + unset-context reads 0 (fail-closed) + `app_rw` proven
  non-super/non-bypass; append-only UPDATE/DELETE raise even for the superuser (trigger, not just
  grant); idempotent replay skips + `field_current` recomputes from logs (correction-beats-extraction);
  PII never in logs; live MinIO content-addressing/write-once/roundtrip. **Full suite 13 passed (incl.
  Phase-0 regression 4); `ruff`/`black` clean; `mypy --strict` clean (24 files).** Config now loads the
  repo-root `.env` by absolute path (was CWD-relative → broke `alembic` from `engine/`).
- **Env restored:** Docker back up (db+minio healthy). **Unpushed Phase-0 commit `617721b` PUSHED** to
  `origin/main`. An adversarial trust-spine review (subagent) runs at phase close per CLAUDE.md §10.
**Next:** Phase 2 — headless engine skeleton + the 4 backend interfaces wired through Procrastinate +
the cost-per-case meter (local-first: faster-whisper / Ollama / BGE-M3). Recordings stay parked.

**UPDATE (2026-08-12) — PHASES 0-1-2 ADVERSARIAL CROSS-PHASE REVIEW done; real gaps closed (`5bcc659`).**
Three independent reviewers (compliance / integration / coverage). **Verdict: Phase 0 & 1 genuinely
met** (verified live: rolbypassrls=false, all 6 immutability triggers incl. TRUNCATE, provenance
NOT NULL, composite FKs, crash-reclaim — enforced *and* tested). **Phase 2 was PARTIAL → now closed.**
Fixed this pass: **(CRITICAL)** CI silently skipped the DB trust-suite if Docker hiccuped → could ship
an RLS regression green; conftest now HARD-FAILS under CI (`REQUIRE_DB`/`CI` env), CI sets `REQUIRE_DB=1`.
**(meter)** was never wired to a real call (`backend_call` empty) → `meter.meter_backend()` added +
proven LIVE (`scripts/verify_meter.py`: a real qwen3:14b call now lands a `backend_call` row).
**(FakeBlob)** was key-addressed while MinioBlob is content-addressed (Phase-3 green-then-404 trap) →
FakeBlob now content-addressed; migration `0003` adds `CHECK(blob_key = sha256)`. **(coverage +15 tests)**
idempotent conflict-returns, composite-FK cross-tenant rejection, fail_stage re-claim, CHECK
constraints, case-created-state, correction-only projection, cloud-backends-raise, nested/list PII,
queue-args-IDs-only. **(config)** docstring said "all-cloud" + defaulted to cloud (ImportError on fresh
checkout) → fixed to local. **Suite 23→38 green.**

**DEFERRED to Phase 3+ (documented, NOT rushed — decide before building on them):**
1. **F5 — provenance cardinality (the #1 Phase-3 decision).** `field_extraction.source_document_id` is
   single (NOT NULL, composite FK). Phase-3 extraction fuses MANY messages/files per value. Decide
   BEFORE the first real `field_extraction` row: (a) "one message = one source_document, cite the
   anchor message" rule in the Phase-3 spec, or (b) a value↔many-sources bridge table. (b) is more
   faithful to the "trace to the exact sentence" moat claim; (a) is lighter. Migrating the immutable,
   RLS'd, trigger-guarded append-only table LATER is the most expensive change in the repo — so choose now.
2. **F7 — `docker compose up` runs the engine against an UNMIGRATED DB** (no alembic/bootstrap in the
   container path; app_rw role doesn't even exist yet). Only survived because dev runs via `uv` + manual
   `alembic upgrade`. Add an idempotent init service/entrypoint (alembic upgrade + apply_procrastinate_schema
   as intake_admin, depends_on db healthy) when the engine container becomes the entrypoint. Contradicts
   the winning-condition setup gate until fixed.
3. **F8 — `field_current` has no auto-refresh** (rebuild is manual). Before the review UI (Phase 7) reads
   it, either funnel every extract/correct through one stage that rebuilds, or make it trigger-maintained
   (AFTER INSERT on the logs). Decide at Phase 4.
4. **A-MED — ASR/embed local wrappers unproven live** (only the LLM wrapper ran end-to-end; faster-whisper/
   BGE-M3 proven at the library level Gate-A4, wrappers are thin). Prove when the Phase-3 pipeline calls them
   (or `verify_backends_local --full` after `uv sync --group asr --group embed`).
5. **M3 — GUC pool-reuse leak test** (nice-to-have): the fail-closed-unset direction is tested; add a
   pool_size=1 same-connection-reuse test to prove `set_config(...,true)` doesn't leak across checkouts.

**UPDATE (2026-08-12) — PHASE 2 DONE (all 3 units, verified live).** Also delivered `TEST-PLAN.md`
(per-phase test plan, 0→9, mapped to BUILD-PLAN exit gates)
and `scripts/demo_phase1.py` (hands-on Phase-1 trust demo, 14/14 live). Practice adopted (owner,
memory [[commit-fixes-directly]]): **fixes are committed directly, no asking.**
- **Unit 1 — local backends behind the 4 interfaces (`d9e0e33`):** `backends/local/` = OllamaLLM
  (qwen3:14b, `think:false`, JSON-schema-constrained), WhisperASR (faster-whisper large-v3, lazy
  GPU/CPU), BGEEmbedding (BGE-M3 1024-d, lazy). Registry `local`→these (loud-stub removed; cloud is
  the deferred path). Each records `last_usage` for the meter. **Live-verified:** Ollama returns a
  real completion AND schema-constrained extraction correctly pulled fault+desired_outcome from a
  complaint (`scripts/verify_backends_local.py`; `--full` also loads BGE+whisper). Ollama must be
  running (start `Ollama app.exe`; it was down after the reboot).
- **Unit 2 — cost-per-case meter (`8ba8f84`):** migration `0002_cost_meter` → `backend_call` table
  (tokens/audio-seconds/wall_ms/$; RLS + composite FK), `store/meter.py`
  (`record_backend_call`/`meter_usage`/`case_cost`). Local path $=0; **wall_ms (GPU time) is the real
  per-case figure.** 2 tests (aggregation + tenant isolation). **20 tests green; ruff/black/mypy clean.**
- **Unit 3 — Procrastinate transactional enqueue + backfill queue (`c5967a9`):** `app/queue.py` on
  the **native `SyncPsycopgConnector` (psycopg3)** — NOT the SQLAlchemy/psycopg2 connector (it
  double-escapes `%` for psycopg2 paramstyle and errors on a psycopg3 conn; discovered via a spike, so
  **psycopg2-binary is NOT a dependency**). `defer_in_transaction(session, task, …)` runs the enqueue
  INSERT on the session's raw psycopg3 connection → **atomic with the business write** (rollback→no
  phantom job + no orphan case; commit→both persist; proven live + 3 tests). Two queues: `default` +
  low-priority `backfill`. Procrastinate owns its schema → `apply_procrastinate_schema()` (idempotent,
  applied to the live DB via `scripts/bootstrap_procrastinate.py`), with `app_rw` grants **scoped to
  `procrastinate_*` objects only** (never broadens app_rw on the trust-spine tables). Tasks are the
  queue contract; **bodies wire in Phase 3**, guarded by the Phase-1 `claim_stage` ledger. Worker-side
  kill-mid-run safety is Procrastinate's own at-least-once+row-lock guarantee; the enqueue atomicity we
  implement is what's tested. **23 tests green.** **Next: Phase 3** (intake + normalise: file-drop
  first, then WhatsApp; ffmpeg/VAD → local ASR/OCR; conversation windowing).
**Careful-note:** a stray `black` run that included a repo-root script path used black's default
width 88 (missed `engine/pyproject.toml`'s 100) and reflowed committed files; reverted. **Always run
`black`/`ruff` from `engine/` on `app tests` only** — never pass external `../scripts/...` paths to black.

**Where we are (2026-08-10):** Design complete (v1.2) **and the Phase-0 scaffold is built + locally
verified.** `GOVERNED-CORE-SCHEMA.md` done. Repo skeleton, config (local|cloud|fake backend switch),
4 backend interfaces (cloud=Phase-2 lazy, local=loud stub, fake=live), `/health`, docker-compose
(pgvector+MinIO), Dockerfile, CI, smoke/verify scripts, and Gate-B assets (2 object-store CSVs,
default policy YAML, starter taxonomy YAML) all written. **Verified live:** engine `uv sync` +
`pytest` (4 passed) + `ruff`/`black`/`mypy --strict` (19 files clean); UI `pnpm(9) install`/`vitest`
(1 passed)/`vite build`. See `PHASE0-READINESS.md` for the live Gate-A checklist.

**UPDATE (2026-08-10, owner override):** **Docker Desktop INSTALLED by assistant** (v4.85.0, CLI
`docker 29.6.2`). **LLM path flipped CLOUD → LOCAL-ON-4070 for the PoC** (owner: "use the LLM on my
device, $0"). This reverses the cloud-first sequencing in decisions #2/#8 below: PoC now builds the
LOCAL backends first — faster-whisper (ASR) + quantized instruct model via Ollama (extraction) +
BGE-M3 (embeddings), all on the RTX 4070, no external call. **Consequence (logged, not hidden):**
local extraction quality < Claude Haiku on the hard Gulf-code-switched slice → the ≥95%/≥98%
thresholds get harder; Phase-0.5 spike measures this on real data before building upstream. **Upside:**
Anthropic + Cohere keys drop off the critical path entirely — the spike no longer waits on any API key.

**UPDATE (2026-08-11) — GATE A IS GREEN; local models pulled + verified live on the 4070.** WSL2 is
up (Docker engine healthy, Linux containers). Done + verified this session:
- **A2 infra:** `docker compose up` → `pgvector/pgvector:pg16` + `minio` healthy; `verify_infra.py` →
  **PASS(pg)** (SELECT 1 + `CREATE EXTENSION vector`) + **PASS(minio)** (bucket write/read/delete).
- **A4 local models — all four load + run:** **Ollama `qwen3:14b`** returns a completion on the GPU
  (note: qwen3 is a *reasoning* model — emits `<think>…`; extraction must pass `think:false`/`/no_think`).
  **BGE-M3** embeds (dim=1024). **faster-whisper large-v3** transcribes **on the GPU (`device=cuda`)**.
  **PaddleOCR** reads Arabic+English.
- **Phase 0.5 — Spike #3 (Arabic-RTL PDF via WeasyPrint): PASS, visually verified** (correct shaping/
  joining, RTL column order, bidi with embedded Latin/numbers). One of the three killers is dead, and
  it needed no owner input. **Spikes #1 (Gulf voice→transcript) and #2 (stamped bilingual doc→fields)
  are STAGED, not proven** — the toolchain runs (proved on synthetic English clip + Arabic text image)
  but the *real* proof needs the **Gate-A5 owner recordings** (`data/spike/audio|docs`, ~1 hr; still
  the only real blocker). Do NOT mark #1/#2 green until real inputs run.

**Fixes/decisions logged this session (not silent):** Dockerfile had two build-breakers — a bash
`<(…)` process-substitution `/bin/sh` can't parse, and deps installed before `COPY engine/` (project
wheel needs `app/`) — both fixed; added `libgomp1` for paddlepaddle. Added the missing **`asr`
dep-group (faster-whisper)** + wrote `test_asr.py`/`test_ollama.py` (the two Gate-A smokes the scaffold
lacked). **PaddleOCR pin `>=2.9`→`>=3.7,<4`**: 3.x changed the API — Arabic is `arabic_PP-OCRv3_mobile_rec`
via `lang="ar"`+`ocr_version="PP-OCRv3"`, and needs `FLAGS_use_mkldnn=0` to dodge a paddle-3.x PIR/oneDNN
inference bug (`test_ocr.py`/`spike2` updated). **GPU faster-whisper on the Windows host:** CT2 ignores
`add_dll_directory` for its lazy cuBLAS load → `scripts/cuda_win.py` colocates the CUDA-12/cuDNN-9 DLLs
next to the ct2 module (reproducible: `nvidia-*-cu12` added to the `asr` group behind a `win32` marker).
Flipped stale cloud-oriented `.env.example`→local; created local `.env`. **Regression: engine `pytest`
4-passed, `ruff`/`black` clean on new files.** Docker db+minio left running.

**GitHub — DONE (2026-08-10):** private repo **`github.com/Colonel94/structured-chaos`** created +
scaffold pushed (`main` @ `130a4ec`), `origin` remote wired, `main` tracks `origin/main`. Auth via PAT
(`gh auth login --with-token`); account **Colonel94**. **SECURITY NOTE:** two PATs were pasted into the
session transcript during setup (both now compromised — owner to revoke at github.com/settings/tokens
and, if desired, mint a fresh one; current gh auth uses the second, `ghp_fTfJ…`, scopes repo/read:org/workflow).

**Remaining OWNER-KEYBOARD item (only this one left):** **Gate-A5 spike recordings** — 3–5 noisy Gulf
voice notes + 1 stamped bilingual photo, ~1 hr, per `docs/recording-guide.md`; drop into `data/spike/audio`
+ `data/spike/docs` (staged, gitignored). Then the assistant runs `spike/spike1_asr.py` + `spike/spike2_doc.py`
for the real Phase-0.5 verdict (spike scripts are written + toolchain-verified; only real inputs are missing).
*(DONE this session, no longer owner items: WSL2 + Docker engine; docker-compose up; all four local models
pulled to the 4070.)* **Still parallel calendar tracks, not blockers:** Meta Business verification (only if/
when WhatsApp channel is built — file/email drop is the $0 self-serve channel for the PoC).

**Repo topology — RESOLVED (owner, 2026-08-10):** dedicated private repo, `git init`ed on `main`
BEFORE any keys (so `.env` never touches a shared tree). First commit `555c0f9` (61 files). Parent
`…/Projects` repo isolated via its local `.git/info/exclude` (non-invasive). **History checked clean:**
real key prefix `sk-ant` never in history, no `.env` ever committed — **no rotation needed on git
grounds** (only `.env.example` templates are tracked repo-wide). Remaining: owner creates the GitHub
private remote and `git remote add` + push (part of the keys step).

**Scaffold decision-audit — PASSED (owner-requested, 2026-08-10):** NO convergence τ / promotion N
hardcoded anywhere; exactly TWO verticals (not six); taxonomy = the locked 8-archetype universal one.
The only open-decision constants (SLA hours + auto-route τ) were in `assets/policy/default_policy.yaml`
→ **neutralised to null placeholders** (status: PLACEHOLDER, version 0), tuned at Phase 6/8 on the
scored set. Scaffold now stays decision-free.

**What is DONE:**
- Governing docs current & cross-consistent: `CLAUDE.md` (law, incl. §10 adversarial-review rubric +
  §11 principles here), this brain, `PRD.md`, `SOLUTION-EDD.md`, `TECH-SPEC.md`, `PREREQUISITES.md`,
  `BUILD-PLAN.md`. Source contracts: `concept-adaptive-intake.md` + `winning-condition.md`.
- All major decisions locked (see §10) and the build plan is sequenced adversarially (see the
  "Build execution" block in §7).
- **Universal governed-core schema + the two verticals' expected-emergence seed sets drafted**
  (`GOVERNED-CORE-SCHEMA.md`, 2026-08-09) — Phase-5 input. Governed core is minimal/universal/seeded
  (Blocks A–D + starter taxonomy + default SLA interface); vertical attributes are **eval-harness
  reference sets only, never seeded into a live schema** (else the convergence moat is faked — §10.1 /
  CLAUDE.md §10-Q3). Was next-action #3; now done.

**Locked, do-not-relitigate (one-liners; detail in §10):** domain-agnostic single engine · ~~cloud-first
PoC~~ → **LOCAL-first PoC on the 4070 (owner override 2026-08-10, see §0 UPDATE)** · **build/eval TWO
verticals** (bakery + home maintenance); six is the market map, not the build list · universal manager
register report · **two moats** = self-converging schema + voice-first Gulf-Arabic · **regulator-shaped
output is PARKED — do NOT raise it until the owner does** (`_parked/`) · ASR = ~~Cohere API (cloud)~~
**local faster-whisper**; extraction = ~~Claude Haiku~~ **local quantized instruct model (Ollama)** ·
trust spine (RLS/provenance/idempotency) built FIRST · regression after every phase.

**Next actions (owner picks — don't assume):**
1. Start the **three parallel calendar tracks** now (T1 design-partner outreach · T2 Meta Business
   verification · T3 ground-truth data + consent/ownership) — they're lead time, not build time.
2. Run **Phase 0.5 de-risk spike** (needs the day-one inputs in PREREQUISITES §6).
3. ~~Draft the universal governed-core schema + the two verticals' emergent seed lists~~ — **DONE
   (`GOVERNED-CORE-SCHEMA.md`).**
4. Begin **Phase 0 scaffold** once PREREQUISITES Gate A is green.

**Watch-items / pending:** cost-per-case is measured from Phase 2 (the ~$1.30/200 figure is a floor,
not a quote) · licence pin-verify silero-vad/pywa/WeasyPrint · τ=0.85/0.70 are unvalidated defaults →
tune on the scored set · WeasyPrint/PaddleOCR run in Docker only on Windows.

**Competitor logged:** **Hafla** (hafla.com) — UAE *vertical* events-planning AI ("Heba" + agents +
event knowledge-graph "data moat"). Validates the thesis (vague→structured + compounding data moat) but
is a different product (vertical events marketplace, not domain-agnostic complaint intake). **Lesson:
never lead with "conversation replaces forms" — it's crowded; lead with our two moats.**

**How the owner works (match this from message one):** adversarial-review-by-default (CLAUDE.md §10 —
he *will* catch buried risk, self-grading, scope creep, missing viability numbers) · verify before
treating anything as load-bearing (citations, licences, prices) · complete the whole job in one pass,
no half-work or phased approvals · direct correction over hedging · give exact links, not "go search."

---

## 1. What this is, in one breath

> **The customer gives zero structure. The fulfiller receives complete structure. The system pays the
> entire cost of the translation.**

Every CRM / case-management / service-desk product pushes the work of structuring onto a human, and
ends at a form. This absorbs it. You send what you were going to send anyway — a messy WhatsApp
thread, a Gulf-Arabic voice note, two photos, a forwarded PDF — and a complete, prioritised,
fully-traceable structured case comes out the other side, with no form, no category picker, no type
selector. Where the mess doesn't contain enough to act, the system drills — anchor + at most two
questions — and closes the gap without asking anything it could have looked up.

**Stakes:** build to a **seven-figure standard**, failure is not an option. (The "1.5M AED" was a
scoped opportunity that died before contract on an RFP change — internal quality bar + demand-shape
evidence, **never an external claim of a signed deal**; approved external line in `CLAUDE.md`
Directive 1.) **Build budget:** $0 (see §9). **Scope of applicability:** domain-agnostic — *a solution
for all* (see §10.1). One universal engine, not per-industry packs.

---

## 2. The problem we're killing

Structured forms → users abandon or fill them badly; they pick the wrong category and dump the cost
back on the fulfiller. Free text → the fulfiller re-keys everything and reporting collapses.
Management's only lever is to mandate fields, which produces `N/A`, `.`, `see details`, `asdf` —
compliant-looking garbage everyone knows is worthless. Underneath: organisations run in chaos and
expect software to absorb it, not demand it be fixed first. Software that demands process change gets
abandoned. **The insight: structure should be *derived*, not *demanded*.** Modern LLMs can read the
mess and produce the case — a capability that didn't exist when today's systems were designed, which
is why every one of them (even the AI-enhanced ones) still ends at a form. Remove the form and the
trade-off disappears. Once structure is derived, the interaction stops being a form and becomes a
**drill-down**: ask only for what couldn't be worked out, only when you can't act without it, never
for something already said.

---

## 3. Why we win — the two moats (everything else is table stakes)

Prior art was researched before committing (concept §7). "Replace the form with a conversation" is a
**consensus position with funded competitors** (AI-native intake platforms in legal, insurance FNOL,
healthcare, B2B lead-qual; WhatsApp-to-ticket tools like Respond.io, Wati, Gorgias). Leading with it
gets us a list of incumbents. Two positions are genuinely defensible and unbuilt commercially:

1. **A schema that converges on its own** — promotion, embedding-based deduplication, and retroactive
   backfill of history. Automatic schema induction is active *research*, not shipped product; no
   commercial intake/case tool promotes its own fields and backfills. This is the only structural
   moat. The named research failure mode (LLM field-discovery hallucinates fields absent from the
   data → unexecutable schemas) has a named fix we adopt: **closed-world grounding** + **statistics
   before semantics**.
2. **Voice-first, Gulf-Arabic, WhatsApp-native intake.** Every serious player is Western,
   web-form-replacement, English-first. Customers here send voice notes for everything; a speaker icon
   that does nothing is "unusable." Underserved and unlikely to be prioritised by any incumbent.

*(Regulator-shaped / regulated-artefact output is **PARKED by owner** — out of scope, not to be
discussed until re-raised. Archived: `_parked/regulator-shaped-output.md`.)*

**The defensibility is the correction log, the promoted-field registry, and the external mappings —
never the extraction.** Extraction is a commodity; the accumulating, self-correcting asset is not.

**Never pitch "we replace forms with a conversation."** Lead with the two claims above.

---

## 4. How it works (the mechanism)

**Pipeline (each stage independently testable, idempotent, retryable; original immutable & retained):**
```
ingest → normalise → transcribe/OCR → extract → elicit (only if below the actionable floor)
       → deduplicate → promote → structured case → human review → commit → report
```

**Two-layer schema (the core design decision):**
- *Governed core* — small, stable, per case-category. Drives SLA clocks, routing, escalation,
  regulator-facing output. Human-controlled. **The AI never creates a field here.**
- *Emergent layer* — unbounded attribute store. Anything the model attests in a case lands here
  immediately, no schema change, no migration.

**Promotion, not creation** (concept §4.5 — the most important constraint):
- Closed-world grounding: propose only attributes attested in the source text.
- Statistics before semantics: types, cardinality, identifier-ness decided deterministically; model
  calls reserved for semantic discovery only.
- Every candidate is embedded and compared to existing fields + prior candidates; above a similarity
  threshold it maps onto the existing field instead of spawning a synonym → this is what converges.
- Promote to governed core only after recurrence across **N distinct cases** in a category; on
  promotion it acquires type, unit, validation rules; then **history is re-extracted and backfilled**.
- Rule: *recurrence proves necessity; one-offs stay in the bag.*

**Drill-down elicitation** (concept §4.3): every complaint has an object that already exists (order,
booking, delivery, asset, subscription, visit). Only three things genuinely can't be looked up —
*which object*, *what specifically was wrong*, *what the customer wants* — and that is exactly where
the anchor-plus-two budget comes from (it's the real count of unknowns, not an arbitrary limit).
The anchor (order # / phone used to order) is a **key**, not a field; it turns questions into
confirmations. The record can contradict the complaint → surface to the agent, never argue with the
customer; also a fraud signal. Emotion is data. Case created immediately, never blocked on
completeness; reengagement outside the messaging window needs a template — design for it up front.

**Determinism where it matters** (concept §4.6): the model supplies inputs (category, severity
signals, entities); a deterministic rules engine assigns priority, SLA and routing. Defensible in an
audit; never model output.

**Provenance & review** (§4.7–4.8): every value carries source/model/version/prompt-version/
confidence/reviewer. The review screen is the most important interface — source on one side,
extracted fields on the other, low-confidence flagged and focused first, keyboard-driven, < 30s/case.
Corrections stored against the original extraction, never overwritten — that log is the eval set and
the moat.

**No cold start** (§9 of concept): extraction is zero-shot; works on an empty DB day one; the
emergent schema bootstraps from the first case. This kills the "give us six months of history first"
objection and neutralises incumbents' data advantage. Two things are needed at setup, neither is
history: (a) the **object store** connected once (orders/bookings/assets/catalogue/customers) —
self-serve by file upload or API key inside the setup window; extraction works without it but
elicitation won't stay short; (b) **written policy** as text (escalation, priority, SLA). The system
needs *current records*, never *case history*.

---

## 5. What this is NOT

Not a CRM (no pipelines/campaigns/quotes/forecasting) · not a chatbot (it drills to close a gap
within a hard budget, never converses, never attempts resolution) · not autonomous (nothing external
without human approval) · not a reporting suite (specific artefacts, not a dashboard builder).

---

## 6. Quantitative thresholds (the ship gate — measured, not asserted)

Ground-truth set: **≥ 100** real/realistically-messy cases, **≥ 30** Arabic/code-switched, **≥ 20**
too-sparse-to-act. Bolded rows are the ones to be brutally honest about.

| Measure | Ship threshold |
|---|---|
| Governed-core field accuracy | **≥ 95%** |
| Emergent attribute accuracy | ≥ 85% |
| Category classification accuracy | ≥ 90% |
| Accuracy on auto-routed cases only | **≥ 98%** |
| Ambiguous cases correctly flagged not guessed (the trust metric — weight highest) | ≥ 90% |
| Cases requiring zero human edits | ≥ 70% |
| Complaints matched to right object without asking | ≥ 60% |
| Object-match accuracy when matched silently | **≥ 99%** |
| Complaint-vs-record discrepancies surfaced | 100% |
| Questions per case after the anchor (median) | **≤ 2** |
| Asked for something already stated | **0%** |
| Asked for something derivable from the anchor | ≤ 5% |
| Sparse complaints reaching actionable state | ≥ 80% |
| Elicitation abandonment | ≤ 20% |
| Desired outcome captured | ≥ 90% |
| Median review time per case | ≤ 30s |
| Message received → case ready | ≤ 60s |
| Arabic accuracy vs English | within 5 points |
| **Duplicate/synonym fields after 200 cases** | **< 5% of promoted fields** |
| **New-field creation rate, cases 1–50 vs 151–200** | **clearly declining** |
| Backfill correctness after promotion | 100% |

The two bolded convergence rows are the proof of the central idea. If the schema doesn't visibly
settle, the core claim is wrong and we need to know before selling anything.

**Two evidence-based spec deltas (from the 2026 research behind `SOLUTION-EDD.md`; see EDD §13 /
PRD §10 — do not take the original numbers at face value):**
- **"Arabic accuracy vs English within 5 points"** is NOT achievable at any budget today (best Gulf/
  code-switched WER ≈ 19–35% vs ~5–10% English). Re-anchor to *field-level extraction-accuracy parity*
  + mandatory audio-timestamp provenance; measure Wow Moment 7 at the case level, not the transcript.
- **"~200 attributes @ 0.95 precision"** is not citable — use AutoSchemaKG 92% / AutoPKG WKE 0.953;
  keep 0.90–0.95 precision and <5% duplicates as internal SLOs, not external claims.

---

## 7. Roadmap & scope

- **Phase 1 — PoC (all we build now).** Standalone case management on ONE universal, domain-agnostic
  engine: intake (WhatsApp + file/email), extraction, emergent schema with dedup + promotion, review
  screen, one queue, SLA clock, one generated report. "Done properly" = the universal engine proven
  zero-shot across ≥ 2 wildly different domains on the eval set — NOT one hand-built industry pack,
  and NOT several shallow ones. Nothing else.
- **Phase 2 — Integratable module.** Same headless engine writing structured cases into existing
  platforms via connectors. No rip-and-replace.
- **Phase 3 — Resolution intelligence.** Uses accumulated history: which attributes predict fast
  resolution; retires drill questions that never change an outcome; promotes the follow-ups agents
  keep asking by hand. Needs history → deliberately out of PoC scope.

Allowed-to-be-missing / never-ship-without: see `CLAUDE.md` §9 and winning-condition §6.

**Build execution (PoC), full plan in `BUILD-PLAN.md` — LOCAL-first (LLM on the 4070; owner override
2026-08-10, §0), adversarially sequenced (v1.2):**
**Parallel calendar tracks from day zero** (T1 design-partner outreach · T2 Meta Business verification ·
T3 ground-truth collection with signed consent + eval-set ownership) — these are lead time, not build
time. Phases: 0 scaffold · **0.5 de-risk spike** (real noisy Gulf voice→transcript, stamped bilingual
doc→fields, Arabic-RTL PDF — kill the 3 riskiest proofs in a day, before building upstream) · 1 trust
spine (built FIRST) · 2 engine + 4 interfaces + **cost-per-case meter** · 3 intake+normalise · 4
extraction + self-converging schema + light PII gate + **the scorer + a JSON-diff view** (convergence
graded on **REAL collected data, never author-generated synthetic** — that's the claim grading itself) ·
5 object store + entity resolution + anchor+2 (**two verticals only: bakery + home maintenance**; the
other four §4a are addressable market, added with real customers) · 6 confidence/rules · 7 review UI +
commit gate + universal register · 8 full threshold scoring + per-case cost · 9 external gate (3
strangers from T1). **Standing rule (CLAUDE.md §6a): after EVERY phase re-run ALL previous phases green**
(trust spine every time); `nabu-qa` on code, `nabu-ui-test` on UI. **Subagents:** parallelise 3 channel
adapters (P3), 2 object stores (P5), per-metric eval scoring (P8), adversarial RLS review (P1); build
the verbatim-critical core (RLS, convergence thresholds, elicitation) yourself. See also CLAUDE.md §10
(adversarial-review rubric) + §11 here. Setup: `PREREQUISITES.md` (two ready-gates). Phase-4/§7
citations verified real; τ=0.85/0.70 are unvalidated defaults — tune on the scored set.

---

## 8. Known risks & the standing mitigations

| Risk | Mitigation (already decided) |
|---|---|
| Schema fails to converge; synonyms proliferate | Embedding dedup before storage; promotion thresholds; admin merge tooling; convergence tracked as a first-class metric |
| Misclassification becomes invisibly the vendor's fault | Confidence thresholds + triage queue; never auto-route ambiguous cases |
| Managers distrust AI-populated reports | Per-field provenance + confidence visible in every report |
| Case boundaries hard (complaints span many messages over time) | Conversation windowing + explicit new-case-vs-update classification. Budget more effort here than for extraction |
| The intake category absorbs our wedge | Don't compete on conversation. Compete on self-converging schema + voice-first Gulf-Arabic. Moat = correction log + field registry + mappings |
| Elicitation becomes an interrogation | Hard budget anchor+2; questions-per-case tracked; any rising trend = a regression |
| Asks for something already said / lookup-able | Extract-before-ask + infer-from-anchor, enforced in the elicitation policy and measured |
| Customer abandons mid-elicitation | Case created immediately incomplete; never block on completeness; out-of-window reengagement template designed up front |
| Regulatory constraints can't be emergent | Governed core human-controlled; only the attribute layer adapts freely |

---

## 9. The $0 technical strategy (how the hard gaps get closed for free)

> **Sequencing note (v1.2, owner override 2026-08-10 — supersedes the v1.1 note; read first):** this
> **local-stack strategy is now the PoC's PRIMARY path**, not a clinic-#1 deferral. The **PoC builds the
> LOCAL impl of each inference interface** — faster-whisper (ASR) + a quantized Ollama instruct model
> (extraction) + BGE-M3 (embeddings), on the 4070, no external call, no API keys, $0. The CLOUD impls
> (Cohere / Claude Haiku) remain behind the same interfaces but are the deferred path now. What stays
> clinic-#1 is the on-prem/residency tax only (WORM, UAE VPS, PHI gate, separate local-eval bar).
> Everything below describes how each gap is closed at $0 — which is exactly what the PoC now installs.

Standing rule: **hit a hard gap → engineer a working free solution, never punt to a paid vendor.**
Hardware available: user's RTX 4070 (12 GB VRAM) — enough to run the local models below. The only
acceptable spend is metered LLM API in *cents* across the ~100–200 eval cases, and only after a local
option is ruled out. **Hard requirement (§10.2): every inference component below exposes a `local`
backend and a `cloud` backend behind one interface, chosen by config — so the exact same engine runs
fully in-region on the 4070 with no external call, or in cloud/metered mode, with zero code change.**
Concrete plan per gap (to be validated live, not trusted from memory):

- **Gulf-Arabic, code-switched voice transcription** (the moat, and the hardest gap): local
  **Whisper large-v3 / faster-whisper** on the 4070, quantised (int8/fp16) to fit 12 GB. Dialect is
  the risk — mitigate with prompt biasing, an Arabic/English lexicon hint, and a targeted eval slice
  of ≥ 30 code-switched notes. If open ASR underperforms on Gulf dialect, the fallback is *still
  free-tier* cloud ASR for the eval only — never a per-customer paid dependency. Diarisation/VAD via
  free OSS (silero-vad). **This must not be a downgrade vs English — measured, not assumed.**
- **Extraction / semantic discovery / classification (the LLM work):** metered API is fine at PoC
  scale (cents over 100–200 cases). Keep the prompt/model swappable behind the headless engine so a
  local model (e.g. a quantised instruct model on the 4070) can replace it later at zero marginal
  cost. Reserve model calls for *semantic* work only — everything structural is deterministic.
- **OCR (photos, screenshots, forwarded PDFs):** free OSS — Tesseract for text, a local vision model
  or `pdfplumber`/`pymupdf` for PDFs. Region-level provenance (bounding boxes) comes free from the
  OCR output and satisfies "click the value → see the region of the image."
- **Embeddings for schema dedup/convergence:** **fully local, fully free** — `bge`/`e5`/
  `sentence-transformers` on the 4070. No API. Cosine similarity + a tuned threshold is the whole
  convergence mechanism; a local vector index (pgvector / FAISS) stores candidates.
- **Statistics-before-semantics layer:** pure deterministic Python — type inference, cardinality,
  identifier detection (regex/format heuristics for order numbers, phones, dates). $0 by definition.
- **Rules engine (priority / SLA / routing):** deterministic code driven by the customer's written
  policy text. Reproducible, auditable, explainable in one sentence. $0.
- **Persistence, tenancy, provenance, immutability, idempotency:** Postgres (free) with **row-level
  security** for tenant isolation (proven by an automated cross-tenant-read-fails test); append-only
  originals; provenance columns on every value; idempotency keys per pipeline stage. `pgvector` for
  embeddings keeps it one database.
- **Intake channel:** whatever is genuinely self-serve inside the setup window (WhatsApp via a free
  tier / sandbox, or file/email drop for the PoC). Extraction must not depend on any paid channel.
- **Hosting for the external gate:** local or a free tier is acceptable for a PoC; residency
  constraints (UAE PDPL, see open questions) may force local/in-region — design so the engine can run
  entirely locally with no cloud dependency, which also protects the $0 rule.

Everything above is deliberately swappable behind the headless engine API, so upgrading a component
later is a config change, not a rewrite.

---

## 10. Settled build decisions (locked 2026-08-09 — no re-litigating once building starts)

These were the open questions; they are now **decided**. A future session inherits the decisions, not
the debate. Change one only if new, disqualifying data emerges — and record why here.

1. **Domain — DECIDED: domain-agnostic. "A solution for all," from a cake store to a government.**
   This is *the* defining decision and it raises the bar rather than lowering it. Consequences:
   - The governed core is **minimal and universal** — the handful of facts every complaint has
     regardless of industry: the object it concerns, what was wrong, the desired outcome, plus the
     deterministic SLA/priority/routing inputs and the emotion/severity signal. **No industry-specific
     fields are configured in the governed core.** Domain specialisation is *emergent*, never seeded.
   - This is only achievable because of the design we already committed to: zero-shot extraction +
     emergent schema + no cold start (§4). The universality *is* the self-converging-schema moat,
     demonstrated at its strongest. A cake store and a government complaint queue run on the **same
     engine, same empty starting schema**, and the schema grows differently for each because the cases
     differ — that is the wow.
   - **Reconciles with winning-condition §6 ("one category done properly"):** we do NOT hand-build
     several shallow domain packs. We build ONE universal engine done properly, and *prove* it is a
     solution for all by running the eval set across at least two wildly different domains (e.g. a
     bakery and a government service complaint). Depth = the engine's zero-shot + convergence quality,
     not per-domain configuration. Never ship a domain-specific hack that a config file has to touch.
2. **Deployment — DECIDED: BOTH fully-local and cloud, switchable by config.** The engine must run
   end-to-end on the customer's own hardware (in-region / on-prem, RTX 4070-class) with **no external
   call**, *and* in a cloud/metered-API mode — selected by configuration, never by a code change.
   Every inference component (ASR, extraction LLM, embeddings, OCR) sits behind an interface with a
   local backend and a cloud backend. This satisfies UAE PDPL / sector residency for buyers who need
   it and the $0 rule simultaneously. This is now a **hard architecture requirement**, not a "later."
   **REFINED (v1.1, owner): the *architecture* (4 interfaces) ships day one, but the PoC builds only
   the CLOUD impls; LOCAL impls are stubs, built when a clinic is customer #1.** The first market is
   any service/delivery biz down to a cake shop — the opposite end from a health tenant — so the local
   architecture tax is deferred to the segment that needs it. Deferred with local: strict PHI-at-
   promotion gate, a **separate per-deployment eval bar** (local 14B ≠ Claude), and the on-prem test
   target. ~~PoC cloud path = Cohere API + Claude Haiku + BGE-M3, cents scale~~ **→ OWNER OVERRIDE
   2026-08-10 (§0): the PoC path is LOCAL — faster-whisper + Ollama instruct + BGE-M3 on the 4070, $0,
   no API keys; the cloud impls stay behind the interfaces as the deferred path.** `TECH-SPEC.md`
   §0.1/§3/§16.9.
3. **Intake channels — DECIDED: both WhatsApp-native AND file/email drop, from the start.** The
   ingest layer is channel-agnostic; a channel is an adapter that produces the same normalised input.
   WhatsApp via free tier/sandbox; file/email drop for instant self-serve. Extraction never depends on
   any paid channel.
4. **Stack — DECIDED: Python headless engine + React/Vite review UI.** Engine stays headless (API
   only); React/Vite gives the keyboard-driven, provenance-popover review screen the room deserves.
   Postgres + pgvector + RLS for storage/tenancy/embeddings. All $0 / OSS.
5. **Go-to-market** — deferred, informs positioning not code (low-priced self-serve vs sales-led).
6. **"1.5M AED" meaning** — not yet clarified by the buyer; treated as the stakes envelope, not a
   scope constraint. Does not block the build; revisit if it turns out to fix scope.

**Review-pass decisions (v1.1, 2026-08-09) — all confirmed by owner:**
7. **Categories are EMERGENT, discovery auto / activation human-gated.** Zero-shot into a minimal
   *hierarchical* universal starter taxonomy (~6–8 archetypes + `UNCLEAR`) so zero-config delivers
   value; tenant categories are discovered automatically but **never auto-activate** — a wrong category
   is a wrong deadline. Activation needs **a human click + ≥15 distinct cases (not the field threshold
   ~4) + a mandatory mapping to an existing SLA policy**; until then the case sits in its nearest
   parent with the candidate recorded. Actionable floor is derived (three unknowns day one → grows per
   category). Universal default SLA policy ships; written policy is optional override, not a gate.
   Design: `SOLUTION-EDD.md` §16.2 / PRD FR-14.
8. **ASR — OWNER OVERRIDE 2026-08-10 (§0): local faster-whisper large-v3 on the 4070** (word-level
   provenance native / via WhisperX-wav2vec2 alignment; $0, no API). ~~Was: start Cohere Transcribe Arabic
   (Apache-2.0); no native timestamps → mandatory forced-alignment.~~ Cohere stays available as the
   deferred cloud backend behind the ASR interface. EDD §4.
9. **Metric hard-rule:** the ASR-WER and "200@0.95" figures are feasibility evidence only — **never in
   buyer material or as a winning-condition target.** Arabic metric re-anchored to **field-level
   extraction accuracy** (winning-condition §4 row updated).
10. **Focus industries — six is the ADDRESSABLE MARKET; the PoC BUILDS/EVALS TWO (v1.2 review).** Market
    map (PRD §4a): order (bakery, e-commerce), job-visit (home maintenance, automotive), booking
    (hospitality), appointment (salon/spa/fitness) — anchor is the same everywhere (sender phone → the
    tenant's object), only the object changes = the domain-agnostic proof. **Build + evaluate only two —
    bakery + home maintenance (order-shaped vs visit-shaped)** — enough to prove generalisation; the
    other four are added when a **real** customer needs one, NOT as synthetic dev breadth (which only
    manufactures the look of a proven moat).
11. **Eval data:** owner-supplied, owned in writing — ~10–15 design-partner real complaints under a DPA
    + ~15–20 self-recorded (Gulf speakers, scenario cards, WhatsApp) + synthetic; public corpora
    calibration-only. EDD §16.7.
12. **Report = universal manager register** (same report across all six §4a verticals).
    **Regulator-shaped / regulated-artefact reporting is PARKED by owner — out of scope, not to be
    discussed until re-raised.** Archived: `_parked/regulator-shaped-output.md`.

---

## 11. Execution & review principles (hard-learned — the standard for this project)

The owner has repeatedly had to catch judgment gaps that document-vs-document review missed. Root
cause: consistency-checking is blind to buried risk, circular self-validation, scope creep, and
missing viability numbers. **The review standard here is adversarial (outside-in), not consistency-
first.** Full rules in `CLAUDE.md` §10; the durable essence:

- **Sequence risk, not just dependencies.** The riskiest unproven assumptions get proven FIRST (a
  cheap throwaway spike on real inputs), before anything is built on top of them. Concretely for this
  build: Gulf-ASR-on-real-noisy-audio, extraction accuracy, and Arabic-RTL-PDF are the killers — prove
  them in a day-0.5 spike, not in phases 3/4/7.
- **Calendar time starts on day zero.** Design-partner acquisition, Meta Business verification, and
  eval-data collection (with consent + client ownership of the set) are people/time-bound, can fail,
  and run in parallel with code from the start — never scheduled as if instant.
- **Never grade the moat on data you authored.** Convergence and accuracy are proven on real,
  not-self-generated data; the scorer + ground-truth set come early (by the convergence phase), not last.
- **Smallest honest test.** One vertical + one contrast (bakery=order, home-maintenance=job-visit) is
  enough to test whether the object model generalises. Six synthetic verticals manufacture false
  confidence — don't generalise before a real user needs it.
- **Instrument viability from the start:** cost-per-case (vision + self-consistency + backfill
  re-extraction make it > naive estimates), latency, licence, consent — measured, never assumed.
- **Verify every load-bearing fact live** (citations/arXiv IDs, licences per pinned version, prices,
  API limits). A plausible identifier is not a source; a hallucinated citation under the moat is a real
  risk. **Split "ready" gates** into start-blocking vs later-phase-blocking.

Meta-rule: run the five questions (`CLAUDE.md` §10) before calling any plan/design done — so these
surface on the first pass, not the third.
