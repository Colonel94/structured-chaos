"""The case-report HTML template — pure, host-safe, RTL-safe (Phase 7).

Builds a self-contained print document from a review payload (``store.api.get_case_review``): the
header + the deterministic decision (priority/SLA/routing, explainable in one sentence), the governed
core, the emergent attributes, and the provenance/approval footer. No WeasyPrint import lives here, so
the template is unit-testable on the Windows host; :mod:`app.report.pdf` renders it to bytes in the
container.

RTL-safe by construction: every value that carries free text gets ``dir="auto"``, so the bidi algorithm
picks direction per value from its first strong character — an Arabic case renders right-to-left and a
mixed English/Arabic case renders each run correctly, with no language flag to set and no separate
"Arabic report" codepath (CLAUDE.md §8 red flag: "it's a different product in Arabic"). The font stack
names Noto families so the container's fonts-noto package supplies Arabic glyphs.
"""

from __future__ import annotations

from html import escape
from typing import Any

_CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "Noto Sans", "Noto Sans Arabic", "DejaVu Sans", sans-serif;
       color: #16202e; font-size: 11pt; line-height: 1.45; }
h1 { font-size: 17pt; margin: 0 0 2mm; }
h2 { font-size: 12pt; margin: 7mm 0 2mm; border-bottom: 1px solid #d7dee8; padding-bottom: 1mm; }
.meta { color: #5a6b80; font-size: 9.5pt; }
.decision { background: #f4f7fb; border: 1px solid #d7dee8; border-radius: 3mm;
            padding: 3mm 4mm; margin: 4mm 0; }
.decision .pri { font-weight: 700; }
.rationale { margin-top: 1.5mm; }
table { width: 100%; border-collapse: collapse; margin-top: 2mm; }
th, td { text-align: start; vertical-align: top; padding: 1.6mm 2mm; border-bottom: 1px solid #e7ecf3;
         font-size: 10pt; }
th { color: #5a6b80; font-weight: 600; font-size: 9pt; text-transform: uppercase; letter-spacing: .04em; }
.label { color: #5a6b80; width: 32%; }
.absent { color: #9aa7b8; font-style: italic; }
.chip { display: inline-block; font-size: 8pt; padding: .3mm 1.6mm; border-radius: 2mm;
        background: #e7ecf3; color: #40506a; }
.footer { margin-top: 8mm; padding-top: 3mm; border-top: 1px solid #d7dee8; color: #5a6b80;
          font-size: 9pt; }
"""

_GOVERNED_ORDER = [
    "category",
    "fault",
    "desired_outcome",
    "severity_signal",
    "emotion_signal",
    "anchor_value",
]


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _cell(value: Any) -> str:
    """A value cell — ``dir="auto"`` so bidi picks direction per value (RTL-safe)."""
    text = _fmt(value)
    if text == "":
        return '<td class="absent">not stated</td>'
    return f'<td dir="auto">{escape(text)}</td>'


def build_case_html(review: dict[str, Any]) -> str:
    """Render one review payload to a complete, self-contained HTML document string."""
    by_path = {f["field_path"]: f for f in review.get("fields", [])}
    emergent = [f for f in review.get("fields", []) if f.get("layer") == "emergent"]
    decision = review.get("decision")
    commit = review.get("commit")

    # Governed core rows, in review order; an absent governed field renders as an explicit
    # refuse-to-guess absence, never a silent blank (§2).
    gov_rows = []
    for path in _GOVERNED_ORDER:
        field = by_path.get(path)
        label = escape(path.replace("_", " "))
        value_cell = _cell(field["value"]) if field else '<td class="absent">not stated</td>'
        gov_rows.append(f'<tr><td class="label">{label}</td>{value_cell}</tr>')

    decision_html = ""
    if decision:
        due = escape(_fmt(decision.get("sla_response_due_at")))
        decision_html = (
            '<div class="decision">'
            f'<span class="pri">{escape(_fmt(decision.get("priority")))}</span>'
            f' · route <b>{escape(_fmt(decision.get("routing")))}</b>'
            f' · SLA {escape(_fmt(decision.get("sla_target_hours")))}h'
            f" (due {due})"
            f'<div class="rationale" dir="auto">{escape(_fmt(decision.get("rationale")))}</div>'
            "</div>"
        )

    emergent_html = "<p class='absent'>none extracted</p>"
    if emergent:
        rows = "".join(
            f'<tr><td dir="auto">{escape(_fmt(f.get("head")))}</td>'
            f'<td dir="auto">{escape(_fmt(f.get("qualifier")) or "—")}</td>'
            f'{_cell(f.get("value"))}</tr>'
            for f in emergent
        )
        emergent_html = (
            "<table><thead><tr><th>head</th><th>qualifier</th><th>value</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )

    approved = ""
    if commit:
        approved = (
            f'approved by {escape(_fmt(commit.get("committed_by")))} '
            f'at {escape(_fmt(commit.get("committed_at")))}'
        )

    case_id = escape(_fmt(review.get("case_id")))
    header_meta = escape(
        f"{review.get('channel')} · {review.get('case_state')} · "
        f"first contact {review.get('first_contact_at')}"
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
  <h1>Case {case_id[:8]}</h1>
  <div class="meta">{header_meta}</div>
  {decision_html}
  <h2>Governed core</h2>
  <table><tbody>{"".join(gov_rows)}</tbody></table>
  <h2>Emergent attributes <span class="chip">{len(emergent)}</span></h2>
  {emergent_html}
  <div class="footer">{approved}</div>
</body></html>"""
