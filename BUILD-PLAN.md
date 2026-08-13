# Phased Build Plan — Adaptive Intake (PoC → winning condition)

*The full build, Phase 0 → ship, for the PoC (LLM path: **local-on-the-4070** — see banner). Each phase
is an independently testable slice. Grounds in `TECH-SPEC.md` (stack), `SOLUTION-EDD.md` (design),
`PRD.md` (requirements), `winning-condition.md` (the gate). Prerequisites: `PREREQUISITES.md`.*

*Version 1.0 — 2026-08-09.*

> **⚠ OWNER OVERRIDE — 2026-08-10 (authoritative: `longterm_context.md` §0).** The PoC's LLM path is now
> **LOCAL, on the owner's RTX 4070 — not cloud.** Wherever a phase below builds/uses *Claude Haiku*
> (extraction), *Cohere Transcribe* (ASR), *Anthropic/Cohere API keys*, or a *per-case cloud-cost meter*,
> read instead: **faster-whisper** (ASR) · **a quantized instruct model via Ollama** (extraction) ·
> **BGE-M3** (embeddings) — all local, no external call, no API keys, $0 (so the cost-meter measures GPU
> time/throughput, not API cents). Phase order and the four-interface architecture are unchanged; only the
> first-built backend flips to local. Logged consequence (§0): local extraction quality < Haiku on the
> hard Gulf/code-switched slice, so the ≥95%/≥98% thresholds get harder — the Phase-0.5 spike measures
> this on real data first. **Until per-phase rewrites land, this banner overrides any cloud-first text.**

---

## How to read this

Each phase has: **Goal · Build · Subagents · Exit gate · Regression gate.**

- **Regression rule (now in `CLAUDE.md` §6a): after every phase, re-run the tests of ALL previous
  phases, green, before the phase is "done."** Each phase below states what its regression gate covers.
- **Subagents** names *when* to fan out and *when not to*, following the standing rule: parallelise
  independent/discovery work; build the verbatim-critical core (RLS, the convergence algorithm) in a
  single context yourself — subagent summaries blur the exact thresholds and policies that matter.
- **UI phases must pass `nabu-ui-test`** (render + screenshot + inspect pixels), not a code audit.
  **All new code passes `nabu-qa`** before a phase closes.
- **Two moving costs are instrumented, not estimated:** **cost-per-case** (from Phase 2) and the
  **ground-truth set** (collected from Phase 0). Both decide go/no-go questions you don't want to learn
  at Phase 9.

---

## Runs in parallel from day one (calendar time, not build time)
These are **sales/legal/vendor lead times**, not code. They start the same day as Phase 0 and run
alongside the whole build, because each can take days-to-weeks and can fail:
- **T1 — Design-partner outreach.** There is no design partner yet; acquiring one is a sales cycle. Start
  outreach now; the **DPA is drafted the day someone says yes** (not "before Phase 8"). The real eval
  data and the three Phase-9 strangers come from here.
- **T2 — Meta WhatsApp Business verification (production).** The dev **test number** (≤5 recipients)
  covers Phases 3–8, but **production** needs Meta Business verification — slow, can fail. Start it now.
- **T3 — Ground-truth data collection.** Self-record ~15–20 real Gulf voice cases (8–10 speakers,
  scenario cards, WhatsApp, **with signed consent + eval-set ownership assigned to us**) + gather
  design-partner cases under the DPA. This feeds the scorer that lands at **Phase 4**, not Phase 8.

---

## Phase 0 — Foundation & scaffolding
- **Goal:** a running skeleton — repo, containers, CI, config — that boots and does nothing yet.
- **Build:** monorepo (TECH-SPEC §4); `docker-compose` (Postgres+pgvector, MinIO); `pydantic-settings`
  with the `local|cloud` backend switch; `.env` wiring; CI (ruff/black/mypy + pytest + Vitest); a
  `/health` endpoint.
- **Subagents:** *Optional, one research agent* to pin exact latest-stable versions of the stack and
  flag any breaking API change since this spec. Otherwise single-context.
- **Exit gate:** `docker compose up` healthy; CI green on an empty test; config loads a fake backend.
- **Regression gate:** n/a (first phase) — but the CI harness that all later regressions run in is proven here.

