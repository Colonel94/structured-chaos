# TEST-PLAN.md — Per-phase test plan for the PoC build

> **Status-note — 2026-08-26:** the phase labels and unchecked implementation bullets below are the
> original execution plan and have not been kept current with every later build. Do not infer current
> readiness from an unchecked box here. Use `docs/WINNING-CONDITION-REVIEW.md` for the evidence ledger,
> `engine/eval/PHASE8_SCORECARD.md` for measured thresholds, and the automated test files named here for
> implementation evidence. A later documentation-only pass should reconcile every historical checkbox.

*The working test checklist for the Adaptive Intake PoC. Every phase maps to its **Exit gate** and
**Regression gate** in `BUILD-PLAN.md` (the backbone), scored against `winning-condition.md` (§2 setup,
§3 wow, §4 thresholds, §5 trust, §7 red flags, §8 external) and `CLAUDE.md` (§2 three claims, §3 trust
gates, §6a regression-after-every-phase, §7 scorecard). This file is grounded in those docs and the
tests that actually exist in `engine/tests/` + `scripts/` — it does not invent gates.*

> **⚠ LLM path is LOCAL-on-the-4070 (owner override 2026-08-10).** Wherever BUILD-PLAN says *Claude
> Haiku / Cohere API / API keys / cloud cost-meter*, read **faster-whisper (ASR) · quantized Ollama
> instruct model (extraction) · BGE-M3 (embeddings)**, $0, no external call; the cost meter measures
> **GPU time/throughput**, not API cents. Exit-gate wording below is quoted verbatim from BUILD-PLAN;
> where it says "cloud impl"/"cloud path", the local backend is what the PoC actually exercises.
>
> **ENGLISH-FIRST focus (owner directive 2026-08-12).** Arabic capability is retained in code but
> deprioritised. **Gate-A5 Gulf recordings are PARKED** → Phase-0.5 spikes **#1 and #2 cannot be marked
> green yet** (toolchain proven on synthetic English; real Gulf proof deferred until re-raised).

---

## How to run

| What | Command | Notes |
|---|---|---|
| **Automated suite** (hermetic + DB) | `cd engine && uv run pytest` | Postgres spun up per-session via **testcontainers** (`pgvector/pgvector:pg16`), real Alembic migration applied. **Skips** (not fails) if Docker is unavailable, so the non-DB tests still run anywhere. |
| **Infra live check** | `uv run --project engine python scripts/verify_infra.py` | Postgres reachable (`SELECT 1` as `app_rw` + `CREATE EXTENSION vector` as `intake_admin`) + MinIO bucket write/read/delete round-trip. Run after `docker compose -f deploy/docker-compose.yml up -d db minio`. |
| **Blob live check** | `uv run --project engine python scripts/verify_blob.py` | Content-addressed + write-once + roundtrip against compose MinIO (kept out of the hermetic suite so CI needs no MinIO). |
| **Local-model smokes** (Gate A4) | `scripts/test_ollama.py` · `test_asr.py` · `test_embed.py` · `test_ocr.py` | The four models on the 4070 (run in-container except GPU ASR on host). |
| **Lint/type gate** | `ruff check` · `black --check` · `mypy app` (strict) | Part of `nabu-qa` on every code change. |
| **UI gate** | `nabu-ui-test` (render + screenshot desktop/mobile + inspect pixels) | Mandatory for any UI change (Phases 4 diff-view, 7 review UI). A source audit is **not** sufficient. |

**Standing regression rule (`CLAUDE.md` §6a):** after completing **any** phase, re-run **all earlier
phases' tests — green — before the phase is "done."** Not just the new phase's tests. The **Phase-1
trust spine** (`test_rls_isolation` · `test_immutability` · `test_idempotency` · `test_pii_redaction` +
`verify_blob`) **re-runs at the end of every later phase without exception.** New code passes `nabu-qa`;
any UI change passes `nabu-ui-test` on real pixels, before the phase closes.

