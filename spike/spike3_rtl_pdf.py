#!/usr/bin/env python
"""Phase 0.5 — Spike 3: structured data -> correct Arabic-RTL PDF.

THROWAWAY. The report path's riskiest proof, and the ONLY one needing no owner input.
WeasyPrint renders a manager-register row with Arabic text, right-to-left layout, and
mixed Arabic/Latin/number runs (bidi). Open the PDF and eyeball: is the shaping/joining
correct and the direction right, or does it mangle? (BUILD-PLAN Phase 0.5, proof #3.)

CONTAINER ONLY (WeasyPrint GTK/Pango — PREREQUISITES §3). Writes to the mounted host dir:
    docker compose --env-file .env -f deploy/docker-compose.yml run --rm \
      -v "${PWD}/artifacts:/app/artifacts" engine python spike/spike3_rtl_pdf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path("/app/artifacts/spike3_rtl.pdf")

# A register row per vertical: object id (Latin/number), Arabic complaint text, desired
# outcome, SLA — the exact mix the universal register report must render RTL-correctly.
HTML = """
<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<style>
  @page { size: A4 landscape; margin: 1.5cm; }
  body { font-family: "Noto Naskh Arabic", "Noto Sans Arabic", "Noto Sans", sans-serif;
         direction: rtl; }
  h1 { font-size: 18pt; }
  table { width: 100%; border-collapse: collapse; font-size: 12pt; }
  th, td { border: 1px solid #333; padding: 8px 10px; text-align: right; }
  th { background: #f0f0f0; }
  .ltr { direction: ltr; unicode-bidi: embed; }
</style></head><body>
  <h1>سجل الشكاوى — Manager Register (spike)</h1>
  <table>
    <thead><tr>
      <th>رقم الطلب</th><th>الشكوى</th><th>النتيجة المطلوبة</th><th>الأولوية</th><th>SLA (hrs)</th>
    </tr></thead>
    <tbody>
      <tr>
        <td class="ltr">ORD-10432</td>
        <td>وصلت الكيكة متأخرة ساعة وكانت ذايبة، أبغى استرجاع المبلغ</td>
        <td>استرجاع كامل (refund)</td>
        <td>عالية</td>
        <td class="ltr">4</td>
      </tr>
      <tr>
        <td class="ltr">JOB-88217</td>
        <td>الفني ما حضر، هذي ثالث مرة والمكيف ما يبرّد</td>
        <td>إعادة جدولة اليوم + متابعة</td>
        <td>حرجة</td>
        <td class="ltr">2</td>
      </tr>
    </tbody>
  </table>
  <p>Mixed bidi check: العميل رقم 55 دفع 280 AED بدل 200 AED.</p>
</body></html>
"""


def main() -> int:
    try:
        from weasyprint import HTML as WeasyHTML
    except ImportError:
        print("FAIL: weasyprint not installed. Run inside the container (§3).")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    WeasyHTML(string=HTML).write_pdf(str(OUT))
    size = OUT.stat().st_size if OUT.exists() else 0
    if size <= 0:
        print("FAIL: no PDF produced.")
        return 1
    print(f"PASS(rendered): {OUT} ({size} bytes).")
    print(
        "EYEBALL THE PDF: Arabic joining/shaping correct, RTL direction right, numbers/Latin"
    )
    print(
        "  runs placed correctly (bidi)? A mangle here = a report-path plan change. Record in §0."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
