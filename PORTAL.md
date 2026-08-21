# Customer portal — design contract

*The first front door that isn't the agent's screen. A stranger submits their mess, gets a case, answers
at most two drills, and returns later to see where it stands. Read this before any component/server code.*

**It is** an intake + status portal (submit · answer what's missing · track). **It is NOT** a chatbot —
no persona, no bubbles, no "how can I help?", no resolution, no policy quotes. It structures and reports.

---

## 0. What already exists server-side — so the portal duplicates NONE of it

You asked me to say plainly what would be duplicated. The answer is: **nothing about the case or the
drill.** The portal is a *thin rendering* of decisions the engine already makes. Concretely:

| Concern | Reused as-is | Portal's new part |
|---|---|---|
| Intake (text + files → case) | `intake.ingest.ingest_messages` (channel-agnostic) | call it with `channel="web"` |
| Windowing (reply → same case) | `intake.windowing` (24h + contact_ref) | a stable per-session `contact_ref` |
| Extraction, resolution, snapshot | `extract.stage`, `resolve.*`, object snapshot | — |
| **Elicitation + the anchor+2 budget** | **`elicit.policy.decide` + `elicit.stage`** | render `next_question`; ask nothing itself |
| Priority / SLA / deadline | `rules.stage.decide_case`, `case_decision` | display the deadline only |
| The async pipeline | the same stages the WhatsApp webhook runs | trigger + poll |

**The portal contains ZERO question logic.** If a drill decision needs to change, it changes in
`elicit/policy.py` and every channel (WhatsApp, portal) inherits it. The portal is, architecturally, just
another **channel** (`channel="web"`) plus a **redacted public read model** and a **widget**. That's the
whole point of the adapter interface, and it's why this is a small build, not a parallel engine.

**New code is confined to:** a separate public router, signed tokens, a redacted status projection
(a *projection*, never a new decision), state→copy presentation text, rate-limiting/CORS/limits, and the
vanilla widget. One small **shared** addition (§7, sign-off): `decide()` gains an optional `options` list
so tappable choices come from the policy, not the widget.

---

## 1. Architecture — a separate public surface

- **A separate router mounted at `/p`, NOT under `/api`.** The agent API stays exactly as-is; one mistake
  on a public route must never reach the back office. `/api/*` keeps requiring `X-Tenant-Id`; `/p/*`
  **rejects** any `X-Tenant-Id` and resolves the tenant only from the embed key / signed token.
- **`channel="web"`** for portal cases (migration adds `web` to the `channel` CHECK, §11).
- RLS is still the isolation boundary: every `/p` handler resolves a tenant (from the key/token), sets the
  transaction GUC, and can only ever touch that tenant's rows.

---

## 2. Routes (all under `/p`)

| Method · path | Purpose | Auth |
|---|---|---|
| `POST /p/submit` | multipart (`text`, `files[]`, `key`) → create case, return `{ref, token}`; kick off processing | **embed key** (form field, not a header) |
| `GET /p/case/{token}` | redacted status JSON (poll this) | **signed case token** |
| `POST /p/case/{token}/answer` | the **single** pending answer (`{answer}`) → continue the case | signed case token |
| `GET /p/s/{key}` | standalone **submit** page (HTML) — the shareable link for a business with no website | embed key in path |
| `GET /p/c/{token}` | standalone **status** page (HTML) — the "check on it later" link | signed case token |
| `GET /p/embed.js` | the widget script (static, cached) | none (public asset) |

`GET /p/case/{token}` is **read-only**; `POST …/answer` is the **only** writable public action, and it
only ever feeds one drill answer. Nothing else on the public surface writes.

---

## 3. Token scheme — unguessable, no login, no enumerable ids

Two credentials, both opaque:

- **Embed key** (per tenant, public): a random 24-byte urlsafe string, stored `tenant.embed_key`. Lives in
  the `<script data-key>`. It is **write-only capability**: it can *create* a case for its tenant, and
  nothing else — it cannot read any case. Public exposure is fine (that's what an embed key is).
- **Case token** (per case, signed): `b64url(payload) + "." + b64url(HMAC_SHA256(secret, payload))`, where
  `payload = "{tenant_id}:{case_id}"` and `secret = settings.portal_secret` (new, required when the portal
  is enabled; the router refuses to start public routes without it). Verified by constant-time compare;
  carries the tenant so the handler sets the GUC with **no cross-tenant lookup**. Unguessable without the
  secret, so no login and no enumerable `/case/{uuid}`. Returned by `/p/submit`, embedded in the "come back
  later" link.

Rotating `portal_secret` invalidates outstanding case links (documented; acceptable for a PoC).

---

## 4. State → customer copy (plain language, no internal state ever)

The status endpoint maps the internal `case_state` (+ whether a question is pending) to human copy. **Raw
`case_state`, enums, confidence, priority, routing, agent identity, emergent attributes are NEVER sent.**

| Internal | Customer sees (headline) | Also shown |
|---|---|---|
| processing (case exists, governed core not extracted yet) | **"Reading what you sent…"** | staged progress (§8) |
| `incomplete` + a pending question | **"We need one more thing from you"** | the read-back + the question |
| `actionable` (or `incomplete`, no question) | **"We've got it — and we're on it"** | the deadline + the read-back |
| `in_review` (angry, or budget spent) | **"Thanks — a person on our team is handling this"** | the deadline + the read-back |
| `committed` | **"This has been reviewed and actioned"** | the read-back |

Every non-processing state also shows the **case reference** and, where a decision exists, the **deadline**
(`case_decision.sla_response_due_at`) — the manager's SLA pitch, made visible to the customer. The clock
starts at first contact (already true in the rules engine); the copy says "by <deadline>", never "since
completeness".

## 5. The "what we understood" read-back — plain words, honest, redacted

A one-sentence human read of the governed core, assembled server-side (never raw fields). Reuses the
resolved-object confirmation the elicit stage already builds (`elicit.stage._confirmation`) for the object
half, plus a small **category→phrase** presentation map (`delivery_fulfilment → "a delivery problem"`,
`billing_charge → "a billing problem"`, …) and the outcome in plain words:

> *"Looks like a delivery problem with order BK-1001, and you'd like a refund."*

If a piece is missing it's simply omitted ("Looks like a delivery problem." ). No enum leaks, no
confidence, no "we're 61% sure". If nothing is understood yet → the processing view, not an empty read-back.

## 6. Security checklist (customer-facing + unauthenticated)

- **No login.** Ever. The tokens carry the capability.
- **Case URLs are signed tokens** (§3), not sequential ids, not raw UUIDs in a path.
- **Read-only + one answer.** `/p/case/{token}` reads; `…/answer` writes exactly one drill reply; nothing
  else is writable publicly.
- **Rate limits** (§9), per IP **and** per tenant, on `submit` + `answer` — abuse is a *cost* problem
  (unauthenticated endpoint triggering paid model calls), so the cap is on cost-bearing actions.
- **File limits at the edge:** max size (e.g. 10 MB/file, 25 MB/request) and an allowlist of MIME types
  (image/*, audio/webm+ogg+mp4, application/pdf, text/plain) rejected with a clear message before any work.
- **Tenant from the embed key, never a client header.** `/p/*` explicitly ignores `X-Tenant-Id`.
- **CORS restricted to the tenant's registered origins** (`tenant.allowed_origins`). Mechanics: a `/p` CORS
  layer reflects an `Origin` only if it appears in *some* tenant's allowed-origins (preflight has no key),
  and `submit`/`answer` additionally verify the request `Origin` is in the **resolved** tenant's list
  (defence in depth). The standalone `/p/s` and `/p/c` pages are same-origin, so unaffected.
- **Separate router** (§1) — the public surface never extends `/api`.

## 7. Tappable options — the one shared server-side change (sign-off)

You want tappable options "where the policy supplies them, free text otherwise", and options belong in the
policy, not the widget. So `ElicitationPlan` gains an optional field:

```python
options: tuple[str, ...] | None = None   # tappable choices for this question, or None → free text
```

`decide()` populates it for the **outcome** drill from the `DESIRED_OUTCOMES` vocab in plain labels
(*Refund · Replacement · Fix it · An answer · Escalate*), and leaves it `None` for the anchor and the
open clarify. This is a **shared** improvement (WhatsApp renders them as interactive buttons later) and
keeps all question logic server-side — the option set is defined once, so the channels can't diverge.

**Options are a HINT, never a CONSTRAINT (owner condition).** The widget always shows a free-text input
*alongside* the option buttons; a customer whose answer isn't one of the three is never forced to pick a
wrong one — that is exactly the upfront-type-picker failure this product exists to avoid. Server-side the
answer is just text fed to extraction whether it came from a button or the box, so free-text-alongside is
free.

## 8 & 9. The wait, and rate limits

**The wait — chosen (owner-approved): return immediately + FastAPI BackgroundTask + poll a stage driven by
REAL PERSISTED STATE.** `/p/submit` creates the case (fast, synchronous — *the case exists on first
contact, always*), returns `{ref, token}` **immediately**, and runs `normalise → extract → decide → elicit`
in a background task (the proven WhatsApp pattern). The customer never watches a cursor.

**The staged view is derived from what is actually persisted in the DB — never an optimistic client
timer:**

`received → transcribing (if audio, until normalised_content exists) → understanding (until governed core exists) → checking your order (until decision/snapshot) → ready`.

**The stall guarantee (owner condition):** because a BackgroundTask dies with the process, a restart
mid-extraction must not leave the customer on a spinner that never resolves. So the poll checks the case's
age: if it is still in `processing` (no governed core) and `now − first_contact_at` exceeds a threshold
(≈90s), the status flips to honest copy — **"This is taking a little longer than usual — we've got your
case and we'll pick it up"** — instead of hanging. The case exists either way; that promise holds
unconditionally. (A future poll may also re-trigger a stalled pipeline; the procrastinate worker is the
documented **production durability upgrade** for when the portal stops being a test surface.)

**Rate limits:** an in-memory sliding-window limiter keyed by IP and by tenant (e.g. 5 submits / 10 min /
IP, 60 / hour / tenant — tunable in config). In-memory = per-process, honest PoC scope; Redis/DB is the
multi-instance upgrade. `429` with a plain message when exceeded. Only the cost-bearing routes
(`submit`, `answer`) are limited; `GET status` is cheap and unlimited.

## 10. The answer path — reusing windowing, no new drill logic

The portal case is created with a **stable synthetic `contact_ref`** (a signed per-session id, not a
phone). `POST …/answer` re-ingests the answer text through the *same* `ingest_messages` with that same
`contact_ref` → windowing attaches it to the open case → re-extract → `decide()` issues the next move (or
none). Identical to a WhatsApp reply, sender = portal-session instead of phone. No portal-side question
logic. (A `channel="web"` case has no real egress recipient, so the elicit stage's channel dispatch is a
no-op for it — the question is *read on poll*, never "sent"; I'll guard the dispatch to skip `web`.)

## 11. Data-model changes (one migration, `0018`)

- `tenant.embed_key text UNIQUE` (nullable; set when a tenant is onboarded to the portal) + index.
- `tenant.allowed_origins jsonb NOT NULL DEFAULT '[]'` (CORS allowlist).
- Add `web` to the `case_record.channel` CHECK constraint (portal cases).
- New config: `portal_secret` (HMAC key), `portal_enabled` (gates the public router), file/rate limits.
- A tiny helper `scripts/portal_enable.py <tenant> <origin…>` to mint an embed key + set origins (manual
  onboarding is allowed, winning-condition §6).

## 12. The embed widget

- **One tag:** `<script src="https://…/p/embed.js" data-key="…" data-accent="#2563eb" data-position="bottom-right"></script>`.
- **Shadow DOM** — host CSS can't break it; it can't break the host. **Vanilla TS/JS, no React**, built to a
  single self-contained file, target **< 50 KB gzipped**. (The review UI's React stack is *not* this
  widget's stack — separate tiny build.)
- **Screen 1 (Submit):** one textarea, placeholder *"Tell us what went wrong. Type it, paste it, or record
  it — no forms."* · a **file attach** · a **press-and-hold / tap voice button** (MediaRecorder → webm/opus
  blob), the second-most-prominent element. No fields, no category, no dropdowns.
- **Screen 2 (Status):** reference · plain-language state · deadline · the read-back · the pending question
  (tappable options or free text). Nothing else.
- **Config via data-attrs:** accent colour + position only. Not a theming engine.
- **Standalone page** at `/p/s/{key}` (submit) and `/p/c/{token}` (status) for businesses with no site.
- **A11y + reality:** keyboard-reachable, labelled controls, visible focus; **mobile-first, tested at 390px
  first**; JS-blocked → an honest message + the standalone link.
- **Voice degrades honestly.** No MediaRecorder → the button is hidden, text still works. **Mic permission
  DENIED → the button is replaced, the moment it's denied, by a visible line — "Mic access is off — just
  type it instead"** — the text box stays primary. Never a dead record button.

## 12a. Voice — accept both formats, normalise, and INSTRUMENT it (owner directive)

Voice is the behavioural wedge and we have **zero real voice data** — the first recordings through this
portal *are* the eval set. So:

- **Accept both containers:** `webm/opus` (Chrome/Android) **and** `mp4/aac` (Safari/iOS). Both already
  normalise through **ffmpeg** in the audio path; no new decode.
- **Instrument every voice submission** with a structured log event (`voice.submission`): **container,
  codec, duration (s), byte size, and whether transcription succeeded + produced non-empty text.** This is
  the data that tells us whether **iOS Safari transcribes as well as Android Chrome** *before* we find out
  in front of a stranger. (Logged, not PII — no transcript text in the log line, per §"no customer data in
  logs".)
- **Honest flag:** **iOS Safari mic permission inside an embedded iframe is historically the flakiest path
  in this entire build.** It must be **tested on a real iPhone, not a simulator**, and the text fallback on
  denial (above) must be immediate and obvious. If the embedded path proves too flaky on iOS, the
  standalone `/p/s/{key}` page (top-level origin, not an iframe) is the reliable fallback link to share.

## 13. Test plan (server first, with the two you named)

- **`/p/*` rejects a client-supplied `X-Tenant-Id`** (it's ignored; tenant only from key/token). *(named)*
- **A case token cannot read another tenant's case** — a token minted for tenant A returns 404 for a B
  case; a tampered signature is rejected. *(named)*
- Embed-key resolves the right tenant; an unknown/blank key → 404.
- `submit` creates a case immediately (before processing finishes) and returns a valid token.
- The status projection **never** contains confidence / enums / priority / routing / emergent names
  (assert the JSON keys).
- The anchor+2 budget holds through the portal (answer twice → third poll has no question) — via the
  shared policy, no portal logic.
- File too large / disallowed MIME → 413/415 before any model call.
- Rate limit trips at the cap (429).
- Widget: `nabu-ui-test` at 390px + desktop, 0 console errors; the five screenshots.

## 14. Build order (after sign-off)

1. Migration `0018` + config + `portal_secret`.
2. Server: `/p` router, token sign/verify, redacted projection, rate limit, CORS, file limits — **with the
   tests above** (server before widget).
3. The shared `options` addition to `decide()` (+ its test).
4. The widget (vanilla, shadow DOM) + standalone pages.
5. `nabu-ui-test` at 390px + desktop; then the end-to-end stranger walk (submit a voice note, answer, close
   tab, return via link, see status).

## 15. Sign-off — RESOLVED (owner, this session)

1. **The wait: BackgroundTask + poll** — approved, with the **stall condition**: the staged view is driven
   by real persisted state (§8), and a case in progress past ~90s shows honest "taking longer" copy instead
   of hanging. Migrate to the procrastinate worker when the portal stops being a test surface.
2. **Tappable options** — approved as a shared `decide()` addition (§7), with the **hint-not-constraint**
   rule: free text is always available alongside the buttons.
3. **Voice** — accept both `webm/opus` + `mp4/aac`, normalise in ffmpeg, and **instrument** container/codec/
   duration/transcription-success per submission (§12a); iOS-Safari-iframe mic flakiness flagged, real-
   iPhone test required, text fallback immediate on denial.

Everything else follows the spec verbatim: thin renderer, shared policy, anchor+2 server-side, no internal
leaks, created-on-first-contact, unguessable read-only links.
