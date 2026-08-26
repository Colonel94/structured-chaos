# Gate B — controlled-pilot readiness

*Working artifact to drive `winning-condition.md §4` (Gate B) from 3/6 to a genuine 6/6.*
*Last verified: 2026-08-26. Owner-fill slots are marked ⬜.*

Gate B has six top-level gates. Three are code/product gates I can verify; three need real
external inputs (a named partner, a named responder, a non-builder operator) that **cannot be
fabricated** without voiding the gate. This document records the verified evidence and provides the
ready-to-use templates for the human-gated remainder.

## Scorecard (verified 2026-08-26)

| Gate | Status | Evidence |
|---|---|---|
| 1. Complete complaint workflow | **CLEAN (verified)** | Full suite green (283 passed); elicit path bug fixed (see below); commit gate refuses undecided cases. |
| 2. Mandatory human control | **CLEAN (verified)** | `test_commit_gate`, `test_review_usability` green; no autonomous approval path. |
| 3. Trust & tenant boundary | **CLEAN (verified)** | Trust-spine 21 tests green: `test_rls_isolation`, `test_provenance`, `test_idempotency`, `test_pii`, `test_pii_redaction`, `test_trust_coverage`. |
| 4. Named pilot governance | **OPEN (owner)** | Requires a named organisation + signed policy. Template below. |
| 5. Operational evidence | **TECHNICAL EVIDENCE DONE; 1 owner slot** | Backup/restore drill + secret fail-closed + CI security scan verified below; needs a named responder + CI scan verdict review. |
| 6. Operator acceptance | **NOT RUN (external human)** | Needs one non-builder operator. Script below. |

**Honest ceiling:** I can move this to *5-technically-complete + 3 clean*. A true **6/6 requires the
owner** to (4) name a pilot org and sign its policy, (5) name an incident responder and accept the CI
security result, and (6) have one person who did not build this complete the acceptance run. None of
those three are fabricatable — that is the point of the gate.

### Fix landed this session (was silently failing Gate 1)
`app/store/api.py :: get_emergent_values_by_head` queried a non-existent `emergent_field.qualifier`
column, crashing the **elicit** path (the anchor+2 drill) with `UndefinedColumn`. It was hidden
because the seed path never calls elicit. Fixed by deriving the qualifier from `field_name`/`head` in
SQL. Also fixed a stale test (`_seed_case` skipped `decide_case`, so its case was never committable and
tripped the `case_commit_pair` constraint). 22 previously-failing tests now pass; full suite 283 green.

---

## Gate 4 — named pilot governance (template — ⬜ owner fills)

**Pilot scope**
- ⬜ Named organisation:
- ⬜ Use case / complaint domain:
- ⬜ Intake channel(s) (file-drop / WhatsApp):
- ⬜ Maximum case volume (per day / total):
- ⬜ Pilot start & end dates:
- ⬜ Success owner (name, role):

**Approved & versioned business policy** (replaces the illustrative default in `assets/`)
- ⬜ Category taxonomy (approved list):
- ⬜ Priority rules:
- ⬜ SLA targets per priority:
- ⬜ Escalation routing:
- ⬜ Retention period:
- ⬜ Deletion policy:
- ⬜ Policy version tag:

**Data authority / DPA**
- ⬜ Lawful basis or consent mechanism:
- ⬜ Controller / processor roles:
- ⬜ Permitted data types (and prohibited):
- ⬜ Residency requirement:
- ⬜ Subprocessors disclosed:
- ⬜ Breach contact:
- ⬜ Deletion-on-request procedure:

Gate 4 is CLEAN when every ⬜ above is filled and the policy is loaded as the tenant's active policy
(not the illustrative default).

---

## Gate 5 — operational evidence

### ✅ Backup / restore drill — PASSED (2026-08-26 12:14:59Z)
- Dumped live DB (`pg_dump -Fc`, 3.9 MB) and restored into a scratch DB.
- Row counts matched exactly across `case_record` (88), `source_document` (106), `field_current`
  (572), `case_decision` (41); zero restore errors.
- Production procedure: `scripts/backup.sh` (Postgres custom-format dump + MinIO originals mirror to a
  timestamped dir, prunes past `RETENTION_DAYS`). Restore per `docs/DEPLOY.md §Backups`.
- ⬜ Owner: schedule `backup.sh` on the pilot host (cron) and record the first live backup timestamp.

### ✅ Secret rotation / fail-closed — TESTED
- `_fail_closed_on_default_secrets` (config R5): in `APP_ENV=prod` the app refuses to boot with any
  empty or placeholder secret (`change_me_*`, `poc-portal-secret`).
- `tests/test_config_secrets.py` — 5 passing.
- ⬜ Owner: rotate the real pilot secrets into the prod `.env` / secret store before first live case.

### ✅ Security scanning — EXISTS (CI)
- `.github/workflows/security.yml`: CodeQL (`security-extended`) + Trivy (`vuln,secret,misconfig`).
- ⬜ Owner: run the workflow on the pilot release commit and accept/triage the results — Gate 5
  requires **no unaccepted high/critical** finding.

### Manual fallback runbook (rehearsed procedure)
If the pipeline degrades (repeated processing failure, worker down, model backend unreachable):
1. **Detect** — `/health` reports `worker.status != alive` or repeated `processing_failed` cases.
2. **Announce** — flip intake to manual: pause the pilot channel; incoming complaints are handled on
   the team's existing manual process until restored (no data is lost — originals are retained).
3. **Contain** — do NOT approve any case whose evidence you cannot trace; the commit gate already
   blocks undecided/failed cases.
4. **Recover** — restart the worker (`python -m scripts.run_worker default --schedule`); it reaps
   orphaned in-flight jobs on startup so stuck cases resume.
5. **Verify** — `/health` green; the previously-stuck cases advance; reconcile against the manual
   queue.
6. **Restore** intake to the channel.
- ⬜ Owner: **named monitor / incident responder** (name, contact): ____________________
- ⬜ Owner: rehearse steps 1–6 once against the pilot host and record the date.

---

## Gate 6 — operator acceptance run (script — ⬜ non-builder runs)

**Operator:** someone who did **not** build the product (owner, colleague, or the pilot's own staff).
Do it without the builder narrating. Record every point of confusion — confusion is data, not failure.

1. Sign in / open the reviewer app; select the pilot workspace.
2. Submit one representative messy complaint (file-drop or the portal) — the real kind the pilot team
   receives, not a clean sample.
3. Watch it become a case. Confirm progress/failure is shown honestly (not a false "done").
4. Open the case. For **each** extracted field, click through to its source evidence — confirm you
   can trace every value in under 5 seconds.
5. Correct at least one field you disagree with; confirm the correction is recorded (not a silent
   overwrite of the original).
6. Approve the case. Confirm you could **not** approve it while it was still processing.
7. Produce the report/output. Confirm it only became available after approval.
8. Don't hand-log your time — the system already did. Read `GET /api/review-stats` for count / median /
   p90 (the ≤30s and ≤60s targets are scored from there, not a spreadsheet). Note only what the
   instrumentation can't see: any moment you looked for a form, any field it got confidently wrong, any
   question it asked that you'd already answered, and whether you needed help or gave up.

Gate 6 is CLEAN when a non-builder completes steps 1–7 end to end and the step-8 notes contain no
trust failure (untraceable value, confidently-wrong field, approval of an unprocessed case).

> Reviewer UI: `http://localhost:5173` · seeded non-US-English demo tenant for a dry run:
> `11aa0e52-6d53-48d1-8383-f25884c903b0` (synthetic, not the pilot's real data).
