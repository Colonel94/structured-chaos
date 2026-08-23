# Review UI — design contract

*Read this before touching a component. It fixes the direction, the type, the palette, the scale, and
the spacing so that every value in the code references a token, not a taste. Visual/interaction redesign
only — no API, engine, or data changes; every field/number/state that renders today still renders, and
`App.test.tsx` passes unmodified.*

---

## 0. What this screen is

A **verification instrument**, not a dashboard. A reviewer sits in it for hours and clears a case in
under 30 seconds — deciding whether a machine read a human correctly. So the whole design has one job:
**make what the machine is unsure about the loudest thing on screen, and everything else quiet.** It
should look operated, not browsed — a DAW, a trading terminal, a code editor.

---

## 1. Direction — **Instrument** (committed, not blended)

Near-black canvas, layered surfaces, hairline rules, monospace for machine data, data-dense, keyboard-
first. Bloomberg by way of Linear. This is the direction your brief already argues for ("dark by
default, keyboard-first, no decoration that doesn't carry information"), and it's right for the task:
long sessions favour a dark, low-glare field, and an instrument earns trust by looking precise rather
than friendly.

Rejected: **Archival** (warm paper) and **Clinical** (high-contrast light) — both are legible, but a
reviewer doing hours of low-glare scanning is better served by dark, and "instrument" is the register
that reads as *operated*. One idea is borrowed from Archival and folded in below: the source text — the
human's own words — is set in a **serif**, so the thing under examination reads like a document.

Single theme, dark. A light mode is explicitly out of scope for this pass (committing to one look beats
two half-done ones).

---

## 2. Typeface pairing — the **IBM Plex** trio (one family, three voices)

One type system, three voices, and the mapping itself carries meaning:

| Voice | Face | Used for | Why |
|---|---|---|---|
| **The machine speaks** | **IBM Plex Mono** | confidence %, identifiers, timestamps, field paths, SLA, doc ids, JSON | machine data should *look* like machine data; Plex Mono reads as terminal/instrument, tabular by nature |
| **The interface speaks** | **IBM Plex Sans** | field labels/values, register, chrome, buttons | a precise neo-grotesque, excellent at 11–15px, `tabular-nums` for aligned numerics |
| **The human speaks** | **IBM Plex Serif** | the **source-text panel only** (the customer's own words) | sets the material under examination as a *document*; differentiates reading-material from scanning-material at a glance (your brief: the two panels "should not share a treatment") |

**Why Plex over the obvious picks:** the three faces are drawn by one team to shared metrics, so using
all three reads as *one deliberate system*, not three fonts bolted together — and it sidesteps the
default stack (Inter/system) that makes everything look like the same Tailwind site. Runner-up was Geist
Sans + Geist Mono (more Linear, but no coherent serif sibling for the source panel).

**Licence:** all three are **SIL OFL 1.1** — permissive, redistribution-safe, clears the ledger's
*distribution* test (TECH-SPEC §6; we ship on-prem, so this matters). I'll **pin-then-verify the licence
on the installed version** before it's load-bearing, per the ledger rule.

**Loading:** self-hosted **woff2 via Fontsource** (`@fontsource/ibm-plex-{sans,mono,serif}`), **Latin-
basic subset** (`@fontsource/…/latin.css`) — no render-blocking CDN, no external request (also keeps it
working on-prem/air-gapped). `font-display: swap`. Weights loaded: **Sans 400/500/600**, **Mono
400/500**, **Serif 400 + 400 italic**.

**APPROVED with two conditions (owner):**
1. **Subset it** — Latin-basic (the Fontsource `latin` CSS entrypoints), not the full family.
2. **Serif is for VERBATIM CUSTOMER TEXT ONLY** — the source-text panel's raw normalised content (the
   customer's own words/transcript/OCR, unedited). **Never** an extracted field value, a model summary
   (`fault`), a confirmation, or anything the model produced. The moment machine output appears in the
   human voice, the mapping stops carrying meaning and becomes decoration. Enforced in code by scoping
   the serif class to the source panel alone; every field value / model output stays Sans or Mono.
   *(Interpretation, owner-aligned: a faithful verbatim transcript/OCR is the human's words; a model
   **summary** of them is not — and `fault` is exactly such a summary, so it stays Sans.)*

---

## 3. Palette — dark-first, **two signal accents and nothing else competing**

The discipline your brief demands: **one accent for uncertainty, one for committed, everything else
neutral.** If everything is coloured, nothing is signal. Colour is spent only where it *is* the
information.

**Neutral ground (the instrument body) — near-black, layered by elevation:**

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0d0f12` | app canvas (near-black) |
| `--surface` | `#14171c` | register + panels |
| `--surface-2` | `#1a1e24` | raised (decision bar, cards, modals) |
| `--surface-3` | `#22272e` | hover / active fill |
| `--line` | `#262b32` | hairline rules (1px) |
| `--line-strong` | `#333a43` | a stronger divider where structure needs it |
| `--ink` | `#e6e9ee` | primary text |
| `--ink-2` | `#9aa4b1` | secondary text |
| `--ink-3` | `#6b7480` | muted / meta / dim |

**The two signal accents:**

| Token | Value | **Sole role** |
|---|---|---|
| `--uncertain` | `#f5a524` (amber) | **UNCERTAINTY.** Low-confidence fields, the "needs review" flag, the confidence spine/meter. This is the loud one — findable in under a second from across the room. |
| `--committed` | `#3fb950` (green) | **COMMITTED.** The approval badge, the committed-state seal, the approve→approved transition. Nothing else is green. |

**Narrow alarm exception (used sparingly, never decoratively):**

| Token | Value | Role |
|---|---|---|
| `--alarm` | `#f0553a` (red) | genuine alarms only: error banners, and the `contradicts` provenance (record-vs-complaint discrepancy). Not a general accent. |

**Priority (P1–P4) is a neutral intensity ramp, NOT four rainbow colours** — so it never competes with
the two signals. P1 = brightest ink on `--surface-3`; P4 = dim ink, quiet. Urgency reads as *contrast/
weight*, not hue. (A hot P1 would steal the eye from the amber that actually needs it.)

Provenance role chips (`primary`/`corroborating`/`derived_from`) are neutral; only `contradicts` uses
`--alarm`. Correction diffs: previous value in `--ink-3` strike-through, new value in `--committed`.

---

## 4. Type scale (Plex, tabular where numeric)

A real scale — hierarchy from size + weight, not boxes and borders.

| Token | px / line-height | Use |
|---|---|---|
| `--t-micro` | 10.5 / 1.3 | uppercase field labels, chip text |
| `--t-meta` | 12 / 1.4 | metadata, register sub-line (mono for machine bits) |
| `--t-ui` | 13 / 1.45 | default UI / buttons |
| `--t-value` | 14.5 / 1.4 | governed field values (the scan target) |
| `--t-read` | 15.5 / **1.7** | **source text panel (serif)** — reading measure, ~68ch max |
| `--t-title` | 17 / 1.3 | case id / section headers |

Weights: Sans 400 body, 500 values, 600 labels/headers. Mono 400 data, 500 emphasised numerics.
`font-variant-numeric: tabular-nums` on every number that sits in a column (confidence, SLA, counts).

---

## 5. Spacing, radius, rules

4px base unit — one scale, referenced by token, no magic values:

`--sp-1: 4 · --sp-2: 8 · --sp-3: 12 · --sp-4: 16 · --sp-5: 20 · --sp-6: 24 · --sp-8: 32`

- **Radius:** `--r-sm: 3px` (chips, meters), `--r: 5px` (inputs, buttons, cards). Tighter than today's
  8px — instruments have crisp corners, not rounded ones.
- **Rules:** 1px `--line`, hairline. Structure comes from rules + surface elevation, **not** from boxing
  every field in a bordered card.
- **Vertical rhythm over horizontal decoration:** fields scan as a column (see §6).

---

## 6. Signature treatments (the moments worth designing)

**Confidence — the "loud from across the room" mechanic, STEPPED not continuous.** Every governed field
carries a **confidence spine**: a 2px vertical bar on its left edge. Confidence is
`P(correct | predicted class) × grounding`, and after the `n<10` cell flooring there are only ~6 trusted
reliability values per field — it is **not** a continuous per-field measurement. So the spine uses
**discrete steps, never a smooth gradient** (a fade would imply precision that doesn't exist — the same
failure mode as implying per-case difficulty). **Five bands:**

| Band | Confidence | Spine |
|---|---|---|
| `--conf-flag` | ≤ 0.50 (the "needs review" line) | solid amber, full height — the loudest thing on screen |
| `--conf-low` | 0.50–0.70 | strong amber |
| `--conf-mid` | 0.70–0.85 | medium amber |
| `--conf-high` | 0.85–0.95 | faint amber |
| `--conf-sure` | > 0.95 | none (bare hairline) — confidence recedes |
| (null) | no confidence | neutral dot, no amber |

A low-confidence field *glows amber down its edge*; a confident one has no edge — findable without
reading a digit. The mono `%` stays for the exact value. Per-**field** signal only; the register's
class-level ordering copy is untouched (no per-case difficulty implied). *Design truth over polish.*

**Fields scan as a column, not cards.** The governed core becomes a single tabular column: `label`
(mono-ish, dim, left) — `value` (Plex Sans 500, prominent) — spine + `%` (right, mono). `fault` (prose)
spans full width. This replaces today's `auto-fill` card grid, per your brief ("fields should scan as a
column"). Emergent attributes stay a tight table.

**"Not stated" is a first-class state.** Rendered as a deliberate, quiet row — `not stated` in muted
italic with a subtle diagonal-hatch left marker — reading as *the system chose not to guess*, never as
an empty cell or an error. It sits in the column like any other field, just quieted.

**The decision bar speaks with rules-engine authority.** Its own raised surface (`--surface-2`) with a
mono treatment and a small `RULES` tag, visually separated from anything model-generated. Priority (mono
pill, neutral ramp) · routing · SLA (mono, tabular, due time) · the one-sentence rationale in plain
authoritative type. It should feel deterministic and distinct from the extracted fields above it.

**The commit gate — visible, weighty, and keyboard-native (UPDATED 2026-08-23: single-key `c` + undo
window, superseding the `c`-arms/`Enter` two-step).** Pre-approval: a prominent `approve (c)` action;
**no report button exists**. **`c` commits immediately** — no arming step — because the previously-deferred
**undo window is now built** (engine `POST /api/cases/{id}/uncommit`, `UNDO_WINDOW_SECONDS`). This is the
owner-blessed long-term answer to commit irreversibility that the old two-step was a stopgap for: instead
of taxing *every* approval to guard against a rare double-tap, a fresh approval is reversible for a few
seconds and durable after. On approval a green **undo toast** appears — `Approved. Nothing external has
been issued yet — you can still undo. undo (Ns) · u` — counting down; `u` (or the button) reverts the case
to `in_review` within the window, 409 after. Nothing external fires on commit alone (the report is pulled
on demand, §3), so undoing before any report is issued leaves no external trace. The chrome still
transforms on approval: a `--committed` green seal stamps `APPROVED · <reviewer>`, a green left-edge on the
case, the approve action replaced by `report (r)`; the HUD freezes at `done`. Pre-approval vs committed is
unmistakable across the room.

**Review-time HUD (new 2026-08-23).** Because τ=1.01 routes nothing automatically, every case is cleared
by a human and **time-to-approve is the load-bearing gate** (winning-condition §4, ≤30s). The case header
carries a live `⏱ <elapsed> · median <tenant median> (n)` readout — amber once a case passes 30s — so the
number being optimised is visible while working, not discovered after. Measured client-side (only the
browser knows when a human started looking) and logged at approval (`review_event`).

**One-key correction (new 2026-08-23).** For a closed-vocabulary governed field the allowed values render
as number-key picks (`CORRECT TO — PRESS THE NUMBER`, `1`–`9`, current value excluded) — the biggest
single lever on review time: a mis-classification becomes one keystroke, not typing. Honest label: the
*allowed* set (from `/api/field-options`), not a claimed likelihood ranking (no per-value probability
exists).

**Triage + batch approve (new 2026-08-23).** The register splits into a "nothing flagged for review" band
(every governed field above the 0.5 flag line) and the needs-you remainder; `approve all N clean` clears
the whole band in one act (still a per-case human approval, §3). Honest: "nothing flagged" is a class-level
band, not a per-case safety guarantee (§10 CORRECTION) — the floor is the same 0.5 line the flag uses, so
it's reachable, unlike an aspirational high-confidence threshold on a MIN-of-products signal.

**The empty register is a first impression, designed.** A new tenant sees a quiet centred state: one
line naming what this screen is, and the `+ submit your first case` action — never a blank rail.

**The ~17s intake wait shows the pipeline, not a spinner.** A staged indicator walks
`normalising → transcribing → extracting → deciding` (the real pipeline order), advancing on a timer
since the request is synchronous with no progress events. Honest about being stage-labels not telemetry;
it shows *what is running*, not a fake percentage. `prefers-reduced-motion` → the stages show statically,
no shimmer.

**Motion — a machine responding, not a website performing.** Focus transitions and highlight reveals
only, ≤150ms, ease-out. No page transitions, no skeleton shimmer, no easing flourishes. All of it inside
`@media (prefers-reduced-motion: reduce)` → none.

**Click-to-trace stays exact.** Sentence `<mark>` (amber-tinted highlight, not softened), the wavesurfer
audio region, and the image bbox overlay keep their precision — I only retune their colours to the
tokens (e.g. region fill → amber-derived), never soften or animate away the exactness. wavesurfer,
react-pdf, react-hotkeys-hook all stay; styled, not replaced.

**White source documents are MATTED, not flush.** A scanned invoice or photographed receipt is a large
white rectangle; dropped flush onto near-black it glares and undoes the whole low-glare argument for
going dark. So the image/PDF provenance viewer gets its **own contained frame**: a matte surround
(`--surface-2`) with padding around the document, an inset shadow, and a hairline — the white sits *in*
a panel, never against the canvas. The bbox overlay geometry is unchanged (precision preserved); only
the surround is matted.

---

## 7. Layout — three zones, tested at 1440 and 1280

```
┌────────────┬───────────────────────────────┬──────────────────┐
│  REGISTER   │  CASE                          │  FIELD DETAIL     │
│  rail       │  ┌ header (id · state)        │  provenance       │
│  ~284px     │  ├ decision bar [RULES]       │  + citations      │
│  queue,     │  ├ governed core (column)     │  + trace          │
│  class-     │  ├ emergent (table)           │  (audio/image)    │
│  reliability│  └ source text (serif)        │  + edit           │
│  first      │                                │  ~340px           │
└────────────┴───────────────────────────────┴──────────────────┘
```

Persistent narrow register rail (left) · dominant case detail (centre) · provenance/field detail
(right). At **1280** the right panel narrows to ~300px and the register to ~260; the centre stays fluid
and never drops below a readable measure. Below 900px it stacks (register → case → detail), as today.
Horizontal scroll is never allowed on the body; wide content (tables, JSON, waveform) scrolls inside its
own container.

---

## 8. Non-negotiables — how the design keeps each

- **Keyboard flow sacred** (`j/k n/p e r ?` unchanged; `1`–`9` one-key correction, `c` commits, `u` undoes, §10):
  no visual change costs a keystroke. Selection and focus states are re-skinned, not re-wired. The
  approve change makes the gate *more* keyboard-native (drops the browser modal), not less.
- **Uncertainty is the primary signal:** the amber confidence spine (§6) is the single loudest thing.
- **Click-to-trace exact:** precision untouched; colours retuned to tokens only.
- **"Not stated" first-class:** designed as a deliberate quiet state (§6).
- **Commit gate visible; report absent before approval:** enforced in the chrome transform (§6).
- **Confidence ordering class-level:** register ordering + its "class reliability" copy untouched; the
  spine is a per-field signal and is not presented as per-case difficulty.

## 9. Preserved test anchors (`App.test.tsx`)

The title text **"Adaptive Intake — Review"**, an input with **`aria-label` matching /tenant id/i**, and
the empty-state text **"Set a tenant id to load cases."** all remain. `pnpm tsc` + `pnpm vitest` stay
green, tests unmodified.

## 10. Speed-vs-weight on approve — RESOLVED, then SUPERSEDED 2026-08-23 (undo window built)

History: `c` first fired a browser `window.confirm()` (broke keyboard flow); owner call 2 replaced it with
`c` ARMS / `Enter` COMMITS (different keys, so a double-tap can't commit). That two-step was always a
stopgap for the real fix, which was logged as deferred engine work: an **undo window**.

**Now built (2026-08-23): `c` commits immediately + a short undo window** (`POST /api/cases/{id}/uncommit`,
`UNDO_WINDOW_SECONDS`, `u` to undo). This is strictly better on review time — it stops taxing *every*
approval to guard against a *rare* accidental one — and it is honest: nothing external happens on commit
alone (the report is pulled on demand, §3), so a fresh approval reversed within the window leaves no trace.
Past the window the approval is durable (server-authoritative clock). The arm/`Enter` two-step is retired.
See §6 for the toast + HUD detail. *(This changes owner call 2; it realises the successor the owner had
already blessed as the long-term answer — flagged here so it's a visible, logged decision, not a silent
drift.)*

## 11. New dependencies (justified, permissive)

| Dep | One-line justification | Licence |
|---|---|---|
| `@fontsource/ibm-plex-sans` | self-hosted UI typeface, no CDN | OFL-1.1 |
| `@fontsource/ibm-plex-mono` | self-hosted machine-data typeface | OFL-1.1 |
| `@fontsource/ibm-plex-serif` | self-hosted source-text (document) typeface | OFL-1.1 |

No component library (no Material/Chakra/Ant), no Tailwind — hand-written CSS with custom properties, as
your brief prefers. React 18 + Vite unchanged. wavesurfer/react-pdf/react-hotkeys-hook kept.

---

## 12. Build order once signed off

1. `@fontsource` deps (pin + verify OFL on the installed version).
2. **Design tokens** — every value in §3–§5 as CSS custom properties in one `:root` block; nothing
   downstream uses a raw hex/px.
3. Re-skin the shell (topbar, layout, register, empty state).
4. Rebuild the case: governed-core column + confidence spine, decision bar, source (serif), not-stated,
   commit-gate transform, field-detail/provenance.
5. Retune the trace colours (mark, audio region, image box) to tokens.
6. Intake pipeline indicator.
7. `pnpm tsc` + `pnpm vitest` green; **`nabu-ui-test`** on desktop + mobile until clean, 0 console
   errors, no overflow; walk a case start→finish by keyboard and time it (<30s).
