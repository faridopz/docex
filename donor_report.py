"""
The donor report: one PDF per project and period.

What a donor's finance officer asks for at the end of a reporting period,
in the order they ask it:

  1. Where does the grant stand?           budget, spent, committed, left
  2. Did spending follow the budget?       budget against actual, line by line
  3. Who worked on it, and is it proven?   approved hours, who signed them
  4. What salary was charged, on what basis? recorded hours or a budgeted split
  5. What was paid?                        each payment, voucher, bank reference
  6. What broke the rules, and why?        every released check, with its reason

Every figure comes from projects.py, which reads the records themselves —
nothing is typed into the report. Payments are read from their frozen
payment records, so a check shows as it stood when the money went out.
Bank account numbers do not appear at all.
"""
from __future__ import annotations

import datetime as dt
import io
from typing import Optional

import grants
import projects


def _org_name(org_id: str) -> str:
    try:
        import payment_voucher
        head = payment_voucher.get_template(org_id).get("letterhead") or {}
        return str(head.get("org_name") or "")
    except Exception:
        return ""


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return dt.date.fromisoformat(iso[:10]).strftime("%d %b %Y")
    except ValueError:
        return iso


def _period_label(period: str) -> str:
    try:
        y, m = (int(x) for x in period.split("-")[:2])
        return dt.date(y, m, 1).strftime("%b %Y")
    except Exception:
        return period


