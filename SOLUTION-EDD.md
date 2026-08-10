# Solution Engineering Design Document — Adaptive Intake

*Engineering design for the domain-agnostic complaint-structuring engine. Grounds every technical
choice in verified 2026 research (URLs inline). Governed by `CLAUDE.md`; context in
`longterm_context.md`; contract in `concept-adaptive-intake.md` + `winning-condition.md`.*

*Version 1.1 — 2026-08-09. Status: design locked pending the open items in §14. v1.1 adds §16
(review-pass addenda closing gaps G1–G11 found comparing v1.0 against the concept + winning condition).*

> **⚠ OWNER OVERRIDE — 2026-08-10 (authoritative: `longterm_context.md` §0).** The PoC's LLM path is now
> **LOCAL, on the owner's RTX 4070 — not cloud.** Wherever this document says *cloud-first PoC*, *Claude
> Haiku* (extraction), *Cohere Transcribe* (ASR — incl. the forced-alignment provenance design in §4/§16.9),
> or *Anthropic/Cohere API keys*, read instead: **faster-whisper** (ASR; word-level provenance via its own
> timestamps + optional WhisperX alignment) · **a quantized instruct model via Ollama** (extraction) ·
> **BGE-M3** (embeddings) — all local, no external call, no API keys, $0. The four-interface architecture
> is unchanged; only which backend the PoC builds first flips to local. Logged consequence (§0): local
> extraction quality < Haiku on the hard Gulf/code-switched slice, so the ≥95%/≥98% thresholds get harder
> — measured at the Phase-0.5 spike. Substantive section rewrites below are deferred to the phase that
> builds each component; **until then this banner overrides any cloud-first text that follows.**

---

## 0. Reading order & what this document is

This is the **HOW**. The PRD (`PRD.md`) is the WHAT and WHY. This EDD is written so an engineer can
build without re-researching: it names exact models, quantizations, VRAM footprints, thresholds,
table schemas, and libraries, each with a verified source. Everything obeys the two prime directives:
**1.5M AED, failure not an option; every gap closed at $0.**

**Two hard truths surfaced by the research that revise the source docs — read §13 first.**

---

## 1. System context

Domain-agnostic engine that turns unstructured, multilingual (English + Gulf Arabic), multimodal
(text, voice notes, images, PDFs) complaint input into a complete, prioritised, fully-traceable
structured case — with no form, no category picker — and drills anchor + ≤2 questions only when the
input is below the actionable floor. One universal engine (a cake store and a ministry run the same
code on the same empty starting schema). Two deployment modes selected by config: **fully local /
in-region** (RTX 4070-class, zero external calls, for UAE residency) and **cloud** (metered API).

```
                         ┌─────────────────────────────────────────────────────────┐
   WhatsApp ─┐           │                  HEADLESS ENGINE (Python)                 │
   Email     ├─ ingest ─▶│ normalise → transcribe/OCR → extract → elicit(if sparse) │
   File drop ─┘  adapters │   → deduplicate → promote → structured case → provenance │
                         └──────────────┬──────────────────────────┬─────────────────┘
                                        │ REST/JSON                 │
                              ┌─────────▼─────────┐        ┌────────▼─────────┐
                              │ React/Vite review │        │ Postgres+pgvector│
                              │ screen (client A) │        │  RLS multi-tenant│
                              └───────────────────┘        │  + object store  │
                                                           └──────────────────┘
```

The engine is an **API**, the review UI is its *first client, not its container* (concept §10). Every
inference component (ASR, LLM, embeddings, OCR) sits behind an interface with a `local` and a `cloud`
backend, chosen by config — never by a code change.

---

## 2. Pipeline (each stage independently testable, idempotent, retryable)

```
ingest → normalise → transcribe/OCR → extract → elicit (only below the actionable floor)
       → deduplicate → promote → structured case → human review → commit → report
```

Original input is immutable and retained permanently; extractions reference it and never replace it.
Stage idempotency is enforced by a version-hashed key (§7.3).

---

## 3. Inference stack — the $0 / dual-mode component matrix

| Component | LOCAL backend (in-region, $0, RTX 4070 12 GB) | CLOUD backend (metered, eval only) | Notes |
|---|---|---|---|
| **ASR** (voice notes) | **START: Cohere Transcribe Arabic (Apache-2.0, 2B)** for the transcript + **mandatory forced-alignment (wav2vec2 Arabic / faster-whisper large-v3 int8 ~2.9 GB)** for word timestamps (Cohere has **no native timestamps/diarization** — see §4); **silero-vad** front-end. Audar-ASR-V1-Turbo is more accurate but **weights are under a non-Apache AudarAI licence** — read before load-bearing | Groq Whisper-large-v3 (free tier) / Deepgram $200 credit for eval baseline | See §4 |
| **Extraction / classification / semantic discovery** | **Qwen3-14B Q4_K_M GGUF (~8–8.5 GB)** via **Ollama**, JSON-schema-constrained; **ALLaM-7B** / **Falcon-Arabic-7B** as config-switchable Gulf-dialect specialists | **Claude Haiku 4.5** (`claude-haiku-4-5`) — $1/$5 per MTok, ~$1.30 for 200 cases | See §5. Grammar-constrained decoding is **mandatory** |
| **Embeddings** (schema dedup/convergence) | **BGE-M3** (1024-d, 8192 tok, ~1.1 GB fp16, dense+sparse hybrid) | same model, run anywhere | See §6 |
| **Vector store** | **pgvector + HNSW** (`m=16, ef_construction=200`) | same | One source of truth with the relational rows |
| **OCR** (images/PDF) | Tesseract + a local vision model / pdf.js text layer for bbox provenance | — | Region bbox = provenance anchor |

