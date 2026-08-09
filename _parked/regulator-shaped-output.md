# PARKED — Regulator-shaped output (do not open until the owner re-raises it)

*Owner directive (2026-08-09): regulator-shaped output is **parked and not to be discussed** until the
owner raises it again. This file is a sealed archive of the analysis so the work is retained but out of
the active governing docs. Do not surface, cite, or act on anything here until explicitly re-raised.*

---

## What is parked
- The idea of the "one report" mimicking a **regulated complaint artefact** as a moat.
- The **DHA (Dubai Health Authority) patient-complaint register** as the chosen artefact.
- The regulated-artefact comparison and the "regulator-shaped GCC output" third-moat framing.

The active PoC ships a **universal manager register** (our layout carrying the tenant's data, via
WeasyPrint) — that is unaffected and stays.

## Retained analysis (do not action)
- DHA won a four-candidate comparison (vs Dubai Municipality food safety, Ministry of Economy consumer
  protection, TDRA telecom) on: universal licence-linked obligation on the buyer; real enforcement
  (Exec Council Resolution 49/2024 — closure/suspension ≤3mo); and **no free government incumbent**
  (food safety loses to DM's free mandatory FoodWatch; TDRA disqualified — the SMB is the complainant,
  not the obligated party; an insurance broker would fall under CBUAE/Sanadak).
- Basis: DHA ST-45 §5.4.13 (patient-complaint policy) + MA-03 §11.1 (complaint monitoring/recording
  system). Mainland delegates the schema; the closest published shape to mimic is the DHCC §7.2 central
  register: `complaint_id · date_received · complainant · category · description · acknowledgement_date ·
  root_cause · corrective_action · resolution + notification · closure_date`.
- Soft spot: no published numeric DHA facility SLA → would be pitched as inspection-readiness, not a
  statutory deadline.
- Tooling implication (if un-parked): if the artefact is an exact stamped form → AcroForm fill (pypdf)
  or pypdfium2 overlay, not HTML→PDF; prove the Arabic PDF in a throwaway script first.
- Residency implication: a clinic = patient health data (Federal Law 2/2019 Art. 13) → local-only
  deployment. (Note: the local-deployment / health-tenant / PHI machinery in the active docs stands on
  **data-residency** grounds for any health/finance tenant — it is independent of this parked topic.)
