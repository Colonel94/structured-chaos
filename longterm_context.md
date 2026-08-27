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

*Last updated: 2026-08-26 (session: **MARKET-READINESS ADVERSARIAL PASS**. Supersedes the historical
batch/inline-intake notes below: reviewer intake now returns 202 onto the single durable worker path and
the UI polls persisted readiness; approval and review timing are locked until the deterministic decision
exists; confidence-band batch approval was removed because 28% zero-edit cannot justify rubber-stamping
unseen cases. Auth tables are behind exact-key SECURITY DEFINER RPCs (migration 0027), portal status/answer
CORS is tenant-enforced, CSV formula injection is neutralised, tenant erasure removes orphaned identities,
and the real upload+elicitation path now wires guarded fuzzy object matching. Independent labels, timed
reviewers, convergence evidence, legal/ops sign-off and three strangers remain external gates.) Prior arc:
2026-08-23b (session: **REVIEW-UI USABILITY — the ≤30s-gate surface**. Built the backend +
frontend that make the review UI fast AND measure time-to-approve: review_event instrumentation + HUD,
one-key correction picks, triage + batch approve, single-key commit + an undo window (superseding the
c-arms/Enter gate), diff-on-return. 256 tests +1 skip, nabu-ui-tested live incl. an end-to-end commit→undo.
Committed `6a5e331`, push pending. See §0 START-HERE. Prior arc:* **market-ready hardening (R1–R8) + W1 harness + W2/W3 eval + SENTIMENT
TRAJECTORY**. Sentiment now routes on the conversation's PEAK emotion + an escalation trend (best practice:
track sentiment over the interaction), with a 72h recency-decay window + a logged escalate-only asymmetry
(owner-flagged design review); additive → eval unchanged. Plus: single-worker advisory lock (zombie footgun
fixed in code), worker-liveness `/health` + honest dead-worker portal copy, fail-closed prod secrets, Ollama
Linux-bind preflight + `docs/DEPLOY.md`, Caddy TLS, backups, engine auto-restart; W1 four-number holdout
scorer (owner-blocked on the labeller); demo tenant reset+reseed. HEAD @ 973d61e, 249 tests +1 skip, all
pushed. See §0 START-HERE. Prior arc below:* **the case-must-not-lie + durable-portal + chat-mode arc**. (1) Portal
moved OFF fragile BackgroundTask onto the DURABLE Procrastinate chain ingest already enqueues — stages now
RETRY + on exhausted retries stamp `processing_failed`; (2) honest failure surfaced end-to-end — migration
0019, `fail_case_processing`, portal stalled/handoff copy, review-UI error state (red banner + "needs a
human" register row + blocked approval, nabu-ui-tested); (3) PORTAL CHAT MODE — the widget is now a
conversational thread that INVESTIGATES vague/emotional openers instead of logging a dead case, with a
server-side reprocessing gate (`processed_at`) so replies don't freeze on a stale question; grounding gate
now rejects customer-state-narration faults (no fabricated category on pure emotion, elicit-v4) + warm
angry-handoff copy. Diagnostic: the 216 eval set has ZERO silent failures (owner's hypothesis falsified);
score.py now flags timeout/empty rows loudly. Two owner-caught tuning fixes landed from live testing —
customer-state-narration grounding (v4) and the contentless-opener instant-handoff (v5, "something hurt
me" was closing a case with no conversation). 225 tests +1 skip, ruff/black/mypy(app)+UI tsc clean. **The
portal now REQUIRES a running worker.** HEAD @ 40328a5, all pushed. Verified the container→Ollama path
works on Docker Desktop but BREAKS on a Linux server (bind trap, logged+deferred). **Next: owner is
live-testing (voice/image/text) → turn each failing case into a prompt/policy fix (the tuning loop).**)*

---

## 0. Current state & next actions  ← read this first every session; keep it current

> ## ✅ 2026-08-27 OWNER-APPROVED TIE-BREAKS → extract-v22, propagated + re-scored (DIRECTIONAL)
> - All six tie-breaks Osman surfaced are IMPLEMENTED and propagated to the three places together:
>   prompt (**extract-v22**), `holdout_labels_INSTRUCTIONS.md` (Tie-break rules section), and the workbook
>   **Option Sets** (23 manager-rule cells; blank regenerated). Rules: product_fault<->safety_health
>   (hazard wins), record_accuracy<->fraud_security (unauthorised vs merely-wrong), billing_charge<->
>   misleading_practice (wrong-amount vs deception), desired_outcome = only a remedy requested IN THIS
>   message (not one recounted as previously asked), financial_harm has NO minimum (kills the small-fee
>   ambiguity), sharpened emotion adjacent-boundaries. **5-point emotion scale KEPT** (collapsing would
>   discard the owner+Osman emotion gold; owner can still request a hard 5->3 as a separate re-label).
> - **Re-score model-v22 vs the EXISTING (old-guideline) labels — DIRECTIONAL ONLY, not the tie-break
>   lift** (owner+Osman labelled BEFORE the tie-breaks, so this is not the clean measure). vs Osman:
>   category 74->76, desired_outcome 78->76, severity 72->72, **emotion 62->71**, all-fields 29->32.
>   vs owner: category 72, outcome 76, severity 61, **emotion 48->53**. Mixed + modest exactly as
>   predicted; emotion moved most (the boundary rules). Human ceiling (osman-vs-owner) UNCHANGED
>   (86/90/86/64) because the humans did not re-label.
> - **The CLEAN measure = a FRESH human round under v22.** Owner is recruiting a new independent labeller;
>   the updated `holdout_labels_blank.xlsx` + INSTRUCTIONS (both carry the tie-breaks) were sent. The
>   financial_harm floor + emotion boundaries + category tie-breaks are aimed at raising the HUMAN
>   inter-annotator ceiling (esp. severity's 22 financial_harm/none splits and emotion's adjacency) —
>   only visible once a fresh human labels under the new guidelines. Then: three-way agreement
>   (new-vs-owner, new-vs-osman) + model-vs-new = the real lift.
> - `holdout_extractions.jsonl` regenerated at v22 (200 rows). Full suite 283 pass. All committed.
>
> ## ✅ 2026-08-27 FIRST INDEPENDENT LABELS (Osman, CR Director, 20y) — the human ceiling
> - **The binding lever landed.** Osman — independent (neither owner nor me), domain expert — labelled all
>   200 cases blind. `holdout_labels_osman.csv`. Gives the two numbers that were always missing:
>   **model vs independent** (real accuracy) and **owner vs independent** (the human ceiling).
> - **Scores (n=200; agreement, still directional):**
>   | field | model-vs-osman | model-vs-owner | **osman-vs-owner (HUMAN CEILING)** | model as % of ceiling |
>   |---|---|---|---|---|
>   | category | 74% | 72% | **86%** | 86% |
>   | desired_outcome | 78% | 78% | **90%** | 87% |
>   | severity | 72% | 62% | **86%** | 84% |
>   | emotion | 62% | 48% | **64%** | **97%** |
>   | all-fields | 29% | 16% | **44%** | — |
> - **The reframe (do NOT read the raw % as model weakness):** two 20-year experts agree only 86/90/86/**64**%.
>   The model sits at 84-97% OF THAT CEILING. **Emotion 62% is not a model failure — humans agree only 64% on
>   the 5-point scale; the model is AT the ceiling.** The bottleneck is TAXONOMY UNDER-SPECIFICATION, not the
>   extractor (the §10 "is the ENUM wrong, not the model?" test — answered on independent data).
> - **Osman's gaps are DATA-CONFIRMED as the exact ceiling-limiters** (owner-vs-osman confusion): category
>   28 disagreements led by **product_fault/safety_health ×12**, billing/record ×5, billing/misleading ×2
>   (his named tie-break gaps); severity 29 disagreements are **financial_harm/none ×22** (his "is a small
>   fee *material*?" gap); emotion 71 disagreements are ALL adjacent-scale (concerned/distressed, angry/
>   frustrated…) → the 5-point scale is too fine to label reliably. repair_redo is NOT overloaded (only 4
>   human disagreements touch it — the `correction` split worked).
> - **NEXT (owner decisions, logged — do NOT self-resolve/re-label to inflate agreement, §10):** owner rules
>   on the tie-breaks Osman named (product-vs-safety, record-vs-fraud, billing-vs-misleading, "material"
>   financial-harm threshold, whether a previously-stated request counts as a desired_outcome), and whether
>   the 5-point emotion scale collapses to 3. Once decided, propagate to Option Sets + INSTRUCTIONS + the
>   extraction prompt TOGETHER, then a FRESH labelling round measures the lift. This is the real path to a
>   higher ceiling — a better-defined task, not a cleverer model.
>
> ## ✅ 2026-08-27 TAXONOMY v0.2 EXPANDED + FULL 200-CASE SCORE (extract-v21)
> - **Owner widened the governed taxonomy** (workbook `holdout_labels.xlsx` Option Sets): category 10→14
>   (+transaction_processing, fraud_security, privacy_data, misleading_practice), desired_outcome 7→13
>   (+correction, cancellation, restore_access, stop_contact, compensation, investigation), severity 4→5
>   (+privacy_security), emotion 3→5 (+concerned, distressed). Propagated across the WHOLE system:
>   `schema.py` enums, `prompt.py` (**extract-v21**, with the owner's definitions + boundary rules),
>   `starter_taxonomy.yaml` (also was missing record_accuracy), `synthesis.py`, portal wording, and
>   `policy_default.yaml` (new categories + privacy_security route **deterministically**, verified —
>   catch-all still last). Calibration NOT re-fit: tau_auto=1.01 = auto-route gate OFF (all→review), so
>   stale confidence is non-safety (ordering only); a proper re-fit needs its own model run + independent
>   labels, deferred.
> - **Full 200-case score (model extract-v21 vs OWNER gold, agreement — NOT independent correctness).**
>   Coverage 200/200 (scorer now HARD-FAILS partial coverage — exit 3 unless ALLOW_PARTIAL=1). Numbers
>   with majority-class baseline + lift:
>   - category 72% (base 12% product_fault, **+59**) — strong
>   - desired_outcome 78% (base 18% null, **+60**) — strong
>   - severity 62% (base 54% financial_harm, **+8**) — WEAK, barely above baseline
>   - emotion 48% (base 37% frustrated, **+12**) — WEAK (5-point scale; concerned/distressed subtle)
>   - all-fields 16%.  n=200 but still DIRECTIONAL (rule of three) and owner-agreement, not correctness.
> - **Gold is OWNER gold, not independent (owner review):** 66 real + 134 owner-authored SYNTHETIC =
>   development evidence, independent of the extractor/me but NOT the third-party representative set the
>   GA gate needs. The independent number (column 2) is still outstanding — hand the workbook to a
>   non-builder. Do not present these as independent accuracy or market-readiness.
> - **Runner/scorer now robust:** `extract_holdout.py` reads `holdout_labels_owner.csv`, incremental +
>   resumable + observable (writes/flushes per case; ~15-25 s/case on the 4070, ~60-80 min for 200).
>   `export_holdout_workbook.py --qa` = integrity report (dupes/OOV/missing/distributions; QA PASS).
>   Rule saved: the extractor enum and its GRADER's label space must move together, and a widened gold
>   caps measured accuracy until the extractor + calibration catch up (do not collapse gold — §10).
> - **GIT:** all of the above uncommitted on branch `fix/elicit-qualifier-gate-b-readiness` at time of
>   writing (owner review flagged the taxonomy files were uncommitted → not covered by remote checks).
>   Committing now. `holdout_extractions.jsonl` regenerated (200 v21 rows).
>
> ## ✅ 2026-08-26 GATE-B VERIFICATION + REAL ELICIT BUG FIXED (aim-for-6/6 session)
> - **The "3/6 CLEAN" claim was not actually true — Gate 1 (complete workflow) was silently broken.**
>   `app/store/api.py::get_emergent_values_by_head` selected/ordered a non-existent
>   `emergent_field.qualifier` column → the **elicit** path (anchor+2 drill) crashed with
>   `psycopg UndefinedColumn`. Hidden because the seed path never calls elicit. **Fixed:** derive the
>   qualifier from `field_name`/`head` in SQL (mirrors the Python `field_path[:-(len(head)+1)]`), bare
>   head sorts last. Also fixed a stale test: `_seed_case` in `test_review_usability.py` skipped
>   `decide_case`, so its case had no decision → the commit gate (correctly) refused it → the backdate
>   tripped `case_commit_pair`. Added `decide_case` to the seed. **22 previously-failing tests now pass.**
> - **Foundation now genuinely verified live:** full backend suite **283 passed / 2 skipped**; trust-spine
>   21 green (`test_rls_isolation`, `test_provenance`, `test_idempotency`, `test_pii`,
>   `test_pii_redaction`, `test_trust_coverage`); mypy clean (93 files); ruff clean on app+tests; **black
>   reformatted 11 pre-existing-drift files** on the release surface (behaviour-preserving, suite still
>   283 green); UI test + production build green.
> - **Gate B-5 operational evidence — real drills run:** backup→restore→verify drill **PASSED** (stamp
>   `20260826T121459Z`, restored counts 88/106/572/41 matched live, 0 errors); secret fail-closed tested
>   (`test_config_secrets.py` 5 pass); CI security scan exists (`security.yml`: CodeQL + Trivy). Captured
>   in new doc **`docs/GATE-B-PILOT-READINESS.md`** with the fallback runbook + Gate-4 governance template
>   + Gate-6 operator-acceptance script.
> - **HONEST CEILING on "6/6":** a true 6/6 on Gate B is NOT achievable by building alone. Gates 4
>   (named pilot org + signed policy), 5 (named incident responder + accepted CI scan verdict) and 6
>   (one **non-builder** operator run) each need a real external human and must not be fabricated
>   (§10 no-self-grading). Buildable outcome reached: **gates 1/2/3 CLEAN (verified) + gate 5 technical
>   evidence done**; 4 and 6 packaged ready in the doc. Owner actions to close 6/6 are the ⬜ slots there.
> - **Also this session:** dev deps got pruned mid-session by an accidental `uv sync` (default group) and
>   `.venv/pyvenv.cfg` was deleted; both restored (`uv sync --group dev --group embed --group asr`; note
>   `FlagEmbedding`/BGE-M3 was never synced before, so the worker's schema-maintenance scans had been
>   erroring — now installed). Seeded a synthetic **non-US-English** diverse demo tenant
>   `11aa0e52-6d53-48d1-8383-f25884c903b0` (14 verticals; dev/demo only, NOT a gate) after the owner
>   flagged the holdout is 55% US-finance/CFPB and English-only. Surfaced one extraction bug on it:
>   an EU261 flight-delay case mis-categorised as `delivery_fulfilment`/`repair_redo`.
> - **CSV-vs-instrumentation correction (owner, 2026-08-26):** the pilot review-time gap was NEVER "a
>   CSV with rows in it" — the product self-instruments (`review_event` → `/api/review-stats`
>   count/median/p90; `field_correction` → `/api/review-breakdown`; the eval scorer). `review_event`
>   count=0/median=null = **nobody has cleared cases**, not an unfilled form; the moment one reviewer
>   uses it for 20 min the number appears. Deleted **all three** session-capture templates
>   (`reviewer-session-`, `voice-pair-`, `stranger-session-template.csv`) and the now-empty `evidence/`
>   dir: a person using the self-instrumenting product never needs a capture form — a **stranger runs the
>   same product a reviewer does**, so the session instruments itself; the few external observations
>   (reaction, price question, help, abandonment) are a free-text note. Voice parity is scored by the eval
>   harness against gold, not hand-counted. Rewrote `docs/EVIDENCE-RUNBOOK.md` accordingly. Rule saved:
>   [[dont-recapture-instrumented-data]]. **The real Gate-6 blocker is the absence of a reviewer, not a
>   spreadsheet.** (Independent GOLD labels in `holdout_labels.csv` are separate and still valid.)
> - **RUN IT:** DB+MinIO via `docker compose -f deploy/docker-compose.yml up -d db minio`; backend
>   `cd engine && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000` (use `-m uvicorn`, not
>   the console script, so `uv sync` never locks it); worker from repo root
>   `./engine/.venv/Scripts/python.exe -m scripts.run_worker default --schedule`; UI `cd ui && pnpm dev`
>   (:5173). Full suite: `cd engine && REQUIRE_DB=1 ./.venv/Scripts/python.exe -m pytest -q`.
> - **GIT:** uncommitted changes: `engine/app/store/api.py` (elicit fix), `engine/tests/test_review_usability.py`
>   (seed fix), 11 black-reformatted files (app+tests), new `docs/GATE-B-PILOT-READINESS.md`. NOT yet committed.
>
> ## ✅ 2026-08-26 WINNING-CONDITION v0.2 — OWNER-AUTHORISED PRODUCT CORRECTION
> - The owner explicitly reconsidered the old 1/6 all-or-nothing contract. It mixed engineering safety,
>   controlled-pilot entry, GA evidence and market reactions, making safe learning with one design partner
>   impossible. `winning-condition.md` v0.2 now separates Gate A engineering readiness, Gate B controlled
>   pilot entry, Gate C paid continuation and Gate D general availability.
> - **Current truth:** engineering readiness **PASS**; controlled-pilot entry **3/6 CLEAN** (workflow,
>   mandatory human control, trust/tenant boundary). Before real data: name/bound the pilot + approve
>   policy/data terms; run restore/security evidence and assign operating owners; complete one non-builder
>   operator acceptance case.
> - Independent labels, cold timing, sparse/voice sets and unassisted stranger studies remain important
>   pilot-learning/GA evidence. They no longer block the first bounded, human-approved pilot. Existing low
>   self-authored accuracy/convergence results are preserved and still block broad claims.
> - The commercial win is an explicit continue/pay/purchase decision against pre-agreed partner targets,
>   not the theatrical proxy of someone asking the price before requesting a feature.

> ## ✅ 2026-08-26 ADVERSARIAL MARKET-READINESS UPDATE
> - **Lifecycle fixed:** `/api/ingest` no longer runs a duplicate inline pipeline. It commits case +
>   originals + durable job and returns 202; the UI polls the selected case. A case with no decision is
>   visibly processing and cannot be approved by API, button or hotkey. Human review timing starts only
>   after processing, so the ≤30s metric is no longer polluted by GPU time.
> - **Human gate restored:** removed `/api/cases/commit-batch` and the "approve all clean" UI. The 0.5
>   class-confidence band plus 28% zero-edit rate never justified approval of unseen cases.
> - **Security/privacy fixed:** migration 0027 revokes bulk app-role access to passwords/sessions and
>   exposes exact-key auth RPCs; portal token reads/answers now enforce the tenant origin allowlist; CSV
>   exports neutralise spreadsheet formulas; full tenant erasure removes identity rows only when their
>   last membership is gone.
> - **Object-resolution path completed:** self-serve uploads now embed records and elicitation passes a
>   narrowly typed customer/complainant name plus the configured embedder into the guarded fuzzy fallback.
> - **Verification so far:** migrations applied to the live DB; backend 147 passed / 138 skipped locally
>   (DB/container cases run in CI); mypy clean; UI typecheck clean, 2/2 tests and production build green.
> - **Still binding, unchanged:** the scorer finds no completed, independently named holdout label file;
>   accuracy/convergence gates fail or are unproven; human review timing, legal/operational evidence and
>   the three-stranger gate remain.

> ## ✅ CURRENT STATE + NEXT STEPS (2026-08-25 — clean top-of-mind summary; the dated FOLLOW-UP + SESSION HANDOFF blocks below are detail + audit trail)
>
> **GIT:** code `HEAD @ d66d89a`, **all pushed, tree clean**. **22 migrations, 270 tests +1 skip**, ruff/black/mypy(app) + UI tsc + vitest + production build clean.
>
> ### ⇢ THIS SESSION (2026-08-25) — also CLOSED THE TUNING-GATE TRAIN/TEST LEAK (owner-flagged). Committed `dfcc570`, pushed.
> - **The bug (owner):** `tuning_eval.py` scored the full 216 (`cfpb|multidomain`) — the SAME cases the digest mines for signal — so any prompt-delta drafted to fix errors on that set scored better on it **by construction**. The merge gate was decorative; the PR-template caveats are a warning, and warnings lose to a green number.
> - **The fix:** a deterministic **held-out / tune split** — `eval/_dataset.py::split_of()` (stable id-hash, ~30% held-out / ~70% tune, no data file, reproducible in CI). `score.py` honours `EVAL_SPLIT` (all|tune|heldout) + prints the split & within-split n; `tuning_eval.py` **defaults to `--split heldout`** and the PR comment flags any non-held-out score as an invalid gate. The **full-set `all` number is UNCHANGED** and stays the §8 scorecard (verified: cfpb all=120/120 category 82%, identical; heldout=38 disjoint, category 68%). The independent holdout labels (`holdout_labels.csv`, owner-blocked) remain the STRONGER gate when they land — this split is the usable-now break.
> - **CLAUDE.md §10** gained the durable rule: *"No tuning PR merges while the scoring set and the signal set are the same data."* +2 guard tests. Full suite **272 passed, 1 skip**, ruff/black clean.
> - **STILL the three levers that move the score (unchanged, from six reviews ago): (1) an independent labeller, (2) a reviewer with a timer on the pristine tenant [~20 min, fully unblocked, produces the load-bearing §4 number], (3) three strangers (§9).** Scorecard 5.6. The tuning loop is now honest but is NOT one of those three — don't mistake it for progress on the score.
>
> ### ⇢ THIS SESSION (2026-08-25) — REVIEW-UI REDESIGN to a LIGHT Fluent / Power Platform look (owner-directed). Committed `d66d89a`, pushed.
> - **Owner directive:** *"make the backend UI sexy + easy to use, follow best design standards; it looks complex when the job is simple; I like Dynamics 365 / Power Platform — take ideas."* This **overrides the earlier owner-blessed DARK "Instrument" contract** (which had rejected light). Logged as a visible decision in `ui/DESIGN.md` (new top block), NOT silent drift (§10). The dark contract is preserved below it as history + the token structure the light theme reuses.
> - **What changed (skin + info-architecture ONLY — zero API/engine/data change):** light Fluent palette (near-white canvas, white cards + soft elevation shadows, **communication-blue `#0f6cbd`** as the one interactive accent), **Segoe UI/system-sans** as the interface voice with **mono reserved for machine data only** (dropped IBM Plex Sans+Serif imports in `main.tsx`; kept Plex Mono; retired the serif source panel → clean sans quote card). The case is now a **stack of clean white cards** (D365 record layout): header · rules strip · human-readable summary (the analysis headline reads as the record title) · **Extracted details** (was "governed core") · **Other details found** (was "emergent attributes") · **What the customer sent** (was "source text") · right rail (field/provenance card + feedback card). Friendlier labels, rounded corners, pill badges, soft message bars (discrepancy=red, next-step=blue). Every colour is a `:root` token → dark = a token swap.
> - **Trust mechanics UNCHANGED + re-verified on pixels:** uncertainty is still the ONE loud amber signal (spine + `needs review` pill + %, verified on a flagged 25% field); every value click-to-traces to source; "not stated" first-class quiet state; commit gate + undo window explicit; full keyboard flow (`j/k n/p e 1-9 c u r ?`) untouched; priority stays a neutral ramp; confidence stays a per-class signal (register ordering copy unchanged).
> - **DARK MODE shipped (`fbe5cf1`):** a `:root[data-theme="dark"]` token-swap block + a top-bar toggle (`☾ dark`/`☀ light`), persisted to localStorage, defaulting to the OS `prefers-color-scheme`, applied before first paint (no flash). Paired helper tokens (`--brand-fg`, `--committed-btn`, `--pri1-bg/-ink`, `--code-bg/-ink`) keep contrast in dark without structural change. Both themes nabu-ui-tested (desktop + mobile, 0 console errors); amber uncertainty reads loud on dark too.
> - **Verified:** `App.test.tsx` passes unmodified; tsc + vitest + `pnpm build` green; nabu-ui-tested desktop 1440 + mobile 390 in BOTH themes, **0 console errors, no overflow**, incl. the flagged case, the one-key correction picker, provenance, and the tuning modal. Files: `ui/src/{App.tsx,main.tsx,styles.css}` + `ui/DESIGN.md`.
> - **DEMO TENANT is SEEDED FOR THE REVIEW-TIME MEASUREMENT (2026-08-25):** 6 varied review cases in the queue (2 clean-band ≥0.5, 4 flagged), **review-stats CLEAN (count 0, median null)** — a human reviewer session is set up and waiting at `http://localhost:5173/?tenant=a17456c2-6dbc-492a-9128-7747f8650196`. Claude deliberately did NOT approve any (machine-speed + case-authored = a fake number, and `review_event` survives undo so it would poison the median). **The ≤30s measurement is a HUMAN cold-read task (owner or someone who hasn't seen these).** RESET before the external gate: `reset_demo_tenant.py "Portal Demo Co"` → `seed_portal_orders.py "Portal Demo Co"`.
> - **Follow-ons if the owner wants (NOT started):** could further simplify by collapsing "Other details found"/JSON behind disclosures; the new-case modal is still ~17s inline.
>
> **PRIOR GIT (pre-redesign): `HEAD @ 7184d91`** (voice-first + reaper).
> **LIVE STACK (may or may not survive into next session — re-launch anything down, see RUN IT):** engine :8000, **ONE worker** (on the new reaper code), review UI :5173, DB+MinIO (docker) + Ollama up. The cloudflared **tunnel is EPHEMERAL** — was up for the voice test, almost certainly DOWN next session; restart it for any phone/portal-from-another-device testing.
> **DEMO TENANT `Portal Demo Co` (`a17456c2-6dbc-492a-9128-7747f8650196`, embed key `ek_ZDw3qSBD1pqXowBRoSQizyNE`) is PRISTINE + EXTERNAL-GATE-READY:** 0 cases (clean register), **6 bakery orders** indexed (Moment 3 can fire), review-time median / feedback / tuning-digest all cleared. Reseed anytime: `reset_demo_tenant.py` → `seed_portal_orders.py` (+ `seed_review_cases.py` for review-time fodder, NOT for the external gate).
> **Demo tuning PR OPEN: [#1](https://github.com/Colonel94/structured-chaos/pull/1)** (DRAFT/do-not-merge, self-authored signal — owner can close).
>
> ### THIS SESSION built the whole REVIEW-USABILITY + FEEDBACK-LOOP arc (the τ=1.01 reframe: nothing auto-routes → the review UI IS the product, ≤30s review time is the load-bearing gate). All $0, all human-gated, all live-verified (nabu-ui-test) + pushed:
> 1. **Review-time INSTRUMENTED** (migration 0021 `review_event`, `/api/review-stats`, live HUD `⏱ elapsed · median`) — the ≤30s gate (winning-condition §4) is now measurable.
> 2. **One-key correction** (number-key enum picks, `/api/field-options`), **triage + batch approve** ("nothing flagged" band at the 0.5 flag line, `/api/cases/commit-batch`), **single-key commit + UNDO WINDOW** (`/api/cases/{id}/uncommit`, 15s — SUPERSEDES the c-arms/Enter gate, owner-blessed, logged in DESIGN.md §10), **diff-on-return**.
> 3. **THE FEEDBACK LOOP, closed end-to-end:** reviewer feedback-to-model (migration 0022 `case_feedback`, `/api/cases/{id}/feedback`) → the **tuning digest** (`/api/tuning-digest` — recurring correction transitions + edit-pressure + feedback, the "what to fix next" view) → the **prompt-delta drafter** (local model, `/api/tuning-digest/draft`) → **open-as-PR** (`scripts/open_tuning_pr.py` applies it as a `tuning_addenda.json` addendum — `[]` on main, eval-neutral — + bumps PROMPT_VERSION, opens a `tuning/` PR) → **gated eval** (`scripts/tuning_eval.py` + `.github/workflows/tuning-eval.yml`, self-hosted; §10 no-merge-without-rescore) → human reviews + merges. Every automated step stops at a human gate ($0, Directive 2).
> 4. **VOICE-FIRST PROVEN on a real iPhone** (the wedge — zero real samples before), which caught + got the **orphaned-job reaper** fix (`run_worker.py`, HEAD 7184d91).
>
> ### ⇢ NEXT SESSION — START HERE (what's next; everything below is owner-action unless noted)
> - **THE EXTERNAL GATE (§8) — the actual win condition, and the tenant is now READY for it.** 3 strangers, their own mess, no walkthrough, you silent; win = someone asks the PRICE before a feature. Needs the portal reachable: **start the tunnel** (`scratchpad/tools/cloudflared.exe tunnel --url http://localhost:8000` → a `*.trycloudflare.com` URL → `/p/s/ek_ZDw3qSBD1pqXowBRoSQizyNE`). A stable named tunnel / real deploy is better than the ephemeral quick tunnel for a scheduled gate.
> - **The ≤30s review-time measurement — NOW UNBLOCKED (owner + me).** Put a real reviewer on the review UI with the HUD, clear cases they didn't author, read the median off `/api/review-stats`. This is THE load-bearing §4 gate under the τ=1.01 reframe, and it's finally instrumented. Decides whether "we fill your forms, you approve in 30s" IS the product at the current 77% category / 28% zero-edit.
> - **W1 independent labelling — STILL the binding accuracy constraint** ([[calibration-label-ceiling-per-class]]). Blind sheet `eval/fixtures/holdout_labels.csv` (66 cases) + `score_holdout.py` are BUILT; needs the owner to hire someone who is neither owner nor me. Turns "77% agreement-with-Claude" into a real number and unblocks the confidence gate + category score + the tuning drafter's honesty (self-authored corrections = self-grading).
> - **Accuracy gates still FAIL (unchanged this session — this session was usability, not accuracy):** category 77% (≥90), zero-edit 28% (≥70), desired_outcome 56% (≥90); auto-route vacuous (τ=1.01 → everything to review). Convergence (the moat) still unproven on real data. These are the honest open gaps; the lever is W1 labels + real recurring data, not more prompt-grinding.
> - **Optional code follow-ons (flagged, don't start unprompted):** close/merge PR #1; the review-UI "+ new case" modal is still ~17s inline (portal path is async — apply the same); elicit-handoff peak-awareness (sentiment); a stable tunnel/deploy for a scheduled external gate; if wanted later, the tuning drafter could pre-draft a full prompt-diff + a self-hosted eval runner registration.
>
> ## ⇢ FOLLOW-UP 6 (2026-08-24, live iPhone voice test → a real durability bug → fix) — done, pushed.
> - **VOICE-FIRST PROVEN ON A REAL iPhone** (over a cloudflared tunnel). Two submissions, both transcribed by local ASR + structured (a property-management gripe + a community/mice complaint → both `other`, which is honest — out-of-domain for the finance/retail taxonomy). The voice-first claim had ZERO real samples before this; gate cleared.
> - **BUG the test caught + FIXED (reaper):** a worker killed MID-JOB (one of the stopped "Restart worker" tasks) left its `pipeline.normalise` job stuck in Procrastinate's `doing` state — Procrastinate's own `worker_id`/stalled-worker pruning did NOT catch it — so the case hung at `created` forever while the live worker still reported healthy (portal would show "still processing" indefinitely). This is a DISTINCT vector from the zombie-worker footgun (orphaned JOB under a live worker, not a zombie worker). **Fix (`scripts/run_worker.py::reap_orphaned_jobs`, HEAD `7184d91`):** on startup, right after acquiring the queue-set's exclusive singleton advisory lock (→ no other worker on these queues + this one hasn't fetched → every `doing` job is provably orphaned), release them to `todo` (clear `worker_id`) so they re-run. Guarded to lock-held only (never under `WORKER_ALLOW_MULTIPLE`), fail-open (never blocks startup), loud WARNING on reap. +2 DB-backed guard tests (only own-queue `doing` released; other queue-set + finished jobs untouched). Verified live: restart logs `no_orphaned_jobs` on a clean queue; the stuck voice case recovered created→actionable when its job was released. **270 tests +1 skip.**
> - **NOT handled (scoped out, noted):** a genuine *poison* job that crashes the worker every run would reap-loop — but that class is caught by each stage's `RetryStrategy` → `processing_failed` on repeated *exceptions* (the reaper is for a healthy job whose worker was killed, not a job that kills workers).
> - **Live test state:** demo tenant now carries a few corrections/feedback + the 2 voice cases (digest is populated for testing — reseed before the external gate). Worker restarted on the new code. Tunnel was up for the test (ephemeral trycloudflare URL).
>
> ## ⇢ FOLLOW-UP 5 (2026-08-24, owner: "open a PR with this delta and a scheduled eval run") — done, pushed. LOOP FULLY CLOSED, EVERY STEP HUMAN-GATED.
> - **`scripts/open_tuning_pr.py`** — applies the drafted delta as a tuning ADDENDUM (`app/extract/tuning_addenda.json`, `[]` on main → eval-neutral, verified byte-identical prompt) + bumps `PROMPT_VERSION` (+tN, quoted string only), commits to a fresh `tuning/…` branch, pushes, opens a `gh` PR (provenance + caveats + a §10 DO-NOT-MERGE checklist). Refuses on a dirty tree; NEVER edits main; NEVER merges. Fetches the delta live from the engine (`--tenant`) or `--delta` inline. **Demonstrated live → real PR #1.**
> - **`scripts/tuning_eval.py`** — re-scores + posts to the PR. `--score-only` (fast, existing extractions, honestly flagged "does NOT reflect the delta") vs `--reextract` (~30 min, the real after-delta number). §10 merge rule in the comment. **Demonstrated live → posted the baseline (category 82%) to PR #1.**
> - **`.github/workflows/tuning-eval.yml`** — runs on `tuning/**` PRs (+ nightly + dispatch) on a **SELF-HOSTED gpu runner** (the eval needs the local model; GitHub-hosted has no GPU/Ollama at $0 — wired, not faked, same posture as the Linux preflight). Until a runner is registered, run `tuning_eval.py` locally.
> - **WHY a script, not a UI button (design decision):** opening a PR needs git-push + gh credentials; the headless engine must NOT hold those or shell out — so the review UI's draft card shows the **copyable command** + an honest "the engine doesn't push" note, and a human runs it. Every automated step still stops at a human gate.
> - **THE FEEDBACK LOOP IS COMPLETE, end to end, all $0, all human-gated:** reviewer signals (correct a field / feedback) → captured → clustered (digest) → drafted (local model) → **opened as a PR + eval-scored** → human reviews the score, merges. The ONLY remaining manual steps are the two that MUST stay human (writing/approving the merge, registering a self-hosted runner). +5 host-safe tests (eval-neutrality, addenda filtering, version-bump safety, comment self-flagging). Demo tenant untouched by the demo (used `--delta` inline).
>
> ## ⇢ FOLLOW-UP 4 (2026-08-24, owner: "have the digest pre-draft a prompt-delta for review") — done, pushed. THE LOOP'S LAST MILE.
> - **`POST /api/tuning-digest/draft` + a `draft from this signal` button in the tuning modal** = the local model ($0) proposes ONE targeted, additive clarification to the extraction prompt's definitions, grounded in the recurring transitions + feedback. `app/extract/prompt_tuning.py::draft_prompt_delta` (grammar-constrained DRAFT_SCHEMA title/delta/rationale). Renders as a green-edged proposal card: title · `target` (prompt+fields) · copyable **proposed addition** · rationale · `grounded in` chips · three fixed guardrail caveats.
> - **KEPT HUMAN-APPROVED (never auto-applied) — this is the point.** The draft is a STARTING POINT: shipping means a human edits `app/extract/prompt.py`, bumps `PROMPT_VERSION`, and RE-RUNS THE EVAL first (§10 — never ship a prompt change without re-scoring). The caveats also carry the self-grading warning ([[calibration-label-ceiling-per-class]]): drafted from reviewer corrections, so on self-authored gold it optimises toward the labels — earns trust only with an INDEPENDENT reviewer; for category the binding lever stays independent labels. `draft_prompt_delta` never raises (returns draft=None + reason on no-signal/bad-output) and never writes anything.
> - **Verified live against Ollama:** signal (delivery→service ×2 + a feedback note) → a genuinely sound delivery-vs-service disambiguation delta ("classify delivery_fulfilment for delays/failures in delivering; service_fault only for post-delivery handling"), grounded + caveated. nabu-ui-tested (0 console errors, em-dash/× render clean in-browser — the json.tool mojibake is display-only). Then the demo tenant was reset+reseeded pristine.
> - **THE FEEDBACK LOOP IS COMPLETE end-to-end:** reviewer signals (correct a field / give feedback) → captured (`field_correction` + `case_feedback`) → clustered (tuning digest) → **drafted into a concrete prompt-delta** → a human reviews, edits prompt.py, re-scores, ships. Every automated step stops at a human gate ($0, §3, Directive 2). Possible future (NOT built, don't start unprompted): a one-click "open a PR with this delta + a scheduled eval run" — but the apply+rescore stays human-approved.
>
> ## ⇢ FOLLOW-UP 3 (2026-08-24, owner: "build the tuning digest") — done, pushed. THE FEEDBACK LOOP IS NOW CLOSED END-TO-END.
> - **`GET /api/tuning-digest` + a `tuning` topbar modal** = the loop's ACTIONABLE end (owner/engineer view, not reviewer-facing): turns accumulated signal into "what to fix next" so the next prompt/policy change picks itself. Three clusters (per tenant, RLS): (1) **correction_transitions** — recurring `prev→new` flips on the closed-vocab governed fields (category/desired_outcome/emotion/severity), ranked; a repeated `delivery_fulfilment→service_fault` names the EXACT boundary to fix (THE signal, top of the backlog); (2) **field_edits** — per corrected field: corrections · distinct cases · median review time (LEFT JOIN review_event) = where the editing effort+time concentrates; (3) **feedback** tally + notes + the headline review median. `api.tuning_digest`.
> - **Honest by construction** ([[calibration-label-ceiling-per-class]]): the modal labels a transition a *reviewer correction* (what a person changed), NOT a proven model error — real signal with an INDEPENDENT reviewer, possibly a label-off on self-authored gold; nothing is auto-applied ($0, human-driven, Directive 2). Caveat stated inline in the UI.
> - **Verified live** (nabu-ui-test desktop+mobile, 0 console errors, 0px overflow after a mobile transition-wrap fix) on a POPULATED digest, then the demo tenant was reset+reseeded pristine.
> - **The loop, now complete:** reviewer gives signal two ways (correct a field → value; feedback → judgement) → captured (`field_correction` + `case_feedback`) → **clustered into the digest** → a human writes the prompt/policy fix. The one remaining manual step is intentional (writing the fix); auto-applying would violate §3/Directive 2. If ever wanted: the digest could pre-draft a prompt-delta for review, but that stays human-approved.
>
> ## ⇢ FOLLOW-UP 2 (2026-08-24, owner: "seed realistic cases + where is the feedback loop") — both done, pushed
> - **6 realistic cases seeded** through the real `/api/ingest` path as reviewer fodder for the ≤30s measurement: a spread of anchored (BK-1004 late→Moment 3 + a red DISCREPANCY; BK-1003 wrong-item) vs open, calm vs angry (staff_conduct→human_review), a too-sparse case (→elicitation), billing, and record_accuracy — real confidence spread (2 clear the 0.5 clean band). Script `scripts/seed_review_cases.py` (dev-only, reusable). Reseed anytime with reset→seed_portal_orders→seed_review_cases.
> - **THE FEEDBACK LOOP is now first-class + VISIBLE** (owner: "I don't see it"). It existed only as the invisible correction log (corrections→eval/tuning set). Added: **migration 0022 `case_feedback`** (RLS, append-only) + `POST /api/cases/{id}/feedback` (verdict accurate|inaccurate|partial + optional note; allowed even on committed cases — feedback ≠ re-opening the record) + `GET /api/feedback` (the loop OUTPUT: verdict tally + recent, per tenant) + feedback surfaced on `get_case_review`. **UI:** a "feedback to the model" panel in the review aside (verdict buttons + note + prior verdicts) that states honestly where it goes — *collected as the model's eval + tuning set → prompt/policy fixes; $0, human-driven, no data leaves; NEVER online fine-tuning (Directive 2)*. Two ways to give the model signal now: correct a field (fixes the value → correction log) OR give feedback (judges the extraction → feedback log). Both feed the human-driven tuning loop. Verified live end-to-end (submit → panel log + tally). `DESIGN.md` §6 logs it.
> - **`reset_demo_tenant.py` now covers `case_feedback` (18→19 tables)** — same class of fix as the review_event one; any new tenant table MUST be added there.
>
> ## ⇢ FOLLOW-UP (2026-08-23b, owner asks before the reviewer sits down — both done, pushed):
> - **Demo tenant reseeded** so the stray review_event from live testing can't skew a small-n median (`reset_demo_tenant.py` → `seed_portal_orders.py`; verified review-stats count=0, median=null). **NB:** `reset_demo_tenant.py` was MISSING `review_event` in its wipe list — added (17→18 tenant tables); without it a reseed would have orphaned review_event against the deleted case_record. Any future tenant table must be added there.
> - **"Which corrections cost the time" is now answerable.** `fields_edited` was already in the same `review_event` row (a count, + `avg_fields_edited` in review-stats). Added the per-FIELD view the owner actually wanted: `GET /api/review-breakdown` (`api.review_breakdown`) — per corrected field, how many approved cases corrected it + the median review time of those cases, slowest-first. Sourced by JOINING the append-only `field_correction` log (which field — the asset, §3) to `review_event` (how long); no state duplicated. **Correlational, labelled as such** (a slow case with several edits attributes its whole time to each field). When the headline median is high, this says where it's going.
>
> ## ⇢ NEXT SESSION — START HERE (2026-08-23b — REVIEW-UI USABILITY: the ≤30s-gate surface)
> **Owner directive: "we need a proper backend for this frontend — we need it usable."** Built the load-bearing surface the τ=1.01 reframe implies: nothing auto-routes → every case is human-cleared → **time-to-approve (≤30s, winning-condition §4) is THE gate, and the review UI IS the product.** All $0, full suite green (256+1), nabu-ui-tested on real pixels, **committed `6a5e331`, NOT yet pushed.**
> - **Review-time is now INSTRUMENTED (the prerequisite — you can't optimise an unmeasured gate).** migration 0021 `review_event` (RLS, one row/case, append-only), `api.record_review_event`/`review_stats`; commit logs client-measured `review_ms` + `fields_edited`; `GET /api/review-stats` (count/median/p90). A live HUD in the case header shows `⏱ elapsed · median (n)`, amber past 30s. **Verified live: commit→ median 2s(1).**
> - **One-key correction (biggest review-time lever):** closed-vocab governed fields render as number-key picks (`1`–`9`, current value excluded), sourced from `GET /api/field-options` (enum vocab from `extract.schema`, so picks can't drift). A misclassification is now one keystroke, not typing.
> - **Triage + batch approve:** register splits into a "nothing flagged for review" band (every governed field > the 0.5 flag line) + the needs-you remainder; `approve all N clean` = `POST /api/cases/commit-batch` (one human act, §3; time split evenly). **HONEST FLOOR DECISION (§10 capped-input trap):** the clean floor is 0.5 (the existing flag line), NOT 0.85 — case confidence is a MIN of per-class reliability×grounding and tops out <0.9 (calibration maxes ~0.87–0.92 per field), so a 0.85 floor would sit permanently empty. Labeled "nothing flagged" (class-level band), never a per-case safety claim.
> - **Single-key commit + UNDO WINDOW (the deferred engine work, now BUILT):** `c` commits immediately; a green undo toast (`u`, counts down) reverts within `UNDO_WINDOW_SECONDS`=15 via `POST /api/cases/{id}/uncommit` (`api.uncommit_case`, server-authoritative clock, 409 after). **This SUPERSEDES owner-call-2's c-arms/Enter two-step** — it's the successor the owner already blessed; logged in `ui/DESIGN.md` §6+§10 as a visible decision, not silent drift. Nothing external fires on commit alone (report is pull, §3) so an undone fresh approval leaves no trace. **Verified live end-to-end against the real DB: c→APPROVED seal + toast → u → back to in_review.**
> - **Diff-on-return:** fields changed since the reviewer last saw a case are highlighted (client-side localStorage snapshot) — a case reopened after new messages shows only what moved.
> - **DELIBERATELY DEFERRED (stated, not silent):** (a) **self-serve tenant signup** (plan backend #2, §2 setup gate) — a portal/onboarding concern, not review-UI usability; not built. (b) **SSE on case status** (plan backend #4) — the review UI doesn't poll (only the portal does), so it's not load-bearing here. Both are the honest next slices if the owner wants §2/portal work.
> - **WHAT'S NEXT:** (1) **push** `6a5e331` + this §0 commit (`git push`, then share the compare link — [[share-commit-links-after-push]]). (2) **The real test the whole surface exists for: put a human on the review UI with the HUD and measure median ≤30s on cases they didn't author** (owner action; this is the load-bearing §4 gate under the τ=1.01 reframe, and now it's measurable). (3) reseed the demo tenant (`scripts/reset_demo_tenant.py`) to clear the stray review_event before the external gate. (4) minor edge (logged): an undone-then-recommitted case keeps its FIRST review_ms (ON CONFLICT DO NOTHING) — undercounts that rare case; acceptable.
>
> ## ⇢ NEXT SESSION — START HERE (2026-08-22→23 session)
> **SESSION SCOPE (all built + verified + pushed):** (1) **Market-ready hardening R1–R8** — single-worker advisory lock (zombie footgun fixed in code), worker-liveness `/health` + honest dead-worker portal copy, fail-closed prod secrets, Ollama Linux-bind preflight + `docs/DEPLOY.md`, Caddy TLS, backups, engine auto-restart. (2) **W1 harness** — model-side holdout extraction + four-number scorer (`eval/score_holdout.py`) + blind labeller packet; owner-blocked on hiring the labeller. (3) **Demo tenant reset + clean reseed** (`scripts/reset_demo_tenant.py`; 0 cases, 6 orders). (4) **Sentiment trajectory** — peak-routing + escalation detection + decay/scope (below). Details in the dated blocks.
> **WHAT'S NEXT — everything left is owner-blocked, not code:** (a) **W1 labeller** — hand `eval/fixtures/holdout_labels.csv` + INSTRUCTIONS to someone who is neither owner nor me, pay them, save as `holdout_labels_<name>.csv`, run `eval/score_holdout.py`. THE binding constraint on the accuracy story. (b) **A Linux box** — the Ollama preflight is built but unverified until a real host exists. (c) **3-stranger external gate.** Code follow-ons (optional, flagged): elicit-handoff peak-awareness; tune `SENTIMENT_WINDOW_HOURS`; the W2/repair_redo enum split (only once W1 labels land — don't guess against my labels).
>
> ### Sentiment trajectory (this session's feature) — "enhance sentiment analysis" (CallMiner best practices + others). Built + tested + LIVE-verified, pushed.
> - **What changed:** the rules engine now routes on the conversation's **peak** emotion + a new **`emotion_trend`** input (single|steady|escalating|de_escalating), not just the latest snapshot — so a customer who vents angry then calmly answers isn't washed to "calm," and a **rising-frustration** customer is caught early (policy `default-v3`, new `escalating-sentiment` rule → human_review). `app/rules/sentiment.py` (pure, $0) + `api.get_emotion_history` (from the append-only extraction log).
> - **Safe by construction:** the scored `emotion_signal` EXTRACTION is untouched → the 216 eval is UNCHANGED (77/28/56); single-message cases have one reading → peak==current, trend='single', identical decision. 249 tests +1 skip, mypy/ruff/black clean.
> - **LIVE-VERIFIED on the portal:** a frustrated opener escalating to angry over two turns → arc `frustrated→angry`, `emotion_trend=escalating`, routed **P2 human_review**. (Gotcha found & noted: the portal `/answer` form field is **`answer=`**, not `text=`.)
> - **DESIGN DECISION (owner-flagged 2026-08-23, "before it meets real data" — logged, reason written down):** peak had no decay and no scope. Fixed + decided:
>   - **Decay + scope (concern 1):** the arc is now bounded to a **recency window** (`sentiment_window_hours`, default **72h**, in `get_emotion_history`) AND is case-scoped (never customer history — a fresh case starts fresh; a committed case >4 days out becomes a NEW case via windowing). So an old peak from an earlier episode (a follow-up windowing folds in days later; a "thanks" after resolution) **ages out** instead of routing the case as angry forever. 72h chosen: > the 24h same-conversation gap (a multi-day active complaint keeps its peak) but < a week (the owner's "week-later thanks" ages out). Verified: `test_old_peak_ages_out_of_the_recency_window`.
>   - **De_escalating override (concern 2) — DECIDED: keep peak-routing, NO priority-drop.** Reason: within an UNRESOLVED episode, evidence of anger is durable (a human should look — winning-condition §5) while a later calm is procedural, not proof the issue is solved. **Sentiment may RAISE priority within an episode (peak), never LOWER it** — de-escalation's value is realised at the episode boundary (resolution/decay), not by overriding the peak. The asymmetry is written into `rules/stage.py` so no future session adds a de_escalating drop. (Covered by `test_peak_routing_survives_a_later_calm_turn`: talked-down still → human_review.)
>   - The within-case leak vector was the only real one (windowing folds follow-ups into a case; `get_emotion_history` reads all its readings) — now bounded by the window. Tunable via `SENTIMENT_WINDOW_HOURS`.
> - **Follow-on (flagged, not built):** the elicit-layer angry→handoff still uses CURRENT emotion, not peak — make it peak-aware for full consistency (delicate elicit policy; rare in practice since an angry OPENER hands off immediately, before any calmer turn). The demo tenant now carries a few sentiment test cases from this verification — reseed (`scripts/reset_demo_tenant.py`) before the external gate.
>
> ## ⇢ PRIOR — START HERE (2026-08-22 handoff — MARKET-READY HARDENING + W2/W3)
> **Owner directive this session: "make it market ready — we're not close."** Worked the W (data/eval) + R (it-runs) blocks. **All $0, full suite green (234+1), pushed** (`dbb45f5` W2/W3, `cc38cde` R1–R8).
> - **THE ZOMBIE-WORKER FOOTGUN IS FIXED IN CODE (R2).** `scripts/run_worker.py` now takes a Postgres advisory lock per queue-set — a 2nd `default` worker refuses to start (exit 3). `default`/`backfill` coexist. Verified live; killed the 2 zombies that were running. **So "restart ONE worker" is now enforced, not a manual discipline** — but still run exactly one (the lock makes a second exit cleanly).
> - **DEAD-WORKER HONESTY (R3).** migration 0020 `worker_heartbeat`; every worker beats ~15s; a stale beat → the portal shows honest handoff copy immediately (not an endless spinner) + `/health` reports `worker.status` alive/down/age. So "it hangs on still-working" now self-diagnoses: `curl localhost:8000/health | jq .worker`.
> - **W2 done + W3 measured & REVERTED (the honest call).** `eval/edit_breakdown.py` decomposes the 28% zero-edit: **desired_outcome is the driver (44% edit, 62% of edited rows), NOT severity** (plan's guess, only +5 rows). A v22 desired_outcome prompt fix gave +6 outcome / +2 zero-edit but **−4 category (same-pass perturbation), all on self-authored labels, no gate passing** → reverted (v20 restored, like v21 fault-nullable). **The lever for outcome+category accuracy is the INDEPENDENT held-out labels (`eval/holdout_labels.csv`), not prompt-grinding** — same ceiling as confidence/category ([[calibration-label-ceiling-per-class]]).
> - **W4 re-verified: anchor+2 holds** (drill_max 1, 0/216 already-stated, 0/216 derivable) post-v4/v5. **W6 was already done** (winning-condition §4 voice-vs-text swap, dated).
> - **DEPLOY-READY (R1,R4,R5,R6,R7,R8): `docs/DEPLOY.md` is the runbook.** R5 fail-closed prod secrets (config.py, APP_ENV=prod refuses change_me_*); R1 `scripts/preflight_ollama.py` catches the Linux bind trap + wired into `deploy_rebuild.sh`; R6 Caddy TLS (SITE_ADDRESS, `--profile edge`); R8 `scripts/backup.sh` (pg_dump + MinIO); R4 engine restart:unless-stopped.
> - **W1 (independent labelling) HARNESS IS BUILT + TESTED — now purely owner-blocked (hire/pay a labeller).** The 66 holdout cases are FRESH (not in the 216) so they had no model output/owner gold. Built: `eval/extract_holdout.py` → `holdout_extractions.jsonl` (v20 model side, 66 rows, kept OUT of the blind packet); `eval/score_holdout.py` = the owner's FOUR numbers (model-vs-owner, model-vs-independent, owner-vs-independent, inter-annotator) generic over N label files + the **repair_redo-split diagnostic** (if two humans also split repair_redo → the ENUM is wrong, not the model — owner's test; DON'T touch the enum before then); `tests/test_score_holdout.py` (3, green). Packet ready+blind: `fixtures/holdout_labels.csv` (66, 0 gold) + `holdout_labels_INSTRUCTIONS.md` (rules-only, keeps overloaded repair_redo def on purpose). **OWNER TODO:** send packet to someone who is neither owner nor me, pay them, save returned file as `fixtures/holdout_labels_<name>.csv`, run `uv run python eval/score_holdout.py`. Preview: even on fresh holdout, model repair_redo = largest non-null outcome (13/22) — the W2 magnet persists.
> - **STILL OPEN (honest): R1 not yet run GREEN on an actual Linux host** (none exists — the preflight is built to catch it, verify on the first real box). Accuracy gates still FAIL (category 77/zero-edit 28/outcome 56) — **blocked on the W1 independent labels, not code**. External gate (3 strangers) still owner-action. See the older START-HERE below for the live-testing tuning loop (still valid).
>
> ## ⇢ PRIOR SESSION — START HERE (2026-08-21c handoff)
> **The owner is now TESTING the live system** (voice/record, images, text through the portal) and will SHARE the cases that work vs don't. **Your job next session: turn each failing case into a fix** — the tightening loop. It's PROMPT/POLICY-driven ($0), not fine-tuning: a misread → tune the extraction prompt (v20) or the elicit policy (v5); a mis-act → tune the policy/routing. Two owner-caught fixes already came from this loop this session (grounding on customer-state faults → elicit-v4; the contentless-opener instant-handoff → elicit-v5). Expect more; each is a durable rule ([[feedback-into-rules-winning-condition-motto]]).
> - **The live stack is UP and serving the owner's tests** (see RUN IT). If the owner reports "it hangs on still-working", the WORKER died — restart ONE (the zombie-worker footgun below). If they hit 429, the rate limit reset — it's currently RAISED for testing.
> - **The portal chat + honest-failure + durable-pipeline work is DONE + verified** (the three owner asks this session). The extractor/policy TUNING is the ongoing work now.
> - **Deferred, logged, DO NOT start unprompted:** the container→Ollama Linux-deploy fix (§0 deploy gotcha); WhatsApp still on BackgroundTask; the chat read-back repeats across turns (polish); the DB-contention root cause of this session's `processing_failed` cases was ZOMBIE WORKERS (not Ollama, not a product bug — [[the eval 28% is unaffected: run_extraction.py is DB/worker-free]]).
>
> **SESSION 2026-08-21c — CASE-MUST-NOT-LIE + DURABLE PORTAL + CHAT MODE (owner: "we still aren't close … the case must not lie … BackgroundTask fragility … make it workable, investigate in chat not just log it"). All verified live.**
> - **Fix 1 — honest processing failure (the case must not lie).** A swallowed pipeline exception used to leave a case in `created`/empty and render as "we read it and found nothing." Root: the stall copy was only reached on the TIMEOUT path, never the EXCEPTION path — nothing recorded that processing died. Now: **migration 0019** adds `processing_failed` to the `case_state` CHECK; `api.fail_case_processing` (guarded — only from `created`/`incomplete`, never un-finishes a done case); the durable stages stamp it on TERMINAL failure. **Portal** `public_status` routes `processing_failed` → the honest stalled/handoff copy ("we've hit a snag … a person is taking over … don't resend"). **Review UI** shows it as an ERROR: red "Processing didn't complete" banner, `case--failed` alarm bar, register row surfaces FIRST with "needs a human / ⚠ error", approval blocked ("handle manually — nothing to approve"), and the misleading synthesis panel is suppressed. `nabu-ui-test` clean desktop+mobile, 0 console errors.
> - **Fix 2 — durable Procrastinate, drop BackgroundTask.** KEY finding: `ingest_messages` ALREADY defers the durable `normalise` chain transactionally, so the portal's BackgroundTask was a REDUNDANT non-durable second run that only ran because the local recipe started no worker. Removed it (submit + answer). Stages `normalise/extract/elicit/rules/dispatch` now carry `RetryStrategy(max_attempts=4, wait=5, linear_wait=15)`; `_fail_case_if_terminal` marks the case failed ONLY when Procrastinate's own `get_retry_exception(...) is None` (exact, no off-by-one). **The portal now REQUIRES a worker** (`scripts/run_worker.py default`). Proven live: an elicit that exhausted 5 attempts correctly stamped its case `processing_failed`.
> - **Chat mode — investigate, don't log a dead case (the bigger ask).** The portal widget (`embed.js`) is now a CONVERSATIONAL THREAD (customer bubbles + system bubbles + composer + typing indicator), NOT a status card — but still NOT a chatbot (every question comes from the enforced anchor+2 elicit policy; the widget renders, never decides). Verified live end-to-end: emotional opener ("i'm gutted…") → **investigates** ("what's your order number?") → reply with BK-1004 → **Moment 3** ("We've found your order BK-1004: … delivered very late, 13:20 … What would you like us to do?") → outcome → **logged** ("Looks like a delivery problem with order BK-1004, and you'd like a refund. … We'll come back by [deadline]."). Two server-side supports: (a) **reprocessing gate** — `public_status` reports "processing" while a reply is in flight (newest inbound message newer than the elicit `processed_at` stamp), so the chat never freezes on the prior turn's stale question; `touch_elicit_processed` clears it even on an idempotent skip. (b) **grounding gate hardened (elicit-v4)** — a fault that NARRATES THE CUSTOMER'S STATE ("the customer feels dismissed") no longer counts as grounded, so the portal never asserts a fabricated category ("a problem with the service") on pure emotion; the sad/frustrated path investigates, the angry path hands off with **warm honest copy** ("we're getting a person … someone will reach out"), never "we've got everything we need."
> - **Diagnostic (owner asked): are silent failures counted as bad extractions?** NO — the 216-case eval set (cfpb 120 + multidomain 96) has **0 timeout-empty, 0 empty-governed, 0 missing-category** rows; 14/216 have zero emergent but a full governed core (legitimate). The 28% zero-edit number is NOT inflated by swallowed exceptions. Hardened anyway: `eval/score.py` now DETECTS `prompt_version=='timeout'`/empty-governed rows, EXCLUDES them from accuracy, and prints a loud banner (§10 no-silent-caps) so a future timeout run can never silently score as a bad extraction.
> - **BUGFIX (owner-caught 2026-08-21c, elicit-v5): a contentless opener was CLOSED into a case with no conversation.** "something hurt me" → the extractor labelled it `emotion=angry`, and the policy's §5 `angry→handoff` fired IMMEDIATELY (qc=0, in_review, zero questions) — the owner's screenshot showed a 3-word opener instantly "built into a case" ("someone will look at it personally"). ROOT: the angry-handoff short-circuited BEFORE any investigation. FIX (`policy.decide`): a **contentless** case (no grounded fault AND no anchor AND no concrete category — new `category_known` signal) is ASKED "what happened" FIRST, even when angry — §5 protects a REAL grievance from being grilled, not an empty opener from being heard. A concrete-but-thin category (delivery/billing) still asks the anchor (directional). Verified live: "something hurt me" → "What happened? …" (not a handoff). +4 policy/stage tests (both branches), 225 tests +1 skip.
> - **Known follow-ons:** the chat read-back repeats "Looks like a delivery problem…" across turns (minor polish); WhatsApp still uses BackgroundTask (same-class, out of this session's scope — the shared durable stages already back it when a worker runs); a stale-worker footgun bit testing hard (multiple `run_worker` processes with mixed code race jobs → mark spurious failures — always confirm exactly ONE worker); the demo tenant carries test cases + one `processing_failed` demo case (`4d27e9d0`) — reseed if a clean register is wanted before the external gate.
>
> **SESSION 2026-08-21b tail — gap audit + owner-directed unblockers (all pushed):** ran a full winning-condition gap audit (see the six-gate map in chat). **Owner corrections logged:** (1) **Arabic gate RETIRED** — `winning-condition.md §4` now carries VOICE-VS-TEXT extraction parity in place of Arabic parity, as a **dated owner decision with reason** (Arabic paused, voice kept; ≥30-Arabic composition requirement suspended with it). Do NOT re-score against Arabic parity. (2) **Critical path reordered: PUBLIC HTTPS is #1** (5 min, unblocks iPhone voice test + external gate); independent labelling starts in parallel but finishes later. (3) **Demo tenant needs a real order CSV before the external gate** (empty object store → M3 can't fire → tests the weak version). Cheap unblockers done: **cloudflared quick tunnel LIVE this session** (`https://reed-send-stream-laboratory.trycloudflare.com` → localhost:8000 portal; EPHEMERAL — a trycloudflare URL changes on restart, re-run `scratchpad/tools/cloudflared.exe tunnel --url http://localhost:8000`); **cloud-backend ImportErrors fixed** (asr_cohere/embed_bge stubs raise clean NotImplementedError); **stale "dedup zero-callers" docstrings cleaned** (machinery IS wired live; convergence still empirically unproven — column-level unit needs richer recurring data); **--no-cache deploy guard** (`scripts/deploy_rebuild.sh` + compose header). **Strategic reframe owner floated (worth holding):** τ=1.01 = zero auto-route may BE the product — "we fill your forms, you approve in 30s" is sellable WITHOUT ≥98% auto-route; that makes **≤30s review time** (unmeasured, needs a human on the review UI) the load-bearing §4 gate, not the accuracy gates. Next per owner: real-iPhone voice test (protocol PORTAL.md §12b, tunnel is up) → bakery demo tenant w/ order CSV → 3 strangers. This session (2026-08-21b) on top of the prior portal/WhatsApp work: `5fb6a57` portal status-link fix, `500ea7d` the "what happened" drill, `01b3202` analytical drill + object store, `1ea1eb1` **case synthesis (the meaningful-resolution arc)**. **Standing rule set this session:** after every commit/push, SHARE the GitHub commit/compare link so the owner can review ([[share-commit-links-after-push]]).
>
> **SESSION 2026-08-21b — the "meaningful resolution" arc (owner: "the analysis is weak vs the winning condition"). All pushed, verified live.** The pipeline STRUCTURED but didn't REASON. Three pieces + a detector fix:
> - **Object store for the portal demo tenant** (`scripts/seed_portal_orders.py`, `01b3202`): a realistic bakery order book (BK-1001 late, BK-1004 very late, BK-1003 wrong-item, BK-1006 undelivered, BK-1002/1005 on time) ingested through the REAL resolution path. Before this the "it already knew" moments had infra but NO data — every drill was open. `Portal Demo Co` = `a17456c2-6dbc-492a-9128-7747f8650196`.
> - **Analytical drill = Moment 3** (`elicit/policy.py`+`stage.py`, `01b3202`): when the anchor RESOLVES, the fault drill STATES the record and narrows with `FAULT_OPTIONS` (late/wrong-or-faulty/never-arrived/other, domain-neutral, free text alongside) instead of the open "what happened". `decide()` gains `fault_prompt`/`fault_options`; confirmation stated ONCE across drills. `POLICY_VERSION → elicit-v3`. LIVE: "i feel let down" → anchor BK-1001 → "We've found your order BK-1001: chocolate cake, delivered late 18:42… What went wrong?" + option pills.
> - **Case synthesis** (`app/rules/synthesis.py` `build_case_analysis`, `1ea1eb1`): a PURE, GROUNDED view (headline · summary · discrepancy · priority reason · next_step) assembled at review time from governed core + decision + contradictions. No model, no invented facts (ungrounded fault never asserted; next_step is a POINTER not an action, §3). Served on `get_case_review` as `analysis`; rendered by the review-UI `AnalysisPanel` ABOVE the raw fields (discrepancy uses the --alarm accent). **Policy → default-v2:** category routing (delivery→fulfilment, product→returns_quality, service→customer_care, staff→people_conduct, access→operations) — the weak "P3 · general_queue · a standard complaint" is now "P3 · fulfilment · A delivery or fulfilment issue…". Priority stays deterministic (§5).
> - **Contradiction-detector false-positive FIXED** (`resolve/contradiction.py`): a "2 hours late" complaint was flagged as contradicting the PROMISED `delivery_slot` (17:00), ignoring the record's own `delivered_at`/`status` that CONFIRM lateness. Prompt now weighs the whole record and treats promised≠actual as the complaint itself, not a contradiction (the domain-footgun pattern the owner flagged). LIVE: late→no contradiction; "never arrived" vs "delivered late"→still flagged. NOTE: contradiction detection is NOT versioned in the elicit idempotency key, so only NEW binds get the corrected prompt (existing cases keep any stale citation until re-elicited).
> - **KNOWN minor polish (not blockers):** the analytical-drill confirmation lists the first 4 non-contact record facts in record order (states "customer name …", can hit the 4-cap before `delivery_slot`) — would be better to prioritise anomaly-bearing fields; the synthesis summary is deterministic (good for trust) not LLM-fluent.
> - **FAULT-NULLABLE EXPERIMENT — TRIED, MEASURED, REVERTED (2026-08-21b, owner-requested "make fault nullable + re-run eval").** Made `fault` `["string","null"]` + a `desired_outcome`-style abstention prompt (extract-v21), re-ran the full 120-case CFPB eval. **Net REGRESSION, hypothesis falsified:** fault-null rate 0→**35% (42/120)** on REAL complaints (over-abstention — CFPB complaints are venty AND substantive, the model latched onto "only vents an emotion → null"), and it PERTURBED entangled scored fields (**emotion 73→63, −10**; category 82→79, −3; outcome/severity flat) even though `fault` isn't itself scored (no `gold_fault` column). Reverted fully to v20 (0/120, HEAD @ 3358d93, tree clean). **LESSON (durable): a per-field abstention instruction over-fires on real data and destabilises fields read in the SAME extraction pass — the elicit-layer grounding gate (elicit-v3, shipped) is the correct home for the contentless-fault fix, NOT the extractor.** Do not retry extractor-level fault abstention without a much narrower trigger (pure-emotion-only, tested against the 35% over-abstention). The eval measurement did its job — caught a regression that the reasoning missed. See [[measure-extraction-changes-abstention-overfire]].
>
> **SESSION 2026-08-21b — portal shakedown + the "what happened" drill (all pushed, verified live):**
> - **Portal `/p/c/{token}` status link was broken** (`5fb6a57`): `embed.js renderLauncher()` always called `renderSubmit()` in standalone mode, so the "come back later" link showed the SUBMIT form, not case status. One-line fix (`token ? renderStatus() : renderSubmit()`) + the standalone page header is now mode-aware (`Your case / Here's where things stand.` vs submit copy, via `__HEAD_TITLE__/__HEAD_SUB__` filled by the router). Verified live @1280+390px, 0 console errors. (The "mojibake" I first saw was an artifact of piping through `python -m json.tool` on Windows cp1252 — the wire bytes are clean UTF-8; NOT a bug.)
> - **The "what happened" drill — ask, never invent, the fault** (`500ea7d`, owner-requested "act natural, not a chatbot"). ROOT CAUSE found: the extraction grammar forces `fault` to a **non-null string** (unlike `desired_outcome`), so on a contentless message ("i feel sad") the model FABRICATES a fault — either inferred from the resolved **order record** ("the order was not delivered or was incorrect") or by echoing emotion ("feels let down after an unspecified event") — and it was passing the actionable gate as fact (a confident-wrong, Claim 2). **Fix is contained to the elicit layer + portal read-back; extraction UNTOUCHED → zero eval-set risk.** A fault is trusted only if BOTH (1) lexically ATTESTED in the customer's own words (content-word overlap ≥0.4, catches the record-inferred fault) AND (2) placed in a concrete category, not `other`/`UNCLEAR` (catches emotional venting). `_fault_grounded` + `_UNCATEGORISED` in `elicit/stage.py`; `policy.decide()` gains `fault_grounded` (default True → prior behaviour preserved) and asks the new `_FAULT_Q` BEFORE the outcome drill, inside anchor+2; portal `public_status` suppresses the phantom category read-back when ungrounded; `POLICY_VERSION → elicit-v2`. Verified live: emotional → anchor → "What happened?", no phantom read-back; concrete "cake turned up smashed and stale" → straight to outcome, category shown, never re-asked. **KNOWN LIMIT (honest):** the grounding is a deterministic heuristic (lexical + category), biased toward asking (safe direction); the deeper root fix — make `fault` nullable in the extraction schema + prompt it to abstain, mirroring `desired_outcome` — is deferred because it changes extraction and needs an eval re-run (low risk: real complaints keep their fault; only contentless inputs would go null, and those aren't in the CFPB eval set). A stubbornly-vague customer can be asked "what happened" up to twice within budget, then hand-off.
> - **RUN IT (this session's live stack):** engine on :8000 with `PORTAL_ENABLED=true PORTAL_SECRET=poc-portal-secret-2026` (in-memory rate limiter = 5 submits/10min/IP, resets on restart); demo tenant **`Portal Demo Co` `a17456c2-6dbc-492a-9128-7747f8650196`, key `ek_ZDw3qSBD1pqXowBRoSQizyNE`**, standalone submit `/p/s/<key>`; back-office review UI `http://localhost:5173/?tenant=a17456c2-…`. Cross-case dedup note: submitting the IDENTICAL text twice hits content-addressed idempotency (`normalise.skip_done`/`extract.skip_empty`) → the 2nd case gets no normalised content and sticks at the anchor. Use UNIQUE text when testing live. (Latent: two real customers sending the exact same words would cross-link — worth a look later, not this session.)
>
> **BUILT & VERIFIED — trust spine + product surface + all three channels:**
> - **Phases 0–7 (trust spine):** RLS isolation, immutable originals, idempotent replay, per-value provenance, the human-approval COMMIT GATE, per-field provenance spans (sentence/audio-seg/image-bbox), the deterministic priority/SLA/routing rules engine, calibrated per-field confidence (honest — `gate_met=False`, all → review).
> - **Self-serve surface:** `POST /api/objects` (connect data) + `POST /api/ingest` (new case) + Moment 3 end-to-end (anchor resolves silently, confirmation STATES the record).
> - **Review UI redesign — "Instrument" (this session):** IBM Plex trio, amber confidence-SPINE (5 discrete bands), fields-as-column, RULES decision bar, `c`-arms/`Enter`-commits gate (double-tap-safe), matted docs, staged intake. Verified live @1440/1280/mobile, 0 console errors.
> - **WhatsApp LIVE transport (this session):** receive webhook + `WhatsAppChannel.send()` — a real message → structured case → confirmation back to the phone (Moment 3 via sender phone). `docs/WHATSAPP-SETUP.md` + `scripts/whatsapp_demo_setup.py`. Owner-gated on the Meta test-number setup (identity, ~20min).
> - **Customer PORTAL (this session):** the first non-agent front door. Separate public `/p` router (embed key + signed case token, never `X-Tenant-Id`), redacted status projection (no internal leaks), vanilla shadow-DOM widget (submit + voice + status/drill), standalone pages. A THIN renderer of the shared elicit policy. `PORTAL.md`; `scripts/portal_enable.py`; gated on `portal_enabled`+`portal_secret`. Verified live @390px, 0 errors, 7 security/behaviour tests.
> - **§4 measurement (this session):** honest Phase-8 scorecard (`eval/score_phase8.py`) + live drill/trust measurement (`eval/measure_elicit.py`, `eval/measure_object_match.py`) + the independent-label blind sheet (`eval/holdout_labels.csv`, 66 held-out cases, ready for a labeller).
>
> **THIS SESSION (2026-08-21) — both §4 measurement tracks landed (owner: "both"). NB: the `record_dispute` taxonomy question I asked was ALREADY IMPLEMENTED as `record_accuracy` (R6-C, 2026-08-17) — the `billing_vs_service_adjudication.md` fixture is a STALE historical artifact whose "current gold" predates the re-label; the gold is reconciled (15/23→record_accuracy, fold-independent fixes in, oldgold preserved). Don't rebuild it. Live category is now **82% cfpb / 71% md** (record_accuracy is the largest correct bucket, 31/31); the residual moved OFF billing↔service to service↔access (cfpb) + service↔delivery (md). Per v20's own note, further category-prompt grinding = self-grading toward my labels → the lever is the independent slice, not another prompt version.**
> - **Track A — blind held-out label sheet BUILT** (`eval/make_holdout_label_sheet.py` → `eval/holdout_labels.csv`, 66 fresh cases held out from the 216 by content-fingerprint: 36 CFPB finance + 14 NHTSA product/safety + 16 Trustpilot service; blind, 0 gold cells; owner picked **fresh T3/real-domain**). Ready to hand to an **independent labeller** (neither me nor owner) — the binding constraint's harness. Commit `e39f9c9`.
> - **Track B — Phase 8 §4 scorecard BUILT** (`eval/score_phase8.py` + `eval/PHASE8_SCORECARD.md`; deterministic/$0/files-only). Every measurable §4 threshold scored + every unmeasurable one listed with reason+command (§10 no-silent-caps). Commit `549c988`.
> - **CUSTOMER PORTAL — BUILT (the first non-agent front door), server-first + verified live.** Design contract `PORTAL.md`. A SEPARATE public `/p` router (never `/api`): never accepts `X-Tenant-Id`; tenant from the **public write-only embed key** (submit) or an **HMAC-signed read-scoped case token** (status/answer). A THIN renderer — reuses ingest, windowing, extraction, resolution, the **elicit policy + anchor+2 budget**, and the rules deadline unchanged (zero portal-side question logic). Migration **0018** (tenant.embed_key + allowed_origins + `web` channel + a permissive embed-key RLS policy). `app/portal/`: tokens (HMAC, fail-closed), redacted status projection (plain-words read-back, customer copy, deadline — NEVER case_state/enums/confidence/priority/routing/emergent), router (submit→BackgroundTask+immediate token, poll with real-persisted-stage + >90s stall copy, answer via windowing, standalone pages, rate-limit per IP+tenant, per-tenant CORS, file size/MIME limits, voice instrumentation). **SHARED policy change:** `ElicitationPlan.options` (OUTCOME_OPTIONS) populated for the outcome drill — defined once so channels can't diverge, a HINT (free text always alongside). The **vanilla shadow-DOM widget** (`static/embed.js`, one `<script data-key>` tag, no framework/build): submit screen (one box + MediaRecorder voice, both formats, graceful degrade), status screen (state copy + deadline + read-back + question/options+freetext), standalone pages. Gated on `portal_enabled` (fail-closed); needs `portal_secret`. `scripts/portal_enable.py` onboards a tenant. **7 DB tests incl. the two named guarantees (client X-Tenant-Id IGNORED; case token can't cross tenants — RLS 404 + tampered-sig reject) + no-leak + limits + shared-options; 200 tests +1 skip; ruff/black/mypy(app) clean.** `nabu-ui-test` @390px live: submit / staged progress / status (read-back + deadline, no leaks), 0 console errors, e2e submit→poll→status clean. Commits `e31f0be` (server) + `ac7135c` (widget), UNPUSHED. Known minors: "transcribing" stage shows for text-only too (transient); recording-state screenshot needs a real mic (headless can't); durable procrastinate worker is the post-test upgrade over BackgroundTask.
> - **WHATSAPP LIVE TRANSPORT — BUILT (was deferred), so a real message end-to-ends.** Owner wanted to test on their own WhatsApp. Verified the official Meta Cloud API path is $0/ToS-clean/on-prem-viable (test number → up to 5 recipients; free conversation tier). Built: **receive webhook** `app/api/whatsapp.py` (GET verify/`hub.challenge` + POST with `X-Hub-Signature-256` HMAC gate → ACK 200 fast → BACKGROUND pipeline: ingest→normalise→extract→decide→elicit→dispatch), routed to `whatsapp_tenant_id` (one number ↔ one tenant, PoC); **send** `WhatsAppChannel.send()` implemented (Cloud API POST; the dispatch path was already wired) so the drill question goes BACK to the sender. Config: `whatsapp_api_version`, `whatsapp_tenant_id`, `CHANNEL_BACKEND=cloud`. **The sender's phone is the anchor → Moment 3 works live: a message whose number is on an order resolves silently and the reply CONFIRMS the record.** Proven inline (scripted, real pipeline, Ollama): a WhatsApp msg from a number on file → structured `delivery_fulfilment` case, P3/general_queue, order BK-1001 bound from the phone, next_question = the confirmation ("We've found your order BK-1001: slot 17:00… What would you like us to do?"). **8 host-safe tests (verify/signature/parse/send); 193 tests +1 skip; ruff/black/mypy(app) clean.** Owner-facing: `docs/WHATSAPP-SETUP.md` (Meta app → tunnel → .env → message) + `scripts/whatsapp_demo_setup.py` (seeds a tenant with THEIR number). The one owner-gated step is the Meta account/test-number setup (identity-gated; ~20min). Media (voice/photo) to the webhook is ignored for now — text only; the Media-API download → existing ASR/OCR is the natural next step. **NB (build-law, §10-style): a newer black in this env reformats ~6 untouched files (docstring-quote drift, prompt.py/schema.py/mint_scan.py/test_config_backends/test_dedup/test_pii) — reverted, NOT mixed into feature commits; a separate `chore: black` pass is owed.**
> - **REVIEW-UI REDESIGN — "Instrument" direction, DONE + verified live on real pixels.** Full visual/interaction redesign of `ui/` (no API/engine/data change; `App.test.tsx` unmodified + green). Signed-off contract in `ui/DESIGN.md`. Near-black instrument; **IBM Plex trio** (self-hosted Fontsource woff2 latin, OFL-1.1) with a semantic mapping — Sans=interface, Mono=machine data, **Serif=the customer's verbatim words only** (source panel; never a model value). Two signal accents only (**amber=uncertainty, green=committed**; red=alarm; priority=neutral ramp). **Confidence SPINE** = a discrete 5-band amber left-edge on each field (stepped, not a continuous fade — matches the ~6 trusted per-class reliabilities; per-field, not per-case). Fields scan as a **column**; "not stated" is a hatched first-class state; decision bar wears a `RULES` tag; white source docs are **matted** (not flush on near-black); intake shows a staged `normalising→transcribing→extracting→deciding` pipeline (not a spinner); designed empty register. **COMMIT GATE changed (owner call): `c` ARMS, `Enter` COMMITS (different keys), `window.confirm` dropped** — a double-tap `c` can't irreversibly commit; verified live (arm/double-tap-safe/Esc-disarm/Enter-commit all pass). `nabu-ui-test` CLEAN on all 4 required states + mobile + 1280px, **0 console errors, no overflow**; `pnpm tsc` + `pnpm vitest` green. Deferred (logged): a commit UNDO WINDOW (engine) as the better long-term answer than pre-confirmation.
> - **Track C — LIVE elicitation + object-match measurement (`1b7c199`), the drill/trust §4 rows measured OFF the gold ceiling** (owner: these don't depend on my labels). `eval/measure_elicit.py` (pure, real 216 states, coop-reply sim of the SHIPPED policy): **questions/case median 2 file-drop / 1 WhatsApp; drills-after-anchor median 1, MAX 1 — anchor+2 holds with margin; asked-already-stated 0/216; derivable 0/216** (the two unforgiving rows PASS); 192 actionable / 24 in_review (angry handoff). `eval/measure_object_match.py` (LIVE resolver+object_key+RLS, 600 cases, objective key GT, scoped-tenant+cleanup): **0 WRONG binds / 311 silent (trust gate); recall 311/311=100%; accuracy ≤1.0% bound.** The **52% silent RATE is MIX-DEPENDENT** (this mix constructs 48% unresolvable) — recall=100% proves the resolver isn't the bottleneck; the real ≥60% needs a real anchored-complaint dataset (CFPB anchors redacted). **Two pictures: drill+trust STRONG (and gold-independent); accuracy side under gate (needs the independent labels).**
>
> **SELLABILITY SURFACE — COMPLETE (this session):** a stranger can now, with NO developer in the room — **(1)** connect their data (`POST /api/objects` + "connect data": CSV/JSON, schema-agnostic, idempotent); **(2)** submit their messiest case (`POST /api/ingest` + "new case": text/files → structured case in ~8–17s, inline); **(3)** watch Moment 3 fire end-to-end — the anchor resolves silently against their data and the confirmation STATES the record facts ("your order BK-1001: slot 17:00, delivered 18:42…") instead of asking. Both §2 self-serve boxes closed; the §7 "touch a DB to serve a case" disqualifier is gone. This session also: floored thin calibration cells (calib-v2), made review ordering honest (class-level, not per-case), corrected the confidence-ceiling framing (the ceiling is LABEL consistency, not the extractor — §10 CORRECTION), and made logging unable to 500 a request.
>
> **HONEST OPEN GAPS (a sellable SURFACE is not a passing SCORECARD — now MEASURED, see `eval/PHASE8_SCORECARD.md`):**
> - **§4 accuracy gates unmet (self-labelled, measured 2026-08-21):** category **77%** (cfpb 82 / md 71; ≥90), zero-edit **28%** (≥70), desired_outcome **56%** (≥90), severity **83%** (≥95); auto-route **VACUOUS** (gate_met=False → 0 auto-route). All FAIL. Trust-flag passes only *trivially* (everything→review = assisted data entry, not automation).
> - **THE BINDING CONSTRAINT (unchanged, but harness now READY):** an INDEPENDENT human-labelled held-out slice — gates the confidence number, category score, AND review ordering; a better extractor can't beat my own label inconsistency ([[calibration-label-ceiling-per-class]]). **Blind sheet is BUILT** (`eval/holdout_labels.csv`, 66 fresh cases) — needs the owner to put it in front of an independent labeller.
> - **Convergence (the moat) FAILS** — composite curve FLAT (cfpb [37,27,23,29,27,20]/md [68,27,29,23,11]), ~85–89% hapax, last live dup 7.6% (>5%); unproven on real data. The `<5%`-dup row still needs the live embed dedup run.
> - **~8 §4 rows UNMEASURED but MEASURABLE with a live run** (no new data): object-match pair, questions/case + asked-already-stated + derivable-from-anchor + sparse→actionable (elicitation), end-to-end latency, backfill correctness. This is the biggest unblocked lever left.
> - **Arabic entirely absent (0/216)** — BLOCKED; the marquee differentiator is unbuilt + unmeasured (separate project).
> - **Cloud path partly vaporware** — `asr_cohere`/`embed_bge` modules missing. (WhatsApp send is now BUILT, no longer a stub.)
>
> **NEXT STEPS (prioritized, owner's ordered path 2026-08-21b) — pick up here:**
> 1. **[owner action — tunnel is UP] Real-iPhone voice test.** Protocol `PORTAL.md §12b`. Open the portal on a physical iPhone in Safari over the HTTPS tunnel (start it: `scratchpad/tools/cloudflared.exe tunnel --url http://localhost:8000` → a `*.trycloudflare.com` URL, then `/p/s/ek_ZDw3qSBD1pqXowBRoSQizyNE`). Test GRANT + DENIAL paths (denial → "Mic access is off…" instant), then check the engine log for `voice.submission` (codec/duration) + that transcription produced non-empty text. **This is THE gate for the voice-first claim** (Chromium logic already verified 6/6; iOS-physical is unrunnable by me). Voice = the wedge, still ZERO real samples.
> 2. **[me, READY] Bakery demo tenant w/ order book before the external gate.** `Portal Demo Co` (`a17456c2-…`) already has 6 seeded bakery orders (`scripts/seed_portal_orders.py`) so M3 ("it already knew") fires for a stranger. Expand to a fuller CSV if wanted before strangers arrive.
> 3. **[owner] External gate — the actual win condition.** 3 strangers, their own mess, no walkthrough, you silent; win = someone asks the PRICE before a feature (§8). Needs the portal reachable — the quick tunnel works for a session; a stable named tunnel / real deploy for a scheduled run.
> 4. **[human/owner — STARTS TODAY in parallel, finishes later] Independent labelling.** `eval/holdout_labels.csv` (66 blind cases, ready) in front of someone who is neither owner nor me. THE binding constraint on the ACCURACY side (turns "77% agreement-with-Claude" into a real number; tells you if the extractor is genuinely ~82% → needs a stronger model, or the gold was inconsistent → real accuracy is higher). Drill+trust side is already measured & strong and does NOT need this.
> 5. **[me, cheap + highest-signal, NO new data] The τ=1.01 review-time test.** Put one real reviewer on the review UI with a timer: at 28% zero-edit, 72% of cases need a correction — is correcting them faster than typing the case? Decides whether "we fill your forms, you approve in 30s" (assisted-review, no ≥98% auto-route needed) IS the product. Makes ≤30s review-time the load-bearing §4 gate, where the strengths compound.
> 6. **Convergence remediation (the moat)** — machinery is wired live (dedup→mint→promote→backfill); the composite curve is still FLAT because ~93% of qualifiers are distinct data. Honest unit is COLUMN-level (minted+promoted); needs richer RECURRING real data (one vertical) to bend, or the retraction stands. Real voice-in-one-domain via the portal is the path.
> 7. **[deploy] Ship-out gaps** — local-single-host only; no hosted config (Caddyfile stub), default `change_me_*` secrets, cloud ASR/embed are honest NotImplementedError stubs (real impls = metered-cloud, $0-gated). Durable Procrastinate worker IS built. For a hosted deploy: real secrets, hosted Caddy+domain, finish cloud ASR/embed OR commit to a local-GPU host, `scripts/deploy_rebuild.sh` (--no-cache).
> - **Arabic** — RETIRED from §4 this session (owner decision, logged; voice-vs-text parity substituted). Separate future project; not a current gate. Do NOT re-score against Arabic parity.
> - Small owed cleanups: a **`chore: black`** pass for the ~6 docstring-quote-drift files (kept out of feature commits); the portal "transcribing" progress row shows for text-only submits (transient cosmetic); the review-UI "+ new case" modal is still ~17s inline (the PORTAL path is already async — apply the same to the modal if wanted).
> - Deferred (wrong lever now): the cloud extractor (until #2 labels); the promised-vs-actual confirmation phrasing (per-tenant field-role pairing); a commit **UNDO WINDOW** (engine — better long-term than the `c`/Enter pre-confirm); durable procrastinate worker for the portal (over BackgroundTask) when it stops being a test surface; WhatsApp/portal media (voice/photo to webhook → Media-API → existing ASR/OCR).
> - Deferred (engine, logged 2026-08-21 from the review-UI redesign): a short **UNDO WINDOW** on commit — the better long-term answer than any pre-approval confirmation. Commit is currently a one-way first-writer-wins stamp (corrections 409 after), so the review UI uses a `c`-arms/`Enter`-commits two-step to prevent an accidental double-tap; the cleaner fix is an immediate commit with a brief reversible window. Engine behaviour, out of scope for the UI pass.
>
> **RUN IT (current — 2026-08-21c):** *At handoff the FULL stack was UP and serving the owner's live tests — engine :8000 (portal, RAISED rate limit), ONE worker, review UI :5173, and an HTTPS tunnel. These processes may or may not survive into the next session (a reboot / a session end kills them); re-launch anything that's down using the commands below. Verify: `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/p/embed.js`.*
> - **Infra:** `docker compose -f deploy/docker-compose.yml up -d db minio`; Ollama up (qwen3:14b — start `Ollama app.exe` after reboot).
> - **Engine (portal enabled):** `cd engine && PORTAL_ENABLED=true PORTAL_SECRET=poc-portal-secret-2026 PYTHONIOENCODING=utf-8 uv run uvicorn app.main:app --port 8000 --host 127.0.0.1`. (Restart it after ANY code change — the running process holds old code; kill the :8000 LISTENER pid first.) **NB: the currently-running engine was started with `PORTAL_RATE_IP_PER_10MIN=1000 PORTAL_RATE_TENANT_PER_HOUR=5000` so the owner isn't 429'd mid-testing — for the real external gate / production, drop those back to the defaults (5 / 60).**
> - **WORKER (NOW REQUIRED for the portal — 2026-08-21c):** `cd engine && POSTGRES_ADMIN_PASSWORD=change_me_admin_local PYTHONIOENCODING=utf-8 uv run python ../scripts/run_worker.py default`. Portal processing is now DURABLE (Procrastinate), not an in-process BackgroundTask — with no worker running, submitted cases sit at `created` and the portal honestly shows "still working / taking longer" but nothing advances. **Run EXACTLY ONE worker** — multiple `run_worker` processes (or a stale one on old code) race jobs and cause spurious stage failures/`processing_failed`. Check with `wmic process where "name='python.exe'" get commandline | grep run_worker`; restart it after any pipeline-stage/elicit code change. Add `--schedule` on ONE worker only if you also want the promote-scan loop.
> - **Review UI:** `cd ui && pnpm dev` → `http://localhost:5173/?tenant=a17456c2-6dbc-492a-9128-7747f8650196&case=<id>` (the `&case=` opens a case directly).
> - **Portal demo tenant:** `Portal Demo Co` = `a17456c2-6dbc-492a-9128-7747f8650196`, embed key `ek_ZDw3qSBD1pqXowBRoSQizyNE`. Standalone submit `/p/s/ek_ZDw3qSBD1pqXowBRoSQizyNE`, status `/p/c/<token>`. **CLEAN as of 2026-08-22: 0 cases, 6 bakery orders** (BK-1001…BK-1006; BK-1001 verified silent-resolve). To fully reset before the external gate: `scripts/reset_demo_tenant.py "Portal Demo Co"` (wipes all per-tenant cases/objects/schema, KEEPS the tenant + embed_key/portal config) then `uv run --group asr python scripts/seed_portal_orders.py "Portal Demo Co"` (both need `POSTGRES_ADMIN_PASSWORD=change_me_admin_local`). Answer the anchor **`BK-1001`** to see M3 STATE the record.
> - **Public HTTPS (iPhone / strangers / voice):** `scratchpad/tools/cloudflared.exe tunnel --url http://localhost:8000` → prints a `*.trycloudflare.com` URL. **EPHEMERAL — changes every restart.** LIVE at 2026-08-23 handoff (handed to the owner as the demo URL): `https://write-supposed-techrepublic-synthesis.trycloudflare.com` — demo submit `/p/s/ek_ZDw3qSBD1pqXowBRoSQizyNE`. **Likely DEAD next session — re-run cloudflared for a fresh URL and hand it to the owner.** No account, $0. (cloudflared.exe is gitignored under `scratchpad/tools/`; re-download from `github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe` if the scratchpad was wiped.)
> - **Deploy safely:** `scripts/deploy_rebuild.sh` (rebuilds engine/migrate/worker `--no-cache` to beat the COPY-cache stale-image footgun) — never a bare `up` after a code change.
> - **🚩 DEPLOY GOTCHA — container→Ollama binds trap (verified 2026-08-21c, logged NOT fixed; owner deferred).** The compose `worker`/`engine` reach the host GPU's Ollama via `OLLAMA_HOST=http://host.docker.internal:11434` + `extra_hosts: host.docker.internal:host-gateway`. VERIFIED the full chain WORKS on the owner's **Docker Desktop (Windows)** box: a container reads `OLLAMA_HOST` (`settings.ollama_host` env-wired), hits `host.docker.internal:11434`, gets the `qwen3:14b` model list — *even though the host Ollama binds to `127.0.0.1` only* (Docker Desktop proxies `host.docker.internal` to host loopback). **BUT on a native LINUX server this BREAKS:** `host.docker.internal:host-gateway` → the host GATEWAY ip (e.g. 172.17.0.1), which does NOT reach a 127.0.0.1-bound Ollama → connection refused → extract/elicit fail → retries exhaust → case honestly `processing_failed` (same shape as the DB-contention failures this session). **FIX at Linux-deploy time (not now):** set `OLLAMA_HOST=0.0.0.0:11434` **on the host running the Ollama SERVER** (⚠ same env-var name, OPPOSITE role: host = Ollama's BIND address; container = the client TARGET url — easy to conflate), restart Ollama, firewall 11434 to the docker bridge only. (This session's live `processing_failed` cases were NOT this — they were `ConnectorException('Database error.')` from 4 zombie `run_worker` procs racing Postgres connections; the eval 28%/82% is unaffected — `run_extraction.py` is DB/worker-free, host→Ollama→JSONL, 0 silent-failure rows.)
> - **Gotchas:** identical submit text hits content-addressed idempotency (`extract.skip_empty`) → use UNIQUE text when testing live; keep `PYTHONIOENCODING=utf-8` on Windows for non-ASCII. Portal in-memory rate limit = 5 submits/10min/IP (resets on engine restart). **Eval:** baseline is v20 (`cfpb_extractions.jsonl`, category 82%/combined 77%); `uv run python eval/run_extraction.py` then `eval/score.py` — the fault-nullable experiment (v21) REGRESSED and was reverted, do not retry without a narrower trigger ([[measure-extraction-changes-abstention-overfire]]).
>
> **📊 TRACKER ARTIFACT (visual status dashboard, private):** https://claude.ai/code/artifact/1f66c29b-1ff6-4eb0-92a4-48b513854ede — source at `docs/tracker.html` (re-publish that file with `url=<that link>` to update it in place; keep it current each session alongside this box).

> ### ⇢ SESSION HANDOFF — read this box first (updated 2026-08-19c: **PHASE 7 COMPLETE — the <30s keyboard review UI + the human-approval COMMIT GATE + per-field provenance spans + the universal register/report, all verified LIVE on real pixels.** Phase 6 COMPLETE below (deterministic rules engine + calibrated confidence, honest auto-route ceiling reported).
>
> **⇢ SELLABILITY STEP 1 — THE SELF-SERVE PRODUCT SURFACE IS NOW LIVE (2026-08-20).** Owner: "make this system sellable." The full-audit's #1 disqualifier (winning-condition §7: "anything requires you to touch a DB/config/prompt to make a customer's case work" — a service business in a product costume) was TRUE: every path in was developer-only Python. **CLOSED for the core intake path:** `POST /api/ingest` (multipart — pasted text and/or dropped files) runs the REAL pipeline INLINE (ingest→normalise→extract→decide→elicit) and returns the structured case, tenant-scoped (RLS); the review UI has a **"+ new case" modal** ("Paste the messiest real case you have… nothing to fill in"). **VERIFIED LIVE on real pixels, a real unseeded case a stranger could send:** a messy Chime complaint → 17s → a complete case (fault verbatim @100%, category access_availability, emergent org=Chime/date/duration), and the rules engine correctly routed the **angry** customer to **P2·human_review** ("An angry customer, routed to a human reviewer" — §5, not interrogated), with low-confidence fields flagged "needs review" + the anchor left "not stated" (refuse-to-guess). Motto held: no field wrong. `python-multipart` added (core dep → container picks it up). **2 ingest tests (scripted LLM, host-safe); 179 tests +1 skip; UI tsc/vitest green; nabu-ui-test clean desktop+mobile, 0 console errors.** **Known follow-ons for sellability:** (a) self-serve OBJECT-STORE upload — ✅ NOW DONE, see SELLABILITY STEP 2 below (§2 box — orders/bookings by file so the anchor→confirm loop works for a stranger; the other self-serve gap the audit flagged); (b) intake is synchronous (~17s spinner) — a background job + progress is the UX upgrade, not blocking; (c) tenant onboarding stays manual-behind-the-scenes (allowed, winning-condition §6). See the FULL-AUDIT gap report (this session) for the rest: convergence gate FAILS at committed altitude, §4 accuracy gates unmet, Arabic entirely absent (0/216), most §4 metrics unmeasured (Phase 8 not started), cloud path partly vaporware (asr_cohere/embed_bge modules missing).
>
> **⇢ SELLABILITY STEP 2 — SELF-SERVE OBJECT-STORE UPLOAD IS NOW LIVE (2026-08-20), and Moment 3 works end-to-end.** The other §2 self-serve box. The object model + resolution existed but were populate-able only from tests (audit gap: "object store = a test-only function; the upload adapter its docstring references doesn't exist"). **BUILT:** `app/resolve/upload.py` (`parse_object_file` — CSV/JSON/JSONL → row dicts, BOM-safe, wrapper-aware) + `POST /api/objects` (multipart file + `object_type`; profiles identifiers itself — no schema declared; idempotent by object content-hash; RLS'd) + a **"connect data" topbar modal** ("Upload your orders/bookings/assets… the system finds the identifiers itself… a case that quotes an order number resolves against it"). **VERIFIED LIVE END-TO-END (the Moment-3 payoff):** uploaded a 5-row bakery `orders.csv` (profiler found `order_id`+`phone` as identifiers) → submitted "my chocolate cake order **BK-1001** arrived crushed… refund" via `/api/ingest` → extraction pulled `anchor_value=BK-1001` → **elicitation SILENTLY BOUND it (object_snapshot created), state `actionable`, `next_question: None`** — the system did NOT ask for the order because it looked it up. "It asked, then it already knew." Re-upload is a no-op (idempotency shown in the UI: "0 new, 5 already present"). **2 object-upload tests (adapter + route + resolves-an-anchor); 181 tests +1 skip; UI tsc/vitest green; nabu-ui-test clean desktop+mobile, 0 console errors.** **Both §2 self-serve boxes (case intake + object store) are now closed** — a stranger can connect their data, submit their messiest case, and see it structured + resolved with no developer in the room. (Note: with few rows the profiler picks any coincidentally-unique column as an identifier — `slot`/`delivered_at` here; harmless, resolves on `order_id`/`phone`; self-corrects at real scale where times repeat. Fuzzy name-match on uploaded objects is exact-key-only for now — embedder=None on the route to keep upload fast; opt-in fuzzy is the follow-on.) **REMAINING sellability follow-ons:** the "confirm the DELAY not just the order" wording (Moment 3's second half — `_confirmation` still says "we found your order", not the record-derived fault); async intake (17s spinner → background job); and the substance gates from the full audit (convergence, §4 accuracy, Arabic, Phase 8) still stand — a sellable SURFACE is not a passing SCORECARD.
>
> **⇢ MOMENT 3's SECOND HALF — CLOSED (2026-08-20).** `_confirmation` (elicit/stage.py) now STATES the record's descriptive facts instead of a bare "we've found your order" — grounded (literal object values; it's customer-facing, §3), domain-agnostic (surfaces the object's non-identifier attrs, capped at 4). VERIFIED LIVE: a sparse case quoting BK-1001 → **"We've found your order BK-1001: slot 17:00, items chocolate cake, delivered at 18:42, customer name Sarah Whitfield. What would you like us to do to put this right?"** (the slot + delivery time make the delay visible; it asks the OUTCOME, not the order details). Fixed a latent display-id bug it exposed: with few rows several columns are coincidentally unique, so `_pick_external_id` had picked a timestamp ("your order 18:42") — added `is_identifier_name` (profile.py) so the display id prefers an id-NAMED column (`order_id`). The elegant promised-vs-actual phrasing ("6:42 against a 5:00 slot") needs per-tenant field-role pairing — noted as future, not built. **183 tests +1 skip.** **HOST-ONLY env gotcha (found live; container unaffected):** run the host engine with `PYTHONIOENCODING=utf-8` or a log line with a non-cp1252 char (→) makes structlog's print 500 the request — a logging error should never crash a request. **✅ FIXED (2026-08-20): logging can no longer 500 a request** — `app/obs/logging.py` now uses a `_SafeLogger` whose emit CANNOT raise (retries ASCII-safe, then swallows) + JSONRenderer `ensure_ascii=True`; proven live: engine started WITHOUT `PYTHONIOENCODING`, the case that previously 500'd returns 200, 0 encode errors. 185 tests +1 skip. Remaining sellability follow-ons: async intake (17s spinner → background job); and the audit's substance gates (convergence, §4 accuracy, Arabic, Phase 8) still stand.
>
> **⇢ POST-PHASE-5/6 OWNER REVIEW (2026-08-19c) — three findings, two fixed in code, one is now the binding constraint.** The owner checked the numbers, not the handoff. **(1) Confidence is a per-CLASS prior, not per-instance** — `P(correct|class)×grounding` gives every case in a class the same base number, so Phase-7 "low-confidence-first" ordering is class-level triage, NOT per-case difficulty. **FIXED:** the register now says "ordered by class reliability — least-reliable predicted class first" + tooltips; do not promise per-case hardness ranking (`reviewOrder` docstring, §10 CORRECTION). **(2) Thin calibration cells were noise wearing a decimal** (replacement=1.00 from n=2, staff_conduct=0.33 from n=5, other=0.11 from n=1). **FIXED:** `_MIN_CELL_N=10` in `app/confidence/model.py` drops any cell with n<10 to the field's conservative default + records surviving `support` in the artifact (**calib-v2**; category 9→6 trusted classes, desired_outcome 5→2, severity 3→2; `gate_met` still False, τ=1.01). **(3) The ceiling is my LABELS, not the extractor** — calibration is fit on gold I authored, so confidence = "P(agrees with my labels)"; a better extractor (Haiku/bigger local) only raises agreement with the LABELLER, not with reality, and would "measure two Claude models converging." **⇒ THE BINDING NEXT STEP (blocks the confidence gate, the category score, AND the review-UI ordering): an INDEPENDENT human-labelled held-out slice, 60–80 cases, someone who is neither the owner nor me.** Everything else is downstream; the cloud extractor is the WRONG lever until this exists (defer it). Harness ready: `eval/make_label_sheet.py` (blind, merge-safe) — needs the owner to pick the slice (re-label existing 216 for inter-annotator agreement vs fresh T3/real-domain data) + an independent labeller. **Honest product framing (owner):** with `gate_met=False` everything routes to review → the product is currently **assisted data entry, not automation**; the 30-second review target is therefore the entire value proposition, not a nice-to-have. **The owner named the gate_met=False discipline "the most valuable thing in the repo" — honest-number-over-forced-pass is the asset; keep declining the fudge.** 177 tests +1 skip after this pass (the commit `c850217` message says 178 — off by one; 177 is correct).
> **PHASE 6 half B — THE DETERMINISTIC PRIORITY/SLA/ROUTING RULES ENGINE (`e9405e4`), DONE:** service levels are a rules engine's output, never a model's (§3). Migration **0016** = `case_decision` (RLS'd disposable projection = governed core × policy) + `tenant.policy_yaml` (optional per-tenant override; NULL → universal default → zero-config). `app/rules/` = `policy_default.yaml` (the shipped universal policy: severity dominates → emotion escalates → billing/record→finance → UNCLEAR→triage → catch-all last so evaluation is TOTAL) + `engine.py` (PURE, clock-free, first-match-wins evaluator + fail-loud policy validation: rejects missing catch-all / bad priority / unknown condition key / non-positive SLA / dup id) + `stage.py` (the `rules` stage: reads governed core, loads tenant policy, computes decision + SLA deadline = `first_contact_at`+hours (the CLOCK STARTS AT FIRST CONTACT), upserts the projection; idempotent on inputs+policy version). Wired: extract transactionally enqueues `pipeline.rules` (parallel to elicit) so SLA/routing set with no manual trigger + recompute on any governed-signal change. Store: get_case_decision_inputs/get_tenant_policy_yaml/upsert_case_decision/get_case_decision. **22 tests** (determinism, first-match precedence, totality, validation, tenant override, clock-from-first-contact, idempotent replay, recompute, RLS isolation). The trust-gate "question budget in code" + "SLA/priority deterministic" both now hold.
> **PHASE 6 half A — CALIBRATED PER-FIELD CONFIDENCE (`f34fc8e`), DONE + the HONEST CEILING reported:** riskiest-assumption spike FIRST (§10) killed the spec's assumed signals: on the committed local qwen3:14b stack the model's introspection is DEGENERATE — self-consistency 7/7 even when wrong (the enum decision never varies though wording does); P(True)/verbalized ~0.95 on wrong labels (sycophantic); Ollama 0.12.3 emits `logprobs:null` (the §16.3 default signal, unavailable); a reframed LLM cross-check is redundant-or-incompetent (the v20 prompt already encodes the best category discrimination; its residual errors sit at the OWNER-AUTHORED gold-ambiguity ceiling). So confidence is **CALIBRATION on the human gold, not the model's number**: `app/confidence/model.py` — confidence = P(correct | predicted class) [gold-measured reliability] × grounding; abstention (UNCLEAR / refused null) → 0; unfitted/missing artifact → low bootstrap (fails safe → review). `route()` = selective prediction by τ. Offline `fit()` (leave-one-out, no self-grading) → persisted `app/confidence/calibration.json` (no sklearn/scipy in the engine — deterministic counts). Wired into extract stage + backfill (replaced the 0.5 placeholder); review model surfaces the rules decision + `min_governed_confidence` (low-confidence-first). **12 tests.** **PROOF (eval/spike_calibration.py, cfpb-120 + multidomain-96, LOO, metric PAIR):** category acc **82.5% cfpb / 70.8% md**; best per-class reliability **~89%**. Calibration is DIFFERENTIATED + useful (refund outcome 92% vs repair_redo 25%; frustrated 89% vs angry 48%; billing 90% vs access 71%). **🚩 HONEST CEILING (reported, knob NOT forced — §10): NO τ reaches ≥98% accepted accuracy on EITHER domain.** The EDD §10 ≥98%-auto-route target is blocked by the EXTRACTOR's ~81% category accuracy (best class ~89%) — an ACCURACY ceiling no cheap confidence signal can fix (top-confidence errors = billing↔service boundary inside high-reliability classes). So `gate_met=False`, τ unreachable, calibration correctly REFUSES to auto-route → everything → review, ordered by confidence, with the commit gate (§16.4) the guarantee nothing is confidently filled wrong. Same shape as the Phase-4 convergence retraction: an aspirational number that needs an upstream fix. **⚠ CEILING FRAMING CORRECTED (owner review 2026-08-19c — see the §10 CORRECTION + the POST-REVIEW note atop this box): the real lever is NOT a more accurate extractor. Calibration is fit on gold I authored, so confidence = "P(agrees with my labels)"; Haiku would just measure two Claude models converging. The binding lever is an INDEPENDENT human-labelled held-out slice.**
> **PHASE 7 — REVIEW UI + COMMIT GATE + PROVENANCE + REGISTER/REPORT, DONE + VERIFIED LIVE (unpushed):** all four trust-gate pieces built and exercised on real pixels against real seeded data.
> **(1) THE COMMIT GATE (§3/§16.4)** — nothing external issues on model output alone. Migration **0017** = `case_record.committed_at`/`committed_by` (one-way stamp + paired CHECK + column-scoped UPDATE grant; `case_state='committed'` already existed). Store: `commit_case` (COALESCE guards → first-writer-wins + idempotent — a re-commit never re-attributes/re-times), `commit_status`. `app/report/`: `render_case_pdf` RE-CHECKS `commit_status` at generation and raises `NotCommittedError` if unapproved (the gate is at generation, never trusting the caller); WeasyPrint is LAZY-imported (container-only; host raises `ReportBackendUnavailable`→503, distinct from the 409 refusal). **PROVEN LIVE:** uncommitted report → 409, committed report on host → 503, approve → `committed` + green badge + report button appears (was absent pre-approval). **(2) PER-FIELD PROVENANCE SPANS — the click-to-trace gate (was flagged in extract/stage.py as "a Phase-7 refinement"; NOW BUILT).** `app/extract/provenance.py` `build_field_citations`: deterministically locates each extracted value in `list_case_normalised_spans` and emits a PRECISE locator — `{char_start,char_end}` (sentence, offsets valid against the concatenated normalised text), audio `{t_start,t_end}` (segment), or image `{bbox}` (region); an inferred enum (category) that isn't a verbatim quote falls back to a whole-doc citation (provenance never lost, only un-highlighted). Wired into the extract stage (replaced the null-locator whole-doc citation). **PROVEN LIVE on real data:** audio case `cake_status='melted'`→segment {0–2.92s}, `desired_outcome='refund'`→a DIFFERENT segment {3.86–5.48s}; text case emergent value → char {232,311} highlighting the exact sentence yellow in the source panel. **(3) THE REVIEW UI** (`ui/`, React/Vite): low-confidence-first register (min_gov_conf asc, approved-last) with P1–P4 pills + confidence% + routing; keyboard-driven (react-hotkeys-hook: j/k field, n/p case, e edit, c approve, r report, ? help); decision bar (priority/SLA/routing + one-sentence rationale); refuse-to-guess "not stated" cards; inline correction (append→rebuild projection→**recompute decision**, blocked 409 post-commit); click-to-trace that lights up the sentence highlight / **wavesurfer audio waveform (real segment regions)** / image-bbox overlay; CSV export; `/api/docs/{id}` RLS'd blob stream for provenance assets. `nabu-ui-test` CLEAN desktop+mobile, **0 console errors**, no overflow (fixed one white-on-white "? keys" button). **(4) THE REPORT** — WeasyPrint per-case PDF (RTL-safe via `dir="auto"` — no separate Arabic codepath) + register CSV; **PROVEN: rendered a valid `%PDF-1.7` (13KB) in the container** from the committed case's HTML (Dockerfile already ships `report` group + `fonts-noto*`). **Store `list_cases` widened** (min_gov_conf/priority/routing/sla/committed) for the register. **18 migrations, 176 tests +1 skip (+5 commit-gate, +5 provenance), ruff/black/mypy clean.** Seed for a live demo: `scripts/seed_review_demo.py` (5 real CFPB + 1 audio, real Ollama+whisper). **INFRA NOTE (pre-existing, not a Phase-7 regression):** the compose `engine`/`migrate` IMAGES carry STALE app code (Docker COPY-cache on the "Structured Chaos" space) — the code is correct (host engine + the container-weasyprint render of host-generated HTML both prove it); a `docker compose build --no-cache engine` is needed before shipping the container (same class as the §0 migrate-image note).
> **⇒ NEXT = Phase 8** (full threshold scoring — the scorer over the matured ground-truth set; §4 metrics + risk-coverage/calibration plots on the cloud path). **OR** revisit the confidence ceiling by standing up the cloud extraction path (Haiku) — an owner call (touches the deferred cloud path). **Prompt at extract-v20; calibration artifact `calib-v1` (gate_met=False).** NEW build-law in CLAUDE.md §10 (the confidence-ceiling / no-magic-separator rule). Known PoC limits carried forward: phone normalisation digits-only; live WhatsApp transport deferred (Meta test number); per-field confidence is calibrated but auto-route is review-only pending a more accurate extractor.) The dated UPDATE blocks below are AUDIT TRAIL ONLY (historical, newest first). **THIS box is the current truth and the live frontier — start Phase 8 from here.** **PARKED (backlog, owner-gated on $0):** the cloud-extractor confidence-ceiling test — `ClaudeLLM` (Claude Haiku) backend is BUILT + wired + committed (`7cfed5f`, unpushed) behind the same LLMBackend interface ($0 to exist), but RUNNING it against the gold needs an API key + ~$1–2 metered spend, which violates the $0 default. Do NOT propose running it; the ≥98%-auto-route gap is an accepted PoC limit (local extractor ~81% category ceiling), not a live lever. Only revive if the owner explicitly opts into spend. See memory [[zero-budget-never-steer-to-cost]]. Dip into the dated blocks only to understand WHY a past decision was made.
>
> **🚩 CONVERGENCE PROOF RETRACTED (2026-08-17, owner + `repo-analysis-remediation.md` R0).** The earlier
> "Phase 4 the moat — PROVEN, self-converging schema" claim was INVALID and is withdrawn. `HEAD_NOUNS` is a
> closed 31-enum, so the new-HEAD curve [15,4,4,1,1,1] is finite-set enumeration — it declines by
> construction and would do so on noise; **a gate that cannot fail is not a gate.** The REAL signal is the
> composite (`qualifier_head`) curve, and it is FLAT: cfpb [46,38,54,45,51,41]/275/**89% hapax**, multidomain
> [70,34,49,41,37]/231/**92% hapax** — same as the pre-Path-A curve [48,52,74,64,77,63] it was meant to fix.
> Sprawl MOVED into the qualifier space (unmeasured + undeduped: `dedup_field` has ZERO live callers). The
> escape valve is closed (`other` 0.7% cfpb / **0.0% multidomain**) so head-promotion can't fire → "emergent,
> never seeded" is **100% seeded** today. 34% of attrs carry a null qualifier (information loss). **Convergence
> is UNPROVEN. The moat has never executed end-to-end.** Do NOT treat Phase 4 as done. **Plan = remediation
> R0–R7 (`repo-analysis-remediation.md`), R1–R3 before any Phase 5.** This is the 2026-08-14 head-noun-altitude
> self-grading move, recommitted under the Path A name (§10) — do not re-promote the head curve to the pass line.
>
> **Status:** Phases **0–3 DONE + verified live.** **Phase 4 (the moat) — MECHANISMS built & sound, PROOF
> INVALID (see retraction above).** Correctly built and NOT to be re-litigated (remediation Finding 5):
> `{head(closed enum), qualifier(open), value}` extraction, two-dimensional promotion (mig `0009`),
> **STAGE-6 backfill = re-EXTRACTION against retained originals** (mig `0010`), periodic promote-scan. What is
> NOT proven: that any of it produces a converging schema — it hasn't run live (no dedup) and the curve is flat.
> **4.7 DONE + verified live on real pixels:** intake→normalise→**extract chained** (transactional enqueue;
> extract-idempotency prompt-version hole fixed), the **review read model + `/api` routes** (tenant-isolation
> test passes), and the **review UI** (governed cards incl. a "not stated" refuse-to-guess card, emergent table,
> click-to-trace provenance) — `nabu-ui-test` clean desktop+mobile on 3 real CFPB cases via the local $0 pipeline.
> **THE WORKER IS STOOD UP (compose):** `worker`(default)+`worker-backfill`(backfill isolated) run
> `scripts/run_worker.py` (sync `app` for defers + async `worker_app` twin for the worker + promote-scan
> scheduler loop; `@app.periodic` removed — it can't run on the twin). The queue now FIRES autonomously —
> proven live in the full container stack (ingest → container worker normalise+extract via host Ollama over
> `host.docker.internal` → served by the container engine). This closes the last 4.7 "not built" gap.
 Structural quality strong: json_valid 100%, grounding 0.980. **Accuracy on the 100-case human-gold
> (v12, latest):** desired_outcome **63%** (v10 41→v10.5 51 via refuse-to-guess abstention gate; **v11 51→63**
> via the wrong-value refund-overfire fix — correct-a-record=repair_redo, validate=information; null-invention
> now 6/39), **org capture 50/51 (98%)** (v12, was 21/51), key-fact recall **24%**, category **60%** (held;
> earlier −6 vs the retired 65 was fragile boundary noise, owner-accepted), emotion 71% (not a gate). **Severity
> 66% (was 71) — a −5 regression FLAGGED for owner: 4/6 losses are credit-report-inaccuracy cases where the
> def makes v12 arguably right vs gold=none (a gold-vs-def boundary q, not degradation); not chased per §10.**
> Planted-probe checks (`eval/gold_checks.py`): UNCLEAR abstention PASS, safety_health 1/2, extractor
> deterministic. **94 tests + 1 skipped; 10 migrations** (+4 this session: review read model, tenant
> isolation, normalise→extract chain). Arabic = separate next project (not blocking).
> `origin/main` @ `HEAD` (pushed). **MOTTO: score every step against `winning-condition.md`; turn
> each owner comment into a durable rule; never repeat a caught mistake ([[feedback-into-rules-winning-condition-motto]], CLAUDE.md §10).**
>
> **⇒ IMMEDIATE NEXT — levers (a)/(b)/(c) all RESOLVED this session; remaining accuracy + Phase-4 wiring.**
> DONE: (a) desired_outcome refuse-to-guess (v10 shipped, 41→51, invention 27→12); (b) key-fact recall
> diagnosed as mostly metric-scope (primary 22% / diagnostic case-recall 49%); (c) taxonomy fork SETTLED —
> no finance branch, CFPB stays a stress-test, finance emerges via the emergent layer (§4). **OPEN next
> levers:** (1) **desired_outcome value-side still ~48%** (24/61 stated outcomes matched) — the abstention
> gate fixed INVENTION but the wrong-VALUE bucket (repair_redo→refund, →escalation, →information) is
> unaddressed; likely ambiguity-bound + may need confidence+abstain, and needs its own probe (do NOT
> blind-tune). (2) **org/counterparty under-capture ~30%** — the real residual behind key-fact recall; the
> model should emit the bank/agency into the `organization` head more reliably. (3) **safety-severity 1/2**
> (24507863 read off the financial dispute, not the underlying biohazard — counterparty-vs-narrator; watch).
> (4) category needs a MIXED-DOMAIN gold set to measure honestly (CFPB is a weak validator, don't over-tune
> it). **Discipline: don't blind-tune, probe→isolate→fix→re-score→watch the DISTRIBUTION; dev set ≠ ship
> gate.** Then Phase-4 operational wiring (below). Older accuracy trail: (was 40-gold)
> a too-sparse slice** — n=24 makes outcome unmeasurable (bounces on noise) and the sparse slice proves
> category/severity still ABSTAIN when they should (refuse-to-guess §2). **100-case sheet is BUILT
> (merge-safe `make_label_sheet.py 25` — 40 labelled preserved + 60 blank, all with narratives); PENDING
> OWNER to label the 60 → `eval/score.py` gives the ≥100 number.** (c) outcome is likely
> ambiguity-bound → may need confidence+abstain, not a better def (do NOT keep tuning the prompt for it).
> Harness: `eval/{make_label_sheet,score,category_probe,governed_probe}.py`. Then the quality/operational
> follow-ons:
> 1. ✅ **DONE (v4 + v5) — extractive qualifiers + tightened head guidance.** v4: verbatim qualifiers,
>    value grounding **0.989**. v5: specific-head guidance + qualifier length-cap → `description` dumping
>    **165 (21%) → 46 (11%)**, grounding **0.984**, convergence `[14,5,3,1,1,0]`/24 heads. Residual (NOT a
>    gate issue): description still catches ~46 clausal VALUES (value slot not length-capped) — optional
>    further tightening (cap value length / force `other`→promotion) if it ever matters.
> 2. **Wire qualifier-space dedup before qualifier-promotion** — the reframed BGE+adjudicator (STAGE 3)
>    RELOCATES from field-names to QUALIFIERS under a head (dedup `charged`/`charge` before a split).
>    Not yet wired; heads need no embedding-dedup (closed exact-match).
> 3. ✅ **DONE (STAGE 6) — promotion wired end-to-end; backfill RE-EXTRACTS history** (not re-projection —
>    see the top 2026-08-14 UPDATE). Periodic trigger + `concept_extract` + `backfill` + migration `0010`
>    + `promote_scan`. Storage = flag+projection (no log rewrite / no physical column). Remaining bits:
>    the review UI reading `promoted`; a real long-running worker so `@app.periodic` actually fires.
> 4. Then the rest of Phase 4: 4.2 profiling · 4.5 convergence-monitor + light PII gate · 4.6 scorer
>    (needs human labels for governed-core ACCURACY — separate) · 4.7 wire extract into the queue +
>    JSON-diff review view · qualifier-space dedup before qualifier-promotion (item 2 above).
> **Dead/parked levers (proven earlier this session, do NOT re-attempt):** example-values in the name
> adjudicator (probe_values.py flipped NOTHING); τ tuning on the proof set (self-grading); **redefining the
> convergence metric to head-noun count (Path B) — REJECTED as self-grading, full-name/column count stays
> the gate; head-noun curve is DIAGNOSTIC-ONLY in `run_convergence.py`.**
>
> **Env note:** the moat needs the embed group — run eval with `uv run --group embed ...`. Keep all groups
> synced: `uv sync --group embed --group asr --group pdf` (a bare `uv sync --group X` PRUNES the others and
> breaks PDF/ASR tests — that bit me this session). Ollama must be up (start `Ollama app.exe`). BGE-M3
> first load downloads ~2.3GB (cached after). Real-data harness: `eval/fetch_cfpb.py` (fetch) +
> `run_extraction.py` (extract → **the Path-A column-convergence proof**) + `run_convergence.py` (the
> PRESERVED pre-Path-A name-dedup negative baseline, historical) + `diag_pairs.py`/`probe_values.py`
> (the geometry + dead-lever diagnostics).
>
> **Phase 3 (earlier this session) — file-drop intake + normalisation, EN-first:** in-house WhatsApp chat-export
> parser (`app/intake/whatsapp_export.py` — iOS+Android, multi-line, attachments, media-omitted, bidi,
> locale-locking, **UTC-aware times**; NOT whatstk/GPL) + generic upload (`upload.py`); channel-agnostic
> `InboundMessage` (`models.py`). **Normalisation** (`app/normalise/`): router by MIME → audio
> (faster-whisper + bundled silero `vad_filter`, segment spans) · ocr (PaddleOCR, **container-only**,
> EN PP-OCRv5) · pdf (pdfplumber text-layer + pypdfium2 rasterise→OCR) · text passthrough — every fragment
> carries a provenance span in the exact `Citation` locator shape. **Windowing** (`windowing.py`): 24h idle
> gap + close-state + LLM classifier for the gray band, biases NEW when unsure. **Ingest orchestrator**
> (`ingest.py`): windows each msg, stores text+attachments as immutable content-addressed
> `source_document`s, **transactionally enqueues** the normalise stage; message-content dedup → re-ingest
> is a no-op. **Pipeline** (`pipeline.py` `normalise_source_document`, claim→work→complete ledger) wired as
> the real `pipeline.normalise` task in `queue.py`. Migrations **`0005` normalised_content** (derived,
> RLS'd, spans) + **`0006` case_record.contact_ref** (windowing anchor).
> **A-MED CLOSED:** `WhisperASR` now calls `enable_cuda_win()` + `vad_filter`; **proven live on the GPU**
> transcribing real speech with segment timestamps. **F7 CLOSED:** compose `migrate` one-shot
> (`app/init_db.py`) runs alembic + procrastinate schema before the engine serves.
>
> **Numbers:** **79 tests green + 1 skipped** (container-only multimodal; run CI-mode `REQUIRE_DB=1`),
> **8 migrations**, ~6k LOC. `origin/main` @ `dd71a07`, tree clean, pushed to
> `github.com/Colonel94/structured-chaos`. ruff/black/mypy --strict clean. New this session (Phase 4):
> `app/extract/` (schema/prompt/extractor/stage), `app/schema/` (dedup/promote), `app/eval/` (real-data
> harness), migrations 0005–0008. Verify: `cd engine && REQUIRE_DB=1 uv run pytest`.
>
> **ADVERSARIAL CROSS-PHASE REVIEW (2026-08-13) — done, all real gaps closed.** 3 independent reviewers
> (trust-spine / correctness / exit-gate). **Trust spine + Phase-2 enqueue: genuinely intact, not
> regressed.** Real gaps found + FIXED this pass: **GAP-1** cost-meter had ZERO production callers →
> now wired into normalise (ASR/OCR) + the windowing classifier, per-case `backend_call` recorded;
> **H1** content-only dedup dropped legit repeated messages → now a stage-ledger key on
> (sender+time+content); **H2** captioned Android media was dropped → attachment matched on the first
> line, caption kept; **H3** scanned-PDF OCR-unavailable was marked done-forever → now `degraded` →
> `fail_stage` (re-claimable in the container); **H4/M5** tiny-text-layer scanned PDFs misread →
> boilerplate-strip + keep partial text; **H5** locale re-locked mid-file → order detected once for the
> whole file; **M1** classifier backend error aborted ingest → fail-safe to new; **L1/L2/M4** negative-gap
> guard / NaN→None confidence / zip basename-collision. **GAP-2** OCR/PDF had no automated test → added a
> container-gated multimodal test (skips on host). Documented-as-PoC-acceptable (real but scale/opt-in):
> M2 classifier cross-call empty context (safe-split bias), M3/M6 batch/stage transaction hold.
>
> **Environment (Windows host):** Docker `db`+`minio` healthy. **Ollama may be DOWN after a reboot →
> start `Ollama app.exe`** (qwen3:14b on the 4070). Migrate a fresh DB: `cd engine && uv run alembic
> upgrade head` + `python scripts/bootstrap_procrastinate.py` (or, in compose, the new `migrate` service).
> Phase-3 host deps: `uv sync --group asr --group pdf` (OCR stays container-only). **Gotcha:** run
> `black`/`ruff` from `engine/` on `app tests` ONLY. Windows console: prefix `PYTHONIOENCODING=utf-8` for
> scripts that print non-ASCII.
>
> **Run/verify:** tests → `cd engine && REQUIRE_DB=1 uv run pytest`. OCR/PDF-image are container-only:
> `docker compose -f deploy/docker-compose.yml build engine` then run a one-off (mounts break on the
> "Structured Chaos" space → rebuild rather than `-v` the source). Live spine proof this session: an
> Android export split into 2 cases (windowing), immutable docs, transactional jobs, idempotent replay,
> per-case transcript projection.
>
> **PHASE 4 — IN PROGRESS (the moat).** Done + verified live: **4.0 spike** (qwen3:14b extraction viable,
> ~7s/case, §10 killer proven first) → **4.1 extraction unit** (`app/extract/`: schema + versioned prompt +
> `extract()` with closed-world grounding gate; nullable refuse-to-guess) → **extract pipeline stage**
> (`app/extract/stage.py`: normalised text → governed core + grounded emergent via `record_extraction`
> + citations, `emergent_field` registry (migration `0007`, pgvector), field_current projection, LLM
> metered, stage-ledger idempotent). **Live E2E proven:** a messy complaint → full structured case
> (governed + emergent) in ~7s @ $0. 77 tests green + 1 skipped. **REMAINING Phase-4 units:** 4.2 stats-
> before-semantics profiling · **4.3 BGE-M3 + pgvector DEDUP** (τ=0.85 merge/0.70 admit — the moat core) ·
> 4.4 promotion (support≥4) + backfill (100%) · 4.5 convergence monitor + light PII gate · 4.6 the scorer
> · 4.7 crude JSON-diff review view. **Moat PROOF (convergence/<5% dup/declining new-field rate) is gated
> on REAL ENGLISH data (design-partner/curated, T1/T3) — NOT Arabic recordings (next project); never
> graded on authored cases.**
>
> **Still deferred (cheap):** **F8** — `field_current` auto-refresh (decide at Phase 4, before the review
> UI reads it); **A-MED(embed)** — BGE-M3 wrapper still only library-proven (lands when Phase-4 dedup calls
> it); **M3** — GUC pool-reuse leak test. **Deferred within Phase 3:** WhatsApp live webhook (needs Meta
> test number, track T2) + email drop (needs UAE mailbox) — file-drop is the $0 PoC channel. **Parked:**
> Gate-A5 owner recordings (spikes #1/#2). **Standing practice:** commit fixes directly ([[commit-fixes-directly]]).
> **Status page (private):** https://claude.ai/code/artifact/4c909fb2-b42e-4f3e-96d2-e7367b366635

**UPDATE (2026-08-17g, OFF-FINANCE CATEGORY PROBE + FIX v17→v19 — combined 73.6%→75.9%, multidomain +7; capped at 3 iterations, best kept).**
Owner: "probe the off-finance category errors before Phase 5." Confusion matrix on multidomain-96 (v16): 66%,
+26 over the 40% majority baseline but 24 under the §4 ≥90% gate. **Root cause (structural, not scatter):** the v16
prompt lavishes 3 discriminator paragraphs on the FINANCE boundaries (billing/service/record, all R6 work) and gives
the off-finance ones ONE LINE each. **42% of errors (14/33) sit in exactly the two most under-specified pairs:**
service_fault→delivery_fulfilment (8 — the model treats `delivery_fulfilment` as a magnet for any order/logistics
noun) and safety_health→product_fault (6 — all NHTSA, the model reads "a part malfunctioned" as product_fault and
misses that a malfunction endangering the driver is safety). Rest (~19) = mostly LABEL NOISE on scraped consumer
reviews that VENT rather than file clean grievances (subjective "not for me", fuzzy staff↔service, fraud→other) +
2 off-finance record_accuracy misses (finance-weighted, expected). Owner adjudicated the 3 debatable delivery rows →
all service. **Fix = two general R6-shaped discriminators (NO eval-case-specific examples — that would overfit the
test set, §10). Three iterations, each on a diagnosed failure mode:** v17 (both discriminators) → safety worked
(recall 11→15/17) but delivery barely moved (8→7) AND safety over-fired on wear/noise/scam; v18 (tightened both) →
delivery FIXED (8→4) but the safety re-write over-corrected into under-firing (back to 10/17); **v19 = SYNTHESIS:
v17's recall-preserving safety block + a one-line scam/fraud carve-out + v18's strict goods-logistics-only delivery
block.** **FOUR-VERSION TABLE (category acc): v16 CFPB80/MD66/comb73.6 · v17 79/68/74.1 · v18 78/69/74.1 · v19
78/73/75.9.** v19 clears BOTH clusters at once (service→delivery 8→3, safety→product 6→2, safety recall 14/17),
record_accuracy held 31/31. **Cost: CFPB 80→78 (−2), concentrated on the PRE-EXISTING fuzzy service↔access boundary
(3 of 4 losses = access→service bleed from the delivery "unreachable/runaround→service" language; 1 service↔billing
noise) — not a core-finance break.** **Honest ceiling finding: combined sat at ~74% through v16–v18 because every
off-finance gain grazes CFPB — a single UNIVERSAL prompt trades one domain's boundary for the other's; v19 only broke
75% by getting both clusters cleanly. Past here the lever is MORE/BETTER GOLD (esp. cleaner multidomain labels +
service↔access adjudication), not more prompt versions.** No enum change, finance defs unchanged, so no governed-core
halt. Preserved `cfpb_extractions_v16/v17/v18.jsonl` + `multidomain_extractions_v16/v17/v18.jsonl`; current fixtures =
v19. **Next lever = service↔access (the CFPB −2 + the known service→access ×8 cluster), then Phase 5 (elicitation) —
extraction is at 76% combined / 78% CFPB, a floor elicitation can build on.** 104 tests +1 skip (prompt-only change).

**UPDATE (2026-08-17c, R4 + EMERGENT HEAD-MINTING ARCHITECTURE BUILT + TESTED — the moat's missing piece is now built; live real-data mint verification pending v14 re-extraction).** `origin/main` @ `1907702`.
Built the two pieces the R2 finding pointed to. **R4 (stats-before-semantics, `app/extract/profile.py`):**
a deterministic value profiler — discriminator is the FUNCTION-WORD RATIO not length, so it keeps concrete
values incl. long proper names (legal citations, "Fair Debt Collection Practices Act") and rejects CLAUSES
("you are in violation") + redaction junk. Extractor drops non-concrete values from the escape-valve heads
(`other`/`description`) ONLY — content heads keep descriptive values (a symptom is signal). Measured scoped
drop 4% cfpb / 3% multidomain, all junk. prompt v13→v14 (text unchanged; busts idempotency key). **HEAD-MINTING
ARCHITECTURE — emergent columns are now BORN, not only seeded:** `minted_head` registry (mig 0011, RLS'd) +
store api; **per-tenant EFFECTIVE vocabulary** threaded through schema/prompt/extractor (all take `heads`,
default=seed HEAD_NOUNS so callers unchanged); the extract stage loads seed+minted heads AND folds a
minted-vocab signature into the idempotency key so minting FORCES re-extraction (re-homes history); `mint_scan`
(cluster escape-valve facts via BGE at a looser concept-τ, mint a head per cluster recurring ≥PROMOTE_HEAD_N
cases, LLM-named, fail-safe: name-collision-with-seed → rejected, below-floor → stays in `other`);
`queue.mint_scan` task + scheduler order **dedup → MINT → promote**; minting re-extracts affected cases.
**101 tests +1 skip green, NO regression.** Tests: recurring `other` cluster mints a head (with gloss) that
joins the vocab; below-floor doesn't; seed-collision rejected; R4 profiler unit + escape-valve-scoped filter.
**✅ VERIFIED LIVE END-TO-END (real Ollama, data we didn't author):** (a) v14 (R4) re-extraction cut `other`
46→28 (clause junk filtered), grounding 0.979 held, composites 189→173; the head-minting spike on clean data
mints a GENUINE concept (`regulatory_reference`) — the `miscellaneous_info` garbage is gone. (b) **THE GLOSS
FINDING (a live test a fake-LLM unit test can't catch): extending the grammar enum is necessary but NOT
sufficient — the model dumped `15 U.S.C. 1692g` into `other` even with `regulation` in the vocab, because the
prompt never said what `regulation` MEANS. Fixed: mint now produces a GLOSS (mig 0012), injected into the
prompt.** Re-test: seed→`other`; +regulation-no-gloss→still `other`; **+regulation+gloss → model EMITS
head=regulation ✓.** So an emergent column never seeded is BORN from data AND used by the model —
"specialisation is emergent, never seeded" made literally true and verified. **✅ FULL-PIPELINE E2E DEMO DONE + VERIFIED LIVE (`eval/demo_head_minting_e2e.py`, real DB + real Ollama+BGE,
data we didn't author):** ingested 12 real citation-bearing CFPB cases → extract (citations → `other`) →
dedup_scan → **`mint_scan` MINTED `regulation_reference`** (4 recurring cases) with an LLM gloss → re-extracted
the affected cases → **5 legal citations (15 U.S.C. 1692g, FDCPA, FCRA, …) now sit under the MINTED column** —
a column no one configured. The moat's central claim ("specialisation is emergent, never seeded") is now proven
END TO END through the production code paths, not asserted. **Clustering hardened (an algorithm fix the demo
forced, NOT a threshold tune): mint_scan uses CONNECTED-COMPONENTS (union-find) not greedy single-centroid —
greedy fragmented the citation concept (spans cos 0.45–0.77) below the floor; union-find holds it at the same
MINT_TAU, outliers ("12 CFR") stay correct singletons.** Infra note: the compose db was stuck at mig 0010 (the
`migrate` container runs a STALE image without 0011/0012) — apply new migrations to the compose db from host via
`POSTGRES_ADMIN_PASSWORD=change_me_admin_local uv run python -m app.init_db`, or rebuild the migrate image.
**✅ R5 PII GATE DONE (`app/schema/pii.py`, mig 0013, 104 tests green):** protected data never becomes governed
schema, at BOTH paths. Deterministic-first classifier — SSN/Luhn-card patterns in values + a curated keyword
set on the concept NAME that excludes every seed HEAD_NOUNS word (so condition/status/amount are never
false-flagged, asserted). Minting: the naming LLM call also returns a semantic `protected?` read; deterministic
OR llm flags → the concept is RECORDED with its sensitivity but BARRED from the vocab (list_minted_heads
excludes it) + not re-homed. Promotion: promote_heads/qualifiers skip + flag a protected concept. Categories:
health/government_id/payment_card/biometric/credentials. **Multidomain re-extracted to v14 (done, `40b09a6`).**
**Remaining (next session):** R6 record_accuracy — **GATED on the owner's billing↔service adjudication fold
decision (A/B/C; Claude rec = C new category); a governed-core change halts for the owner (§4/§10), so it's
the one plan item that needs you.** **✅ COLUMN-LEVEL CONVERGENCE PROOF DONE (`eval/run_column_convergence.py`, real dedup+mint logic, combined
n=216):** measures the COLUMN a reviewer sees (seed-head-used + minted + promoted-qualifier), separating the
bounded seed enumeration (DIAGNOSTIC, declines by construction) from EARNED columns (the real signal). Result:
**31 total columns (28 seed + 3 earned) across 216 mixed-domain cases; earned curve `[0,2,0,1,0,0,0,0,0,0,0]`
PLATEAUS** (0 new earned in the last 140 cases). **Honest framing (comfortable-reframe check applied): the
bucket count ALONE can't distinguish this plateau from noise (random `other` rarely clusters ≥4); what proves
it's real convergence is that the earned columns are SEMANTICALLY coherent — the E2E demo minted a genuine
`regulatory_reference`. So: schema is BOUNDED + SETTLES with a small, REAL emergent layer — NOT that emergence
is rich (3 earned columns is thin; §4's full weight wants a corpus with richer recurring novelty).** This is
the honest §4 gate R0 pointed to, no longer the retracted head-noun tautology.
**✅ R6 DONE (owner chose C — add `record_accuracy`). Category accuracy 59% → 82% (CFPB n=100).** Added the
category + three-way rule (billing=the number / service=conduct / record_accuracy=a held/published record is
wrong→verify/correct/delete) + fraud sub-rule + primary-ask tiebreak to the prompt (v15) and enum. **Full-set
sweep:** all 100 CFPB re-labeled + all 96 multidomain labeled vs the rule (via 2 subagents applying the owner's
verbatim rule; owner's 23 anchors enforced as hard truth + asserted; Claude verified every record_accuracy call
+ 3 flips + read the 18 residual errors). New CFPB gold: record_accuracy 29/billing 25/access 21/service 20.
Old gold + v14 extractions preserved (`*_oldgold.csv`, `*_v14.jsonl`). **FOUR-NUMBER MATRIX (`eval/score_r6_matrix.py`):
old-gold×old-prompt 59% · old-gold×new-prompt 50% · new-gold×old-prompt 49% · new-gold×new-prompt 82%. Neither
change alone helps (both off-diagonals BELOW 59) — only both together → 82% (+53 over the 29% majority baseline);
record_accuracy 29/29 correct; off-diagonal lows prove it's EARNED not relabeled-to-fit.** Residual concentrates
on service_fault (10/20) — service↔record + service↔access; ~5 real errors / ~9 label-noise / ~4 hard → true
ceiling ~88-90% once service↔record settled (owner spot-check list: 24516794, 7452657, 24365881, 24483748).
**GENERALISATION: record_accuracy off finance = 2/96 (2%) vs 29% CFPB → FINANCE-WEIGHTED, real analogues exist
(§4-safe, not a seeded field). Recorded in schema.py taxonomy def.** Determinism PASS (reproducible; note the
"identical" pair is only NEAR-identical). **COMPOSITE CURVE AFTER DEDUP (owner asked for the number): does NOT
bend, dup 7.6% (>5%) — raw [29,26,22,36,32,26]→[29,21,19,35,30,24]; the magnitude drop was HYGIENE not dedup.
~92% of qualifiers are genuinely distinct data → convergence is real at the COLUMN level (bounded 31 + earned
curve plateaus + mints semantically real), NOT the composite level. Stated plainly, not spun.**
**⇒ THE ENTIRE REMEDIATION IS NOW DONE (R0–R7 + head-minting + 2 live demos + column-convergence proof + R6).**
14 migrations; 104 tests +1 skip. Remaining lift is DATA SCALE (a 200+ richer corpus for a stronger emergence
signal + to push category past 82%) and owner spot-check of the service↔record gold — NOT architecture. Next
natural work: settle the service↔record boundary (prompt tighten, re-score), grow the gold/corpus, or move to
Phase 5 (elicitation) now that extraction is at 82% not 60%.

**UPDATE (2026-08-17e, R6 v16 service↔record TIGHTEN done + GOLD-GROWING-TO-~200 in progress at handoff).** `origin/main` @ `e79a32e`.
**v16 (committed `e79a32e`):** tightened service↔record — the model over-fired record_accuracy when an account/credit
was merely MENTIONED; added a prompt discriminator (a record must be alleged WRONG; conduct/withholding/runaround/
cease-and-desist → service EVEN IF an account is named). Result (CFPB n=100, new gold): **service_fault recall
10→13 (+3, the 3 target cases fixed: 7451352, 24483748, 24365881), record_accuracy HELD 29/29, overall 82→82
(FLAT)** — a clean win on the targeted boundary; the offsets (−1 billing/−2 access) are noise/defensible
(24134219 conduct-framed fraud; 24186443 access→delivery unrelated). Kept v16 (owner). Scorers built:
`eval/score_r6_matrix.py` (the 4-number matrix), `score_v15_v16.py` (v15↔v16 per-category), `score_combined.py`
(the ~200 combined). v15/v14 extractions preserved (`cfpb_extractions_v15.jsonl`, `*_v14.jsonl`).
**⇒ GOLD GROWN — CFPB 100→120 DONE (committed `77a6c7c`):** labelled the 20 extra cases (subagent, v16 rule).
**CFPB-120 v16 category accuracy = 96/120 = 80% (majority 26%, +54); record_accuracy 31/31 (perfect on the
expanded set).** New CFPB-120 dist: billing 31 / record 31 / service 30 / access 22 (balanced). Dip 82→80 is the
harder new 20 (10 service_fault), honest not regression. **✅ COMBINED 216-ROW NUMBER DONE (2026-08-17f, `eval/score_combined.py` on v16
multidomain re-extraction):** **CFPB-120 96/120=80% (maj 26%) · multidomain-96 63/96=66% (maj service_fault 40%) ·
pooled-216 159/216=74% (maj 31%).** record_accuracy recall 31/31 CFPB, 0/2 off-finance (finance-weighted, as recorded).
**Harsh read (comfortable-reframe check applied):** category GENERALISES off-finance (+26 over baseline) but MATERIALLY
WEAKER than on the domain it was tuned on (66% vs 80%), and BOTH sit below the §4 ≥90% category gate. The v16 prompt's
billing/service/record/access discriminators are CFPB-shaped; the 9-sector consumer-review classes (product_fault 28 /
service_fault 25 / delivery 14 / safety 11 …) get less lift from that tuning. So the honest cross-domain category number
is **74%**, not the 80% finance headline — off-finance category tuning is the next real lever, alongside data scale.
**Generalisation stands: record_accuracy is finance-weighted (2/96 off finance).** Then: to push category past
82%, more gold + settle service↔access + owner spot-check of the ~9 contestable service↔record rows; OR move to
Phase 5 (elicitation) now extraction is at 82% not 60%. 14 migrations, 104 tests +1 skip, prompt extract-v16.

**UPDATE (2026-08-17b, R7+R3+R1 BUILT/TESTED/COMMITTED + R2 MEASURED — the composite curve does NOT bend; the real moat piece (emergent head-minting from `other`) is still MISSING).** `origin/main` @ `68b961d`.
Executed remediation in dependency order, all verified live (96 tests +1 skip green; NO regression).
**R7 (determinism):** extraction verified reproducible (greedy temp0, 3 identical runs) + hardened with an
Ollama `seed` — idempotent replay is a trust-gate. **R3 (hygiene + escape valve), prompt v13:** reopened
`other` (prefer to force-fitting) → **`other` 0.7% → 11.7%** (R3 target 5–15% HIT); qualifier is a LABEL not
a value + drop fully-redacted (all-XXXX) values (code guard in extractor). Effect: raw composite variants
**275 → 189 (−31%)**, qualifier dup rate **17.3% → 6.9%**, hapax 89%→87%. **NO governed-core regression:**
category 60% (held), outcome 63→65, emotion 71→74, severity 66→64 (re-extraction noise; governed text
unchanged). Retention 0.66→0.52 is legit hygiene (v12 invented junk qualifiers like `company` on org names;
v13 nulls them — 104/105 orgs null, correct). **A REAL emergent cluster surfaced in `other`: legal citations**
(`15 U.S.C. 1692c`, `Fair Debt Collection Practices Act`, `12 CFR 1006.34`; quals `act`/`law`/`regulation`/
`u_s_code`) — a `regulation`/`statute` head trying to be born. **R1 (dedup LIVE, head-scoped):** built +
committed + tested end-to-end — `nearest_canonical_field` head anchor, `list_undeduped_variants`,
`list_promotable_qualifier_variants` (alias-collapsed, pooled support), `dedup_field` head-scoping,
`dedup_registry` (incremental/idempotent), `dedup_scan` module + `queue.dedup_scan` task + `run_worker`
scheduler defers dedup BEFORE promote, `promote_qualifiers` gates on pooled canonical support. Tests: head
anchor (identical vector, different head → NO merge), idempotency, **dedup-prevents-duplicate-promoted-columns**
end-to-end. (Live worker firing not re-verified E2E this session; mirrors the already-proven promote_scan
pattern + unit-tested scan fn.)
**⚠ R2 — THE PIVOTAL FINDING, not spun: even after v13 hygiene + live dedup the composite curve does NOT
bend.** cfpb raw new-composite/bucket `[22,29,30,38,37,18]` → after-dedup `[21,24,28,35,37,17]`, only 12/174
merged. **A 6.9% dup rate means ~93% of qualifiers are genuinely DISTINCT data, not synonym sprawl** — so the
composite (`qualifier_head`) is NOT a convergence unit dedup can bend; qualifiers are DATA and proliferate by
nature (Path A always said so). This is the remediation's explicit checkpoint ("if the curve doesn't bend
after dedup, the concept is wrong") firing: **column-level, not composite-level, is the only honest
convergence unit.** ⟹ **THE REAL MOAT PIECE IS STILL MISSING: minting a NEW head from `other` clusters.**
Today `other` catches novelty (11.7%, the legal cluster) but `promote.py` can only mark the literal head
`other` promoted — it CANNOT cluster `other` facts into a new named head (`regulation`). So R3's own
verification ("confirm ≥1 head promotes from `other`, else §4's central claim fails") WILL FAIL until this is
built. **NEXT BUILD (the masterpiece move): emergent head-minting — cluster `other` (+`description`) facts by
value/qualifier embedding; when a cluster recurs ≥N distinct cases, mint a new governed head, re-extract
history against it (backfill). This is what makes "specialisation is emergent, never seeded" TRUE and
demonstrable — a `regulation` head emerging from CFPB with zero configuration.** Remaining remediation: R4
stats-before-semantics (filters the clausal junk still in `other` like "you are in violation"), R5 PII gate,
R6 record_accuracy category (folds the pending billing↔service adjudication), R7-determinism DONE.
**HEAD-MINTING SPIKE (this session, `eval/spike_head_minting.py`, on real cfpb v13 — premise PROVEN):** embed
`other`/`description` facts (BGE), greedy concept-cluster, mint an LLM-named head when a cluster spans ≥
PROMOTE_HEAD_N distinct cases. Real concepts DO emerge — a credit-report/financial-reference head recurs across
~14 distinct cases → column-level emergence is viable, the moat CAN work. **BUT the decisive blocker: `other`
is polluted with CLAUSES ("you are in violation" ×3, "stress causing stress") + redacted junk that cluster into
GARBAGE heads (`miscellaneous_info`) at every τ tried (0.55/0.63) — tightening just fragments, doesn't clean.**
⟹ **R4 IS THE LYNCHPIN: clean `other` (deterministic clause/junk filter) BEFORE both clean dedup AND clean
head-minting.** REFINED BUILD ORDER (evidence-backed): **R4 (clean the escape valve) → head-minting
architecture (cluster + mint + PER-TENANT grammar extension so the head enum = seed + minted, + backfill
re-extracts history) → the honest column-level convergence proof.** R2 corroborated on multidomain too (other
0→8.3%, dup rate 3.1% — dedup does almost nothing because qualifiers are distinct data, both sets). The one
architectural fork for head-minting (flagged, not assumed): a minted head EXTENDS the live extraction grammar
per-tenant (so future cases emit it directly — the §4 "enters via the promotion path" reading) vs a post-hoc
re-clustering of `other`. Plan = the former.

**UPDATE (2026-08-17, CONVERGENCE PROOF RETRACTED — remediation R0 DONE; R0–R7 is now THE plan; do NOT start Phase 5 until R1–R3).**
Owner + an external repo read (`repo-analysis-remediation.md`, now committed) invalidated the Path-A
convergence proof — **the 6th instance of the cheap-path-that-keeps-a-gate's-letter pattern** ([[comfortable-reframe-trap]],
CLAUDE.md §10). The invalidity, verified live this session (numbers reproduced exactly): the head curve
[15,4,4,1,1,1] is a **closed-31-enum enumeration** (declines by construction, can't fail = not a gate); the
composite curve — the real §4 signal — is **flat + ~90% hapax** (cfpb [46,38,54,45,51,41]/275/89%; multidomain
[70,34,49,41,37]/231/92%), i.e. the pre-Path-A sprawl [48,52,74,64,77,63] just MOVED into the qualifier space,
which is unmeasured + undeduped (`dedup_field`: 0 live callers). Escape valve closed (`other` 0.7%/**0.0%**) →
promotion can't fire → "emergent, never seeded" is 100% seeded; 34% null-qualifier = information loss.
**R0 DONE (this session):** retracted the claim in every site it lived — `run_extraction.py` docstring +
printed gate labels (now: head=diagnostic, composite curve+hapax=THE gate, and the harness now PRINTS the
composite curve/hapax so the gate is shown not asserted), `head_nouns.py`, `dedup.py`, `run_convergence.py`,
and this file (§0 box header + status + `Last updated`). **THE PLAN — remediation `repo-analysis-remediation.md`,
ordered, R1–R3 gate Phase 5:** R1 wire `dedup_field` into the live pipeline **head-scoped on qualifier space**
(embed `f"{qualifier} {head}"`, keep τ=0.85/0.70 + fail-safe; consider an off-hot-path `dedup` stage) — BUT
the 2026-08-16b hazard stands: on the value-polluted slot dedup over-merges DATA (6_weeks↔6_months), so R1
needs R3/R4 hygiene first or a value-guard. R2 replace the gate with **composite-curve-after-dedup + dup-rate
(<5%) + hapax**, invert the head/composite labelling (DONE in run_extraction), run on both sets; if the curve
doesn't bend after dedup **the concept is wrong** — know it before Phase 5. R3 reopen the escape valve in the
prompt (target `other` 5–15%, add a `credit_score_dropped→amount` bad-force-fit negative example, then confirm
≥1 head actually promotes on multidomain — else §4's central claim fails) + fix the 18 null-qualifier `amount`
attrs. R4 statistics-before-semantics (§4.2, deterministic type/cardinality/identifier pass — the published
fix for force-fit, also cuts model calls). R5 PII gate at promotion (§4.5). R6 adopt `record_accuracy` third
category + re-label + re-score (**lowers the score first — that direction IS the correctness check**; verify it
generalises off finance: bakery analogue = membership/loyalty/warranty/service-history). R7 determinism check
(free, during R2): `24483813`≡`24490268` are identical narratives — identical input MUST give identical
extraction or every measurement is void. **Score (external): 4/10** (engineering strong, but a measured-invalid
moat is worse than unmeasured — it gave false confidence 3 phases built on). 6 ← R1–R3 done + composite curve
reported honestly *whatever it shows*; 8 ← the curve actually bends after dedup on data we didn't author. That
single result is product-with-a-moat vs well-engineered ticketing system. `origin/main` @ `<this commit>`.
Adjudication (billing↔service) still PENDING OWNER and folds into R6.

**UPDATE (2026-08-16b, MOAT'S FIRST LIVE RUN — qualifier-space dedup MEASURED; wiring it live is BLOCKED on qualifier hygiene; task 4 now PRECEDES task 3).** `origin/main` @ `6f2ca06`.
Ran the built-but-never-run dedup end-to-end for the first time (`eval/run_qualifier_dedup.py`, head-scoped,
reuses `app/schema/dedup.py`'s BGE + τ gate + `_adjudicate` — not reimplemented) on real data (cfpb 120,
multidomain 96, combined 216). **Confirmed live: dedup is ABSENT from the live flow** — `dedup_field` appears
ONLY in `run_convergence.py`; `stage.py`/`promote.py`/`backfill.py` never call it. **Results (harsh read
first):** (1) mechanism FIRES correctly on true synonyms (`wells_fargo_bank`/`wellsfargo`→`wells_fargo`,
`citibank`→`citi_bank`, `account_was_closed`→`account_closed`, `rejected`→`declined`) and the fail-safe holds
(`bank_of_america`≠`us_bank`, `charged_off`≠`charged`). (2) Raw qualifier dup rate **13.9% combined** (17.3%
cfpb / 7.1% multidomain) — NOT the §4 gate (qualifiers are data, expected to proliferate). (3) The real §4
COLUMN-dup gate is **unmeasurable-grade at n=216**: only **2 qualifiers promote** (support≥8), so 0/2=0% is
NOT reported as a pass (§10 substance-free-pass trap). **Non-obvious win: dedup ENABLED promotion 0→2** by
pooling fragmented synonym support over M=8 — its real value at this n is anti-fragmentation, not
dup-prevention. (4) **BLOCKER — 36% of qualifier variants are leaked VALUES, and dedup over values
OVER-MERGES distinct data even in the hard-merge band:** `6_weeks`→`6_months`, `over_a_month`→`over_a_week`,
`6_inch_wrap`→`12_inch_wrap`, distinct dates collapsed. **⟹ wiring dedup into the live promote flow NOW would
corrupt data — deliberately NOT wired.** The qualifier slot is verbatim-grounded but at VALUE altitude, not
specificity-label altitude — an ALTITUDE problem, not a grounding problem, so "qualifier grounding" (task 4 as
framed) would read misleadingly HIGH; the honest metric is the value-leakage/altitude rate (36% here).
**⇒ RE-SEQUENCED: task 4 (clean the qualifier slot to specificity-labels, kill value-leakage) is now the
PREREQUISITE for task 3 (safe live dedup wiring), not a follow-on.** Also fixed `score.py` crashing on its own
tail (Windows cp1252 can't encode `≤`/`∅` → the confusion matrix never printed); forced UTF-8 stdout — the
matrix now prints and confirms a SECOND error cluster beyond billing↔service: `service_fault→access_availability`
×8 + `billing_charge→access_availability` ×5 (~13 errors on a service/access boundary). Adjudication still
PENDING OWNER (below); added Claude's adversarial per-row read of all 23 as a PROPOSAL in the fixture (owner's
`your call` column untouched) — decisive fork: where do record-accuracy disputes go (billing / service / a new
`record_dispute` category — Claude's rec is the new category, since forcing them into a binary is why the
boundary wobbles; governed-core change = owner call).

**UPDATE (2026-08-16, HONEST CORRECTION — accuracy is FAILING on finance (near baseline), NOT "unproven off finance"; confusion matrix + adjudication PENDING OWNER).**
Owner caught the **5th comfortable reframe** — a standing trap to stop repeating ([[comfortable-reframe-trap]]):
stop framing failures in the direction that feels better. **The real read:** on the 100-case CFPB gold the
governed core scores NEAR the majority-class baseline — **severity 66% vs 62% always-"financial_harm" = +4 =
WORTHLESS; category 60% vs 37% = +23; outcome 63% vs 39%-blank = +24.** §4 gate wants **≥90% category, ≥95%
governed-core** → we're **~30 pts short on the only domain measured.** **CONFUSION MATRIX (owner-demanded,
decisive):** 90% of category errors (36/40) are inside the billing/service/access triad; **57% (23) are the
single `service_fault`↔`billing_charge` pair** the owner wobbled on (19 gold=service→model=billing, 4
reverse); only 4 scatter. ⟹ CONCENTRATED = a taxonomy-DEFINITION problem (cheap branch), NOT prompt-scatter;
clean classes (product/delivery/staff/safety) near-perfect. **⇒ ADJUDICATION PENDING OWNER:**
`eval/fixtures/billing_vs_service_adjudication.md` (23 rows + proposed decision rule + a "your call" column).
Some of the 19 are **LABEL NOISE not model error** — the credit-report-inaccuracy cluster (7448709 · 7450437
· 7450993 · 7451012 · 7452822 · 7452911) is `billing_charge`=reporting-problem under the proposed rule →
MODEL right / gold wrong. **DO NOT tune the prompt until the boundary is adjudicated (tune to TRUTH, not noisy
labels).** Sequence: owner fills "your call" → update `cfpb_labels.csv` → re-score for the TRUE baseline →
encode the rule in the category prompt ONLY if real errors remain → then wire dedup live + measure the dup
rate. **PHASE-4 REFRAME (owner-ranked by cost-of-delay): DO NOT START PHASE 5** (5–9 consume extraction
output; building elicitation/confidence on a 60% classifier = rebuild). Ranked gaps: **(1+4) dedup is
built+unit-tested but NEVER RUN LIVE + the duplicate rate is NEVER MEASURED = the moat has never executed
end-to-end [TOP]**; (2) stats-before-semantics profiling = the published fix for the hallucination mode we're
exposed to (may be why grounding is softer than 0.941 implies); (3) PII gate = low urgency, unbounded
liability. **Owner's MISSING-gaps (verified this session):** head-noun list is CLOSED → dedup HAS a merge
anchor ✓; backfill=re-extraction is implemented+unit-tested+cost-measured but **100%-on-real-history NOT
measured E2E**; cost/case IS measured ($0 local ~6s, backfill fan-out ~46min); **qualifier-grounding NOT
separately measured** — the 0.969 is VALUE-only; the qualifier is a 2nd invention site (guarded by
extractive-null, but unmetered). `origin/main` @ `c6fd79e`.

**UPDATE (2026-08-16, MULTI-DOMAIN SET STOOD UP — the taxonomy was STARVED, not weak; + Phase-4 reframe).**
Owner: "why is everything financial?!" — because the whole eval was CFPB (financial-only by
construction). Built a real, non-authored, multi-sector set (§10-Q3): **`eval/fetch_multidomain.py`** →
96 cases across **9 sectors** — NHTSA vehicle complaints (US-gov public domain, product/safety) +
Trustpilot (`Kerassy/trustpilot-reviews-123k`, **MIT**, filter stars≤2) across electronics, retail,
restaurants, travel, utilities, home services, health, legal/government. (Rejected: gov service APIs =
no prose; Twitter/support corpora = non-commercial; Yelp = restrictive.) Harness made **dataset-agnostic**
(`eval/_dataset.py` + `EVAL_DATASET=multidomain`); blind label sheet `multidomain_labels.csv` (96 rows)
PENDING OWNER LABELS for the first non-financial ACCURACY numbers. **STRUCTURAL RESULT (v12, no labels
needed) — the reveal:** the universal taxonomy SPREADS across every class on real product+service data —
**product_fault 3→32, service_fault 21→29, delivery_fulfilment 1→13, safety_health 1→7, staff_conduct
2→4, billing_charge 53→3**; severity now fires on SAFETY (safety_health 1→10), not just financial. The
self-converging schema **CONVERGED on a brand-new domain** (new-head `[15,3,2,3,0]`, 23 bounded heads,
json 100%, grounding 0.969). ⟹ the category/severity "weakness" was CFPB starving the taxonomy, NOT a
taxonomy flaw — validates the §4 domain-agnostic claim. Shape note: desired_outcome 90/96 null (reviews
VENT, don't ASK — refuse-to-guess correctly abstains; a real intake channel prompts for the outcome).
**PHASE-4 REFRAME (owner: "stuck in Phase 4 for ages"):** the exit gate is about MECHANISMS (extract →
merge → promote → backfill → converge → no-hallucination) — 4/5 DONE + proven. The endless-feeling part
was open-ended ACCURACY tuning (v6→v12), which the gate never asked for and is really Phase-6
calibration. **Remaining true Phase-4 gaps:** (1) BGE-M3 synonym-merge dedup is built+unit-tested but NOT
WIRED into the live flow (post-Path-A → reframe to qualifier-space under a head); (2) stats-before-
semantics profiling (4.2) never built; (3) light PII gate at promotion (4.5) never built; (4) the <5%-dup
half of the convergence gate never explicitly measured; (5) accuracy is finance-only until the
multi-domain set is labeled. **Plan: close Phase 4 on mechanisms (wire dedup, PII gate, <5%-dup metric,
profiler build-or-log-defer), move accuracy to Phase 6.** `origin/main` push pending.

**UPDATE (2026-08-16, ACCURACY — outcome value-side 51→63 (v11) + org capture 41→98% (v12); both probe-first, not blind-tuned).**
Two grounded fixes, each diagnosed on the real data BEFORE touching the prompt (§10). **LEVER: outcome
wrong-VALUE (v11).** Probe of the 32 gold=value/model=wrong cases → **21/32 (66%) were `refund`
over-firing** in the credit/debt domain: the model mapped "correct my credit report" (→ should be
repair_redo, 10 cases), "validate this debt" (→ information, 6), and account-closure/other (5) all onto
refund. Fix: sharpen the three value defs — refund = MONEY returned; repair_redo = fix/remove/update an
inaccurate record; information = validate/prove/documentation — framed universally (a bakery has
"fix my order" vs "refund" too), NOT a domain seed. Result: outcome **51→63%** (+12), gold=value matched
**24→30/61**, refund dist **61→35**, repair_redo **1→12**, information **3→8**; null-invention even
IMPROVED **12→6/39**. **LEVER: org capture (v12).** Probe: of 51 org key-facts, 0 redacted, 30 were
names IN the text (Wells Fargo, Truist, USAA…) the model put only in `fault`, never as a structured
`organization` attr. Fix: one line in the emergent section — "ALWAYS capture the named organization…".
Result: org capture **21/51 → 50/51 (98%)**, `organization` head 42→136, key-fact recall **22→24%**,
grounded 0.980. **HELD:** category 59→60, convergence declining `[15,4,4,1,1,1]`/26 heads (closed vocab),
json 100%, determinism verified. **REGRESSION (flagged, NOT chased): severity 71→66 (−5).** Diagnosed:
6 lost / 2 gained; **4/6 losses are "remove inaccurate credit-report entry" cases where the severity def
("damaged credit = financial_harm") makes v12 arguably MORE correct than gold=none** — a gold-vs-def
boundary disagreement, not degradation; 2 are real misses (funds-denied). Per §10 I did NOT narrow the
owner-tuned severity def to chase debatable gold (fix system to metric, not metric to system); per the
motto (big outcome+org wins) shipped it and flagged for owner — **the 4 credit-inaccuracy gold labels may
warrant review (is an inaccurate late-mark `financial_harm` or `none`?).** **Harness hardening:**
`run_extraction.py` now retries-once-then-records-empty on `httpx.ReadTimeout` (intermittent GPU/Ollama
stalls under sustained batch load blew 2 cases mid-run — both extract fine in 8–15s in isolation, so it's
environmental, not case-pathological; the 2 were re-extracted with retries and patched in). Dev set, not
the ship gate. Pushed `origin/main` @ `1083274`.

**UPDATE (2026-08-15, THE WORKER IS STOOD UP — the queue now FIRES autonomously in the compose stack).**
Closes the last 4.7 "not built" gap. The moat runs end-to-end with NO manual trigger: ingest → worker
`normalise.done` → chained → worker `extract.done` (governed+emergent via Ollama) → readable via the API.
**The hard part was a Procrastinate sync/async connector conflict** (this is WHY the worker was never
stood up): the worker CLI needs an ASYNC connector to listen/fetch/run-periodic, but every DEFER we do is
SYNCHRONOUS — transactional in the engine, AND inside each worker task body (which does `asyncio.run(...)`
then enqueues the next stage). Findings, in order: (1) a sync-connector app crashes the worker on the
periodic deferrer (`SyncConnectorConfigurationError`); (2) an async-connector app crashes the in-task
transactional defer (`get_sync_connector()`→`AsyncToSync` deadlocks on the worker task's own event loop);
(3) `with_connector` is DEPRECATED and leaves the periodic bound to the wrong connector. **Solution:**
`app` stays SYNC (native psycopg — the only thing that defers cleanly in BOTH the engine and a worker task
thread); `worker_app = app.with_connector(PsycopgConnector)` is an async twin the worker PROCESS runs
(with_connector's task→app link, deprecated in general, is exactly what we want here — task-body `.defer()`
stays native-sync); `@app.periodic` is REMOVED (the twin can't run procrastinate's periodic deferrer) and
replaced by a scheduler loop in the entrypoint. New `scripts/run_worker.py` opens the sync `app` (so
no-connection defers like the backfill re-enqueue have a live pool) + runs the async worker on `worker_app`
+ (`--schedule`) defers promote-scan on a 30-min loop; a Windows-only `WindowsSelectorEventLoopPolicy`
guard (psycopg async can't use ProactorEventLoop; no-op on the Linux container). **Compose:** two worker
services — `worker` (queue=default, intake + promote-scan) and `worker-backfill` (queue=backfill, isolated
so a long re-extraction drain never starves intake) — both reaching the host's Ollama (the 4070, $0) via
`host.docker.internal`. **VERIFIED LIVE TWICE:** on the host, then in the FULL CONTAINER STACK — a fresh
CFPB case ingested, the containerised worker ran normalise+extract on its own (Ollama over
host.docker.internal, `extract-v10`), case served by the container engine; a null-outcome case correctly
stayed `desired_outcome=null` (refuse-to-guess end-to-end). Workers stable (no crash loop), 94 tests +1
skip green. **Still deferred (smaller):** the review UI reading the `promoted` flag; per-field span
locators; real auth; graceful-shutdown tuning + a worker healthcheck. Pushed `origin/main` @ `5cd319a`.

**UPDATE (2026-08-15, PHASE 4.7 DONE — extract wired into the queue + the review view, verified live on real pixels).**
The moat now runs end-to-end with no manual trigger AND is reviewable. Built + verified:
- **Chain intake→normalise→EXTRACT.** New `pipeline.extract` queue task (`queue.extract_case_task`); `normalise_
  source_document` transactionally enqueues it on the SAME txn that completes normalisation (mirrors intake→
  normalise: commit → durably queued, rollback → nothing). Multi-doc cases collapse to "last text wins" via
  extract's stage-ledger idempotency; a redundant mid-burst extract is an accepted PoC cost (scale path = a
  per-case queueing-lock). **Latent bug fixed while wiring:** the extract idempotency key used `prompt_version=""`,
  so a prompt bump (v8→v10) would NOT re-extract already-done cases — the §3/§4 "a better prompt re-runs history"
  guarantee was silently holed. Now keyed on `PROMPT_VERSION` (importable constant).
- **Review read model + routes.** `store/api.get_case_review` (governed core + emergent split into Path-A
  head/qualifier + confidence + provenance citations + prev→new correction diff + normalised text + source docs)
  and `list_cases` (register summary). `/api/cases` + `/api/cases/{id}` (FastAPI router, `X-Tenant-Id` header =
  PoC tenant convention, RLS is the real boundary), test-overridable session factory. **Tenant isolation proven
  by an automated test** (tenant B → 404 on tenant A's case, register empty) — the trust gate holds through the
  new HTTP surface.
- **The review UI** (`ui/`, was a bare scaffold): dependency-free React (no new npm/licence surface), Vite `/api`
  dev-proxy (no CORS), `?tenant=&case=` deep-links. Governed-core cards (a null field renders an explicit
  **"not stated"** refuse-to-guess card — the visible face of the lever-(a) fix), emergent table, click-to-trace
  provenance aside, source-text panel, raw-JSON toggle, responsive (mobile breakpoint).
- **VERIFIED LIVE (not a source audit):** migrated the stale live DB 0008→0010 (Path-A `head` col was missing),
  seeded 3 real CFPB cases through the full local $0 pipeline (Ollama), ran the engine+Vite, `nabu-ui-test` on real
  pixels desktop+mobile → 0 console/page/network errors, no overflow; the null-outcome case renders "not stated".
  Fixed 2 layout bugs found in the pixels (governed-card dead-space; broken mobile — both re-shot green).
- **Numbers: 94 backend tests +1 skip (was 90; +4 review/isolation/chain tests), 10 migrations, ruff/black/mypy
  --strict clean; UI tsc + vitest green.** Trust spine (RLS/provenance/idempotency/no-PII) re-ran green.
  **Still not built (honest, deferred):** ~~a real long-running worker + scheduler in compose~~ — **DONE, see the
  top 2026-08-15 worker UPDATE** (the queue now fires autonomously in the container stack); the review UI reading
  the `promoted` flag; per-field span locators (provenance is whole-source at PoC); real auth (header is the PoC seam).
  Pushed `origin/main` @ `f312f07`.

**UPDATE (2026-08-15, LEVER (a) SHIPPED — desired_outcome refuse-to-guess fix (v10); null-invention 27→12).**
Diagnosed on real data BEFORE tuning (§10): the model INVENTED an outcome from the grievance TYPE
(monetary→refund, "filing a complaint"→escalation, misc→other), not from a stated request. Clean
separating signal on n=100: an explicit-request phrase appears in **4% (1/27)** of the invented-null
cases vs **55%+ (16/29)** of the true-positive value cases → systematic over-inference, NOT the
earlier n=24 "ambiguity-bound noise" worry. Fix (prompt **v10**, PROMPT_VERSION bumped): lead
desired_outcome with an ABSTENTION GATE — require a STATED remedy; "a money grievance is not a refund
request; filing a complaint is not escalation"; absence→null. **Value defs UNCHANGED** (owner: "not a
def tweak" — the prior escalation-def tweak footgunned). v9 first attempt worked but the verbose,
domain-noun-heavy block bled into category; v10 stripped the domain nouns (leaner, principle-first) —
proved the bleed is the gate's CONTENT not its verbosity (v9≡v10 on category). **Clean before→after
(same scorer, temp-0 deterministic):** null-invention **27/39→12/39** (escalation over-fire 42→4
corpus-wide), desired_outcome **41→51%**, severity 70→71, emotion 70→73, key-fact 21→22; convergence
held (plateau/23 heads), grounding 0.966→0.983, json 100%. **COST: category 65→59% (−6).** Investigated
(read all 7 flips): ALL on the known service_fault↔billing↔access seam; ≥2 are credit-REPORTING cases
where v10's `billing_charge` is arguably BETTER than gold (def includes "reporting problem") → fragile-
boundary NOISE on a weak validator (top-2 still 74%, 4 classes ≤2 gold), not a capability drop. Mechanism:
the abstention gate makes the model read a case as "just a grievance" (surface topic→billing/access)
rather than "company mishandled it" (service_fault). **OWNER DECISION (logged, §10): "do what serves the
motto and vision" → SHIP v10.** Rationale: null-invention is nameable confident-wrongness (§2/§3 TRUST
gate — "confident wrongness destroys trust permanently"); the category loss is coin-flip boundary cases
a stranger can't name wrong; decoupling category into a 2nd LLM call to hold both was REJECTED as
over-engineering against the sub-60s/$0 vision for boundary noise. **90 tests +1 skip green; ruff/black/
mypy --strict clean.** **LEVER (b) key-fact recall DIAGNOSED (largely a metric-scope artifact):** the
soft matcher searched ONLY the emergent-table VALUES; ~half the human "key facts" are PROCESS facts
("refund reversed", "bank acknowledged error") + the counterparty name that by DESIGN land in the
`fault` sentence, not the value table. Added a DIAGNOSTIC-ONLY "case recall (table+fault)" line to
score.py (primary 22% UNCHANGED, §10 refined-metric rule) → **case recall 49%** (org capture 19/50→34/50
with fault counted). Real residual: model still under-captures bank/organization ~30% even counting
fault — a genuine but smaller gap than 22% implied. **LEVER (c) taxonomy fork — SETTLED (motto/§4):**
NO finance category branch (would violate §4 "never seeded" + trip the §8 "touch config to make a case
work" red flag). CFPB stays a STRESS-TEST validator (65%→59% both ≫37% baseline); finance specificity
lives in the EMERGENT layer (heads/qualifiers) + fault + promotion, never the governed enum. Caveat:
don't over-tune category on CFPB (weak validator); the real category proof needs a mixed-domain gold set
later. Pushed `origin/main` @ `7d540ff`.

**UPDATE (2026-08-15, 100-CASE GOLD SCORED + planted-probe checks — new insight: outcome INVENTS nulls).**
All 100 labelled (25/product; owner). Scores: **category 65%** (vs **37% majority-class baseline** — real
signal, but top-2 hold 74% + 4 classes have ≤2 gold = unmeasurable; CFPB is a weak taxonomy validator —
service_fault bleeds into billing/access), **severity 70%**, **emotion 70%** (NOT a gate — subjective),
**desired_outcome 41%**, key-fact recall 21% (soft; biggest gap). **KEY NEW INSIGHT the bigger set
revealed:** desired_outcome's real problem isn't just boundary ambiguity — it's that the model **INVENTS
an outcome 27/39 times when the customer stated none** (gold=null → model non-null): a **§2 refuse-to-guess
failure**, and the clearest actionable lever (make it return null more, not a better def). gold=value only
29/61 (48%). Scoring policy (owner): desired_outcome blank = "correctly null" (scored, not skipped) — baked
into `score.py`; category majority-baseline added. **Planted-probe checks (`eval/gold_checks.py`):** (1)
safety_health 1/2 — 24507863 MISSED (read severity off the financial dispute, not the underlying biohazard;
confirms owner's counterparty-vs-narrative concern); (2) UNCLEAR row 24513554 (pure redaction) **PASS** —
model=UNCLEAR + 0 invented facts (abstention works); (3) the "identical" IC System triplet is NOT
byte-identical (390/386/375) so differing extractions ≠ instability — true determinism verified separately
(same narrative ×2 → identical). **OWNER DESIGN FORK (taxonomy):** finance branch (violates §4
"never seeded") vs CFPB-as-stress-test-only → let finance categories EMERGE via promotion (§4-consistent,
recommended). Dev set, not the ship gate. `origin/main` push pending.

**UPDATE (2026-08-15, PROBED outcome + severity — severity 55→82 fixed, outcome NOT prompt-fixable).**
Same method as category (`eval/governed_probe.py` + confusion-first). **SEVERITY = a real prompt bug,
FIXED:** shipped def too narrow ("a disputed charge/overcharge") → systematic UNDER-call
(gold=financial_harm→model=none ×12); broadened to monetary-harm-of-any-kind (debt wrongly reported,
damaged credit, frozen funds, denied refund). Probe 60→82; held end-to-end **55→82%** (v8). KEPT.
**DESIRED_OUTCOME = NOT cleanly prompt-fixable:** scattered boundary ambiguity (escalation/refund/
acknowledgement/repair_redo). Probe's sharper defs got 58→67 ISOLATED but did NOT generalise — ported
full-corpus it stayed 58 AND caused an **escalation over-fire (57/120) via a domain footgun** ("complaint
to a higher authority" — every CFPB complaint IS filed to an authority). Reverted (v8). Outcome bounces
**50–62% on n=24 even with UNCHANGED wording** (prompt-context noise) → ambiguity-bound + n too small;
NOT tuned further (overfitting a noisy signal). **Final v8 vs 40 gold: category 70, severity 82, outcome
50 (noise band), emotion 78, key-fact recall 26.** Convergence held `[14,5,4,0,1,0]`/24 heads, grounding
0.966. Lessons: (1) the probe (isolated, 1 field) OVERSTATES fixability — always confirm end-to-end +
watch the DISTRIBUTION, not just gold-N accuracy (n=24 outcome accuracy is noise; the escalation over-fire
was the reliable signal). (2) outcome needs MORE gold (≥100) to measure at all, and is likely
ambiguity-bound (may need confidence+abstain, not a better def). `origin/main` push pending.

**UPDATE (2026-08-15, FIRST ACCURACY NUMBERS + category 8%→68% fix; a wrong earlier read CORRECTED).**
Owner filled the 40-case gold sheet → the first CORRECTNESS measurement (everything before was
structural). Shipped-prompt (v5) scores: **category 8%**, desired_outcome 62%, severity 55%, emotion
78%, key-fact recall 27% (soft). Category was a near-total failure — model blanket-abstained to UNCLEAR.
**Isolating probe (`eval/category_probe.py`, same least-bad-fit policy + one-line definitions, scored vs
human gold) → 65%**, proving the 8% was a PROMPT BUG (the shipped prompt listed the category enum with
NO definitions and told the model to abstain), NOT a taxonomy/capability failure. **⟹ CORRECTION to the
record: my earlier "seeded taxonomy near-useless on financial domain / model correctly abstains"
(2026-08-14 real-data-test block) was WRONG — an over-charitable reading of a prompt bug. The universal
taxonomy is fine; the prompt was starving it.** Fixed in prompt.py (v6: definitions + least-bad-fit),
re-extracted + re-scored: **category 8%→68%** (UNCLEAR 117→1; residual = legit boundary ambiguity
service_fault↔billing_charge↔access_availability), severity 55→60, emotion 78→82, outcome 62→58 (noise,
n=24), key-fact recall 27→30. Consistent with refuse-to-guess §2 (classifying a debt as billing_charge
is correct, not a guess; UNCLEAR kept for sparse). Convergence held `[15,5,4,0,0,0]`/24 heads, grounding
0.974; **qualifier retention drifted 0.727→0.648** across the longer prompt (WATCH, not a gate issue).
**The accuracy LOOP now works (label→score→fix→re-score, proven by 8→68).** Still middling / open:
outcome 58% + severity 60% need their own probes; **key-fact recall ~30% is the biggest open gap** (the
emergent layer misses much of what the human flags — though the soft value-token matcher may undercount;
needs a qualitative look before concluding). `origin/main` push pending.

**UPDATE (2026-08-15, ACCURACY HARNESS built + BACKFILL COST measured — the plan's solo parts).**
Everything proven so far is STRUCTURAL; accuracy (is the governed core CORRECT) is the first unproven
front. Built (no owner labels needed): **`eval/make_label_sheet.py`** → a BLIND 40-case sheet
(`fixtures/cfpb_labels.csv`, 10/product, model predictions withheld to avoid anchoring) +
`cfpb_labels_INSTRUCTIONS.md`; **`eval/score.py`** → governed-core exact-match accuracy + category
confusion (is UNCLEAR right?) + soft key-fact recall. Scorer VERIFIED on crafted labels (1 match/1
mismatch → 50%, confusion already shows the expected `gold=billing_charge → model=UNCLEAR`
over-abstention). **⇒ PENDING OWNER: fill `cfpb_labels.csv`, then `uv run python eval/score.py` → the
first correctness number.** **Backfill cost (`eval/measure_backfill_cost.py`, unit measured live +
fan-out from the real 120-case corpus):** unit **1.9s/call** (252/27 tok); **15 heads** would promote
(support≥4); naive fan-out **1764 calls ≈ 55 min GPU** (optimized skip-already-attested 1462 ≈ 46 min);
tokens ~0.49M; **$0** (local qwen3 — the spike is WALL-CLOCK + GPU, not dollars), linear in
corpus×concepts. Two findings: (1) **category scoping barely narrows** (every head scans ~all 120 —
116/120 are UNCLEAR, the weak-governed-taxonomy problem again); (2) **backfilling a promoted HEAD on a
same-prompt corpus finds ~nothing net-new** — backfill earns its cost on QUALIFIER-variant promotion +
prompt evolution, so a cost-control gate should fire there, not on every head promotion (recommended
follow-on, NOT built). `origin/main` push pending.

**UPDATE (2026-08-14, STAGE 6 — PROMOTION WIRED END-TO-END; backfill RE-EXTRACTS history, the moat).**
Owner correction (the 3rd goalpost-relaxing fork — logged as a standing rule in `CLAUDE.md` §10: *"when a
gate can be satisfied two ways, distrust the one that costs nothing"*). My proposed "backfill = re-run
`rebuild_field_current`" was REJECTED: re-projection only reads back already-extracted values; it finds
nothing in the cases where the concept was never extracted *because the extractor wasn't looking for it
then* — the only cases that matter. §4's claim is **re-EXTRACTION against the retained originals**, which
is why originals are kept forever and is the thing no incumbent does. Built it that way:
- **Storage = flag + projection** (promoted flag; `field_current` already projects) — NO immutable-log
  rewrite, NO physical columns.
- **Backfill = re-extraction**, scoped tightly (biggest cost spike): `app/extract/concept_extract.py`
  (targeted single-concept prompt, same grounding gates as forward) + `app/schema/backfill.py`
  (re-extract ONE concept across cases IN THE CONCEPT'S CATEGORY, oldest-first, bounded batches; found →
  new `field_extraction` rows w/ FRESH citations, log stays append-only; **metered per case**; each case
  its own txn; re-enqueues next batch). **Migration `0010` `backfill_attempt`** — per-(case,concept)
  `found|absent` marker; the `absent` marker is what makes it idempotent (never re-extract-forever);
  deterministic uuid5 run_id makes crash-retry writes idempotent too.
- **Trigger = PERIODIC, not per-case** (owner): `app/schema/promote_scan.py` + `queue.promote_scan`
  (`@app.periodic` 30m). `promote()` now returns `PromotedConcept(is_new=…)`; only newly-promoted concepts
  enqueue backfill, **transactionally** with the promotion mark. `queue.backfill` body runs a batch +
  re-enqueues while cases remain (low-priority queue, never blocks intake).
**Tests +7 → 90 passed + 1 skipped**; ruff/black/mypy --strict clean. `origin/main` push pending.
**Still not built (honest):** the review UI reading the `promoted` flag; extract-as-a-queue-task (4.7);
qualifier-space dedup before qualifier-promotion; a real long-running worker + periodic scheduler in the
compose stack (the periodic task is DEFINED and its logic tested, but firing it needs the worker running).

**UPDATE (2026-08-14, v5 — TIGHTENED HEAD GUIDANCE; `description` dumping cut 72%).** Owner follow-on.
Root cause in the v4 fixture: `description` was the model DUMPING whole narrative sentences (verbatim,
so they passed the extractive check). Fix: prompt v5 (choose the MOST SPECIFIC head; `description`/
`other` last-resort only, never a sentence; each attr = ONE concrete value; "prefer FEWER, cleaner
facts") + a code cap `_MAX_QUALIFIER_TOKENS=4` (a longer verbatim qualifier is a dumped clause → nulled;
enforces the prompt's "1-3 words" in code, §3 discipline). **Re-measured (120-case CFPB):** description
**165 (21%) → 46 (11%)**; total attrs kept 774 → 425 (stopped over-extracting narrative); grounding
(value) **0.984** (> 0.941); qualifier retention 0.727 (down from v4's INFLATED 0.937 — that had counted
sentence-qualifiers; SPECIFIC heads stay well-qualified: amount 72/89, date 36/44, identifier 38/42 —
only catch-alls barer, correct); convergence `[14,5,3,1,1,0]`, 24 bounded heads (holds, cleaner);
json_valid 100%; latency p50 5.9s. **Residual (honest):** description still catches ~46 clausal VALUES
(only the qualifier slot is length-capped) — reduced, not eliminated; value-capping is beyond the ask +
risks dropping legit facts. `origin/main` push pending.

**UPDATE (2026-08-14, v4 — STRICTLY-EXTRACTIVE QUALIFIERS; grounding re-measured 0.941→0.989).** Owner
follow-on. The qualifier must now be a VERBATIM contiguous span of the source (`extractor._is_extractive`
+ prompt v4 "copy a contiguous phrase or use null"). Asymmetric slot handling (still independent per
constraint #3): the VALUE gates the attribute (overlap grounding), a non-extractive QUALIFIER is NULLED
(not allowed to nuke a grounded value) — fixing the v3 over-drop. **Re-measured on the real 120-case
CFPB baseline:** grounding(value) **0.989** (UP from pre-Path-A 0.941; the v3 "0.822 combined" was a
conflated value+qualifier metric, not comparable); **qualifier retention 0.937** (725/774 kept attrs
keep a verbatim qualifier — strict extraction did NOT gut specificity); attrs kept 774/783 (99%); column
convergence still holds `[15,7,3,1,0,2]`, 28 bounded heads; json_valid 100%; latency p50 7.2s. **Watch:**
the `description` catch-all grew to 165/774 (21%) — not a gate issue (bounded column, verbatim qualifiers
carry structure) but low-information; candidate for later head-guidance tightening. `origin/main` push
pending. Follow-on #1 (qualifier extractiveness) in the box below is now DONE.

**UPDATE (2026-08-14, PATH A BUILT + PROVEN — the column schema CONVERGES on real data).** Built the
closed-head + open-qualifier extraction contract and re-extracted the real 120-case CFPB baseline
(qwen3:14b, $0). **The convergence gate PASSES at the column level:** new-column(head)/20-bucket =
**[20, 6, 2, 1, 0, 0]** — zero new columns in the last 40 cases (pre-Path-A was flat
[48,52,74,64,77,63]); **29 distinct heads** (bounded by the closed vocab, ~0% synonym columns); 484
composite qualifier-names (qualifiers proliferate as DATA — *not* the gate). json_valid **100%**;
dual-slot grounding **0.822** (value+qualifier, STRICTER by constraint #3 — the honest re-measure;
0.941 did NOT carry over; ungrounded candidates dropped = safe); latency p50 **6.7s** (up from 4.4s —
longer structured prompt, still ≪60s). **Honest caveat:** convergence is by BOUNDED-VOCAB +
qualifier-offloading (as directed), not free-invention magically converging — it structurally cannot
sprawl; specialisation still emerges only via promotion. **What shipped:** `app/extract/head_nouns.py`
(31 universal primitives + `other` escape); `{head(enum), qualifier(open), value}` schema; extractor
grounds BOTH free-text slots independently; migration **0009** (`emergent_field.head` + `emergent_head`
registry, RLS'd); **two-dimensional promotion** (`app/schema/promote.py`): HEAD promotes at N=4 → a
column, a QUALIFIER splits into its own variant column only at the strictly-harder M=8 AND under an
already-promoted head (head-first invariant holds by construction since head-support ≥ qualifier-
support). `run_extraction.py` is now the Path-A convergence proof; `run_convergence.py` repointed to the
preserved pre-Path-A baseline (`cfpb_extractions_prePathA.jsonl`). **81 passed + 1 skipped**; ruff/black/
mypy --strict clean. `origin/main` @ `a957b9e` (pushed). **Open follow-ons (quality, not gate):**
(a) qualifiers run long / over-drop legit info (e.g. an org dropped on a bad qualifier) → tighten
qualifier extraction to be strictly extractive; (b) `description` head is a catch-all (62 uses) — watch
it doesn't become a dumping ground; (c) qualifier-space dedup before qualifier-promotion is where the
reframed BGE+adjudicator RELOCATES (not yet wired); (d) governed `category` still 117/120 UNCLEAR on
financial data (seeded taxonomy weak far from retail — model correctly abstains); (e) backfill on
promotion (STAGE 6) still pending.

**UPDATE (2026-08-14, DECISION — owner) — Path A chosen; Path B (redefine the metric) REJECTED as
self-grading; new standing rule added.** Owner call on the convergence-root-cause fork: build **Path A
(constrain extraction granularity)**, NOT Path B (measure convergence at head-noun altitude). Reason,
in the owner's words: "You noticed the convergence curve wasn't converging, and the tempting move was
to redefine convergence. Don't. Section 4 of the winning condition exists precisely so this moment has
a pre-committed answer." **The full-field-NAME curve stays the gate; the head-noun/concept curve is a
DIAGNOSTIC only** (labelled as such in `run_convergence.py`, and now in code). New standing rule in
`CLAUDE.md` §10: *any proposal to redefine a winning-condition metric halts for an explicit owner
decision, logged* — because this is the 2nd fork where the shortcut was to move a threshold, and the
pattern is easier to catch as a rule than case-by-case. **Path A design constraints the owner set (bake
these in):** (1) the **head noun comes from a CLOSED list** (enforced in code via the schema enum, not
left to the model), extended only by promotion; **qualifiers stay OPEN** — keeps closed-world grounding
on the part that matters and lets the head vocab converge while qualifiers proliferate. (2) **Promotion
is now two-dimensional with asymmetric thresholds:** promoting a HEAD creates a column; promoting a
QUALIFIER *splits* an existing column into variants (a schema change with backfill implications), so
qualifier-promotion is STRICTLY HARDER than head-promotion **and requires the head to be promoted
first** (no orphan-qualifier column). (3) **Grounding must be RE-MEASURED on the qualifier slot
independently** — it's a second free-text slot = a second place to hallucinate; closed-world grounding
applies to both slots, and the 0.941 number does NOT carry over unproven. **Assumption I'm proceeding
under (flagging per §4):** "seeded per category" is implemented as a single UNIVERSAL head-noun seed
available to every (universal) governed category — domain-agnostic primitives (amount/date/status/…),
NOT industry fields — to stay consistent with §4 "no industry-specific field is ever configured;
specialisation is emergent, never seeded." Per-category seed *subsets* remain a trivial future
refinement. Say so if you meant literal per-category seed lists.

**UPDATE (2026-08-14, later) — ROOT CAUSE: the convergence "failure" is a MEASUREMENT ALTITUDE +
EXTRACTION-GRANULARITY problem, not a dedup-tuning problem (supersedes the "tune the adjudicator"
framing).** Ran lever #1 (reframe `_adjudicate` "same attribute?" → "same DB COLUMN?", + example-value
plumbing) and re-ran the proof on the frozen fixture (no re-extraction). Result: `378 → 291` (was 303),
reduction 20%→23%, `llm_merge 12→24`, `llm_admit 217→201`. The reframe DOUBLED merges but is nowhere
near enough — so I went deeper (adversarial, §10) and the picture flipped:
- **Geometry is SOUND** (`eval/diag_pairs.py`): BGE puts real synonyms in the gray band
  (amount|charged_amount **0.829**, account_status|payment_status 0.821) and correctly rejects the
  non-synonym control (account_number|account_status 0.798→"different"). Bottleneck = adjudicator
  JUDGEMENT, not embedding/τ.
- **Example values are a DEAD lever** (`eval/probe_values.py`): feeding both sides real dollar values
  flips NOTHING (amount|charged_amount stays "different"). This SAVED a 12-min re-extraction to capture
  values — the fixture only stored field names, and values would not have helped anyway.
- **The flat curve is driven by a HAPAX TAIL, not synonym sprawl:** **340/378 (90%) of raw fields appear
  exactly ONCE** — hyper-specific `{qualifier}_{headnoun}` compounds (`pension_amount`, `deposit_date_2`,
  `overdrawn_amount_after_deposit`). These are NOT synonyms; collapsing them (e.g. all `*_date`) is the
  lossy over-merge §3 forbids. Deterministic token-normalisation catches only ~13 true variants (3%).
- **DECISIVE — the concept space DOES converge:** new-full-NAME/bucket `[48,52,74,64,77,63]` is flat,
  but new-HEAD-NOUN/bucket **`[37,26,37,25,22,18]` HALVES**. 165 head-nouns vs 378 names. The moat works
  at concept altitude; the convergence METRIC (raw field-NAME count) is one level too fine, and dedup
  already did all it honestly can (378→291).
**⇒ Two paths, owner-decision (a moat-core design fork): Path A (real fix) = constrain the EXTRACTOR to
canonical head-noun field + qualifier slot, killing the hapax tail at source (re-extraction + re-eval
grounding/refuse-to-guess); Path B = fix the metric to measure at concept granularity.** Both are in
the SESSION HANDOFF box. Committed `5789623` (reframe + `run_convergence.py` concept curve + the two
diagnostics) + docs `283a4e3`; pushed. 79+1skip green.

**UPDATE (2026-08-14) — CONVERGENCE PROOF: NEGATIVE RESULT (the moat did NOT converge on real data).**
4.3 dedup (BGE-M3 + pgvector + τ=0.85/0.70 + gray-band LLM) is BUILT + unit-correct (2 tests), but run
over the real 120-case CFPB baseline it **did not self-converge**: raw 378 → **303 canonical (only 20%
reduction)**; new-canonical/20 = **[46,43,59,52,54,49] — STILL FLAT** (raw was [48,52,74,64,77,63]);
smoking gun: `amount`(9) AND `charged_amount`(12) both promoted as SEPARATE fields. Diagnostic: methods
= merge 63, **llm_merge 12 vs llm_admit 217** — the gray-band adjudicator refuses to merge 95% of the
time, and τ=0.85 is too high so real synonyms (0.64–0.83) all fall to that adjudicator. **The
self-converging-schema moat is NOT validated on real data.** Honest levers (do NOT tune on this same
set — self-grading): (1) reframe the adjudicator "same DB COLUMN?" + show example values (biggest lever,
217 wrong "different" calls); (2) embed name+example-values not bare names; (3) tune τ on a HELD-OUT
slice (BGE separation ~0.61: distinct max 0.58 / synonym min 0.64); (4) build the batch HAC
complete-linkage re-cluster (spec STAGE 3, not yet built). Found cheaply on real data before any pitch —
which is exactly why we tested. Harness: `eval/run_convergence.py` (re-run after each lever).

**UPDATE (2026-08-14) — FIRST REAL-DATA TEST (CFPB public complaints, n=120, NOT author-generated).**
Harness in `engine/eval/` (fetch_cfpb.py + run_extraction.py + fixtures/cfpb_sample.jsonl). Run over
real English complaints (debt/card/bank/transfer) on qwen3:14b. **Confirmed on real data:** extraction
robust (json-valid **100%**, grounding **0.941**, latency **p50 4.4s**); refuse-to-guess real
(desired_outcome null 18×, severity discriminates — only 1 spurious safety_health); emergent discovery
works zero-shot on a domain we never designed for (financial schema found: charged_amount,
account_status, dispute_status, fraud_type…). **Two hard findings:** (1) **NO convergence without dedup**
— new-field/20-bucket = **[48,52,74,64,77,63] (flat)**, **378 distinct fields / 120 cases** = synonym
sprawl. This is the honest PRE-DEDUP BASELINE; unit **4.3 (BGE-M3 dedup + promotion) must bend this curve
down + drop duplicates <5% on a RE-RUN of this same harness** — that re-run is the real moat proof, not
yet achieved. (2) Seeded taxonomy near-useless on financial domain (**98% UNCLEAR**) — model correctly
abstains (validates EMERGENT categories §16.2), but "universal taxonomy = day-one value" is weak far from
retail. Accuracy (governed-core correctness) NOT measured — needs human labels, separate step.

**UPDATE (2026-08-13) — ARABIC IS A SEPARATE NEXT PROJECT (owner directive). DO NOT re-raise the
Gate-A5 Gulf voice recordings as a blocker for anything — they belong to a future Arabic project, not
this build.** Consequences: (1) Phase 0.5 spikes #1/#2 are not "parked pending recordings", they are
**out of scope for this project**; stop treating them as an open item. (2) Phase 4's moat/convergence
**proof-on-real-data** is gated on **real ENGLISH cases** (design-partner / curated complaints, track
T1/T3) — NOT on Arabic recordings. This is a calendar track, non-blocking to the BUILD. Build the
machinery English-first now; the proof-on-real-English-data is the deferred item, never faked on
authored cases.

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

**F5 — RESOLVED + IMPLEMENTED (owner decision 2026-08-12, `3f59913`):** provenance is a **value↔many-sources
bridge**, not one-source-per-value. My earlier "one-message rule" was wrong on the design's own facts
(delay=102min is derived from the order record + complaint time; looked-up fields cite an object-store
row, not a message; "cite the anchor" fails audit). Migration `0004`: dropped
`field_extraction.source_document_id`/`source_span`; added `extraction_citation`
(field_extraction─<citation>─source_document, **role** ∈ primary|corroborating|derived_from|**contradicts**,
locator, weight — append-only + immutable + RLS'd) + `source_document.doc_kind`
(message|file|**object_snapshot** — object-store rows snapshotted+content-hashed are source documents too).
`record_extraction` now requires ≥1 citation (invariant moved from NOT-NULL column → boundary check).
Human corrections stay the human citation (`field_correction.reviewer_id`). weight stored, not yet computed
into confidence. Done pre-real-data (the bridge is cheap now, unreconstructable later). 42 tests green.

**Still DEFERRED to Phase 3+ (documented, NOT rushed):**
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