## Phase 0.5 — De-risk spike (one day, three throwaway scripts, zero integration)
*The three riskiest proofs are otherwise buried at Phases 3, 4 and 7 — you'd discover a fatal flaw after
building everything upstream of it. Prove them cold, first, so the plan can change before it's expensive.*
- **Goal:** kill or confirm the three assumptions the whole build rests on, in isolation, in a day.
- **Build (throwaway — delete after):**
  1. **Real Gulf voice note → transcript.** A genuine complaint voice note recorded in a *noisy real
     environment* (kitchen/street), through Cohere API. Is it usable, or unusable on real audio?
  2. **Photographed, stamped, bilingual document → fields.** A real angled/stamped Arabic-English doc
     through the vision path (pypdfium2 render → PaddleOCR/vision extraction). Does it read?
  3. **Structured data → Arabic RTL PDF.** WeasyPrint renders an Arabic register row. Does the RTL/shaping
     come out correct, or does it mangle?
- **Inputs (day-one, from PREREQUISITES §6):** 3–5 real Gulf voice notes + 1 photographed stamped
  bilingual document. Record them yourself in an hour.
- **Subagents:** None — three tiny scripts, run and eyeball the output.
- **Exit gate:** each of the three either passes or the plan changes now (swap tool / adjust claim /
  re-sequence) — *before* Phase 1. A red here is cheap; a red at Phase 7 is not.
- **Regression gate:** n/a (throwaway).

## Phase 1 — Trust spine: store, tenancy, provenance, immutability, idempotency
*Built first, because nothing is trustworthy until isolation is proven (EDD §7).*
- **Goal:** the data layer with tenant isolation, per-value provenance, immutable originals, append-only
  corrections, idempotent stages.
- **Build:** Postgres schema + Alembic; **RLS** (session-GUC, `FORCE`, fail-closed `NULLIF`); the three
  append-only logs (`source_document`, `field_extraction`, `field_correction`) + the `field_current`
  projection; MinIO blob store with content-addressing; idempotency-key constraint; structlog with PII
  redaction.
- **Subagents:** *One adversarial reviewer* to attempt cross-tenant reads/writes and log leakage —
  independent perspective on the isolation gate. Core schema/RLS: build yourself (verbatim-critical).
- **Exit gate (BLOCKING trust gates):** the **cross-tenant-read-fails test passes as the app role**
  (`rolbypassrls=false`); replay of any stage produces no duplicate; `field_current` recomputes from
  the logs; a known-PII string never appears in logs.
- **Regression gate:** this suite becomes the permanent spine — **it re-runs at the end of every later phase.**

## Phase 2 — Headless engine skeleton + 4 backend interfaces
- **Goal:** the FastAPI engine + the four `Protocol` interfaces (ASR/LLM/Embedding/Blob), **cloud impls
  built, local impls stubbed**, orchestrated by Procrastinate.
- **Build:** `LLMBackend`→Claude Haiku (structured output), `ASRBackend`→Cohere API, `EmbeddingBackend`
  →BGE-M3 self-hosted, `BlobStore`→MinIO/S3; Procrastinate wired for **transactional enqueue** + a
  **dedicated low-priority backfill queue**; the pipeline stage contract (idempotent/retryable).
  **Cost-per-case meter (new):** every backend call logs tokens/audio-seconds + $ against a `case_id`,
  aggregated per case — so the real per-case cost (incl. vision, self-consistency, and backfill
  re-extraction) is *measured* as features land, not estimated. This decides whether per-case pricing survives.
- **Subagents:** *Optional, short research spike* to confirm current Anthropic structured-output + Cohere
  transcription request shapes. Implementation: single-context.
