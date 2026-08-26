# Data governance and retention

This is an implementation-ready operating policy, not legal advice or a substitute for jurisdiction-
specific review. The controller, processor, subprocessors, residency, lawful basis and contract terms
must be completed and approved before real customer data is accepted.

## Data map

| Data | Purpose | Store | Default pilot retention |
|---|---|---|---|
| Original messages/files/audio/images | evidence, provenance and reprocessing | MinIO/S3 + source metadata in Postgres | pilot term + 30 days |
| Extracted fields, decisions and links | case handling | Postgres | pilot term + 30 days |
| Corrections, approvals and reviewer feedback | audit and quality improvement | Postgres | pilot term + 90 days unless contract requires less |
| Accounts, memberships and sessions | access control | Postgres | account life; sessions 12 hours |
| Redacted operational logs | reliability/security | selected log platform | 30 days |
| Backups | recovery | isolated encrypted storage | 30 days, then expiry |

Do not claim “retained forever.” Immutability means records cannot be silently rewritten during their
approved retention period; it does not cancel deletion obligations.

## Principles

- Minimise intake, disable unused channels, and never copy customer content into tickets or alerts.
- Keep inference local unless the signed customer agreement names and permits a cloud subprocessor.
- Encrypt transport, volumes and backups; separate runtime, migration and backup credentials.
- Limit operator access by role, review it monthly, and revoke membership/sessions promptly.
- Use customer data for quality improvement only within the agreed purpose and boundary.

## Access/export/deletion procedure

1. Authenticate the requester and obtain the controller's written approval and exact workspace UUID.
2. Snapshot the request, scope, legal hold status, operator and deadline in the audit register.
3. Export through the tenant-scoped report/register path when access is requested.
4. For approved full erasure, take a final authorised backup if policy permits, then run from the engine
   environment: `python /app/scripts/delete_tenant.py --tenant <uuid> --confirm DELETE-<uuid>`.
5. The offline tool removes all tenant-keyed database rows, queued jobs and blobs no longer referenced by
   another tenant. Verify the tenant is absent, record object counts, and let backup copies expire under
   the documented schedule (or remove them where contract/law requires).
6. Have a second operator review the evidence and notify the requester without exposing internal data.

## Before launch

Fill and approve: controller/processor names, countries/regions, subprocessors, lawful purpose, retention
exceptions, legal holds, request SLA, breach notification SLA, deletion approvers and security contact.
