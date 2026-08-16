"""Which eval dataset the harness operates on — so the same scripts score any domain set, not just
CFPB. Select with the ``EVAL_DATASET`` env var (default ``cfpb``):

    EVAL_DATASET=multidomain uv run python eval/run_extraction.py
    EVAL_DATASET=multidomain uv run python eval/score.py

``cfpb`` = the financial stress-test (one sector); ``multidomain`` = real PRODUCT + SERVICE complaints
across many sectors (auto/electronics/retail/restaurants/travel/utilities/home/health/legal) — the set
that actually tests the domain-agnostic §4 claim off the financial domain.
"""

from __future__ import annotations

import os
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "fixtures"

DATASET = os.environ.get("EVAL_DATASET", "cfpb").strip() or "cfpb"

SAMPLE = _DIR / f"{DATASET}_sample.jsonl"
EXTRACTIONS = _DIR / f"{DATASET}_extractions.jsonl"
LABELS = _DIR / f"{DATASET}_labels.csv"
INSTRUCTIONS = _DIR / f"{DATASET}_labels_INSTRUCTIONS.md"