- **Exit gate:** a trivial job flows ingest→persist through Procrastinate in one transaction (kill mid-run
  → no orphan/phantom); each interface's impl returns a real response; **the cost meter reports a per-case
  $ figure.** *(v1.2 reality, per the banner: the **LOCAL** impls are built (faster-whisper/Ollama/BGE-M3);
  the CLOUD impls are the deferred path and raise `ImportError` if selected — the inverse of the original
  cloud-first wording. The meter's per-case wiring into the real ASR/OCR pipeline landed in Phase 3, GAP-1.)*
- **Regression gate:** Phase 1 spine + the transactional-enqueue no-orphan test.

## Phase 3 — Intake + normalisation
- **STATUS (2026-08-13): DONE + verified live (EN-first, file-drop).** In-house WhatsApp export parser
  (iOS/Android) + upload adapter; normalisation router (audio=faster-whisper+vad_filter · ocr=PaddleOCR
  container-only · pdf=pdfplumber+pypdfium2 · text) with Citation-shaped provenance spans; conversation
  windowing (24h/close-state/LLM classifier, biases NEW); ingest orchestrator (immutable content-addressed
  source docs + transactional normalise enqueue + re-ingest dedup); `pipeline.normalise` stage on the
  claim/complete ledger; migrations `0005` normalised_content + `0006` contact_ref. **A-MED + F7 closed.**
  63 tests green; live E2E proof (2-case windowing split, projection, idempotent replay); ASR proven on GPU.
  Deferred within: WhatsApp live webhook (Meta test number, T2) + email drop (UAE mailbox). Commit `8759a34`.
- **Goal:** real input in → normalised text/media out, both channels, with segment-level provenance.
- **Build:** **file-drop first** (WhatsApp chat-export parser in-house + uploads), then **WhatsApp test
  number** (webhook + 2-step media fetch, download-on-receipt within the 5-min URL); normalise: ffmpeg
  + silero-vad + ~~**Cohere API ASR**~~ **→ local `WhisperASR` (faster-whisper large-v3), already built in
  Phase 2** (segment-level timestamps native) + **PaddleOCR** + **pdfplumber/pypdfium2**;
  conversation windowing (24h gap + state + new-vs-follow-up classifier). **Provenance model is
  settled (F5, migration 0004): extraction cites MANY sources via `extraction_citation` with roles;
  each inbound message/file is a `source_document`, object-store lookups are `object_snapshot` docs.**
- **Subagents:** **Parallelise (fan-out).** The three channel adapters (file, WhatsApp, email-poll) are
  independent → one subagent each, then integrate. *Plus one research agent* to re-verify current
  WhatsApp Cloud API limits/media rules at build time (they change). Normalisation pipeline: single-context.
- **Exit gate:** a messy multi-message thread with a voice note + photo + PDF becomes normalised text with
  source anchors; originals stored immutably; windowing splits a new case from a follow-up correctly.
- **Regression gate:** Phases 1–2 + intake idempotency (re-ingest → no dup case).

## Phase 4 — Extraction + self-converging schema (the moat) + light PII gate + the scorer
- **Goal:** zero-shot structured case; the two-layer schema that promotes, dedupes, backfills — **proven
  on data we did NOT author.**
- **Build:** `LLMClient` extraction with **GBNF/JSON-schema-constrained** output + closed-world grounding
  (FieldValidity<1.0 reject); statistics-before-semantics profiling; BGE-M3 embeddings → pgvector dedup
  (τ merge / τ admit — **one lab's tuned defaults (Jonnalagedda et al. 2026, arXiv:2606.05415 — verified
  real, but no published sensitivity sweep), so tune on the scored set, EDD §6**); nightly
  complete-linkage re-cluster; recurrence promotion (fields N; **categories
  human-gated: click + ≥15 cases + SLA mapping**); idempotent bounded **backfill on the low-priority
  queue**; convergence monitor; **light PII sensitivity gate at promotion**.
- **The scorer lands here, not Phase 8.** You cannot tune τ or N, and Phase 6's calibration is meaningless,
  without a *labelled* set. Build the pandas scorer now and point it at the **real ground-truth cases from
  track T3** (growing since Phase 0).
- **A crude JSON-diff review view lands here too** — extraction-vs-corrected, in the browser. Internal
  sanity check *and* the first recordable/marketable artefact (no nine-phase silence before the Phase-7 UI).
- **Subagents:** **Core built by you, single-context** — convergence thresholds, grounding, promotion are
  the moat and verbatim-critical. Fan out only labelling help. *One research spike* for Ollama-stub/GBNF +
  Haiku structured-output syntax.
- **Exit gate (no self-grading):** a case extracts to governed core + emergent; a synonym merges instead of
  duplicating; a field promotes after N and **backfills history 100%**; **convergence (declining new-field
  rate, <5% duplicates) is measured on the REAL collected set — never on cases we generated from
  templates** (template cases converge by construction — that is the claim grading itself); no hallucinated
  field survives.
- **Regression gate:** Phases 1–3 + the convergence/backfill/grounding suite.

## Phase 5 — Object store + entity resolution + drill-down elicitation
- **Goal:** the anchor→confirmation loop and the ≤2-question drill.
- **Build:** self-serve object-store ingest (arbitrary schema → profiling → hashed exact-key + pgvector
  fuzzy); entity resolution (silent match only when unique → ≥99%); confirmation lookup; contradiction
  detection (surface 100%, never argue); **no-object fallback**; elicitation policy with the **anchor+2
  budget enforced in code**, desired-outcome always asked, questions-per-case metric.
- **Subagents:** **Two sample object stores only — bakery orders + home-maintenance jobs** (order-shaped
  vs visit-shaped is enough to prove the object model generalises; that is the only reason to have two).
  The other four §4a verticals are addressable market, added when a *real* customer needs one — not
  synthetic breadth that makes the moat look more proven than it is. Entity-resolution + elicitation core:
  single-context.
