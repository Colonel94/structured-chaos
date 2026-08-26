# Operations runbook

Use this runbook for a controlled pilot. Put the named owner and contact channel in the release record;
do not launch with placeholders.

## Service signals

- Poll `GET /health` every minute. Page when API status is not `ok`, worker is `down` for two checks, or
  the endpoint is unreachable. `unknown` is degraded and must be investigated.
- Alert on HTTP 5xx rate, p50/p95 intake latency, `processing_failed` cases, queued-job age, disk usage,
  Postgres connections, MinIO capacity, and backup age in the chosen monitoring platform.
- Never put complaint text, names, emails, phone numbers, transcripts, or attachment names in alert text.

## Severity and response

| Severity | Example | Acknowledge | Action |
|---|---|---:|---|
| SEV-1 | cross-tenant exposure, lost originals, credential compromise | 15 min | stop intake, preserve logs, revoke secrets, notify owner and follow breach process |
| SEV-2 | intake or review unavailable, growing queue, repeated processing failures | 30 min | switch to manual intake, diagnose, post hourly updates |
| SEV-3 | isolated bad extraction or report defect | 1 business day | correct through review, capture feedback, schedule fix |

## Safe fallback

If processing is unavailable, keep the case and source intact, mark it for a person, and use the
customer's original message as the manual record. Never issue a report without human approval. Do not
restart multiple default workers; the singleton guard exists to prevent duplicate processing.

## Backup and recovery

1. Schedule `scripts/backup.sh` outside the application host and monitor its exit status and age.
2. Run `scripts/restore_drill.sh <backup-directory>` monthly. It restores only into names ending
   `_restore_drill`, verifies database tables/case counts and an isolated MinIO bucket, then cleans up.
3. Attach the command output, backup timestamp, duration, RPO, achieved RTO, operator, and commit to the
   release evidence folder. A backup without a green restore drill is not accepted.

## Release and rollback

Run migrations before the API, smoke-test signup/login/logout and one uncommitted/committed report, then
verify `/health`. Roll back application code only to a revision compatible with the applied schema; use
forward-fix migrations for data-bearing releases. Keep the previous immutable image tag available.

## Data requests

Authenticate the requester, record scope and approval, export or delete through an audited operator
procedure, and verify both primary and backup-retention effects. Never act on an unauthenticated email.
