# Recording guide — Phase 0.5 spike inputs + T3 ground-truth kit

*Two jobs live here: (1) the **day-one spike inputs** you record yourself in an hour (Gate A5), and
(2) the **T3 self-recording kit** (8–10 speakers, ~15–20 cases) that feeds the scorer at Phase 4.
Both must be real: real WhatsApp, real codec, real code-switch, real noise. Synthetic-clean audio
proves nothing (CLAUDE.md §10 — never grade the moat on data you authored).*

---

## Part 1 — Gate A5 spike inputs (record TODAY, ~1 hour, yourself)

The Phase 0.5 spike kills or confirms the three riskiest proofs before anything is built on them.
It needs, at minimum:

### 1a. 3–5 Gulf-Arabic voice notes, recorded in a NOISY real environment
- **How (this is the part that's easy to do wrong so it *looks* fine):** record **inside WhatsApp**
  (hold-to-record in a chat to yourself) and send it, then export the `.opus`. **Do NOT use the phone's
  voice-memo app** — it skips the real Opus compression path, which is exactly what the model receives.
  A clean memo-app file will flatter the model and prove nothing.
- **Where:** a kitchen with the extractor fan on, a street, a car, a shop floor — **noisy on purpose**.
  A clean recording proves nothing about a bakery.
- **Cards, not scripts:** let yourself **ramble, repeat, trail off, and switch to English mid-sentence**.
  Scripted Arabic is easier than real Arabic and will flatter the model. Say the *situation* in your words:
  - *Bakery:* the cake came an hour late **and melted**, you want a refund, and you're annoyed.
  - *Home maintenance:* the technician **never showed**, the AC still isn't cooling, it's the **third time**.
- **Include ONE deliberately useless recording** — ~5 seconds of pure emotion, no case content:
  *"I'm very mad, this is unacceptable."* / *"شي ما ينطاق، زعلان وايد."* Nothing else. **This is the
  single most important clip:** it's the elicitation fuel — the case the entire anchor+2 drill-down design
  exists to handle (angry + incomplete → hand to a human, don't interrogate).
- **Save to:** `data/spike/audio/` (gitignored). Name them `voice_01.opus` … `voice_05.opus`.

### 1b. 1 photographed, stamped, bilingual document (the real-world one, not a clean scan)
- A real invoice/receipt/form with **Arabic + English**, shot on your phone: **angled, in poor light,
  with a stamp or signature that overlaps the printed text, and ideally slightly creased.** That overlap
  + skew + glare is the actual test — a flat clean scan is the easy case and won't tell you anything.
  Save to `data/spike/docs/doc_01.jpg`.

**These two are the highest-leverage hour in the project.** Without them the spike is theatre.

---

## Part 2 — T3 ground-truth kit (calendar track — start recruiting now)

Target: **~15–20 cases** across **8–10 Gulf-Arabic speakers**, split across the **two built verticals**
(bakery orders, home-maintenance jobs). Capture through WhatsApp. Public corpora (SADA/MASC) are
**calibration only** — never the case set.

### Scenario cards (hand these out — NOT scripts; let them improvise in their own words)
Each speaker gets 2–3 cards. A card gives a *situation*, not lines to read.

**Bakery (object = order):**
- B1 — Your birthday cake arrived **over an hour late and partly melted**. You want a refund. You're annoyed.
- B2 — You ordered **a dozen croissants, only got six**, and they were **cold**. Decide what you want.
- B3 — Wrong flavour: you ordered **pistachio, got vanilla**. You just want them to acknowledge it.
- B4 — **Allergen**: you said "nut-free" and there were nuts. You're worried — this is urgent.
- B5 — *(sparse)* Just say "my order is wrong" and nothing else, and wait to be asked.

**Home maintenance (object = job visit):**
- H1 — The **technician never showed up** today; it's the **third time**. You're furious.
- H2 — The AC was "fixed" last week and **still isn't cooling** (recurring). You want it done right.
- H3 — You were **quoted 200 AED and charged 280** (overcharge). You want the difference back.
- H4 — Poor workmanship: a **leak they fixed is leaking again**. Warranty should cover it.
- H5 — *(sparse)* "The guy did a bad job" and nothing else.

Mix in: at least one **angry** delivery per speaker, one **pure-emotion useless clip** ("I'm very mad,
this is unacceptable" — no case content, the elicitation-fuel case), natural **Arabic/English
code-switch** (let them ramble/repeat/switch mid-sentence), and several recorded in **background noise**.

### Capture & storage
- Record as WhatsApp voice notes (+ a few typed messages, + a photo or two for the multimodal path).
- Store originals in `data/groundtruth/` (gitignored). Label each with the scenario id + a
  field-by-field ground-truth sheet (that labelling is the eval set — the moat asset).

---

## Part 3 — Consent + ownership (REQUIRED before any real voice is used)

Voice is personal, biometric-adjacent data. No handshake — get it in writing. Draft one-pager below;
have a lawyer glance before design-partner (real customer) data, but for your own recruited speakers
this is the floor.

> **Recording consent & assignment (v0 draft — not legal advice)**
>
> I, ______________________ (name), agree to record voice notes and messages for the purpose of
> building and evaluating [Company]'s complaint-intake software. I understand:
> 1. The recordings and any transcripts/derived data may be stored, processed, and used to build,
>    test, and improve the software and its evaluation set.
> 2. I **assign all rights** in the recordings and the resulting evaluation dataset to [Company].
> 3. Recordings will be handled per applicable UAE PDPL; I can request deletion of my raw recordings
>    (derived, anonymised eval data may be retained).
> 4. Participation is voluntary and [paid/unpaid as agreed].
>
> Signature: __________________  Date: __________  Contact: __________

**Design-partner (real complaint) data is different:** that needs a **DPA**, drafted the day a partner
says yes (track T1), not this consent form. No real customer data is touched without the DPA.
