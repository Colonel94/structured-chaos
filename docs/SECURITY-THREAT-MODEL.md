# Security threat model

**Scope:** reviewer API and SPA, customer portal, uploads, WhatsApp webhook, Postgres, MinIO, worker, local
model boundary and release pipeline. Review this document for every material architecture change.

| Threat | Control in this repository | Residual / release evidence |
|---|---|---|
| Tenant or reviewer spoofing | HttpOnly session, membership-derived tenant, server-derived reviewer; production rejects `X-Tenant-Id` | Run DB-backed auth/RLS tests in CI; revoke sessions after personnel changes |
| Cross-site state change | SameSite=Strict session and CSRF cookie/header binding on mutations | TLS and same-origin deployment required |
| Password theft | Per-user scrypt salt/hash; raw passwords never stored; generic login failure; rate bound | Add managed edge rate limiting and credential-reset process before wide launch |
| Session database theft | Random session token; only SHA-256 digest stored; 12-hour expiry and logout revocation | No remote session-management UI yet |
| Malicious/oversized upload | 25 MB request/read bounds and explicit intake MIME allowlist; portal limits | File signatures and malware scanning are required before accepting unknown public files at scale |
| Webhook forgery | Meta signature/verify-token checks | Rotate and rehearse credentials; restrict ingress where practical |
| Signed-link leakage | HMAC tokens, separate portal surface, production secret gate | Tokens remain bearer links; choose expiry/retention policy and avoid analytics referrer leakage |
| Stored customer-data leak | RLS, immutable originals, append-only corrections, redacted structured logs | Encrypt volumes/backups and restrict operator access on the deployment host |
| Supply-chain compromise | Locked Python/JS dependencies, CodeQL, dependency review, Trivy secret/vulnerability/config scan | Resolve high/critical findings or record a time-bounded exception before release |
| Model prompt injection | Model output is schema-constrained and cannot act; deterministic rules and human commit gate | Treat all extracted text as untrusted; never add autonomous tools without a new threat review |
| Denial of service | Upload bounds, auth/portal rate limits, worker isolation and liveness | Add shared edge limits for multi-instance deployments and capacity alerts |
| Stale or unsafe release | migration dependency, no-cache release procedure, prod secret fail-close, TLS edge | Sign/tag immutable images and retain rollback evidence |

## Release security gate

- All CI and security workflow jobs green; no unexplained high/critical finding.
- Production header spoof test, RLS suite, upload size/type tests, CSRF test and commit-gate tests green.
- Real secrets present and rotated in a rehearsal; no secrets in Git history or logs.
- TLS, CSP, HSTS and cookie flags verified at the public endpoint.
- Restore drill and incident tabletop completed with named owners.
- Any exception has an owner, expiry date, impact, mitigation and written approval.
