# Phase 0.5 — de-risk spike (THROWAWAY)

*Three tiny scripts, zero integration. Kill or confirm the three riskiest proofs the whole
build rests on, in isolation, before Phase 1. A red here is cheap; a red at Phase 7 is not.
Delete this directory once the verdict is recorded in `longterm_context.md` §0.*

The three proofs (BUILD-PLAN Phase 0.5):

| # | Script | Proves | Inputs (owner-recorded, Gate A5) | Runs on |
|---|--------|--------|----------------------------------|---------|
| 1 | `spike1_asr.py` | Real noisy Gulf voice note → usable transcript (the ASR moat) | `data/spike/audio/voice_*.opus` | HOST (faster-whisper; GPU if CUDA/cuDNN present, else CPU) |
| 2 | `spike2_doc.py` | Photographed, stamped, bilingual doc → readable fields (vision path) | `data/spike/docs/doc_01.jpg` | CONTAINER (PaddleOCR + pypdfium2) |
| 3 | `spike3_rtl_pdf.py` | Structured row → correct Arabic-RTL PDF (report path) | none — self-contained | CONTAINER (WeasyPrint) |

**Spike 3 needs no owner input — it runs the moment the engine image is built.**
**Spikes 1 & 2 need the Gate-A5 recordings** (`docs/recording-guide.md`, ~1 hour, yours to record).
Until those land, the ASR and doc proofs are *staged, not proven* — do not mark them green.

## Run

```bash
# 1 — ASR (host). Drop your .opus notes in data/spike/audio/ first.
uv run --project engine --group asr python spike/spike1_asr.py

# 2 — bilingual doc (container). Drop your photo at data/spike/docs/doc_01.jpg first.
docker compose --env-file .env -f deploy/docker-compose.yml run --rm \
  -v "${PWD}/data:/app/data" engine python scripts/../spike/spike2_doc.py data/spike/docs/doc_01.jpg

# 3 — Arabic RTL PDF (container). Self-contained; writes artifacts/spike3_rtl.pdf on the host.
docker compose --env-file .env -f deploy/docker-compose.yml run --rm \
  -v "${PWD}/artifacts:/app/artifacts" engine python scripts/../spike/spike3_rtl_pdf.py
```

## Exit gate
Each proof either passes, or the plan changes NOW (swap tool / adjust the claim / re-sequence)
— before Phase 1. Record the verdict per proof in `longterm_context.md` §0.
