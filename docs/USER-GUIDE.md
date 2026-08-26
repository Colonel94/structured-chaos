# Adaptive Intake user guide

This guide covers the current proof-of-concept workflow. It is written for reviewers and pilot
administrators; customers using the public intake page should not need documentation.

## The 60-second mental model

The system reads what a customer sent, proposes a structured case, and shows where every value came
from. It does **not** approve its own interpretation. A reviewer checks uncertain fields, corrects what
is wrong, and approves the case. Approval unlocks the report.

The confidence percentage is a review-ordering signal, not a guarantee that a case is correct. Amber
means “look here.” “Not stated” means the system deliberately refused to invent a value.

## Start a review session

1. On first use, select **Create account**, enter your name, workspace name, work email and a password of
   at least 10 characters. Otherwise select **Sign in**.
2. Choose a case from the review queue. The least-reliable predicted class appears first.
3. If the queue is empty, select **New case** to paste text or attach source files.

Your secure session selects the workspace and your signed-in name is recorded by the server on corrections
and approvals. Reviewers never need to copy a tenant UUID or type an audit identity.

## Review and approve a case

1. Read the summary and the rules decision (priority, route, and SLA).
2. Start with amber fields marked **needs review**.
3. Select a field to see its source citation. Text is highlighted; audio and image evidence opens in the
   relevant trace viewer.
4. Correct a closed-list value with keys `1`–`9`, or press `e` to edit it as text.
5. Record an accuracy verdict when useful. A verdict evaluates the model; a correction changes case data.
6. Press `c` or select **Approve** only after the case matches the source. Use the short undo window if
   approval was accidental.
7. Download the report only after approval. The commit gate intentionally blocks earlier output.

Cases with nothing flagged can be approved as a band, but this is still a human decision. Spot-check the
band during a pilot until independent accuracy and calibration gates pass.

## Submit a case

Select **New case**, paste the customer’s words, attach any relevant files, and submit. The engine may
take several seconds while local models process the material. Do not refresh repeatedly; if processing
fails, the case remains visible as **needs a human** rather than disappearing.

Supported paths depend on the deployment configuration. Text and file upload are the simplest pilot
path. The customer portal and WhatsApp require separate enablement; see [WhatsApp setup](WHATSAPP-SETUP.md).

## Connect business data

Select **Data sources** to upload a CSV, JSON, or JSONL export of orders, bookings, assets, or jobs.
Choose a meaningful object type such as `order` or `job`. The system profiles identifier columns and
uses them to match complaints to the right record.

Before a real pilot:

- remove unnecessary personal data from the export;
- agree the allowed columns and retention period with the customer;
- verify sample matches manually;
- never use production data in the repository or evaluation fixtures.

## Keyboard reference

| Key | Action |
|---|---|
| `j` / `k` | Next / previous field |
| `n` / `p` | Next / previous case |
| `1`–`9` | Apply a listed correction |
| `e` | Edit the selected field |
| `c` | Approve the case |
| `u` | Undo a recent approval |
| `r` | Download the approved report |
| `?` | Open in-product help |

## Common problems

- **Cannot sign in:** check the email and password, then confirm the API and database migrations are current.
- **Request failed / queue disappears:** check `/health`, confirm the API and worker are running, then
  reload the workspace. The health response should show a live worker, not only `status: ok`.
- **Case stays in processing:** the worker or local model may be unavailable. Follow the worker and
  Ollama checks in [Deployment guide](DEPLOY.md).
- **Source preview is blank:** confirm object storage is reachable and the source belongs to the current
  workspace.
- **Report is unavailable:** approve the case first; this is an intentional trust control.
- **Wrong priority or SLA:** do not edit the illustrative starter values silently. Escalate to the tenant
  administrator and replace them with an approved policy.

## Administrator handoff checklist

- Create the first workspace account and use a separate secure channel for any access handoff.
- Upload only the agreed object-store sample.
- Replace placeholder policy values with written customer policy.
- Demonstrate intake, trace, correction, approval, undo, and report once.
- Explain what happens when processing fails and who owns manual handling.
- Record support contact, retention period, backup owner, and incident route before accepting real data.
- Use [Data governance](DATA-GOVERNANCE.md), [Security threat model](SECURITY-THREAT-MODEL.md), and the
  [Operations runbook](OPERATIONS-RUNBOOK.md) as release evidence; assign named owners to every blank.