- **Exit gate:** the four-word "delivery was bad" case resolves the object by phone, confirms the delay
  rather than asking, captures desired outcome, and closes in ≤2 questions; a walk-in with no object
  degrades to open questions without failing; a complaint-vs-record contradiction surfaces to the agent.
- **Regression gate:** Phases 1–4 + the anchor-budget + silent-match-accuracy tests.

## Phase 6 — Confidence/abstention + deterministic rules engine
- **Goal:** "refuse to guess," and reproducible priority/SLA/routing.
- **Build:** self-consistency (capped-N on gray-band fields only) + calibrated logprobs (scikit-learn
  Platt/temperature) + selective-prediction routing (τ for ≥98% auto-routed / ≥90% flagged); the
  deterministic YAML-driven rules engine (universal default policy + optional tenant override); clock
  starts at first contact.
- **Subagents:** *Optional research spike* on calibration method. Core: single-context (it's the trust metric).
- **Exit gate:** ambiguous fields route to review not a wrong value; same inputs+policy → identical
  SLA/priority, explainable in one sentence; the abstention threshold holds both SLAs on a dev slice.
- **Regression gate:** Phases 1–5 + confidence-routing + rules-determinism tests.

## Phase 7 — Review UI + commit gate + universal register report
- **Goal:** the <30s keyboard review screen, the human-approval gate, and the one report.
- **Build:** React/Vite SPA (source↔fields, low-confidence-first, **wavesurfer.js** audio provenance,
  bbox overlay, react-pdf, react-hotkeys-hook); the **commit gate** (nothing external fires pre-approval);
  the **universal manager register** + one report via **WeasyPrint** (RTL-safe), export PDF/CSV.
- **Subagents:** **Parallelise independent UI panels** (audio-provenance panel, image-bbox panel, report
  template) as separate subagents; integrate into the SPA yourself. **Then run `nabu-ui-test`** (render,
  screenshot desktop+mobile, inspect pixels) — re-run after every fix.
- **Exit gate:** a reviewer clears a case in <30s; clicking any value jumps to its source (audio segment /
  image region / sentence); no report/notification/external write occurs before approval; **`nabu-ui-test`
  passes on real pixels.**
- **Regression gate:** Phases 1–6 + the commit-gate + provenance-traceability tests.

## Phase 8 — Full threshold scoring (the scorer already exists from Phase 4)
- **Goal:** run the complete quantitative ship gate on the matured ground-truth set.
- **Build:** the scorer (built Phase 4) now runs over the **full T3 set as it has grown** — ≥100 cases,
  ≥30 Gulf-Arabic voice, ≥20 sparse, spanning the **two built verticals** (bakery + home maintenance);
  design-partner (DPA) + self-recorded real cases are the spine, synthetic fills the edge slices
  (injection/sparse) only. Every winning-condition §4 metric + risk-coverage/calibration plots.
- **Subagents:** **Parallelise scoring** per metric slice (Arabic / sparse / injection / object-match),
  then synthesise. A **completeness-critic subagent** checks which metrics are unmeasured.
- **Exit gate:** every §4 threshold measured and met on the **cloud path** (field-level Arabic parity,
  not WER — Δ1); convergence rows (duplicates <5%, declining new-field rate) hold **on real data**; the
  **per-case cost** is reported against the pricing model.
- **Regression gate:** the full Phases 1–7 suite runs as part of the eval build.

## Phase 9 — External gate + winning-condition scorecard
- **Goal:** the actual winning condition (winning-condition §8/§9).
- **Build:** run the setup-gate + seven-wow-moments checks end-to-end on the two demos (bakery +
  home maintenance); then **three strangers, no walkthrough, own messy inputs** (recruited via track T1
  from Phase 0 — lined up in advance, not scrambled at the end). Fill the scorecard honestly.
- **Subagents:** **None** — this is real humans and owner judgement; a subagent can only pre-flight the
  seven wow moments as a dry run beforehand.
- **Exit gate (SHIP):** all six scorecard rows clean; the win is **a stranger asking the price before
  asking for a feature.**
- **Regression gate:** the entire suite green; no red flag (winning-condition §7) present.

---

## Deferred milestone (post-PoC, trigger = clinic customer #1)
Build the four `local` backend impls (Qwen3-14B/Ollama, self-hosted Cohere + word-level forced-align,
MinIO object-lock); the **strict PHI-at-promotion gate**; a **separate local-stack eval run + lower bar
(Δ4)**; the **on-prem test-matrix target**. Not the PoC.
