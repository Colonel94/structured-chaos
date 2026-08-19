"""Calibrated per-field confidence + selective-prediction routing (Phase 6, EDD §10).

The trust metric "refuse to guess": confidence is CALIBRATION on the human gold (the reliability of a
predicted value), not the model's degenerate self-reported number. Below the auto-route threshold a field
is flagged and routed to review, never confidently filled wrong.
"""

from __future__ import annotations

from .model import (
    Calibration,
    FieldCalibration,
    FitRow,
    fit,
    load_calibration,
    save_calibration,
)

__all__ = [
    "Calibration",
    "FieldCalibration",
    "FitRow",
    "fit",
    "load_calibration",
    "save_calibration",
]
