# Testing end-to-end on your real WhatsApp

Send a message from your normal WhatsApp, watch it become a structured case, and get the drill question
**back on your phone** — the full loop. The transport uses Meta's official **WhatsApp Cloud API** (free,
ToS-clean, on-prem-viable). You do the Meta account setup (the one part gated on your identity); the
engine already has the webhook + send wired.

**Time:** ~20–30 min, first time. **Cost:** $0 (free API access, free test number, personal test sits in
the free conversation tier; tunnel is free).

---

## The shape of it

```
your WhatsApp ──text──▶ Meta ──POST──▶ [tunnel] ──▶ engine /api/whatsapp/webhook
                                                        │ ingest → normalise → extract
                                                        │ → decide → elicit
                                                        ▼
your WhatsApp ◀──reply── Meta ◀──send── WhatsAppChannel.send()   ("We've found your order BK-1001…")
```

Your phone number is the anchor: if it's on an order, the case resolves it **silently** and the reply
**confirms the record** instead of asking (Moment 3). Step 6 seeds an order with your number.

---

## 1. Create a Meta app + WhatsApp test number  *(you — needs your Meta login)*

1. Go to **developers.facebook.com** → log in → **My Apps** → **Create App** → type **Business**.
2. In the app, **Add product → WhatsApp → Set up**. This gives you, on the **API Setup** page:
   - a **temporary access token** (24h) — fine to start; swap for a permanent System-User token later,
   - a **Test number** (Meta's, free) and its **Phone number ID**,
   - a box to **add recipient numbers** — add **your personal WhatsApp number** (a test number can message
     up to 5 recipients). Confirm the code WhatsApp sends you.
3. Note **App secret**: app **Settings → Basic → App secret** (Show).

You now have four things: **token**, **phone number ID**, **app secret**, and you've registered **your
number** as a test recipient.

## 2. Put the credentials in `.env`  *(repo root)*

```ini
WHATSAPP_TOKEN=<the access token>
WHATSAPP_PHONE_NUMBER_ID=<the phone number id>
WHATSAPP_APP_SECRET=<the app secret>
WHATSAPP_VERIFY_TOKEN=pick-any-string-you-invent      # you'll paste the same one into Meta in step 5
WHATSAPP_API_VERSION=v21.0                             # match what the Meta dashboard shows
CHANNEL_BACKEND=cloud                                  # flips egress from the $0 sink to live WhatsApp
# WHATSAPP_TENANT_ID=...  ← filled in step 6
```

## 3. Seed a tenant with YOUR number so the order resolves for you

```bash
cd engine
uv run python scripts/whatsapp_demo_setup.py "+<your full number>"   # e.g. +447700900123
```

It prints a **tenant id** and seeds order **BK-1001** keyed to your number (slot 17:00, delivered 18:42 —
so the lateness shows up in the confirmation). Put the id in `.env`:

```ini
WHATSAPP_TENANT_ID=<the printed tenant uuid>
```

## 4. Start the engine (with the new env) and a public tunnel

Meta must reach your machine over **HTTPS**, so tunnel to the engine on **:8000**.

```bash
# engine (reads the .env above)
cd engine && uv run uvicorn app.main:app --port 8000

# tunnel — either one, in another terminal:
cloudflared tunnel --url http://localhost:8000      # no signup
#   or:  ngrok http 8000
```

Copy the public HTTPS URL it prints (e.g. `https://abc-123.trycloudflare.com`).

## 5. Register the webhook in Meta

In the app → **WhatsApp → Configuration → Webhook → Edit**:

- **Callback URL:** `<your tunnel URL>/api/whatsapp/webhook`
- **Verify token:** the exact `WHATSAPP_VERIFY_TOKEN` string from step 2.
- Click **Verify and save** — Meta calls `GET …/webhook`; you should see it succeed (the engine echoes the
  challenge). If it fails, the token doesn't match or the tunnel/engine isn't up.
- Under **Webhook fields**, **Subscribe** to **messages**.

## 6. Send the message

From your normal WhatsApp, message the **test number** (save it as a contact first):

> hey the birthday cake turned up really late and it was all squashed, not happy at all

Within ~10–15s:
- a **structured case** appears at `http://localhost:5173/?tenant=<WHATSAPP_TENANT_ID>` — category
  `delivery_fulfilment`, your fault text, routed with a priority/SLA, and the order **resolved from your
  number** (no "what's your order number?");
- **your phone gets the reply:** *"We've found your order BK-1001: slot 17:00, items chocolate birthday
  cake, delivered at 18:42, customer name You. What would you like us to do to put this right?"*

Reply **"a refund please"** → it re-enters the same case → `desired_outcome=refund` → the case reaches
**actionable**. Loop closed.

---

## Troubleshooting

- **Webhook "verify" fails** → `WHATSAPP_VERIFY_TOKEN` in `.env` ≠ what you typed in Meta, or the engine
  wasn't restarted after editing `.env`, or the tunnel URL is wrong/expired.
- **Message arrives but no reply** → `CHANNEL_BACKEND` isn't `cloud`, or the token/phone-number-id is
  wrong. Check the engine log for `whatsapp.processed` / `dispatch.sent` vs an error.
- **Reply says it couldn't find the order** → the number you messaged *from* isn't the one you seeded in
  step 3 (WhatsApp sends the wa_id without a `+`; the resolver normalises to digits, so `+4477…` and
  `4477…` match — but a *different* number won't). Re-run step 3 with the exact sending number.
- **cloudflared/ngrok URL changed** → free tunnels get a new URL each start; re-do step 5 with the new one.
- **Nothing at all** → confirm the tunnel forwards to `:8000` (the engine), not `:5173` (the UI), and that
  you subscribed to **messages** in step 5.

## What this is / isn't

- **Is:** the real Cloud API, ToS-clean, the same path a production tenant would use (one number ↔ one
  tenant here; a multi-number product maps `phone_number_id → tenant`).
- **Isn't:** a way to use your *personal* number as the business line — that needs a QR-bridge
  (whatsapp-web.js / Baileys) which violates WhatsApp ToS and can't ship on-prem. Don't. The test number
  is the correct tool, and you still message it from your real personal WhatsApp.
- **Voice notes / photos** sent to the webhook are ignored for now (text only); the media path is the
  natural next step (download via the Media API → the existing ASR/OCR normalisers).