**VRAM budget check (local, worst case):** Qwen3-14B Q4 (~8 GB) + BGE-M3 (~1.1 GB) + faster-whisper
int8 (~2.9 GB) = ~12 GB. ASR and extraction don't run in the same instant per case; sequence them, or
run ASR then release before extraction. Cap LLM context (KV cache grows with the thread) — chunk long
WhatsApp threads, never truncate silently (the resolution is often the last message).

---

## 4. ASR design (the voice-first moat) — and its honest ceiling

**Decision — start on Cohere Transcribe Arabic (Apache-2.0, 2B, dialect + Arabic-English
code-switching).** On the Open Universal Arabic ASR Leaderboard it is best-in-class among clean-license
options: **Cohere 25.87 avg WER** vs OmniASR-LLM-7B 28.32 vs Whisper Large V3 36.86. Audar-ASR-V1-Turbo
posts the lowest WER of any evaluated system (#1 of 36) but **only its repo code is Apache-2.0 — the
weights ship under AudarAI model licences**; read that licence before it is load-bearing for a
commercial product. Best-in-class still means **~1 word in 4 wrong** on hard conversational
multi-dialect sets — which is fine, because the metric that matters is field-level extraction, not WER
(see §13.1).

**The timestamp problem is now a hard dependency, not a footnote.** **Cohere emits no word timestamps
and no diarization**, but provenance requires "click a field → hear the exact moment in the audio."
Resolution: **mandatory forced-alignment** — Cohere produces the transcript, then a **wav2vec2 Arabic
aligner (or faster-whisper large-v3 int8)** force-aligns transcript-to-audio for word-level timings
(the WhisperX pattern, transcript-source-swapped). Both fit in 12 GB together (~5.5 GB). **Degraded
fallback if alignment underperforms on Gulf audio: segment-level provenance** (jump to the utterance,
not the word) — acceptable, but word-level is the target. Single-model alternative: Qwen3-ASR base
(native timestamps, weaker accuracy). **silero-vad** front-end is a cheap, large quality win.
**Scope note:** this whole word-level forced-alignment path is part of the **local stack, deferred to
clinic #1 (§16.9)**. The **PoC (cloud path) ships segment-level provenance** from silero-vad utterance
boundaries — word-level is not built now.

**Free accuracy levers (in impact order):** right base model (~10–11 WER pts over Whisper) → silero-vad
→ **LoRA fine-tune on the 4070** (Whisper-large LoRA peaks at 8.5 GB VRAM — fits; rank 32/alpha 64) →
tight `initial_prompt` biasing (last 224 tokens; put rare domain terms at the end) → small hotword list.

**Honest ceiling (see §13.1):** out-of-the-box Gulf code-switched voice notes land ~20–35% WER; with
domain LoRA + VAD + biasing, plausibly ~12–18% on Gulf-dominant audio, but pure Arabic↔English
code-switched segments stay materially worse. **"Within 5 points of English" is not defensible at any
budget today.** The product survives this because it is *complaint intake, not verbatim transcription*:
field-level extraction tolerates transcript noise, and word-timestamp provenance lets a human verify
any extracted value against the audio in the review screen.

Sources: Audar https://huggingface.co/audarai/Audar-ASR-V1-Turbo · Cohere https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026 · Qwen3-ASR https://github.com/QwenLM/Qwen3-ASR · Leaderboard https://huggingface.co/spaces/elmresearchcenter/open_universal_arabic_asr_leaderboard · WhisperX https://github.com/m-bain/whisperX · faster-whisper https://github.com/SYSTRAN/faster-whisper · LoRA-on-4070 https://www.mdpi.com/2076-3417/15/24/13090 · Groq free tier https://console.groq.com

---

## 5. Extraction / classification / semantic discovery

**Local model:** **Qwen3-14B** (Q4_K_M GGUF ~8 GB; 32K native / 128K YaRN) — the largest dense model
that fits comfortably and the strongest small model at structured/JSON + instruction-following. Arabic
is "good, not best," which is acceptable because structural decisions are deterministic (§7) and JSON
is grammar-enforced. Config-switchable Gulf-dialect specialists: **ALLaM-7B-Instruct** (SDAIA,
Apache-2.0 — best native dialect, but **only ~4K context**, a trap for long threads) and
**Falcon-Arabic-7B / Falcon-H1-7B** (TII Abu Dhabi, 32K/256K context).

**Constrained decoding is mandatory** (guarantees valid JSON for the machine-readable verdict and
underpins "refuse to guess"): **Ollama** `format=<json_schema>` (compiles to llama.cpp **GBNF**) is
the local default; drop to raw llama.cpp GBNF for one-of-N category-label grammars; **vLLM +
xgrammar** if throughput demands it (heavier on 12 GB). The key architectural point: **grammar
constraint decouples "pick the model for Arabic" from "guarantee valid JSON"** — choose the model on
dialect quality, let the grammar enforce structure. Never trust prose-instructed JSON from a 7–14B model.

**Cloud counterpart:** **Claude Haiku 4.5** — `claude-haiku-4-5`, **$1.00/MTok in, $5.00/MTok out**,
200K context, native JSON-schema structured outputs + strict tool use. The **~$1.30/200-cases figure is
a text-only FLOOR** — it excludes vision extraction, Phase-6 self-consistency sampling, and backfill
re-extraction (which replays the pipeline over history on every promotion). **Measure the real
cost-per-case from Phase 2 (BUILD-PLAN)**, don't quote the floor. Must be firewalled to CLOUD mode only
— an external call, never used for UAE-resident data.

Sources: Qwen3-14B GGUF https://huggingface.co/Qwen/Qwen3-14B-GGUF · ALLaM https://huggingface.co/ALLaM-AI/ALLaM-7B-Instruct-preview · Falcon-Arabic https://huggingface.co/blog/tiiuae/falcon-arabic · Ollama structured outputs https://docs.ollama.com/capabilities/structured-outputs · vLLM/xgrammar https://blog.vllm.ai/2025/01/14/struct-decode-intro.html · Claude models https://platform.claude.com/docs/en/about-claude/models/overview.md

---

## 6. The self-converging schema — the crown-jewel moat (buildable spec)

The concept doc paraphrases one specific paper almost line-for-line: **"Executable Schema Contracts"**
(Jonnalagedda et al., arXiv:2606.05415, Jun 2026, https://arxiv.org/abs/2606.05415) — read it first;
it is the reference implementation. Architectural ancestors: **EDC** (Extract-Define-Canonicalize,
EMNLP 2024, https://arxiv.org/abs/2404.03868), **AutoSchemaKG** (92% schema-human alignment,
https://arxiv.org/abs/2505.23628), **ZOES** (open-schema attribute discovery + value-anchored
re-extraction = a backfill primitive, https://arxiv.org/abs/2506.04458), **CESI** (embedding +
complete-linkage HAC canonicalization, https://arxiv.org/abs/1902.00172), **PG-HIVE** (incremental
provisional→confirmed promotion, convergence via declining new-type rate, https://arxiv.org/abs/2512.01092).

> **Citation integrity (verified 2026-08 against the arXiv API — all six IDs are real, incl. the
> future-dated 2606.05415).** Two honesty caveats: **(1) τ=0.85/0.70 are one lab's chosen defaults with
> no published sensitivity sweep** — in the source, 0.85 is a fallback clustering threshold for types
> lacking keys and 0.70 gates schema *extension*; our "merge/admit-new" framing is a reasonable
> restatement, not an established constant. **Treat both as tunable defaults and calibrate them on our
> scored set.** **(2) "closed-world grounding" and "statistics before semantics" are OUR paraphrases** —
> the paper says "closed-world constrained discovery / field catalog" and "statistical-before-semantic
> ordering." Don't present the paraphrases as verbatim quotes in buyer/technical material.

### 6.1 Two-layer schema
- **Governed core** — small, stable, human-controlled per category. Drives SLA/routing/reports. The
  AI never creates a field here.
- **Emergent layer** — unbounded attribute store; anything the model *attests* lands here immediately,
  no migration.

### 6.2 The algorithm (defaults are the papers' actual numbers — hardcode them)

```
STAGE 1 — PROFILE (deterministic, NO LLM)
  Enumerate every observed field → stable hash ID, data type, null rate, example values.
  This attested set ℱ is the ONLY vocabulary the LLM may reference (closed-world grounding).

STAGE 2 — EXTRACT into emergent layer (LLM, semantics only; two-pass; +10–15% long-tail recall)
  Prompt constrained to ℱ. FieldValidity = |referenced ∩ ℱ| / |referenced|.
  ANY schema with FieldValidity < 1.0 is REJECTED and flagged for repair.  ← anti-hallucination gate
  Embed each emergent field_name with BGE-M3 → pgvector.

STAGE 3 — DEDUP / CANONICALIZE (embeddings; statistics first, LLM only in the gray band)
  nn_sim = 1 - cosine(f.emb, nearest governed_core.emb)
  sim ≥ 0.85  → MERGE (link to governed field, add alias, support_count++)
  sim < 0.70  → keep as candidate-new
  0.70–0.85   → ONE LLM adjudication call ("same field? y/n")
  Nightly BATCH re-cluster of emergent layer: HAC, cosine, COMPLETE linkage, cut ~0.80–0.85
     (complete linkage + high cut avoids over-merge/chaining)

STAGE 4 — PROMOTE (recurrence, deterministic)
  Promote candidate → governed_core when support_count ≥ N (default N=4, tune)
     AND non-null rate across supporting cases ≥ 0.50.

STAGE 5 — STRUCTURAL INFERENCE (deterministic, NO LLM)
  identity_key : uniqueness_ratio > 0.98 AND id-naming pattern
  foreign_keys : confidence = min(0.95, 0.5 + 0.3*overlap + 0.15*[exact_name_match])
  cardinality  : value-distribution asymmetry + row-count ratios

STAGE 6 — BACKFILL (idempotent, bounded)
  On promotion of field g: ALTER add nullable column g (prospective, immediate);
  enqueue re-extraction ONLY for historical cases whose emergent layer maps to g;
  key writes on case.id → idempotent overwrite, no dupes (ZOES value-anchored enrichment).

CONVERGENCE MONITOR
  new_fields_per_100_cases → must decline & flatten (PG-HIVE convergence signal)
  duplicate_ratio < 5% (internal SLO)
  new-field-rate RE-SPIKE = concept drift → trigger re-convergence sweep (not a bug)
```

**Hardcoded constants:** merge τ=**0.85**, admit-new τ=**0.70**, batch-HAC cut≈**0.80–0.85** complete
linkage, promotion N=**4**, FK formula above, embeddings **BGE-M3 1024-d**, two-pass extraction. All
tuned on a held-out validation set, never guessed in prod.

**Over-merge (lossy collapse) is treated as more expensive than a duplicate** — hence the asymmetric
two-threshold gap and complete-linkage. See §13.2 on why the "200 attrs @ 0.95" claim is replaced.

---

## 7. Data & trust layer (Postgres + pgvector, RLS, provenance, immutability)

### 7.1 Multi-tenancy — session-GUC RLS, fail-closed
Shared schema; `tenant_id uuid NOT NULL` on every tenant table; app connects as a **non-owner,
non-superuser, non-BYPASSRLS** role; `ENABLE` + **`FORCE ROW LEVEL SECURITY`**; policy keyed to a
session GUC with a fail-closed `NULLIF` guard so an unset context reads **zero** rows:

```sql
CREATE POLICY tenant_isolation ON complaints TO app_rw
  USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE INDEX ON complaints (tenant_id);   -- RLS predicate MUST be indexed
```
Per request: `SET LOCAL app.tenant_id = %s` **inside the transaction** (never plain `SET` — under
PgBouncer transaction pooling it leaks context to the next tenant). Separate `USING` (read) from
`WITH CHECK` (write) so a tenant can't write into another it can't read.

**Acceptance gate — automated cross-tenant test (runs as the app role, asserts `rolbypassrls=false`):**
seed a row for tenant A; assert B reads 0; assert A reads 1 (positive control); assert B's INSERT into
A's tenant raises (WITH CHECK); assert unset context reads 0 (fail-closed). Adopt **pgrls** (pytest
plugin + 67 RLS lint rules + CI policy-diff gate): https://github.com/pgrls/pgrls

### 7.2 Provenance / immutability / correction log (three append-only logs → a projection)
- `source_document` — write-once (UPDATE/DELETE blocked by RULE); bytes in object storage
  (MinIO on-prem / S3 cloud) with **object-lock/WORM**, content-addressed by `sha256`.
- `field_extraction` — **append-only**, one row per extracted value with the full provenance chain:
  `model, model_version, prompt_version, confidence, run_id, source_span (audio {t_start,t_end} /
  image {page,bbox}), extracted_at`; `UNIQUE(run_id, field_path)`.
- `field_correction` — **append-only** (UPDATE/DELETE blocked): `prev_value, new_value,
  based_on_extraction_id, reviewer_id, note, corrected_at`. **Never overwritten — this is the moat asset
  and the eval/training set.**
- `field_current` — a rebuildable **projection** (latest correction else latest extraction). Disposable.

### 7.3 Idempotency
`idempotency_key = hash(source.sha256 + stage + model_ver + prompt_ver + code_ver)` with a UNIQUE
constraint per `(tenant, key)`. Replay collides → skipped. Bump any version → new key → new run, old
provenance retained (never silently overwritten).

Sources: Crunchy RLS https://www.crunchydata.com/blog/row-level-security-for-tenants-in-postgres · RLS footguns https://www.bytebase.com/blog/postgres-row-level-security-footguns/ · pgvector https://github.com/pgvector/pgvector · event-store-in-PG https://github.com/eugene-khyst/postgresql-event-sourcing

---

## 8. Determinism where it matters (concept §4.6)
The model supplies inputs (category, severity signals, entities); a **deterministic rules engine**
assigns priority, SLA and routing from the tenant's written policy text. Same inputs + same policy →
same result, explainable in one sentence, defensible in an audit. Never model output. **The `commit` stage is a human-approval gate — nothing
external fires on model output alone (§16.4). Zero-config tenants run on a universal default policy;
written policy is optional refinement, not a setup gate (§16.2).**

---

## 9. Elicitation engine (drill, not form) — budget enforced in code
Unknowns are only three (concept §4.3): which object, what was wrong, desired outcome — that IS the
budget. Anchor (order # / phone = a **key**, not a field) resolves identity; everything downstream is
looked up and turned into a **confirmation** ("delivered 6:42pm against a 5:00pm slot — was it the
delay?"). Rules: extract-before-ask; infer-from-anchor-before-ask; order by information gain; tappable
options after narrowing; always ask desired outcome; **hard budget = anchor + 2, enforced in code**,
then hand off. Case created immediately (never block on completeness); angry + incomplete → route to
human. Questions-per-case tracked as a first-class metric; any rising trend is a regression. **The
anchor resolves against the tenant's object store — silent match, confirmation lookup, contradiction
detection, and the no-object fallback are designed in §16.1; the emergent category and derived
actionable floor in §16.2.**

## 10. Confidence & "refuse to guess" (the trust metric)
**Do not gate on verbalized confidence** — 2026 research shows it tracks *commitment, not correctness*
(66.7% of errors at >80% stated confidence). Build the field-level trust signal on, best→worst:
**self-consistency / sampling agreement** (N=5–10, highest correlation with correctness) → **calibrated
token log-probs** → P(True) → verbalized (weak tiebreaker only). Calibrate raw scores → P(correct) with
**temperature scaling / Platt / isotonic** on a labeled dev set. Route by **selective prediction**:
pick the **lowest threshold τ whose accepted-set accuracy still ≥ 98%** (satisfies "≥98% on auto-routed"),
then verify **≥90% of ambiguous cases fall below τ** ("≥90% flagged"). If both can't hold at any τ, the
*signal* is too weak — raise N / add features, don't force the knob. Reserve high-N sampling for
near-threshold fields to control cost **(the latency budget this must fit on the local 4070 is worked
out in §16.3 — naive N=5–10 breaks the ≤60s trust gate).** Sources: commitment-not-correctness https://arxiv.org/pdf/2606.29490 ·
self-consistency https://arxiv.org/pdf/2607.08065 · calibration https://arxiv.org/pdf/2409.19817

## 11. Intake channels (both, self-serve) — verified $0 design
Channel-agnostic ingest: an adapter normalises each channel to the same input object, then a **shared
local normalisation pipeline** (faster-whisper large-v3 + PaddleOCR + pdfplumber, all on the 4070) runs
100% on-prem — so a deployment that never touches Meta's cloud still ingests everything from the
file/email drop with zero foreign data flow (the residency-degraded mode).

**WhatsApp (Cloud API):** pricing is now **per-message (since 1 Jul 2025), not per-conversation**.
The $0 lever is the **free, unlimited service window**, not a monthly quota: an inbound message opens a
**24-hour window** (any inbound resets it) during which free-form + utility messages are free. Outside
it, only **approved templates** can re-engage → so the PoC is designed **inbound-first** to never depend
on template approval. **Media retrieval is two-step**: webhook delivers a media *ID* → `GET /{media-id}`
returns a temporary URL → `GET` that URL **with the Bearer auth header** returns bytes; **the URL
expires in 5 minutes** — download on receipt, never queue past it. Prototype on **Meta's free test
number** (raw Cloud API, real media flow, ≤5 verified recipients) — https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/ ;
Twilio sandbox is a faster webhook shortcut for a demo only. **Residency crux:** Meta Cloud API has
**no UAE region** — WhatsApp content transits Meta's global cloud, a cross-border transfer under PDPL;
mitigation is the file/email channel + local pipeline.

**File / email drop (residency-safe, ~2-min self-serve, no credentials):** upload a WhatsApp chat
export `.zip`/`.txt` (parse with **whatstk**, MIT-adjacent — https://github.com/lucasrodes/whatstk;
handle iOS vs Android grammars, and voice notes as `.opus` *or* `.m4a` — don't hardcode); forwarded
email via **self-hosted Postfix/aiosmtpd on a UAE VPS** or IMAP-poll a UAE mailbox with `imap_tools`
(Cloudflare Email Workers is a demo-only shortcut — it transits foreign edge). **Avoid PyMuPDF (AGPL);**
use pdfplumber/pypdf/PaddleOCR (permissive). Size limits to design for: WhatsApp inline 16 MB /
document 2 GB; email 10–25 MB; base64 inflates ~1.35×.

**Conversation windowing / new-case-vs-update** (budget more effort here than extraction — concept §13):
hybrid of **24h idle-gap** + explicit **resolve/close state** + an **embedding/LLM new-issue-vs-follow-up
classifier** for the ambiguous middle (customer messages 3h after "solved"). Prior art: Freshdesk
threading interval (24h, →48h), Zendesk reopen-vs-follow-up on Solved→Closed (default 4d, cap 28d),
Chatwoot's `lock_to_single_conversation` boolean (self-hostable $0 path, but **no native TTL** — build
it). Disentanglement research: Kummerfeld et al. ACL 2019 https://aclanthology.org/P19-1374/

**Self-serve 10-min setup:** Path 1 (WhatsApp, ~7 min) — create Meta app → test number → add ≤5 test
recipients → paste Phone Number ID + System-User token → auto-register webhook → test message (no
template approval needed for inbound-first). Path 2 (file/email, ~2 min) — drag-drop the `.zip` or
forward an email; zero API, zero Meta account; also the pure-local residency fallback.

## 12. Review screen (React/Vite, most important interface) — all free, bundled, no CDN
Source on one side / fields on the other; low-confidence flagged and focused first; keyboard-driven;
< 30s/case. Libraries (self-contained, on-prem-friendly, no network calls): **wavesurfer.js v7** +
Regions plugin (waveform, click-to-seek, draw the audio `{t_start,t_end}` provenance span) · div-overlay
from `bbox` over the rendered image for OCR-region highlight (prefer over heavy annotation libs) ·
**react-pdf** (pdf.js) for PDF originals · **react-hotkeys-hook** for the keyboard flow (Enter=approve,
Tab/j·k=next field, Space=play source span). Compute overlay coords from *rendered* dimensions (not
source pixels) so boxes track zoom/scale. Bundle everything into the Vite build — a CDN asset breaks
both offline and residency.
- **PoC provenance granularity (resolves the trust-gate reading):** sentence and image-region are
  exact; **audio `{t_start,t_end}` is the VAD utterance the value came from** (segment-level — cloud
  ASR has no word timestamps). Clicking a value plays that utterance — this is the PoC reading of "the
  moment in the audio." Word-level highlighting arrives with the local stack's forced-alignment (§16.9).

---

## 13. Spec deltas / hard truths (must be reconciled with the winning condition)

**13.1 — RESOLVED (owner, v1.1): the Arabic metric is re-anchored to field-level extraction accuracy,
not transcript WER.** WER parity "within 5 points" is unachievable and irrelevant: best-in-class open
ASR posts ~26% WER on hard conversational Arabic (Cohere 25.87, OmniASR-LLM-7B 28.32, Whisper Large V3
36.86) — ~1 word in 4 wrong — yet a 26% WER transcript can still yield ~95% correct *fields*, because
the anchor already supplied most of them. **Winning-condition §4 row updated** to *Arabic field-
extraction accuracy vs English, within 5 points (field-level, not transcript WER)*, backed by mandatory
audio provenance (word-level via forced alignment; segment-level fallback). **Hard rule:** the WER
numbers above and any ASR benchmark are *feasibility evidence only* — they must **never** appear in
buyer material or as a target/threshold in the winning condition. Measure field-level parity on the
≥30 Arabic cases before claiming readiness.

**13.2 — "~200 attributes @ 0.95 precision" is not a citable result.** No paper reports that tuple; it
comes from published KG schema-induction research and is **feasibility evidence, never a promise**.
**Hard rule (owner, v1.1):** it must **not** appear in buyer material or as a target in the winning
condition — same rule as the ASR numbers (§13.1). Internally, cite **AutoSchemaKG 92%** / **AutoPKG
WKE 0.953**; keep "0.90–0.95 field precision" and "<5% duplicates after 200 cases" as **internal
SLOs**, achieved via the two-threshold + complete-linkage + nightly re-cluster design.

**13.3 — Cloud LLM/ASR = a cross-border transfer.** Any hosted API call (Haiku, Cohere, Groq) is an
outbound transfer and a logging surface. For health-/finance-adjacent tenants this is *categorically*
prohibited (§14) — those tenants must run the LOCAL backend end-to-end. The dual-mode design exists
precisely for this.

**13.4 — Accuracy thresholds are PER-DEPLOYMENT (owner, v1.1; also PRD Δ4).** A local 14B is not
Claude; the local stack extracts materially worse than the cloud path. There cannot be one threshold
table across both deployments — the winning-condition numbers are validated on the **cloud path** for
the PoC, and the **local deployment needs its own eval run and its own (lower) bar** (built at clinic
#1, §16.9). Shipping one set of numbers across both is a promise met on only one deployment.

## 14. Deployment, residency & open items

**Residency (verified):** UAE federal PDPL (Decree-Law 45/2021) does not itself mandate local storage
— it restricts cross-border transfer (adequate jurisdiction / safeguards / consent). What *forces*
fully-local: **health data — Federal Law 2/2019 Art. 13** (health data may not be stored/processed/
transferred outside the UAE; Cabinet Decision 32/2020) and **payment/stored-value data** (must stay in
UAE). **DIFC (DP Law 5/2020) and ADGM (DPR 2021) are separate regimes** — mainland↔free-zone movement
is a cross-border transfer. Executive-Regulation enforcement dates are contradictory across sources —
**design for the strict reading, don't couple rollout to a date.** Default posture: single codebase
that deploys **fully local/on-prem** (Postgres + MinIO object-lock + local Whisper/OCR/LLM, no outbound
calls); cloud-outside-UAE is opt-in, gated on a documented lawful basis. **No customer data in logs**
(log by `source_id`/`run_id`; scrub filter + a test asserting known PII never appears; disable
`log_statement=all` in prod). Sources: DLA Piper https://www.dlapiperdataprotection.com/countries/uae-general/law.html ·
health-data ban https://www.dataprotectionreport.com/2019/04/uae-bans-exporting-health-data-and-restricts-domestic-use/

**Open engineering items (resolve before build — see PRD §Open decisions):** Audar vs Cohere ASR
license call (accuracy vs Apache-2.0 cleanliness for a commercial product); N and τ initial values
confirmed against the first labeled eval slice; object-store choice per deployment (MinIO local /
S3 cloud); production WhatsApp path (BSP vs Meta-direct) post-PoC — the PoC uses the free test number.

---

## 15. Test & evaluation strategy
Ground-truth set: **≥100** real/realistically-messy cases, **≥30** Arabic/code-switched, **≥20**
too-sparse-to-act, spanning the **six §4a verticals across four object archetypes** — order (bakery,
e-commerce), job-visit (home maintenance, automotive), booking/stay (hospitality), appointment
(salon/spa/fitness). Headline built demos = bakery + home maintenance (maximal contrast); the other
four broaden coverage to stress convergence and the phone-anchor across every archetype. (PRD §4a.) Every field labelled correct/incorrect; an ambiguity-tagged subset for the
abstention SLA. Automated: the cross-tenant isolation test (blocking), idempotent-replay test
(no dupes), projection-rebuild test (`field_current` recomputes from logs), PII-not-in-logs test,
convergence monitor (new-field-rate curve + duplicate ratio). Nothing is "done" until scored on this
set — building the set is part of the job.

---

## 16. Review-pass addenda (v1.1) — gaps closed after comparing v1.0 to the contract

*These sections close G1–G11 from the review of v1.0 against `concept-adaptive-intake.md` and
`winning-condition.md`. They are design, not open questions, except where flagged for confirmation.*

### 16.1 Object store, entity resolution & the confirmation lookup (G3, G4)
*Closes: silent object match ≥60%, match accuracy when silent ≥99%, discrepancies surfaced 100%,
Wow Moment 3. The whole anchor→confirmation loop depends on this component.*
- **Self-serve connect (inside the 10-min window):** CSV/JSON/XLSX upload or a read-only API key.
  Schema is **unknown and arbitrary** (a cake store's orders ≠ a ministry's service requests).
- **Schema inference reuses §6 Stage-1 profiling (deterministic, no config):** detect identifier
  columns (phone, order #, email, booking ref) by uniqueness + format pattern, plus types/cardinality.
- **Index:** identifier columns hashed for O(1) exact lookup; descriptive text columns embedded
  (BGE-M3) into pgvector for a fuzzy fallback.
- **Matching / anchor resolution:** (1) exact key match on sender phone or a quoted order # →
  **if exactly one candidate, MATCH SILENTLY**; (2) zero or >1 candidates → ask the anchor (2–3
  tappable options when few). **Silent match only when unique** — this is what protects the ≥99%
  metric (acting on the wrong object is worse than asking).
- **Confirmation lookup:** once matched, pull the object's fields and convert questions to
  confirmations ("delivered 6:42pm against a 5:00pm slot"). This is the mechanism behind ≤2 questions.
- **Contradiction detection:** deterministic compare of extracted claim fields vs the matched record
  (claimed-late vs recorded-on-time) → surface to the agent **100%**, never argue with the customer;
  log as a fraud/pattern signal.
- **No-object fallback (concept: "must not fail"):** if no object store is connected, or a walk-in/
  prospect with no record, degrade gracefully to open questions **within the same anchor+2 budget**;
  the case is still created.
- **Dependency note for the demo:** silent match + confirmations require the object store connected.
  Extraction works without it, but elicitation will not stay short — Moment 3 needs it wired in setup.

### 16.2 Category & actionable-floor bootstrap (G1, G2, G11)
*Closes the tension between "zero config / no category list built" (WC §2) and the concept's
"per case category" governed core, actionable floor, and drill tree.*
- **CONFIRMED (owner, v1.1) with a gate: discovery is automatic, activation is NOT.** A wrong field is
  cheap; a wrong category is a wrong deadline (it drives the SLA clock, routing and the report), so
  categories do **not** auto-activate. Day one, a case is zero-shot classified into a **minimal
  universal starter taxonomy** (~6–8 archetypes: product-fault, service-fault, delivery/fulfilment,
  billing/charge, access/availability, staff-conduct, safety/health, other) plus an **`UNCLEAR`**
  class. The taxonomy is **hierarchical** so every candidate has a nearest parent.
- **Category promotion is human-gated and stricter than fields:** candidate categories surface exactly
  like candidate fields, but going live requires **(1) a human click, (2) recurrence across ≥ 15
  distinct cases (not the field threshold of ~4), and (3) a mandatory mapping to an existing SLA
  policy** before activation. **Until activated, the case sits in its nearest parent category with the
  candidate recorded** — so value is delivered with zero config while no unvetted category can ever set
  a deadline. This keeps "no category list built" literally true (the tenant builds nothing; it only
  approves) and still gates the deadline-bearing decision behind a human.
- **The actionable floor is DERIVED, not hand-authored.** Universal floor = the three unknowns (which
  object, what was wrong, desired outcome). Per emergent category, the floor grows to the governed
  fields that have promoted for that category. It bootstraps: minimal on day one, converges per tenant.
- **Rules-engine defaults reconcile "zero config" with "written policy."** A **universal default
  priority/SLA/routing policy ships**, so a tenant gets value with zero input; the tenant's written
  policy text (optional) *overrides* it. Policy is refinement, never a setup gate. This is why the
  setup gate can be honoured while §8's determinism still holds.
- **PII/PHI governance at promotion (new — a self-creating schema can invent a field holding sensitive
  data).** Every candidate field passes a **sensitivity classifier + redaction gate before promotion**:
  deterministic patterns (phone/ID/address) + an LLM check for free-text health content → tag, and
  block/redact per tenant sensitivity, recording the classification in provenance. **Light PII tier
  ships in the PoC** (a phone in a bakery complaint is PDPL-relevant); the **strict PHI tier is a hard
  prerequisite for a health/clinic tenant** — what a health-sector audit looks for — and is built with
  the local stack (§16.9), not the PoC.

### 16.3 Performance & latency budget on the local 4070 (G5)
*Closes the ≤60s "time from message to case ready" trust gate against real local compute.*
- **Reality:** Qwen3-14B Q4 on a 4070 ≈ 25–35 tok/s → a ~700-token structured extraction ≈ 20–30s;
  ASR of a 30s voice note ≈ 3–5s (≈12× real-time, faster-whisper int8); embeddings sub-second.
  Single-pass fits ~60s; **naive self-consistency N=5–10 does NOT.**
- **Budget design:** (a) the case is created immediately on ingest — "message→ready ≤60s" targets the
  *structured output*, not a blocking synchronous round-trip; (b) default **single-pass extraction +
  calibrated logprobs**; escalate to sampling **only for gray-band fields, cap N=3**, and only within
  the remaining budget, else route straight to review; (c) if 14B can't hold ≤60s on the target box,
  drop to **Qwen3-8B** (faster) or enable **speculative decoding** — validate on the actual 4070, don't
  assume; (d) batch the confirmation lookups.
- **VRAM / model lifecycle (explicit runtime requirement):** you cannot hold 14B (~8 GB) +
  faster-whisper (~2.9 GB) + BGE-M3 (~1.1 GB) + KV cache with headroom on 12 GB. Orchestrate:
  run ASR → release → load the extraction LLM; keep the small BGE-M3 resident; sequence per case.
  *(All of the above is the local stack — deferred per §16.9; the PoC cloud path has no 4070 budget.)*
- **Backfill isolation (new):** promoting a field re-extracts history — potentially thousands of model
  calls in a burst. Run backfill on a **dedicated low-priority queue + separate worker pool**
  (Procrastinate) so a promotion event can never starve live intake. True in both cloud and local modes.

### 16.4 Human-approval commit gate (G6)
*Closes the trust gate "nothing external happens without approval."*
- The `commit` pipeline stage is a **hard gate**: no report generated, no external record written, no
  notification/WhatsApp template sent on model output alone. Reviewer approval in the review screen
  transitions the case to `committed`; only then can outbound actions fire, and approval is itself
  provenance (`reviewer_id`, timestamp). **Auto-routed (high-confidence) cases still pass the approval
  gate for any EXTERNAL action**, even when not field-by-field reviewed — auto-route governs internal
  routing, not external side effects.

### 16.5 Field-registry external mappings (G7 — concept §10)
- `governed_core` carries an optional **`external_mappings jsonb`** column **from day one** (canonical
  field → external system field IDs). An emergent schema is useless at Phase-2 integration time if it
  can't translate into someone else's fixed one; deferring the column is a rewrite risk, so it exists now.

### 16.6 Threat model — adversarial / injection complaint content (G8)
- Complaint text is **untrusted input fed to an LLM** → prompt-injection risk (a complaint crafted to
  manipulate extraction or the customer-facing confirmation text). Mitigations, layered:
  closed-world grounding + grammar-constrained decoding bound outputs to attested fields (injected
  "instructions" can't invent fields or actions); **customer-facing elicitation text is templated, not
  free-LLM-generated**, so it can't be hijacked into arbitrary output; the engine never executes or
  routes on instructions found inside complaint content; no-customer-data-in-logs limits exfiltration.
  Add an **injection-attempt slice to the eval set** (§16.7).

### 16.7 Evaluation data sourcing (G9)
*Closes "where do ≥100 real messy + ≥30 Gulf-Arabic voice cases come from at $0?" — RESOLVED (owner,
v1.1): the owner supplies it and owns it in writing.*
- **(a) Design-partner real complaints, ~10–15**, under a **written data-processing agreement**,
  anonymised. This is the legal spine — no eval data without the DPA.
- **(b) Self-recorded, ~15–20:** brief **8–10 Gulf-Arabic speakers**, hand them **scenario cards, not
  scripts**, capture on their phones **through WhatsApp** (real channel, real codec, real code-switch).
  Cheap, legal, realistic.
- **(c) Synthetic** messy/code-switched + sparse + injection cases to reach the ≥100 total and exercise
  edge slices, each validated by a native Gulf-Arabic speaker.
- **Public corpora (SADA/MASC/Emirati) are for CALIBRATION ONLY** — they are speech, not complaints,
  so they never count toward the case set. ≥30 must be genuine Gulf-Arabic/code-switched voice (b+a
  supply most). Label field-by-field; tag the ambiguous subset for the abstention SLA. **Building this
  set is part of the job**, and the same corpus later fine-tunes the ASR LoRA.

### 16.8 Report artefact (G10 — universal manager register)
- PoC ships a **register view + one universal manager report**: every field provenanced, produced
  **only post-approval**, exportable (PDF/CSV). Fields are the universal governed core + whatever has
  promoted for the tenant — so the *same* register serves all six §4a verticals (order, shipment,
  job-visit, vehicle, booking, appointment). This is the "100% completion, zero mandatory fields" artefact.
- **Tooling:** our layout carrying the tenant's data → **WeasyPrint** (HTML→PDF; Pango/HarfBuzz handle
  Arabic RTL). CSV via stdlib.
- **Regulator-shaped / regulated-artefact reporting is PARKED by owner — out of scope, not to be
  discussed until the owner re-raises it.** Archived: `_parked/regulator-shaped-output.md`. *(The
  local-deployment / health-tenant / PHI machinery in §16.9 stands separately on data-residency grounds.)*

### 16.9 PoC scope — cloud-first, local deferred (owner, v1.1)
*The first market is any service/delivery business down to a cake shop — the opposite end of the market
from a health tenant. Building four local backends on the 4070 is a large architecture tax for a
segment not yet chosen. So the dual-deployment decision is refined, not reversed:*
- **The four backend interfaces (TECH-SPEC §3) stay from day one** — cheap, and the module hedge.
- **The PoC builds only the cloud implementation of each; local impls ship as stubs.** Cloud path:
  Cohere Transcribe Arabic **API**, Claude Haiku 4.5, BGE-M3 self-hosted, Postgres, S3/MinIO — cents at
  PoC scale. **PoC provenance is segment-level** (VAD boundaries; cloud ASR has no word timestamps);
  word-level forced-alignment is deferred with the local stack.
- **The local build is triggered when a clinic is customer #1** — and only then do these costs land:
  the four local impls (Qwen3-14B/Ollama, self-hosted Cohere + forced-alignment, MinIO), the strict
  PHI-at-promotion gate (§16.2), and — critically — a **separate eval bar + run for the local stack**.
- **Accuracy thresholds are per-deployment, not one number (new — see §13.4/PRD Δ4).** A local 14B is
  not Claude; the local stack will extract materially worse. The winning-condition thresholds are
  validated on the **cloud path for the PoC**; the local deployment needs its **own eval run and its own
  (lower) bar**, or we ship a promise we only meet on one deployment.
- **Two deployment targets ≈ double the test matrix** — a real cost, and another reason to defer the
  local target until a clinic justifies it. Until then the matrix is single (cloud).
