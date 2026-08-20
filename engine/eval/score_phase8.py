"""Phase 8 — the winning-condition §4 threshold scorecard, over the real ground-truth set.

One place that runs EVERY §4 quantitative threshold that is measurable from on-disk artifacts (the
216-case human-labelled set + the current v20 extractions + the shipped calibration), reports each as
PASS / FAIL against its ship threshold, and — critically — lists every §4 row that is NOT measurable
this way with the honest reason and the command that WOULD produce it. Silent omission of an unmet or
unmeasured metric is the failure this guards against (CLAUDE.md §10 "no silent caps"): a scorecard that
only shows the green rows is worse than no scorecard.

Deterministic and $0: reads files only — no LLM, no DB, no network. So it is safe to run every session
and its number never drifts under you. The metrics that genuinely need a live run (elicitation budget,
object-match, end-to-end latency) or that are structurally blocked (Arabic parity — 0/216 in the set;
review time / abandonment — need humans; the TRUE accuracy ceiling — needs the independent held-out
labels from make_holdout_label_sheet.py) are reported as UNMEASURED/BLOCKED with the reason, never faked.

Honesty notes baked in:
- Accuracy here is measured against gold **I (Claude) authored**, so it is agreement-with-the-labeller,
  not agreement-with-reality (longterm_context.md §0; CLAUDE.md §10 CORRECTION). The independent
  held-out slice is what turns these into real accuracy. Every accuracy row is tagged (self-labelled).
- The shipped calibration is gate_met=False / τ=1.01, so EVERY case routes to review. That makes the
  "ambiguous correctly flagged" gate pass *trivially* (100%) while "auto-routed accuracy" is *vacuous*
  (no case auto-routes). Both are reported as such, plus a DIAGNOSTIC discrimination curve (labelled
  diagnostic-only, never promoted to the gate — §10).
- Metrics are reported as a PAIR where a single number is gameable by abstention ([[report-metric-pairs-and-n]]).

Usage:  uv run python eval/score_phase8.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.confidence.model import load_calibration
from app.extract.schema import GOVERNED_KEYS  # noqa: F401  (kept for reference of the governed set)

_DIR = Path(__file__).resolve().parent / "fixtures"
_DATASETS = ("cfpb", "multidomain")

# gold csv column -> extraction governed key
_FIELD_MAP = {
    "gold_category": "category",
    "gold_desired_outcome": "desired_outcome",
    "gold_severity_signal": "severity_signal",
    "gold_emotion_signal": "emotion_signal",
}
_NULL_ON_BLANK = {"gold_desired_outcome"}  # blank = a real "customer stated no outcome" label


def _norm(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    return "" if s in ("", "null") else s


@dataclass
class Case:
    id: str
    gold: dict[str, str]  # governed key -> normalised gold ("" = labelled-absent, for outcome)
    labelled: set[str]  # which governed keys have a real gold label on this row
    pred: dict[str, object]  # governed key -> model value
    grounding: float


def _load_cases(dataset: str) -> list[Case]:
    labels = _DIR / f"{dataset}_labels.csv"
    extr = _DIR / f"{dataset}_extractions.jsonl"
    if not labels.exists() or not extr.exists():
        return []
    preds = {
        str(json.loads(line)["id"]): json.loads(line)
        for line in extr.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rows = list(csv.DictReader(labels.open(encoding="utf-8", newline="")))
    # A blank cell means "labelled null" ONLY for a _NULL_ON_BLANK field the labeller ACTUALLY used in
    # this dataset (≥1 non-blank cell). If a column is entirely empty (e.g. multidomain never labelled
    # desired_outcome), every blank is an UNLABELLED skip, not a null — otherwise we'd spuriously score
    # "model returned null" as accuracy on a field no human ever judged.
    active_null_on_blank = {
        col for col in _NULL_ON_BLANK if any(str(r.get(col, "") or "").strip() for r in rows)
    }
    cases: list[Case] = []
    for row in rows:
        p = preds.get(str(row["id"]))
        if p is None:
            continue
        gov = p.get("governed") or {}
        gold: dict[str, str] = {}
        labelled: set[str] = set()
        for col, key in _FIELD_MAP.items():
            raw = str(row.get(col, "") or "").strip()
            if raw == "" and col not in active_null_on_blank:
                continue
            labelled.add(key)
            gold[key] = _norm(raw)
        fv = p.get("field_validity")
        grounding = float(fv) if isinstance(fv, (int, float)) else 1.0
        cases.append(
            Case(
                id=str(row["id"]),
                gold=gold,
                labelled=labelled,
                pred={k: gov.get(k) for k in _FIELD_MAP.values()},
                grounding=grounding,
            )
        )
    return cases


# --------------------------------------------------------------------------- individual §4 measures


def _field_accuracy(cases: list[Case], key: str) -> tuple[int, int]:
    correct = total = 0
    for c in cases:
        if key not in c.labelled:
            continue
        total += 1
        if _norm(c.pred.get(key)) == c.gold[key]:
            correct += 1
    return correct, total


def _zero_edit_rate(cases: list[Case]) -> tuple[int, int]:
    """§4 'cases requiring zero human edits' (≥70%). Proxy: a case where EVERY labelled governed field
    matches gold — a reviewer would change nothing. Only cases with ≥2 labelled governed fields count
    (a single-field row is too weak to call 'no edit needed')."""
    ok = total = 0
    for c in cases:
        if len(c.labelled) < 2:
            continue
        total += 1
        if all(_norm(c.pred.get(k)) == c.gold[k] for k in c.labelled):
            ok += 1
    return ok, total


def _ambiguous_flag_gate(cases: list[Case]) -> dict[str, object]:
    """The trust metric (§4 'ambiguous cases correctly flagged rather than guessed ≥90%'), under the
    SHIPPED policy. A case is flagged-for-review if any labelled governed field routes to review. With
    gate_met=False / τ=1.01 this is 100% by construction — reported honestly, not hidden."""
    cal = load_calibration()
    flagged_wrong = wrong = flagged_right = right = 0
    for c in cases:
        # min governed-field confidence drives case routing (least-reliable field wins).
        confs = [
            cal.confidence(k, c.pred.get(k), grounding=c.grounding)
            for k in c.labelled
            if c.pred.get(k) is not None
        ]
        case_conf = min(confs) if confs else 0.0
        flagged = cal.route(case_conf) == "review"
        case_wrong = any(_norm(c.pred.get(k)) != c.gold[k] for k in c.labelled)
        if case_wrong:
            wrong += 1
            flagged_wrong += int(flagged)
        else:
            right += 1
            flagged_right += int(flagged)
    return {
        "tau": cal.tau_auto,
        "gate_met": cal.gate_met,
        "wrong": wrong,
        "flagged_wrong": flagged_wrong,
        "right": right,
        "flagged_right": flagged_right,
    }


def _ambiguous_flag_diagnostic(cases: list[Case]) -> list[tuple[float, int, int, int, int]]:
    """DIAGNOSTIC-ONLY (§10 — never the gate): at a sweep of thresholds, does low confidence actually
    concentrate the errors? Returns rows of (tau, wrong_flagged, wrong_total, right_flagged, right_total)
    using the calibrated confidence VALUES (ignoring the shipped unreachable τ). This shows whether the
    signal discriminates at all — a diagnostic for review-ordering, not an accepted-accuracy claim.
    """
    cal = load_calibration()
    scored: list[tuple[float, bool]] = []
    for c in cases:
        confs = [
            cal.confidence(k, c.pred.get(k), grounding=c.grounding)
            for k in c.labelled
            if c.pred.get(k) is not None
        ]
        if not confs:
            continue
        case_conf = min(confs)
        case_wrong = any(_norm(c.pred.get(k)) != c.gold[k] for k in c.labelled)
        scored.append((case_conf, case_wrong))
    wrong_total = sum(1 for _, w in scored if w)
    right_total = sum(1 for _, w in scored if not w)
    out = []
    for tau in (0.9, 0.8, 0.7, 0.6):
        wf = sum(
            1 for conf, w in scored if w and conf < tau
        )  # wrong cases flagged (conf below tau)
        rf = sum(1 for conf, w in scored if not w and conf < tau)  # right cases wrongly flagged
        out.append((tau, wf, wrong_total, rf, right_total))
    return out


def _convergence_curve(dataset: str) -> dict[str, object] | None:
    """The §4 convergence rows, at the COMPOSITE (head+qualifier) altitude that is the real gate
    (longterm_context.md retraction 2026-08-17 — the head-only curve is a closed-enum tautology and is
    NOT the gate). Deterministic count from the extraction attributes: the new-composite-name-per-bucket
    curve and the hapax (seen-once) fraction. The <5%-DUPLICATE row needs the live embedding dedup
    (run_convergence.py / run_column_convergence.py) and is reported separately."""
    extr = _DIR / f"{dataset}_extractions.jsonl"
    if not extr.exists():
        return None
    rows = [
        json.loads(line) for line in extr.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    bucket = 20
    seen: set[str] = set()
    curve: list[int] = []
    new_in_bucket = 0
    names: Counter[str] = Counter()
    for i, r in enumerate(rows):
        for a in r.get("attributes", []) or []:
            head = str(a.get("head", "")).strip().lower()
            qual = str(a.get("qualifier") or "").strip().lower()
            name = f"{head}|{qual}" if qual else head
            names[name] += 1
            if name not in seen:
                seen.add(name)
                new_in_bucket += 1
        if (i + 1) % bucket == 0:
            curve.append(new_in_bucket)
            new_in_bucket = 0
    if new_in_bucket:
        curve.append(new_in_bucket)
    hapax = sum(1 for _n, c in names.items() if c == 1)
    return {
        "n_cases": len(rows),
        "distinct_names": len(names),
        "total_attrs": sum(names.values()),
        "new_per_bucket": curve,
        "hapax_frac": hapax / len(names) if names else 0.0,
    }


# ------------------------------------------------------------------------------------- scorecard


def _status(measured: float | None, threshold: float, higher_is_better: bool = True) -> str:
    if measured is None:
        return "UNMEASURED"
    if higher_is_better:
        return "PASS" if measured >= threshold else "FAIL"
    return "PASS" if measured <= threshold else "FAIL"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    per: dict[str, list[Case]] = {ds: _load_cases(ds) for ds in _DATASETS}
    allc = [c for cs in per.values() for c in cs]
    if not allc:
        print("no labelled cases found — check fixtures/*_labels.csv + *_extractions.jsonl")
        return 1

    print("=" * 78)
    print("PHASE 8 — winning-condition §4 threshold scorecard")
    print(
        f"ground-truth set: {len(allc)} cases ({', '.join(f'{k}={len(v)}' for k, v in per.items())})"
    )
    print("accuracy rows are (self-labelled): gold authored by Claude → agreement, not truth.")
    print("The independent number needs the held-out slice (eval/make_holdout_label_sheet.py).")
    print("=" * 78)

    rows: list[tuple[str, str, str, str]] = []  # (measure, threshold, measured, status)

    def acc_row(label: str, key: str, thr: float) -> None:
        c, t = _field_accuracy(allc, key)
        pct = c / t if t else None
        parts = []
        for ds in _DATASETS:
            dc, dt = _field_accuracy(per[ds], key)
            if dt:
                parts.append(f"{ds} {dc}/{dt}={dc / dt:.0%}")
        detail = f"{c}/{t} = {pct:.0%}  [{', '.join(parts)}]" if t else "no gold labelled"
        rows.append((label, f"≥{thr:.0%}", detail, _status(pct, thr)))

    # Governed-core accuracy — §4 splits category out; the rest of the governed core drives SLA/routing.
    acc_row("Category classification accuracy", "category", 0.90)
    # Zero-edit rate depends on HOW MANY governed fields a row labels: cfpb labels up to 4
    # (category+outcome+severity+emotion), multidomain labels only 1 (category), so the two domains are
    # NOT comparable and the combined number is dominated by that density, not by quality. Surface the
    # mean labelled-field count per domain so the 28% vs 66% split reads as an artifact, not a signal.
    ze, zt = _zero_edit_rate(allc)
    dens = {
        ds: (sum(len(c.labelled) for c in per[ds]) / len(per[ds]) if per[ds] else 0.0)
        for ds in _DATASETS
    }
    zparts = []
    for ds in _DATASETS:
        zc, zct = _zero_edit_rate(per[ds])
        if zct:
            zparts.append(f"{ds} {zc / zct:.0%} over ~{dens[ds]:.1f} fields/row")
    rows.append(
        (
            "Cases requiring zero human edits",
            "≥70%",
            f"{ze}/{zt} = {ze / zt:.0%}  [{'; '.join(zparts)}]" if zt else "n/a",
            _status(ze / zt if zt else None, 0.70),
        )
    )
    acc_row("Desired outcome captured", "desired_outcome", 0.90)
    # Governed-core field accuracy (§4 ≥95%): severity is the other closed governed field with gold.
    acc_row("Severity accuracy (governed core)", "severity_signal", 0.95)

    # Ambiguous-flagged — the trust gate, under the shipped policy.
    fg = _ambiguous_flag_gate(allc)
    wrong, fw = int(fg["wrong"]), int(fg["flagged_wrong"])
    right, fr = int(fg["right"]), int(fg["flagged_right"])
    flag_recall = fw / wrong if wrong else None
    rows.append(
        (
            "Ambiguous cases correctly flagged",
            "≥90%",
            (
                f"{fw}/{wrong} wrong-cases flagged = {flag_recall:.0%}  "
                f"(τ={fg['tau']}, gate_met={fg['gate_met']}; ALSO flags {fr}/{right} correct cases → "
                f"everything routes to review, so this passes trivially)"
            ),
            _status(flag_recall, 0.90),
        )
    )
    rows.append(
        (
            "Accuracy on auto-routed cases only",
            "≥98%",
            (
                f"VACUOUS — gate_met={fg['gate_met']}, τ={fg['tau']}: 0 cases auto-route "
                "(everything → review). Nothing is auto-filled, so the gate is not yet exercised."
            ),
            "N/A",
        )
    )

    # ---- print the measurable scorecard ----
    print("\n### MEASURED from the ground-truth set (self-labelled)\n")
    w0 = max(len(r[0]) for r in rows)
    for measure, thr, measured, status in rows:
        print(f"  [{status:^10}] {measure:<{w0}}  {thr:>5}   {measured}")

    # ---- convergence (the moat) ----
    print("\n### CONVERGENCE — the moat (§4 'the core claim of the design')\n")
    for ds in _DATASETS:
        cv = _convergence_curve(ds)
        if not cv:
            continue
        print(
            f"  {ds:<12} composite new-name/bucket {cv['new_per_bucket']}  "
            f"| {cv['distinct_names']} distinct / {cv['total_attrs']} attrs "
            f"| hapax {cv['hapax_frac']:.0%}"
        )
    print(
        "  [   FAIL   ] Duplicate/synonym fields <5% after 200: last live measure 7.6% dup, ~90% hapax\n"
        "              (retraction 2026-08-17). The <5%-dup row needs the LIVE embedding dedup:\n"
        "              uv run --group embed python eval/run_column_convergence.py\n"
        "  [   FAIL   ] New-field creation rate declining: composite curve is FLAT (above) → sprawling."
    )

    # ---- diagnostic (never the gate) ----
    print("\n### DIAGNOSTIC ONLY — non-gate signals (§10, never a pass line) \n")
    ec, et = _field_accuracy(allc, "emotion_signal")
    if et:
        print(
            f"  emotion accuracy (not in §4): {ec}/{et} = {ec / et:.0%}  [cfpb only — md unlabelled]"
        )
    print(
        "  does low confidence concentrate the errors? (for review-ORDERING, not accepted accuracy)"
    )
    for tau, wf, wt, rf, rt in _ambiguous_flag_diagnostic(allc):
        print(
            f"    conf<{tau}: catches {wf}/{wt} wrong ({wf / wt:.0%})  "
            f"vs {rf}/{rt} correct false-flagged ({rf / rt:.0%})"
            if wt and rt
            else f"    conf<{tau}: n/a"
        )

    # ---- honestly unmeasured / blocked ----
    print("\n### NOT MEASURABLE from files — reported, never faked (§10 'no silent caps')\n")
    blocked = [
        (
            "Emergent attribute accuracy",
            "≥85%",
            "needs labelled emergent-attribute gold (only soft key-fact recall exists today)",
        ),
        (
            "Complaints matched to object w/o asking",
            "≥60%",
            "live entity-resolution run: uv run python eval/spike_entity_resolution.py",
        ),
        (
            "Object match accuracy when silent",
            "≥99%",
            "same live run; report as a PAIR with the rate above ([[report-metric-pairs-and-n]])",
        ),
        (
            "Discrepancies surfaced to agent",
            "100%",
            "needs cases labelled with a known complaint-vs-record discrepancy",
        ),
        (
            "Questions per case (median)",
            "≤2 after anchor",
            "enforced in code (elicit budget); measure on the ≥20 sparse cases via a live elicitation run",
        ),
        ("Asked for something already stated", "0%", "live elicitation run over the labelled set"),
        ("Asked for something derivable from anchor", "≤5%", "live elicitation run"),
        (
            "Sparse complaints reaching actionable",
            "≥80%",
            "live elicitation run over the sparse slice",
        ),
        (
            "Elicitation abandonment",
            "≤20%",
            "needs real customers / a reply-simulator — out of PoC scope",
        ),
        ("Median review time per case", "≤30s", "needs a human reviewer timed on the review UI"),
        (
            "Time message→case ready",
            "≤60s",
            "live pipeline timing run; observed ~8–17s inline this build (§0) — confirm under load",
        ),
        (
            "Arabic field-extraction parity",
            "within 5pts",
            "BLOCKED: 0/216 Arabic in the set — the differentiator is unbuilt + unmeasured (separate project)",
        ),
        (
            "Backfill correctness after promotion",
            "100%",
            "live: re-extract against retained originals (migration 0010 path) + diff",
        ),
    ]
    w1 = max(len(b[0]) for b in blocked)
    for measure, thr, why in blocked:
        print(f"  [UNMEASURED] {measure:<{w1}}  {thr:>14}   {why}")

    print("\n" + "=" * 78)
    n_pass = sum(1 for r in rows if r[3] == "PASS")
    n_fail = sum(1 for r in rows if r[3] == "FAIL")
    print(
        f"MEASURED: {n_pass} PASS / {n_fail} FAIL / {len(rows) - n_pass - n_fail} N/A   |   "
        f"CONVERGENCE: FAIL   |   {len(blocked)} rows UNMEASURED/BLOCKED"
    )
    print("A sellable SURFACE is not a passing SCORECARD — this is the honest §4 state.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
