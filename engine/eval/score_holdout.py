"""Score the held-out slice once the INDEPENDENT human labels come back (W1) — the four numbers.

The binding constraint on the whole accuracy story: the existing gold is Claude-authored, so every accuracy
figure is "agreement with the labeller", not "correctness" (CLAUDE.md §10 CORRECTION). This script turns
that into a real number by comparing the model against a human who is neither the owner nor me, on 66 fresh
held-out cases.

It computes the owner's four numbers, generically over however many label files you hand it:
  1. model vs OWNER gold          (agreement with the owner's own reading)
  2. model vs INDEPENDENT          (the first honest, non-self-graded accuracy)
  3. OWNER gold vs INDEPENDENT     (how much the two humans agree — the real ceiling)
  4. INDEPENDENT-1 vs INDEPENDENT-2 (inter-annotator, if you can afford two)

Plus the diagnostic the owner asked for (2026-08-22): the desired_outcome / repair_redo split. If the two
HUMANS also disagree on repair_redo, the ENUM is wrong (repair_redo was overloaded with "correct a record"
when record_accuracy arrived — a missing outcome value, one field over from the R6 category fix), not the
model. That is the signal that would justify splitting the enum — measured, not guessed.

Honest stats: n≈66 (fewer per field after co-label filtering). By the rule of three a ≥99% claim needs
~300 clean observations, so every cell prints its n and this is a DIRECTIONAL read, not a gate
([[report-metric-pairs-and-n]]). Report the pair, never a lone number.

Usage:
  # auto-discover fixtures/holdout_labels_<name>.csv (name → the label source), model = holdout_extractions.jsonl
  uv run python eval/score_holdout.py
  # or name them explicitly:
  uv run python eval/score_holdout.py owner=fixtures/holdout_labels_owner.csv independent=fixtures/holdout_labels_alice.csv
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "fixtures"
_MODEL = _DIR / "holdout_extractions.jsonl"

_FIELD_MAP = {
    "gold_category": "category",
    "gold_desired_outcome": "desired_outcome",
    "gold_severity_signal": "severity_signal",
    "gold_emotion_signal": "emotion_signal",
}
_FIELDS = list(_FIELD_MAP.values())
_NULL_ON_BLANK = {
    "desired_outcome"
}  # blank = a real "null" label (only if the source used the column)
# The label space is the owner's governed taxonomy — the "Option Sets" sheet of
# eval/fixtures/holdout_labels.xlsx (v0.2, 2026-08-26, tightened so complaints are not forced into
# coarser buckets). It is a SUPERSET of the extractor's enums (app/extract/schema.py): the extractor
# cannot yet emit transaction_processing / fraud_security / privacy_data / misleading_practice, the six
# new outcomes, privacy_security, or concerned/distressed — so those gold rows will score as mismatches
# until the governed enum is expanded and history re-extracted. That gap is the honest signal; do NOT
# collapse gold to the extractor's coarser set to hide it (CLAUDE.md §10).
_ALLOWED = {
    "category": {
        "product_fault",
        "service_fault",
        "delivery_fulfilment",
        "billing_charge",
        "transaction_processing",
        "record_accuracy",
        "access_availability",
        "staff_conduct",
        "safety_health",
        "fraud_security",
        "privacy_data",
        "misleading_practice",
        "other",
        "unclear",
    },
    "desired_outcome": {
        "",
        "refund",
        "replacement",
        "repair_redo",
        "acknowledgement",
        "information",
        "escalation",
        "correction",
        "cancellation",
        "restore_access",
        "stop_contact",
        "compensation",
        "investigation",
        "other",
    },
    "severity_signal": {
        "safety_health",
        "vulnerable_party",
        "financial_harm",
        "privacy_security",
        "none",
    },
    "emotion_signal": {"calm", "concerned", "frustrated", "angry", "distressed"},
}


def _norm(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    return "" if s in ("", "null") else s


class Source:
    """One label source (a human CSV or the model), exposing value(id, field) and which fields it labelled.

    Mirrors score_phase8: a blank desired_outcome counts as the real label 'null' ONLY when this source
    actually used the column (≥1 non-blank cell); otherwise every blank is an unlabelled skip.
    """

    def __init__(self, name: str, values: dict[str, dict[str, str]], null_ok: set[str]):
        self.name = name
        self._v = values  # id -> {field -> normalised value ("" = null/absent)}
        self._null_ok = null_ok  # fields where "" means a real null label for this source

    def labelled(self, cid: str, field: str) -> bool:
        row = self._v.get(cid)
        if row is None or field not in row:
            return False
        return bool(row[field]) or field in self._null_ok

    def value(self, cid: str, field: str) -> str:
        return (self._v.get(cid) or {}).get(field, "")

    @property
    def ids(self) -> set[str]:
        return set(self._v)


def _load_csv(name: str, path: Path) -> Source:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    values: dict[str, dict[str, str]] = {}
    used: Counter[str] = Counter()
    invalid: list[str] = []
    for r in rows:
        cid = str(r["id"])
        # A blank outcome is a real null only on a row the labeller has otherwise completed. This keeps
        # an in-progress sheet from scoring every untouched row as a correct null prediction.
        active = any(
            str(r.get(col, "") or "").strip() for col in _FIELD_MAP if col != "gold_desired_outcome"
        )
        if not active and not str(r.get("gold_desired_outcome", "") or "").strip():
            continue
        fv: dict[str, str] = {}
        for col, field in _FIELD_MAP.items():
            raw = str(r.get(col, "") or "").strip()
            fv[field] = _norm(raw)
            if fv[field] not in _ALLOWED[field]:
                invalid.append(f"id={cid} {col}={raw!r}")
            if raw:
                used[field] += 1
        values[cid] = fv
    if invalid:
        raise ValueError(f"{path} contains invalid labels:\n  " + "\n  ".join(invalid))
    null_ok = {f for f in _NULL_ON_BLANK if used[f] > 0}
    return Source(name, values, null_ok)


def _load_model() -> Source:
    values: dict[str, dict[str, str]] = {}
    for line in _MODEL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        gov = r.get("governed") or {}
        values[str(r["id"])] = {f: _norm(gov.get(f)) for f in _FIELDS}
    # The model always "labels" every field (a null prediction is a real prediction).
    return Source("model", values, set(_NULL_ON_BLANK))


def _agreement(a: Source, b: Source, field: str) -> tuple[int, int]:
    """Rows both sources labelled for this field where they agree, and the co-labelled total."""
    agree = total = 0
    for cid in a.ids & b.ids:
        if a.labelled(cid, field) and b.labelled(cid, field):
            total += 1
            agree += int(a.value(cid, field) == b.value(cid, field))
    return agree, total


def _report_pair(a: Source, b: Source) -> None:
    print(f"\n### {a.name}  vs  {b.name}")
    per_field_all = []
    for field in _FIELDS:
        ag, tot = _agreement(a, b, field)
        if tot:
            per_field_all.append((ag, tot))
            print(f"   {field:<16}: {ag}/{tot} = {ag / tot:.0%} agree  (n={tot})")
        else:
            print(f"   {field:<16}: no co-labelled rows")
    # combined: rows where BOTH labelled ALL of the fields they share, all matching
    both_ids = [
        cid
        for cid in a.ids & b.ids
        if any(a.labelled(cid, f) and b.labelled(cid, f) for f in _FIELDS)
    ]
    clean = 0
    for cid in both_ids:
        shared = [f for f in _FIELDS if a.labelled(cid, f) and b.labelled(cid, f)]
        if shared and all(a.value(cid, f) == b.value(cid, f) for f in shared):
            clean += 1
    if both_ids:
        print(
            f"   {'ALL-FIELDS':<16}: {clean}/{len(both_ids)} = {clean / len(both_ids):.0%} "
            f"rows fully agree  (n={len(both_ids)})"
        )


def _repair_redo_diagnostic(sources: list[Source]) -> None:
    """The owner's test (2026-08-22): do the HUMANS disagree on repair_redo? If yes, the enum is wrong
    (overloaded), not the model. Shows each source's desired_outcome distribution + every human-vs-human
    disagreement that TOUCHES repair_redo."""
    print("\n" + "=" * 78)
    print("DIAGNOSTIC — desired_outcome / repair_redo split (is the ENUM wrong, not the model?)")
    print("=" * 78)
    for s in sources:
        dist = Counter(
            s.value(cid, "desired_outcome") or "∅"
            for cid in s.ids
            if s.labelled(cid, "desired_outcome")
        )
        print(f"  {s.name:<14} desired_outcome dist: {dict(dist.most_common())}")
    humans = [s for s in sources if s.name != "model"]
    for a, b in combinations(humans, 2):
        touching = 0
        examples = []
        for cid in a.ids & b.ids:
            if not (a.labelled(cid, "desired_outcome") and b.labelled(cid, "desired_outcome")):
                continue
            va, vb = a.value(cid, "desired_outcome") or "∅", b.value(cid, "desired_outcome") or "∅"
            if va != vb and "repair_redo" in (va, vb):
                touching += 1
                if len(examples) < 8:
                    examples.append(f"{cid}: {a.name}={va} / {b.name}={vb}")
        print(
            f"\n  {a.name} vs {b.name}: {touching} disagreements TOUCHING repair_redo "
            f"(if this is high, humans can't agree on it either → split the enum)"
        )
        for e in examples:
            print(f"     {e}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if not _MODEL.exists():
        print(f"no model extractions at {_MODEL} — run eval/extract_holdout.py first")
        return 1

    # Discover label files: explicit `name=path` args, else fixtures/holdout_labels_<name>.csv.
    specs: list[tuple[str, Path]] = []
    for arg in sys.argv[1:]:
        if "=" in arg:
            name, path = arg.split("=", 1)
            specs.append((name, Path(path)))
    if not specs:
        for p in sorted(_DIR.glob("holdout_labels_*.csv")):
            specs.append((p.stem.replace("holdout_labels_", ""), p))

    if not specs:
        print(
            "No filled label files found. Hand fixtures/holdout_labels.csv (+ its INSTRUCTIONS) to an\n"
            "independent labeller; save the returned file as fixtures/holdout_labels_<name>.csv (e.g.\n"
            "holdout_labels_owner.csv, holdout_labels_alice.csv), then re-run. The model side "
            f"({_MODEL.name}) is ready ({sum(1 for _ in _MODEL.open())} cases)."
        )
        return 0

    model = _load_model()
    try:
        humans = [_load_csv(name, path) for name, path in specs]
    except ValueError as exc:
        print(f"INVALID LABEL FILE — no official score produced:\n{exc}")
        return 2
    print("=" * 78)
    print(
        f"HELD-OUT ACCURACY — model ({sum(1 for _ in _MODEL.open())} cases) vs {len(humans)} human label set(s)"
    )
    print("n≈66 → DIRECTIONAL (rule of three: a ≥99% claim needs ~300 clean obs). Report the pair.")
    print("=" * 78)

    # (1)&(2) model vs each human; (3)&(4) every human pair.
    for h in humans:
        _report_pair(model, h)
    for a, b in combinations(humans, 2):
        _report_pair(a, b)

    _repair_redo_diagnostic([model, *humans])

    print("\n" + "=" * 78)
    print("MAP TO THE FOUR NUMBERS: name your files owner / <independent> so the rows read as:")
    print(
        "  1. model vs owner   2. model vs independent   3. owner vs independent   4. indep1 vs indep2"
    )
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
