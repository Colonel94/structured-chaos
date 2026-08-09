# GOVERNED-CORE-SCHEMA.md — universal governed core + emergent seed reference (Phase-5 input)

*The minimal, universal governed core (human-controlled, **seeded** — the AI never creates a field here)
and the two built verticals' **expected-emergence reference sets** (for eval labelling + convergence
targets — **never seeded into any tenant schema**). Feeds Phase 5 (object store + entity resolution +
anchor+2) and Phase 4 (extraction + self-converging schema + scorer). Source contracts:
`concept-adaptive-intake.md` §4, `SOLUTION-EDD.md` §6 + §16.1–16.2, `PRD.md` §4a + FR-14,
`longterm_context.md` §10.1. Version 1.0 — 2026-08-09.*

---

## 0. The one rule that governs this whole file

**The governed core is minimal and universal; domain specialisation is emergent, never seeded**
(`longterm_context.md` §10.1). Two consequences that this document must not violate:

1. **Seeded (this file, §1–§3):** the universal governed core + the universal starter taxonomy + the
   universal default SLA policy. Identical for a bakery and a ministry. Human-controlled. The AI never
   writes a field into the governed core; it only *extracts into* the universal fields and *proposes
   candidates* that promote in via the §6 pipeline.
2. **NOT seeded (this file, §4–§6):** every vertical-specific attribute (`flavour`, `technician`,
   `warranty_status`, …). These must be **discovered** by the engine on real data, or the convergence
   moat is fake. Pre-loading them would violate the zero-config setup gate (winning-condition §2),
   §10.1 ("never seeded"), and CLAUDE.md §10-Q3 ("never grade the moat on data you authored"). The
   "seed lists" in §5 are therefore **eval-harness reference sets only** — ground-truth vocabulary and
   convergence targets — and live in test fixtures, never in a migration, a `governed_core` row, or an
   emergent-store row.

If a future change tries to put a bakery field in a migration, stop: that is the service-business-in-a-
product-costume red flag (CLAUDE.md §8), and it disqualifies the moat.

---

## 1. Universal governed core — the minimal fields every complaint has

Four blocks. Every **value** in blocks A–C carries the full provenance chain via the append-only
`field_extraction` / `field_correction` logs (`source_span`, `model`, `model_version`,
`prompt_version`, `confidence`, `run_id`, `reviewer_id`, timestamps — EDD §7.2); provenance is a
per-value invariant, not repeated per field below. `field_current` is the disposable projection.

### Block A — Anchor & identity *(keys, not content fields — resolved, never asked)*
The anchor is a **key, not a field** (concept §4.3). Everything here is looked up, not interrogated.