**Status legend:** ✅ DONE (built + verified live) · ⏳ PENDING · ⛔ BLOCKED/PARKED.

**Phase status at a glance:** Phase 0 ✅ · Phase 0.5 partial (spike #3 ✅; #1/#2 ⛔ parked on Gate-A5) ·
Phase 1 ✅ · Phases 2–9 ⏳.

---

## Phase 0 — Foundation & scaffolding ✅ DONE
**Goal:** a running skeleton — repo, containers, CI, config — that boots and does nothing yet.

**Automated tests**
- [x] `tests/test_health.py::test_health_ok` — app boots, `/health` returns `status:"ok"` + the four backend keys `{asr, llm, embedding, blob}`.
- [x] `tests/test_config_backends.py::test_fake_backends_selected` — config loads the **fake** backend for all four interfaces.
- [x] `tests/test_config_backends.py::test_local_backends_are_wired` — the `local` backends resolve behind the interfaces (was `test_local_backend_is_a_loud_stub`; the local-first override made local the built path, so it no longer stubs). Plus `test_cloud_inference_backends_are_not_built_yet` — `cloud` ASR/LLM/embed raise until built.
- [x] `tests/test_config_backends.py::test_fake_embedding_is_1024d` — fake embedding returns BGE-M3 dimensionality (1024).
- [x] CI green on the empty/scaffold suite (ruff/black/mypy strict + pytest + Vitest). Verified: engine **4 passed**, mypy strict 19 files; UI **1 vitest passed**, `vite build` ok.

**Manual / live checks**
- [x] `docker compose -f deploy/docker-compose.yml up -d db minio` healthy, then `scripts/verify_infra.py` → **PASS(pg) + PASS(minio)** (Gate A2, verified 2026-08-11).
- [x] Config `local|cloud|fake` backend switch loads a fake backend with no external call.

**Exit gate (verbatim):** *"`docker compose up` healthy; CI green on an empty test; config loads a fake backend."*
**Regression gate:** n/a (first phase) — but the CI harness that all later regressions run in is proven here.

---

## Phase 0.5 — De-risk spike (throwaway, one day, zero integration) ⛔ PARTIAL
**Goal:** kill or confirm the three assumptions the whole build rests on, in isolation, in a day.

**Manual / eyeball checks** (three throwaway scripts — run and look at the output; no automated suite)
- [ ] **Spike #1 — Gulf voice note → transcript** (`spike/spike1_asr.py`). Toolchain runs (faster-whisper on GPU, proven on a synthetic English clip). ⛔ **NOT green** — real proof needs the Gate-A5 noisy Gulf recordings (`data/spike/audio`), which are **PARKED**.
- [ ] **Spike #2 — photographed, stamped, bilingual doc → fields** (`spike/spike2_doc.py`, pypdfium2 render → PaddleOCR/vision). Toolchain runs (proven on a synthetic Arabic text image). ⛔ **NOT green** — needs the Gate-A5 stamped bilingual photo (`data/spike/docs`), **PARKED**.
- [x] **Spike #3 — structured data → Arabic RTL PDF** (WeasyPrint). ✅ **PASS, visually verified** (correct shaping/joining, RTL column order, bidi with embedded Latin/numbers). No owner input needed; one killer is dead.

**Exit gate (verbatim):** *"each of the three either passes or the plan changes now (swap tool / adjust claim / re-sequence) — before Phase 1. A red here is cheap; a red at Phase 7 is not."*
> **Status:** #3 PASS; #1/#2 STAGED but un-proven because Gate-A5 recordings are parked. The build
> proceeded to Phase 1 (which has zero dependency on the recordings) per owner directive. **This phase
> does not fully close until #1/#2 run on real Gulf inputs.**
**Regression gate:** n/a (throwaway).

---

## Phase 1 — Trust spine: store, tenancy, provenance, immutability, idempotency ✅ DONE
**Goal:** the data layer with tenant isolation, per-value provenance, immutable originals, append-only corrections, idempotent stages.

**Automated tests** — the permanent trust spine (13 tests green; re-runs every later phase)
- [x] `tests/test_rls_isolation.py::test_app_role_cannot_bypass_rls` — runtime `app_rw` is `rolsuper=false, rolbypassrls=false` (the gate is meaningless if the app connects as superuser).
- [x] `test_rls_isolation.py::test_cross_tenant_read_is_empty` — tenant B sees **0** of tenant A's cases; positive control confirms A sees its own.
- [x] `test_rls_isolation.py::test_cross_tenant_write_is_rejected` — `WITH CHECK` rejects planting a row stamped for another tenant.
- [x] `test_rls_isolation.py::test_app_role_cannot_repoint_tenant_id` — column-scoped UPDATE grant excludes `tenant_id`; a case cannot be moved to another tenant.
- [x] `test_rls_isolation.py::test_unset_context_reads_zero` — a connection with no `app.tenant_id` set reads nothing (fail-closed default).
- [x] `tests/test_immutability.py::test_append_only_tables_reject_update_and_delete` — trigger blocks UPDATE/DELETE on `source_document`/`field_extraction`/`field_correction` even for the **superuser**.
- [x] `test_immutability.py::test_append_only_tables_reject_truncate` — statement-level guard blocks a wholesale TRUNCATE wipe.
- [x] `test_immutability.py::test_app_role_denied_update_delete_on_append_only` — defence in depth: `app_rw` lacks UPDATE/DELETE on the logs.
- [x] `test_immutability.py::test_provenance_is_required` — a value with NULL `source_span`/source doc/confidence is rejected (no value exists without complete provenance).
- [x] `tests/test_idempotency.py::test_idempotency_key_is_deterministic_and_version_sensitive` — same inputs → same key; bumped prompt version → different key.
- [x] `test_idempotency.py::test_completed_stage_blocks_replay` — a completed stage is skipped on replay (idempotent success).
- [x] `test_idempotency.py::test_crashed_stage_is_reclaimable` — a claimed-but-not-completed stage is re-claimable (work retried, not lost).
- [x] `test_idempotency.py::test_field_current_rebuilds_from_logs` — `field_current` recomputes from the logs (latest correction beats latest extraction; monotonic `seq` breaks same-txn ties); rebuild is idempotent (no duplicate projection rows).
- [x] `tests/test_pii_redaction.py::test_pii_never_appears_in_logs` — known-PII (phone/email, incl. buried in free text) never appears raw in a log line; non-PII survives.

**Manual / live checks**
- [x] `scripts/verify_blob.py` → content-addressed + write-once + roundtrip on live MinIO (immutable originals, EDD §7.2).
- [x] Adversarial trust-spine review (subagent) at phase close per `CLAUDE.md` §10.
- [x] `ruff`/`black` clean; `mypy --strict` clean (24 files).

**Exit gate (verbatim, BLOCKING trust gates):** *"the **cross-tenant-read-fails test passes as the app role** (`rolbypassrls=false`); replay of any stage produces no duplicate; `field_current` recomputes from the logs; a known-PII string never appears in logs."*
**Regression gate:** this suite becomes the permanent spine — **it re-runs at the end of every later phase.**

---

## Phase 2 — Headless engine skeleton + 4 backend interfaces ✅ DONE
**Goal:** the FastAPI engine + the four `Protocol` interfaces (ASR/LLM/Embedding/Blob), local impls built (per override; cloud stubbed), orchestrated by Procrastinate.

**Automated tests**
- [x] `test_queue.py::test_enqueue_commits_atomically_with_the_write` + `test_rollback_leaves_no_phantom_job_or_orphan_case` — a job is deferred on the **same psycopg3 transaction** as the business write: commit → case+job persist; **rollback → no phantom job, no orphan case** (transactional enqueue). ✅ **unit 3 (`c5967a9`)**.
- [x] `test_config_backends.py::test_local_backends_are_wired` — the local impls (faster-whisper / Ollama / BGE-M3; blob: MinIO) resolve behind the interfaces. **Live:** `scripts/verify_backends_local.py` → Ollama real completion + schema-constrained extraction (fault+desired_outcome). ✅ **unit 1 (`d9e0e33`)**.
- [x] `test_cost_meter.py` — **cost-per-case meter** logs tokens/audio-seconds/GPU-time (`wall_ms`) against a `case_id` and **reports a per-case figure**; aggregation per case; tenant-isolated. ✅ **unit 2 (`8ba8f84`)**.
- [x] pipeline stage contract is **idempotent/retryable** — the Phase-1 `claim_stage`/`complete_stage` ledger (crash-reclaimable) is what Procrastinate task bodies plug into (Phase 3). ✅ (Phase 1)
- [x] `test_queue.py::test_backfill_uses_its_own_low_priority_queue` — dedicated **low-priority backfill queue** exists and is separately schedulable. ✅ **unit 3**.

**Manual / live checks**
- [x] `uv run --project engine python scripts/verify_backends_local.py` → 2/2 (LLM); `--full` adds BGE+whisper. Ollama must be running.
- [x] Transactional enqueue proven live (spike) + `scripts/bootstrap_procrastinate.py` applied the queue schema to the live DB. *Worker-side kill-mid-run/no-lost-job is Procrastinate's own at-least-once + row-lock guarantee; the enqueue atomicity we implement is what's tested.*

**Exit gate (verbatim):** *"a trivial job flows ingest→persist through Procrastinate in one transaction (kill mid-run → no orphan/phantom); each interface's cloud impl returns a real response; local stubs raise `NotImplemented`; **the cost meter reports a per-case $ figure.**"* *(Local override: the **local** impl is the one built + returning a real response for the PoC; the cost meter reports GPU-time, not API cents.)*
**Regression gate:** Phase 1 spine + the transactional-enqueue no-orphan test.

---

## Phase 3 — Intake + normalisation ⏳ PENDING
**Goal:** real input in → normalised text/media out, both channels, with segment-level provenance.

**Automated tests that SHOULD exist**
- [ ] TODO — a messy multi-message thread with **voice note + photo + PDF** normalises to text **with source anchors** (segment/utterance-level for audio, region for image, sentence for text).
- [ ] TODO — **originals stored immutably** on ingest (re-uses the Phase-1 blob + immutability gates).
- [ ] TODO — **conversation windowing** (24h gap + state + new-vs-follow-up classifier) splits a new case from a follow-up correctly.
- [ ] TODO — **intake idempotency:** re-ingesting the same thread → **no duplicate case**.
- [ ] TODO — file-drop parser (WhatsApp chat-export) + uploads produce the same normalised input as the WhatsApp adapter (channel-agnostic).

**Manual / live checks**
- [ ] Feed a real exported WhatsApp thread through file-drop; eyeball the normalised text + anchors.
- [ ] (If WhatsApp channel built) test-number message → tunnelled webhook → 2-step media fetch within the 5-min URL window.

**Exit gate (verbatim):** *"a messy multi-message thread with a voice note + photo + PDF becomes normalised text with source anchors; originals stored immutably; windowing splits a new case from a follow-up correctly."*
**Regression gate:** Phases 1–2 + intake idempotency (re-ingest → no dup case).

---

## Phase 4 — Extraction + self-converging schema (the moat) + PII gate + the scorer ⏳ PENDING
**Goal:** zero-shot structured case; the two-layer schema that promotes, dedupes, backfills — **proven on data we did NOT author.**

**Automated tests that SHOULD exist**
- [ ] TODO — a case extracts to **governed core + emergent** layers (constrained GBNF/JSON-schema output; `FieldValidity<1.0` rejected).
- [ ] TODO — **closed-world grounding:** no hallucinated field survives (a field not attested in the source is rejected).
- [ ] TODO — a **synonym merges** onto an existing field instead of duplicating (BGE-M3 → pgvector dedup at τ; **τ tuned on the scored set**, not trusted as a default — Claim 1 / `CLAUDE.md` §2).
- [ ] TODO — a field **promotes after N distinct cases** and **backfills history 100%** (idempotent, bounded, on the low-priority queue).
- [ ] TODO — categories are **human-gated** (click + ≥15 cases + SLA mapping) — never auto-activated.
- [ ] TODO — **convergence monitor:** duplicate/synonym fields **<5%** and a **declining new-field rate** — measured on the **REAL collected T3 set, never on template cases we generated** (`CLAUDE.md` §10 Q3: template cases converge by construction = the claim grading itself).
- [ ] TODO — **light PII sensitivity gate** fires at promotion.
- [ ] TODO — the **pandas scorer** exists here (not Phase 8) and runs against the labelled ground-truth set.

**Manual / live checks**
- [ ] **JSON-diff review view** (extraction-vs-corrected, in-browser) renders — run **`nabu-ui-test`** on real pixels (first UI artefact).
- [ ] Run the scorer over the current T3 cases; read the convergence plots (new-field rate 1–50 vs 151–200, duplicate %).

**Exit gate (verbatim, no self-grading):** *"a case extracts to governed core + emergent; a synonym merges instead of duplicating; a field promotes after N and **backfills history 100%**; **convergence (declining new-field rate, <5% duplicates) is measured on the REAL collected set — never on cases we generated from templates** (template cases converge by construction — that is the claim grading itself); no hallucinated field survives."*
**Regression gate:** Phases 1–3 + the convergence/backfill/grounding suite.

---

## Phase 5 — Object store + entity resolution + drill-down elicitation ⏳ PENDING
**Goal:** the anchor→confirmation loop and the ≤2-question drill.

**Automated tests that SHOULD exist**
- [ ] TODO — self-serve object-store ingest (arbitrary schema → profiling → hashed exact-key + pgvector fuzzy) for the **two verticals only** (bakery orders + home-maintenance jobs).
- [ ] TODO — **entity resolution:** silent match only when unique → **≥99%** object-match accuracy when matched silently (winning-condition §4).
- [ ] TODO — the **four-word "delivery was bad"** case resolves the object by phone, **confirms** the delay rather than asking, captures desired outcome, closes in **≤2 questions** (anchor+2 budget **enforced in code** — Claim 3 / `CLAUDE.md` §2/§3).
- [ ] TODO — a walk-in with **no matching object degrades to open questions** without failing (fallback path).
- [ ] TODO — a **complaint-vs-record contradiction surfaces to the agent** (100%), never argues with the customer.
- [ ] TODO — **desired outcome always asked**; questions-per-case metric recorded; **0%** asks-for-something-already-stated.

**Manual / live checks**
- [ ] Upload each sample object store (`assets/objectstores/bakery_orders.csv`, `home_maintenance_jobs.csv`); confirm self-serve ingest inside the setup window.
- [ ] Walk the anchor→confirmation loop by hand on a sparse case; count the questions (watch the count, not the rationale — `CLAUDE.md` §2).

**Exit gate (verbatim):** *"the four-word "delivery was bad" case resolves the object by phone, confirms the delay rather than asking, captures desired outcome, and closes in ≤2 questions; a walk-in with no object degrades to open questions without failing; a complaint-vs-record contradiction surfaces to the agent."*
**Regression gate:** Phases 1–4 + the anchor-budget + silent-match-accuracy tests.

---

## Phase 6 — Confidence/abstention + deterministic rules engine ⏳ PENDING
**Goal:** "refuse to guess," and reproducible priority/SLA/routing.

**Automated tests that SHOULD exist**
- [ ] TODO — an **ambiguous field routes to review, not a wrong value** (Claim 2 / winning-condition Moment 5 — the trust metric, weight highest).
- [ ] TODO — self-consistency (capped-N on gray-band fields only) + calibrated logprobs (Platt/temperature) drive selective-prediction routing (τ for ≥98% auto-routed / ≥90% flagged).
- [ ] TODO — **deterministic rules engine:** same inputs + same policy → **identical** SLA/priority every time, **explainable in one sentence** (never model output).
- [ ] TODO — the **clock starts at first contact**, not at completeness.
- [ ] TODO — the abstention threshold holds **both** SLAs (≥98% auto-routed, ≥90% flagged) on a dev slice.

**Manual / live checks**
- [ ] Run the same case twice through the rules engine; diff the SLA/priority output → must be byte-identical.
- [ ] Read the one-sentence explanation for a routed case.

**Exit gate (verbatim):** *"ambiguous fields route to review not a wrong value; same inputs+policy → identical SLA/priority, explainable in one sentence; the abstention threshold holds both SLAs on a dev slice."*
**Regression gate:** Phases 1–5 + confidence-routing + rules-determinism tests.

---

## Phase 7 — Review UI + commit gate + universal register report ⏳ PENDING
**Goal:** the <30s keyboard review screen, the human-approval gate, and the one report.

**Automated tests that SHOULD exist**
- [ ] TODO — **commit gate:** no report / notification / external write fires **before human approval** (trust gate — `CLAUDE.md` §3; assert on model output alone → nothing external happens).
- [ ] TODO — **provenance traceability:** clicking any value jumps to its exact source — audio **segment** (wavesurfer.js), image **region** (bbox overlay), or **sentence** — in <5s.
- [ ] TODO — universal manager register + one **WeasyPrint** report (RTL-safe) exports PDF/CSV with every value traceable.

**Manual / live checks (UI phase — pixels, not source)**
- [ ] **`nabu-ui-test`** on real pixels, desktop + mobile; re-run after every fix (mandatory, `CLAUDE.md` §8).
- [ ] A reviewer clears a case in **<30s** keyboard-driven (median review-time metric).
- [ ] Click a value → land on its audio segment / image bbox / sentence; confirm the jump.
- [ ] Attempt an external action pre-approval → confirm it is blocked.

**Exit gate (verbatim):** *"a reviewer clears a case in <30s; clicking any value jumps to its source (audio segment / image region / sentence); no report/notification/external write occurs before approval; **`nabu-ui-test` passes on real pixels.**"*
**Regression gate:** Phases 1–6 + the commit-gate + provenance-traceability tests.

---

## Phase 8 — Full threshold scoring (the scorer already exists from Phase 4) ⏳ PENDING
**Goal:** run the complete quantitative ship gate on the matured ground-truth set.

**Automated tests / scorer runs that SHOULD exist**
- [ ] TODO — the scorer runs over the **full T3 set** (≥100 cases, ≥30 Gulf-Arabic voice, ≥20 sparse) across **both built verticals** (bakery + home maintenance); DPA + self-recorded real cases are the spine, synthetic fills injection/sparse edges only.
- [ ] TODO — **every winning-condition §4 threshold measured and met** (table below).
- [ ] TODO — **Arabic = field-level extraction parity within 5 points, NOT WER** (delta Δ1; raw WER never a ship metric / buyer claim).
- [ ] TODO — convergence rows hold **on real data**: duplicates **<5%**, **declining** new-field rate.
- [ ] TODO — **per-case cost** (GPU-time) reported against the pricing model.
- [ ] TODO — risk-coverage + calibration plots produced; a **completeness-critic** confirms no §4 metric is unmeasured.

**Manual / live checks**
- [ ] Parallelise scoring per slice (Arabic / sparse / injection / object-match), then synthesise.
- [ ] Read every §4 row's measured value against its threshold; flag any miss (fix the design, don't ship and hope).

