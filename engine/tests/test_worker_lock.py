"""Guard test for the single-worker advisory-lock KEY derivation (R2, the zombie-worker footgun).

The live behaviour (a second worker on the same queue-set refuses to start) is proven against a real
Postgres by hand; what a unit test protects is the KEY logic underneath it — that the key is stable
across processes (so two workers actually collide) and that different queue-sets get different keys (so
the intake and backfill workers are allowed to coexist). ``run_worker`` lives in the repo-root
``scripts/`` dir, which is not on the engine test path, so we add it explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_worker import _lock_key


def test_lock_key_is_stable_and_order_independent() -> None:
    # Same queue-set, any order → same key (else two workers would not collide on the same queues).
    assert _lock_key(["default"]) == _lock_key(["default"])
    assert _lock_key(["a", "b"]) == _lock_key(["b", "a"])


def test_different_queue_sets_get_different_keys() -> None:
    # intake (default) and backfill MUST take different keys so compose can run both at once.
    assert _lock_key(["default"]) != _lock_key(["backfill"])


def test_lock_key_fits_a_signed_bigint() -> None:
    # pg_try_advisory_lock takes a signed 64-bit bigint; the key must be in range.
    for qs in (["default"], ["backfill"], ["default", "backfill"]):
        k = _lock_key(qs)
        assert -(2**63) <= k < 2**63