def build(org_id: str, ag: grants.Agreement, *, date_from: str = "", date_to: str = "",
          generated_by: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    import payment_voucher as pv

    font = pv._unicode_font()
    mark = pv._currency_mark(ag.currency)

    def money(x: float) -> str:
        sign = "-" if x < 0 else ""
        return f"{sign}{mark}{abs(x):,.2f}" if mark != ag.currency.upper() else f"{sign}{ag.currency} {abs(x):,.2f}"

    styles = getSampleStyleSheet()
    base = font or "Helvetica"
    bold = f"{font}-Bold" if font else "Helvetica-Bold"
    body = ParagraphStyle("b", parent=styles["Normal"], fontName=base, fontSize=8.5, leading=11)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#4b5563"))
    h1 = ParagraphStyle("h1", parent=body, fontName=bold, fontSize=15, leading=19, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=body, fontName=bold, fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor("#1f3a5f"), keepWithNext=1)
    cell_b = ParagraphStyle("cb", parent=body, fontName=bold)

    def P(text, st=body):
        return Paragraph(str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), st)

    def table(rows, widths, *, numeric_cols=(), total_row=False):
        data = [[P(c, cell_b) for c in rows[0]]] + [[c if hasattr(c, "wrap") else P(c) for c in r] for r in rows[1:]]
        t = Table(data, colWidths=widths, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#94a3b8")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for c in numeric_cols:
            style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
        if total_row:
            style += [("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#1f2937")),
                      ("FONTNAME", (0, -1), (-1, -1), bold)]
        t.setStyle(TableStyle(style))
        return t

    def num(x):
        p = Paragraph(money(x), body)
        p.style = ParagraphStyle("n", parent=body, alignment=2)
        return p

    # ── the figures ────────────────────────────────────────────────────────
    to_date = projects.figures(org_id, ag)
    pays = projects.payments(org_id, ag, date_from=date_from, date_to=date_to)
    excs = projects.exceptions(org_id, ag, date_from=date_from, date_to=date_to)
    time_rows = projects.approved_time(org_id, ag, period_from=date_from[:7], period_to=date_to[:7])
    salary_rows = projects.salary_charged(org_id, ag, period_from=date_from[:7], period_to=date_to[:7])
    paid_in_period = round(sum(p["amount"] for p in pays), 2)
    salary_in_period = round(sum(r["cost"] for r in salary_rows), 2)

    # Budget lines: what the period's payments put on each line.
    import requisitions as rq
    reqs = {r.id: r for r in rq.list_requisitions(org_id)}
    line_period: dict[str, float] = {}
    for p in pays:
        src = reqs.get(p["requisition_id"])
        for key, amt in projects.split_by_line(ag, p["amount"], src.budget_lines if src else []).items():
            line_period[key] = round(line_period.get(key, 0.0) + amt, 2)

    window = (f"{_fmt_date(date_from) or 'the start'} to {_fmt_date(date_to) or _fmt_date(dt.date.today().isoformat())}")

    # ── the document ───────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"{ag.project_code} donor report", author=_org_name(org_id) or "")
    W = A4[0] - 32 * mm
    story = []

    org = _org_name(org_id)
    if org:
        story.append(P(org, small))
    story.append(P(f"{ag.donor} · {ag.project_code}" + (f": {ag.title}" if ag.title else ""), h1))
    story.append(P(f"Financial report for {window}", body))
    meta = []
    if ag.start_date or ag.end_date:
        meta.append(f"Agreement period {_fmt_date(ag.start_date) or 'open'} to {_fmt_date(ag.end_date) or 'open'}")
    meta.append(f"Prepared {_fmt_date(dt.date.today().isoformat())}" + (f" by {generated_by}" if generated_by else ""))
    story.append(P(" · ".join(meta), small))
    story.append(Spacer(1, 6))

    # 1. Where the grant stands
    story.append(P("1. Where the grant stands", h2))
    story.append(table([
        ["", "This period", "Project to date"],
        ["Budget", "", num(to_date.budget)],
        ["Payments", num(paid_in_period), num(to_date.paid)],
        ["Salaries charged", num(salary_in_period), num(to_date.salary)],
        ["Committed (approved or in review, not yet paid)", "", num(to_date.committed)],
        ["Left", "", num(to_date.remaining)],
    ], [W * 0.5, W * 0.25, W * 0.25], numeric_cols=(1, 2), total_row=True))
    if to_date.used_percent is not None:
        story.append(Spacer(1, 3))
        story.append(P(f"{to_date.used_percent}% of the budget has been spent (payments and salaries).", small))

    # 2. Budget against actual
    story.append(P("2. Budget against actual", h2))
    if not ag.budget_lines:
        story.append(P("No budget lines are recorded for this project, so spending is reported in total only.", small))
    else:
        rows = [["Budget line", "Budget", "This period", "To date", "Left"]]
        for lf in to_date.lines:
            name = "Not assigned to a budget line" if lf.code == projects.UNASSIGNED else \
                (f"{lf.code} · {lf.label}" if lf.label else lf.code)
            rows.append([name, "" if lf.code == projects.UNASSIGNED else num(lf.budget),
                         num(line_period.get(lf.code, 0.0)), num(lf.paid),
                         "" if lf.remaining is None else num(lf.remaining)])
        story.append(table(rows, [W * 0.36, W * 0.16, W * 0.16, W * 0.16, W * 0.16], numeric_cols=(1, 2, 3, 4)))
        story.append(Spacer(1, 3))
        story.append(P("Payments only; salaries are reported in section 4. A payment is placed on a budget line "
                       "when its request named one.", small))

    # 3. Staff time
    story.append(P("3. Staff time", h2))
    if ag.staff:
        story.append(P("Planned: " + "; ".join(
            f"{s.name}{(' (' + s.role + ')') if s.role else ''} {s.percent:g}%" for s in ag.staff), small))
        story.append(Spacer(1, 3))
    if not time_rows:
        story.append(P("No approved timesheets record time on this project in this period.", small))
    else:
        rows = [["Month", "Person", "Hours on project", "Share of their time", "Approved by", "On"]]
        for r in time_rows:
            rows.append([_period_label(r["period"]), r["staff_name"], f"{r['hours']:g}", f"{r['share_percent']:g}%",
                         r["approved_by"], _fmt_date(r["approved_at"])])
        rows.append(["Total", "", f"{sum(r['hours'] for r in time_rows):g}", "", "", ""])
        story.append(table(rows, [W * 0.11, W * 0.22, W * 0.13, W * 0.13, W * 0.26, W * 0.15],
                           numeric_cols=(2, 3), total_row=True))
        story.append(Spacer(1, 3))
        story.append(P("From timesheets recorded after the fact and approved by a supervisor. Unapproved time is not included.", small))

    # 4. Salaries
    story.append(P("4. Salaries charged", h2))
    if not salary_rows:
        story.append(P("No paid payroll charged salary to this project in this period.", small))
    else:
        rows = [["Month", "Person", "Share", "Charged", "Based on"]]
        for r in salary_rows:
            rows.append([_period_label(r["period"]), r["name"], f"{r['percent']:g}%", num(r["cost"]),
                         "Approved hours" if r["basis"] == "timesheet" else "Budgeted split (no timesheet)"])
        rows.append(["Total", "", "", num(salary_in_period), ""])
        story.append(table(rows, [W * 0.12, W * 0.28, W * 0.1, W * 0.2, W * 0.3], numeric_cols=(2, 3), total_row=True))
        budgeted = [r for r in salary_rows if r["basis"] != "timesheet"]
        if budgeted:
            story.append(Spacer(1, 3))
            story.append(P(f"{len(budgeted)} {'line was' if len(budgeted) == 1 else 'lines were'} charged on a "
                           "budgeted split rather than recorded hours.", small))

    # 5. Payments
    story.append(P("5. Payments", h2))
    if not pays:
        story.append(P("No payments were charged to this project in this period.", small))
    else:
        rows = [["Paid", "Request", "Payee", "Voucher", "Bank ref.", "Amount"]]
        for p in pays:
            rows.append([_fmt_date(p["paid_at"]), p["requisition_ref"], p["payee"], p["voucher_number"] or "—",
                         p["bank_reference"] or "—", num(p["amount"])])
        rows.append(["Total", f"{len(pays)} payment{'s' if len(pays) != 1 else ''}", "", "", "", num(paid_in_period)])
        story.append(table(rows, [W * 0.15, W * 0.13, W * 0.26, W * 0.12, W * 0.14, W * 0.2],
                           numeric_cols=(5,), total_row=True))

    # 6. Exceptions
    story.append(P("6. Exceptions and the reasons given", h2))
    if not excs:
        story.append(P("No policy check was released on any payment in this period: every payment met the "
                       "organisation's rules as they stood when it was made.", small))
    else:
        for e in excs:
            story.append(KeepTogether([
                P(f"{e['requisition_ref']} · {_fmt_date(e['paid_at'])} · {e['payee']} · {money(e['amount'])}", cell_b),
                P(f"Check: {e['check']}. {e['message']}", small),
                P(f"Reason: “{e['reason']}” — released by {e['released_by']}"
                  + (f" ({e['authority']})" if e['authority'] else ""), body),
                Spacer(1, 5)]))

    story.append(Spacer(1, 10))
    story.append(P("Every figure in this report is computed from the organisation's payment, payroll and timesheet "
                   "records; nothing is typed in. Payments are read from the record frozen when each was paid. "
                   "Bank account numbers are deliberately left out.", small))

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(base, 7)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(16 * mm, 10 * mm, f"{ag.project_code} · {ag.donor} · {window}")
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