**Exit gate (verbatim):** *"every §4 threshold measured and met on the **cloud path** (field-level Arabic parity, not WER — Δ1); convergence rows (duplicates <5%, declining new-field rate) hold **on real data**; the **per-case cost** is reported against the pricing model."* *(Local override: measured on the **local** 4070 path, which the PoC runs; the local-vs-cloud bar delta is logged.)*
**Regression gate:** the full Phases 1–7 suite runs as part of the eval build.

---

## Phase 9 — External gate + winning-condition scorecard ⏳ PENDING
**Goal:** the actual winning condition (winning-condition §8/§9).

**Manual / human checks** (real humans + owner judgement — no subagent decides this)
- [ ] Run the **setup gate** (§2, all boxes) end-to-end on the two demos (bakery + home maintenance).
- [ ] Confirm the **seven wow moments** (§3), each **without prompting** — dry-run a pre-flight beforehand.
- [ ] **Three strangers, no walkthrough, own messy inputs** (recruited via track T1 from Phase 0, lined up in advance):
  - [ ] All three complete a case without asking you a question.
  - [ ] At least two ask **how** it did something, unprompted.
  - [ ] At least one asks whether they can use it for something you hadn't thought of.
  - [ ] None asks for a feature before asking about price.
  - [ ] **At least one asks what it costs** — the actual winning condition.
