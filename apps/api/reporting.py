from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "0"


def build_report_filename(now: datetime | None = None) -> str:
    ts = (now or datetime.now()).strftime("%Y%m%d")
    return f"retirement_etf_report_{ts}.pdf"


def _pdf_with_reportlab(payload: dict[str, Any], result: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 20 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, "퇴직연금 포트폴리오 리포트 (MVP)")

    y -= 10 * mm
    c.setFont("Helvetica", 9)
    mode = payload.get("withdrawal_mode", "target_years")
    mode_text = "20년 받기" if mode == "target_years" else f"매달 {_fmt_int(payload.get('fixed_monthly_withdrawal_krw'))}원"
    summary = [
        f"현재자산: {_fmt_int(payload.get('current_balance_krw'))}원",
        f"월불입: {_fmt_int(payload.get('monthly_contribution_krw'))}원",
        f"개시시점: {payload.get('start_date', '-')}",
        f"목표수익률: {payload.get('target_cagr', 0)}%",
        f"허용MDD: {payload.get('max_mdd', 0)}%",
        f"수령방식: {mode_text}",
    ]
    for line in summary:
        c.drawString(20 * mm, y, line)
        y -= 6 * mm

    y -= 2 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "추천 포트폴리오")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, y, "Ticker")
    c.drawString(55 * mm, y, "Name")
    c.drawString(160 * mm, y, "Weight")
    y -= 4 * mm
    c.line(20 * mm, y, 190 * mm, y)
    y -= 5 * mm
    for row in result.get("portfolio", [])[:12]:
        c.drawString(20 * mm, y, str(row.get("ticker", "")))
        c.drawString(55 * mm, y, str(row.get("name_kr", ""))[:36])
        c.drawRightString(190 * mm, y, f"{float(row.get('weight', 0))*100:.1f}%")
        y -= 5 * mm

    y -= 2 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "핵심 지표")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    metrics = result.get("metrics", {})
    retire = result.get("retirement_summary", {})
    metric_lines = [
        f"exp_return: {float(metrics.get('exp_return', 0))*100:.2f}%",
        f"vol: {float(metrics.get('vol', 0))*100:.2f}%",
        f"est_mdd: {float(metrics.get('est_mdd', 0))*100:.2f}%",
        f"start_balance_at_retirement: {_fmt_int(retire.get('start_balance_at_retirement'))}원",
        f"monthly_withdrawal: {_fmt_int(retire.get('monthly_withdrawal'))}원",
        f"duration_months: {_fmt_int(retire.get('duration_months'))}",
        f"end_balance: {_fmt_int(retire.get('end_balance'))}원",
    ]
    for line in metric_lines:
        c.drawString(20 * mm, y, line)
        y -= 5 * mm

    y -= 2 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "연도별 요약(적립기)")
    y -= 6 * mm
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y, "Date")
    c.drawRightString(90 * mm, y, "Balance")
    c.drawRightString(130 * mm, y, "Principal")
    c.drawRightString(170 * mm, y, "Gain")
    y -= 4 * mm
    c.line(20 * mm, y, 190 * mm, y)
    y -= 4 * mm

    acc = result.get("accumulation_series", [])
    sampled = [row for row in acc if str(row.get("date", "")).endswith("-12-31")]
    if not sampled and acc:
        sampled = acc[:: max(1, len(acc)//8)]
    for row in sampled[:10]:
        c.drawString(20 * mm, y, str(row.get("date", "")))
        c.drawRightString(90 * mm, y, _fmt_int(row.get("balance")))
        c.drawRightString(130 * mm, y, _fmt_int(row.get("principal")))
        c.drawRightString(170 * mm, y, _fmt_int(row.get("gain")))
        y -= 4.5 * mm

    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 12 * mm, "본 리포트는 정보 제공 목적이며 투자 손실 가능성이 있습니다. 과거 성과는 미래를 보장하지 않습니다.")

    c.showPage()
    c.save()
    return buffer.getvalue()


def _pdf_minimal(payload: dict[str, Any], result: dict[str, Any]) -> bytes:
    text = "퇴직연금 포트폴리오 리포트 (MVP)"
    body = f"Input: {payload}\nResult keys: {list(result.keys())}"
    content = f"BT /F1 14 Tf 50 760 Td ({text}) Tj 0 -20 Td /F1 9 Tf ({body[:180].replace('(', '[').replace(')', ']')}) Tj ET"
    stream = content.encode("latin-1", errors="ignore")
    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>endobj\n")
    objects.append(b"4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    objects.append(f"5 0 obj<< /Length {len(stream)} >>stream\n".encode() + stream + b"\nendstream endobj\n")

    out = b"%PDF-1.4\n"
    xref = [0]
    for obj in objects:
        xref.append(len(out))
        out += obj
    xref_start = len(out)
    out += f"xref\n0 {len(xref)}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in xref[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer<< /Size {len(xref)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode()
    return out


def generate_report_pdf(payload: dict[str, Any], result: dict[str, Any]) -> bytes:
    try:
        return _pdf_with_reportlab(payload, result)
    except Exception:
        return _pdf_minimal(payload, result)