| Field | Type | Meaning / role | Notes |
|---|---|---|---|
| `sender_identity` | text | The channel handle the message came from (WhatsApp phone / email). **The universal anchor** — §4a: sender phone resolves to the tenant's object. | Always present; it is the default anchor even when no key is quoted. |
| `anchor_value` | text · nullable | An explicit key the customer stated (order #, job #, tracking #, booking ref) if any. | Optional; strengthens/uniquifies the match. |
| `object_ref` | fk · nullable | The matched object in the tenant object store (order/job/booking/…). The **"which object"** unknown, resolved by §16.1 entity resolution. | Nullable = the no-object fallback (walk-in/prospect) — the case still exists. |
| `object_match_status` | enum | `silent` · `confirmed` · `ambiguous` · `none`. | Silent match **only when exactly one candidate** (protects the ≥99% metric, EDD §16.1). |
| `object_match_confidence` | float | 0–1. | Feeds review flagging. |

### Block B — Universal content core *(AI extracts INTO these; it may NEVER create a new field here)*
The "handful of facts every complaint has regardless of industry" (§10.1). This is the entire seeded
content surface — a cake store and a government run on exactly these.

| Field | Type | Meaning / role | Rule |
|---|---|---|---|
| `category` | enum (taxonomy §2) | Zero-shot into the universal starter taxonomy; sits in its **nearest parent** until a tenant category is human-activated (FR-14). | Deadline-bearing → activation is human-gated (§2). |
| `fault` | text | **What specifically was wrong** (concept unknown #2). Closed-world grounded in the source. | Free-text summary; a normalised `fault_type` is an emergent/promoted refinement, not seeded. |
| `desired_outcome` | enum | The **one fact that can never be inferred** (concept §4.3): `refund` · `replacement` · `repair_redo` · `acknowledgement` · `information` · `escalation` · `other`. | **Always elicited if absent** — the one question we always ask. |
| `emotion_signal` | enum + float | `calm` · `frustrated` · `angry` (+ optional score). Emotion is **data**, not content (concept §4.4). | Drives "angry **and** incomplete → route to human, don't interrogate." |
| `severity_signal` | enum/flags | Model-supplied severity/safety hints: `safety_health` · `vulnerable_party` · `financial_harm` · `none`. | An **input** to the rules engine, never the SLA itself. |

### Block C — Deterministic decision outputs *(rules engine; reproducible; NEVER model output)*
Computed from `category` + `severity_signal` + entities + tenant policy. **Same inputs + same policy →
same result, explainable in one sentence** (CLAUDE.md §3). Stored with the policy version that produced
them, for audit.

| Field | Type | Meaning |
|---|---|---|
| `priority` | enum | Rules-engine output. |
| `sla_policy_id` | fk | Which policy applied (universal default ships; tenant text overrides — §16.2). |
| `sla_due_at` | timestamptz | **Clock starts at `first_contact_at`, not at completeness** (CLAUDE.md §3). |
| `routing_target` | text | Queue / team. Auto-route only for high-confidence, unambiguous cases. |
| `policy_version` | text | The exact policy revision that produced the three outputs above. |

### Block D — Lifecycle / system *(structural, domain-independent)*

| Field | Type | Meaning |
|---|---|---|
| `tenant_id` | uuid · NOT NULL | RLS key on every tenant table (EDD §7.1). |
| `case_id` | uuid | The case. **Created on first contact, incomplete, never blocked on completeness** (CLAUDE.md §3). |
| `case_state` | enum | `created` → `incomplete` → `actionable` → `in_review` → `committed`. |
| `first_contact_at` | timestamptz | The clock start. |
| `channel` | enum | `whatsapp` · `email` · `file_drop`. A channel is an adapter producing the same normalised input. |
| `question_count` | int | The **anchor + ≤2** budget counter, **enforced in code**, not model judgement (CLAUDE.md §3). |
| `external_mappings` | jsonb | Canonical field → external-system field IDs, **on the `governed_core` registry from day one** (EDD §16.5). Empty in the PoC; its existence prevents a Phase-2 rewrite. |

### The two schema tiers (how B/C relate to what grows)
- **Universal governed core** = Blocks A–D above. Seeded, identical for every tenant, human-controlled.
- **Per-category promoted governed fields** = **empty on day one for every tenant.** Grows *only* by
  promotion (§6): `support_count ≥ 4` **and** non-null rate ≥ 0.50; a **category** promotion is stricter
  still (human click + ≥15 distinct cases + mandatory SLA mapping — §16.2). On promotion a field acquires
  type/unit/validation and **history is backfilled 100%**. This is where domain specialisation lives —
  and it is emergent.

**Actionable floor is derived, not authored.** Universal floor = the three unknowns
(`object_ref`, `fault`, `desired_outcome`). Per activated category it grows to that category's promoted
governed fields (EDD §16.2). The elicitation budget drills only the difference, anchor + ≤2.

---

## 2. Universal starter taxonomy *(seeded; hierarchical; ~6–8 archetypes + `UNCLEAR`)*

Day-one zero-shot target so zero-config delivers value; every candidate has a nearest parent
(EDD §16.2). Tenant sub-categories are discovered automatically but **never auto-activate** — a wrong
category is a wrong deadline.

| Archetype | Covers (illustrative, cross-domain) |
|---|---|
| `product_fault` | wrong/missing/defective item, quality, freshness, spec mismatch |
| `service_fault` | poor workmanship, incomplete work, repeat/recurring fault, service not delivered |
| `delivery_fulfilment` | late, not delivered, wrong address, damaged in transit, no-show for a slot |
| `billing_charge` | overcharge, wrong price, unexpected fee, refund not processed |
| `access_availability` | can't book, unavailable, denied access, appointment problems |
| `staff_conduct` | rudeness, unprofessional behaviour, dispute with staff |
| `safety_health` | allergen, injury risk, hygiene, gas/electrical hazard — **deadline-bearing** |
| `other` | genuine catch-all |
| `UNCLEAR` | below the classification floor → route, don't guess (feeds the abstention SLA) |

---

## 3. Universal default SLA/priority/routing policy *(seeded; overridable)*

A universal default ships so a tenant gets deterministic value with **zero input**; the tenant's
written policy text (optional) **overrides** it. Policy is refinement, never a setup gate (§16.2).
Inputs = `category` + `severity_signal` + entities; outputs = Block C. `safety_health` and
`vulnerable_party` escalate priority regardless of category. (Concrete default table is a Phase-6
deliverable; this file fixes the interface, not the numbers.)

---

## 4. The emergent layer *(seeded with NOTHING)*

Unbounded attribute store. Each attested attribute row: stable-hashed `field_name`, `value`, inferred
`type`, **BGE-M3 1024-d** embedding, `support_count`, provenance. Domain specialisation emerges here and
promotes upward via §6. **On day one this table is empty for every tenant, in every vertical.**

---

## 5. Expected-emergence reference sets *(the "seed lists" — EVAL HARNESS ONLY, never a live schema)*

**Read §0 first.** These are the vocabularies a human uses to **label eval ground truth** field-by-field
(EDD §16.7) and the **convergence targets** the monitor checks discovered fields against (recall of the
expected set; duplicate ratio <5%). They belong in `eval/fixtures/`, never in a migration, a
`governed_core` row, or the emergent store. The engine must **discover** these from real cases — that
discovery, with zero config, *is* the moat demonstration.

Source of the anchor attributes: PRD §4a. Groupings and the rest are the expected long tail to label
against, not an exhaustive prescription.

### 5.1 Bakery — object = **order** *(order-shaped: item-centric, one-shot transaction)*

| Group | Expected emergent attributes |
|---|---|
| Item | `item_name`, `flavour`, `size`, `quantity`, `inscription_customization`, `dietary_allergen_flag`, `missing_item`, `wrong_item` |
| Fulfilment | `delivery_slot`, `promised_time`, `actual_delivery_time`, `driver`, `delivery_method` (pickup/delivery), `packaging_condition`, `temp_on_arrival` (freshness/melt) |
| Quality | `freshness`, `taste_issue`, `appearance_decoration_issue`, `staleness` |
| Commercial | `order_value`, `payment_method`, `discount_voucher` |

- **Anchor attributes (PRD §4a):** `flavour`, `delivery_slot`, `driver`, `temp_on_arrival`.
- **Typical faults → archetype:** wrong/missing item → `product_fault`; late → `delivery_fulfilment`;
  quality/freshness → `product_fault`; **allergen → `safety_health`** (deadline-bearing); overcharge →
  `billing_charge`.
- **Common desired outcomes:** `refund`, `replacement` (remake), `repair_redo` (redeliver),
  `acknowledgement`.

### 5.2 Home maintenance — object = **job visit / work order** *(visit-shaped: recurrence, workmanship over time)*

| Group | Expected emergent attributes |
|---|---|
| Job / visit | `job_no`, `visit_date`, `scheduled_window`, `technician`, `trade` (plumbing/AC/electrical/…), `unit_no`, `arrival_status` (no-show/late) |
| Work | `work_performed`, `parts_used`, `workmanship_issue`, `recurring_fault` (repeat visit), `warranty_status`, `follow_up_required` |
| Commercial | `quoted_price`, `charged_amount`, `overcharge_flag`, `payment_method`, `invoice_no` |
| Condition | `damage_caused`, `safety_issue` (gas/electrical), `incomplete_work` |

- **Anchor attributes (PRD §4a):** `technician`, `trade`, `parts_used`, `warranty_status`, `unit_no`.
- **Typical faults → archetype:** no-show → `delivery_fulfilment` / `access_availability`; poor
  workmanship → `service_fault`; recurring fault → `service_fault`; overcharge → `billing_charge`;
  damage in service → `product_fault` (property); safety issue → `safety_health`.
- **Common desired outcomes:** `repair_redo` (revisit), `refund` (or partial), `escalation` (warranty
  honour), `acknowledgement`.

### 5.3 Why these two prove generalisation (the contrast that matters)
Same governed core (§1), same anchor (sender phone → the tenant's object), same taxonomy (§2), same
default policy (§3) — yet the **emergent layer diverges sharply**: bakery converges on
item/flavour/delivery/temperature; home maintenance converges on technician/trade/workmanship/warranty
and carries **recurrence over time** (repeat visits) that an order does not. That divergence, arising
with **zero configuration**, is the self-converging-schema moat shown at its strongest. The other four
§4a verticals are added only when a real customer needs one (PRD §4a scope note) — not as synthetic dev
breadth.

---

## 6. Promotion pipeline this schema plugs into *(reference; full detail EDD §6)*

`PROFILE (deterministic) → EXTRACT into emergent, closed-world grounded to attested set ℱ →
DEDUP/CANONICALIZE (BGE-M3 cosine: merge τ=0.85, admit-new τ=0.70, 0.70–0.85 = one LLM adjudication) →
PROMOTE (support_count ≥ 4 AND non-null ≥ 0.50; categories stricter, §16.2) → STRUCTURAL INFERENCE →
BACKFILL (idempotent, bounded, 100% correct)`. Convergence monitor: new-fields-per-100-cases must
decline & flatten; duplicate ratio <5% (internal SLO). **Graded on real collected data, never
author-generated synthetic** (BUILD-PLAN Phase 4 / CLAUDE.md §10-Q3).

---

## 7. What this file deliberately does NOT do
- Does **not** enumerate a per-category governed field list — those are *promoted*, not authored.
- Does **not** fix SLA numbers — §3 fixes the interface; the default table is Phase 6.
- Does **not** seed any vertical attribute — §5 is eval-harness reference, quarantined from live schema.
- Does **not** cover the local/PHI-strict tier (deferred with the local stack, EDD §16.9).