- [ ] Confirm **no red flag** (§7) is present.
- [ ] Fill the scorecard honestly.

**Exit gate (verbatim, SHIP):** *"all six scorecard rows clean; the win is **a stranger asking the price before asking for a feature.**"*
**Regression gate:** the entire suite green; no red flag (winning-condition §7) present.

---

## Ship gate — the scorecard (`CLAUDE.md` §7 · winning-condition §9)

Ship only when **all six** rows are clean. Do not fill optimistically; do not ship on the wow moments alone.

| Gate | Source | How it's measured | Phase |
|---|---|---|---|
| **Setup gate** — every box (zero-config, <10 min to first value, empty DB, no per-customer tuning, you're not in the room, object-store self-serve inside the 10 min) | winning-condition §2 | Timed run by someone who has never seen it; object-store upload inside the window | 9 (built on 3/5) |
| **Seven wow moments**, each without prompting | winning-condition §3 | Live demo on the two verticals; dry-run pre-flight | 9 (mechanisms land 3–7) |
| **Quantitative thresholds** met on the ground-truth set | winning-condition §4 | The **Phase-4 pandas scorer** over the **real T3 set** (≥100 / ≥30 Arabic / ≥20 sparse) | 8 |
| **Trust gates** — every box | `CLAUDE.md` §3 / winning-condition §5 | The **Phase-1 spine** (`test_rls_isolation`, `test_immutability`, `test_idempotency`, `test_pii_redaction`, `verify_blob`) **re-run every phase** + Phase-7 commit-gate/provenance + Phase-6 determinism | 1 (✅) → re-run every phase |
| **No red flags present** | winning-condition §7 | Owner + stranger observation in the external gate; the last red flag ("touch a DB/config/prompt to make a case work") disqualifies outright | 9 |
| **External gate** — 3 strangers, no walkthrough, complete a case without asking you a question | winning-condition §8 | Track-T1 strangers on their own messy inputs; owner watches and says nothing | 9 |

### Quantitative thresholds (winning-condition §4 / `longterm_context.md` §6) — scored by the Phase-8 run on the real T3 set
Bolded rows are the ones to be brutally honest about (the convergence proof + the trust metric).

| Measure | Ship threshold |
|---|---|
| Governed-core field accuracy | **≥ 95%** |
| Emergent attribute accuracy | ≥ 85% |
| Category classification accuracy | ≥ 90% |
| Accuracy on auto-routed cases only | **≥ 98%** |
| Ambiguous cases correctly flagged not guessed (trust metric — weight highest) | ≥ 90% |
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
| Arabic accuracy vs English (**field-level, not WER**) | within 5 points |
| **Duplicate/synonym fields after 200 cases** | **< 5% of promoted fields** |
| **New-field creation rate, cases 1–50 vs 151–200** | **clearly declining** |
| Backfill correctness after promotion | 100% |

> **The two bolded convergence rows are the proof of the central idea.** If the schema doesn't visibly
> settle on real data, the core claim is wrong — fix the design, don't ship and hope (`CLAUDE.md` §2,
> winning-condition §10). **These must be scored on data we did NOT author** (`CLAUDE.md` §10 Q3).
