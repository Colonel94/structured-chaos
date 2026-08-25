"""Which eval dataset the harness operates on — so the same scripts score any domain set, not just
CFPB. Select with the ``EVAL_DATASET`` env var (default ``cfpb``):

    EVAL_DATASET=multidomain uv run python eval/run_extraction.py
    EVAL_DATASET=multidomain uv run python eval/score.py

``cfpb`` = the financial stress-test (one sector); ``multidomain`` = real PRODUCT + SERVICE complaints
across many sectors (auto/electronics/retail/restaurants/travel/utilities/home/health/legal) — the set
that actually tests the domain-agnostic §4 claim off the financial domain.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "fixtures"

DATASET = os.environ.get("EVAL_DATASET", "cfpb").strip() or "cfpb"

SAMPLE = _DIR / f"{DATASET}_sample.jsonl"
EXTRACTIONS = _DIR / f"{DATASET}_extractions.jsonl"
LABELS = _DIR / f"{DATASET}_labels.csv"
INSTRUCTIONS = _DIR / f"{DATASET}_labels_INSTRUCTIONS.md"

# ---------------------------------------------------------------------------------------------------
# Tune / held-out split — so a tuning-derived prompt change is NEVER scored on the same cases its signal
# came from (CLAUDE.md §10: "No tuning PR merges while the scoring set and the signal set are the same
# data."). Without this the tuning merge gate is decorative: a delta drafted to fix errors on the 216
# scores better on the 216 by construction. ~30% of EACH dataset is reserved as the held-out SCORING
# slice; the other ~70% is the only slice tuning signal may be drawn from. Deterministic by a stable hash
# of the row id (no data file, reproducible across machines/CI, disjoint by construction).
#
# The FULL-SET number (`all`, the §8 scorecard) is unchanged and stays the default — only the tuning gate
# selects `heldout`. When the INDEPENDENT holdout labels land (eval/fixtures/holdout_labels.csv, currently
# blind/owner-blocked) that becomes the STRONGER gate; until then this split is the usable-now break.
HELDOUT_PCT = 30
# 'all' (default — full set, the scorecard) | 'tune' (~70%, the only signal source) | 'heldout' (~30%).
SPLIT = os.environ.get("EVAL_SPLIT", "all").strip().lower() or "all"


def split_of(row_id: object) -> str:
    """'heldout' for the reserved scoring slice, else 'tune'. Deterministic in the row id (stable hash)."""
    h = int(hashlib.md5(str(row_id).encode("utf-8")).hexdigest(), 16)
    return "heldout" if (h % 100) < HELDOUT_PCT else "tune"


def in_active_split(row_id: object) -> bool:
    """Whether a row is scored under the current EVAL_SPLIT ('all' scores everything)."""
    return SPLIT == "all" or split_of(row_id) == SPLIT
