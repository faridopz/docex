"""
PDF and Excel exports for the requisition engine — the artifact an auditor,
donor, or bank actually keeps and files, as opposed to the web screen they
browse once and lose in a tab.

Two shapes:
  - Per-requisition packet (PDF or Excel): everything on one requisition —
    request details, the deterministic policy checks (with any overrides),
    the approval trail, the compliance-rulebook check if one has been run,
    comments, the attachment list (filenames/metadata — not the files'
    binary content, which stays behind the authenticated download route),
    and the hash-chained audit log with its verification result. The same
    content requisitions/[id] shows in the browser, laid out to print,
    email, or file.
  - Period log (Excel only): one row per requisition raised in a date
    range, for a weekly/monthly audit sweep. A list an auditor wants to
    sort and filter — which is what Excel is for. A PDF table serves that
    worse, not better, so this module doesn't build one; per-requisition
    detail is what PDF is for here.

Pure functions returning bytes. The route layer (api/requisition_routes.py)
wraps these in a StreamingResponse/Response with the right
Content-Disposition header — this module never imports FastAPI, so every
function here is testable by calling it directly and inspecting the output
bytes, the same convention accounting_export.py already established at the
repo root.
"""
from __future__ import annotations

import io
from typing import Optional

import requisitions as rq

# ─── shared formatting helpers ──────────────────────────────────────────────
# Small, local, and deliberately NOT imported from the frontend's
# requisitionFormat.ts (a different language) or from any other engine —
# this module renders documents, nothing here is a policy decision, so it
# owns its own tiny formatting vocabulary.


def _money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _humanise(key: Optional[str]) -> str:
    if not key:
        return "—"
    return " ".join(w.capitalize() for w in str(key).replace("_", " ").split())


def _dt(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    return iso[:19].replace("T", " ")


# ─── per-requisition PDF ─────────────────────────────────────────────────────


def requisition_pdf(req: rq.Requisition) -> bytes:
    """A printable packet for one requisition. Reportlab platypus, following
    the same direct-build style as docs/build_product_pdf.py (no HTML step)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=16 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
        title=f"{req.ref} — {req.vendor_name}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("DOCexH1", parent=styles["Heading1"], fontSize=17, spaceAfter=2,
                         textColor=colors.HexColor("#111827"))
    h2 = ParagraphStyle("DOCexH2", parent=styles["Heading2"], fontSize=11, spaceBefore=12,
                         spaceAfter=4, textColor=colors.HexColor("#111827"))
    meta = ParagraphStyle("DOCexMeta", parent=styles["Normal"], fontSize=9,
                           textColor=colors.HexColor("#4B5563"), spaceAfter=2)
    body = ParagraphStyle("DOCexBody", parent=styles["Normal"], fontSize=9, leading=12)
    cell = ParagraphStyle("DOCexCell", parent=styles["Normal"], fontSize=8, leading=10)
    banner = ParagraphStyle("DOCexBanner", parent=styles["Normal"], fontSize=9,
                             textColor=colors.white, leading=12)

    def table(header, rows, col_widths, header_bg="#1F3A5F"):
        data = [[Paragraph(f"<b>{h}</b>", cell) for h in header]]
        for r in rows:
            data.append([Paragraph(str(v) if v not in (None, "") else "—", cell) for v in r])
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    story: list = []

    story.append(Paragraph(f"{req.ref}", h1))
    story.append(Paragraph(f"{_money(req.amount, req.currency)} to {req.vendor_name}", meta))
    story.append(Paragraph(
        f"{_humanise(req.category)} · {_humanise(req.department)} · "
        f"status: {_humanise(req.status.value)}"
        + (f" · with {_humanise(req.current_step)}" if req.current_step else ""),
        meta,
    ))
    story.append(Paragraph(
        f"Raised by {req.submitted_by} on {_dt(req.submitted_at)}"
        + (f" · project {req.project_code}" if req.project_code else "")
        + (f" · grant {req.grant_code}" if req.grant_code else ""),
        meta,
    ))
    story.append(Paragraph(
        f"Payment type: {_humanise(req.payment_type)} · "
        f"Amount in words: {rq.amount_in_words(req.amount, req.currency)}",
        meta,
    ))
    if req.description:
        story.append(Spacer(1, 4))
        story.append(Paragraph(req.description, body))

    # Payee bank/contact detail — the memo/Payment Voucher fields beyond the
    # bare name (multi-payee requisitions already carry this per row below).
    if not req.payees and (req.vendor_account or req.vendor_bank_name or req.vendor_tin
                            or req.vendor_phone_or_email):
        story.append(Paragraph("Payee detail", h2))
        rows = [[
            req.vendor_account or "—", req.vendor_bank_name or "—",
            req.vendor_tin or "—", req.vendor_phone_or_email or "—",
        ]]
        story.append(table(
            ["Account number", "Bank", "TIN", "Phone / email"], rows, [100, 100, 90, 130],
        ))

    # Budget line breakdown — mirrors NEEM's own memo item table. Totals are
    # always server-computed (see requisitions.BudgetLine).
    if req.budget_lines:
        story.append(Paragraph("Budget breakdown", h2))
        rows = [
            [bl.description, bl.unit, bl.budget_line, bl.quantity, bl.frequency,
             _money(bl.unit_cost, req.currency), _money(bl.line_total, req.currency)]
            for bl in req.budget_lines
        ]
        total_line = sum(bl.line_total for bl in req.budget_lines)
        rows.append(["", "", "", "", "", "Grand total", _money(total_line, req.currency)])
        story.append(table(
            ["Description", "Unit", "Budget line", "Qty", "Freq.", "Unit cost", "Total"],
            rows, [110, 45, 55, 30, 30, 65, 65],
        ))

    # Policy checks
    if req.checks:
        story.append(Paragraph("Policy checks", h2))
        rows = []
        for c in req.checks:
            result_label = c.result.value.upper() + (" (overridden)" if c.overridden else "")
            rows.append([c.name, result_label, c.policy_value, c.actual_value, c.message])
        story.append(table(
            ["Check", "Result", "Policy", "Actual", "Message"], rows,
            [95, 60, 60, 60, 145],
        ))
        overridden = [c for c in req.checks if c.overridden]
        if overridden:
            story.append(Spacer(1, 3))
            for c in overridden:
                story.append(Paragraph(
                    f"<b>{c.name}</b> released by {c.override_by or '—'}, "
                    f"authority: {c.override_authority or '—'} — "
                    f"&ldquo;{c.override_reason or ''}&rdquo;",
                    cell,
                ))

    # Approvals
    if req.approvals:
        story.append(Paragraph("Approval trail", h2))
        rows = [
            [_humanise(a.step), a.actor, a.decision.value.upper(), a.notes, _dt(a.at)]
            for a in req.approvals
        ]
        story.append(table(["Step", "Actor", "Decision", "Notes", "At"], rows, [70, 90, 55, 130, 75]))

    # Compliance check
    if req.compliance:
        story.append(Paragraph("Compliance rulebook check", h2))
        story.append(Paragraph(
            f"<b>{req.compliance.overall_verdict.upper()}</b> against "
            f"&ldquo;{req.compliance.rulebook_name}&rdquo; — {req.compliance.overall_summary}",
            body,
        ))
        story.append(Paragraph(
            f"Checked by {req.compliance.checked_by} on {_dt(req.compliance.checked_at)} "
            f"· {req.compliance.document_count} document(s) read",
            meta,
        ))
        if req.compliance.results:
            rows = [
                [f.rule_description, f.verdict.upper(), f.reasoning]
                for f in req.compliance.results
            ]
            story.append(table(["Rule", "Verdict", "Reasoning"], rows, [180, 60, 180]))

    # Comments
    if req.comments:
        story.append(Paragraph("Comments", h2))
        rows = [[c.author, _humanise(c.department), c.text, _dt(c.at)] for c in req.comments]
        story.append(table(["Author", "Department", "Comment", "At"], rows, [80, 65, 175, 100]))

    # Attachments — filenames/metadata only, never the file's own bytes.
    if req.attachments:
        story.append(Paragraph("Attachments", h2))
        rows = [
            [a.filename, f"{a.size:,} bytes", a.uploaded_by, _dt(a.uploaded_at)]
            for a in req.attachments
        ]
        story.append(table(["Filename", "Size", "Uploaded by", "At"], rows, [140, 60, 100, 120]))

    # Audit log
    story.append(Paragraph("Audit log", h2))
    story.append(Paragraph(
        "Hash chain verified — this record has not been altered outside the application."
        if rq.verify_audit_chain(req)
        else "⚠ HASH CHAIN DOES NOT VERIFY — this record's history may have been altered "
             "outside the application. Do not rely on this export without investigating.",
        ParagraphStyle(
            "DOCexAuditNote", parent=body,
            textColor=colors.HexColor("#059669") if rq.verify_audit_chain(req) else colors.HexColor("#DC2626"),
        ),
    ))
    rows = [
        [e.seq, _dt(e.at), e.actor, _humanise(e.event), e.detail]
        for e in req.audit_log
    ]
    story.append(table(["#", "At", "Actor", "Event", "Detail"], rows, [20, 75, 90, 70, 165]))

    doc.build(story)
    return buf.getvalue()


# ─── per-requisition Excel ──────────────────────────────────────────────────


def requisition_xlsx(req: rq.Requisition) -> bytes:
    """The same content as requisition_pdf(), laid out one sheet per section
    — the shape a finance officer can filter/sort/paste into a working
    file, matching the styling template bank_verify_routes.py established
    (banner row, colored header row, tinted verdict cells)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.worksheet import Worksheet

    HEADER_FILL = PatternFill("solid", start_color="2563EB")
    BANNER_FILL = PatternFill("solid", start_color="1F3A5F")
    RESULT_FILL = {
        "pass": PatternFill("solid", start_color="D1FAE5"),
        "warning": PatternFill("solid", start_color="FEF3C7"),
        "fail": PatternFill("solid", start_color="FEE2E2"),
    }

    def banner_row(ws: Worksheet, title: str, subtitle: str, span: int):
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
        c = ws.cell(row=1, column=1, value=title)
        c.font = Font(name="Arial", size=13, bold=True, color="FFFFFF")
        c.fill = BANNER_FILL
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 26
        if subtitle:
            ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
            c2 = ws.cell(row=2, column=1, value=subtitle)
            c2.font = Font(name="Arial", size=9, italic=True, color="666666")

    def header_row(ws: Worksheet, headers: list[str], row: int = 4):
        for col_idx, h in enumerate(headers, start=1):
            c = ws.cell(row=row, column=col_idx, value=h)
            c.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            c.fill = HEADER_FILL
            c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[row].height = 20

    def write_rows(ws: Worksheet, rows: list[list], start_row: int = 5, tint_col: Optional[int] = None,
                    tint_map: Optional[dict] = None):
        for r_off, row in enumerate(rows, start=start_row):
            for c_idx, value in enumerate(row, start=1):
                c = ws.cell(row=r_off, column=c_idx, value=value)
                c.font = Font(name="Arial", size=10)
                c.alignment = Alignment(vertical="top", wrap_text=True)
            if tint_col and tint_map:
                fill = tint_map.get(str(row[tint_col - 1]).lower())
                if fill:
                    for c_idx in range(1, len(row) + 1):
                        ws.cell(row=r_off, column=c_idx).fill = fill

    wb = Workbook()

    # Summary sheet
    ws = wb.active
    ws.title = "Summary"
    banner_row(ws, f"{req.ref} — {req.vendor_name}", f"Exported for audit", 2)
    summary_rows = [
        ["Reference", req.ref],
        ["Vendor / payee", req.vendor_name],
        ["Amount", _money(req.amount, req.currency)],
        ["Amount in words", rq.amount_in_words(req.amount, req.currency)],
        ["Payment type", _humanise(req.payment_type)],
        ["Category", _humanise(req.category)],
        ["Department", _humanise(req.department)],
        ["Status", _humanise(req.status.value)],
        ["Current step", _humanise(req.current_step) if req.current_step else "—"],
        ["Submitted by", req.submitted_by],
        ["Submitted at", _dt(req.submitted_at)],
        ["Project code", req.project_code or "—"],
        ["Grant code", req.grant_code or "—"],
        ["Vendor account", req.vendor_account or "—"],
        ["Vendor bank", req.vendor_bank_name or "—"],
        ["Vendor TIN", req.vendor_tin or "—"],
        ["Vendor phone / email", req.vendor_phone_or_email or "—"],
        ["Description", req.description or "—"],
        ["Audit chain", "Verified" if rq.verify_audit_chain(req) else "DOES NOT VERIFY"],
    ]
    for r_off, (label, value) in enumerate(summary_rows, start=4):
        ws.cell(row=r_off, column=1, value=label).font = Font(name="Arial", size=10, bold=True)
        ws.cell(row=r_off, column=2, value=value).font = Font(name="Arial", size=10)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 60

    # Policy checks sheet
    if req.checks:
        ws2 = wb.create_sheet("Policy Checks")
        banner_row(ws2, "Policy checks", req.ref, 6)
        header_row(ws2, ["Check", "Result", "Policy", "Actual", "Message", "Override"])
        rows = [
            [c.name, c.result.value, c.policy_value, c.actual_value, c.message,
             f"{c.override_by} — {c.override_reason}" if c.overridden else ""]
            for c in req.checks
        ]
        write_rows(ws2, rows, tint_col=2, tint_map=RESULT_FILL)
        for col, w in zip("ABCDEF", [28, 12, 18, 18, 40, 40]):
            ws2.column_dimensions[col].width = w

    # Budget lines sheet — the expense breakdown, mirroring NEEM's own memo
    # item table. Totals are always server-computed (requisitions.BudgetLine).
    if req.budget_lines:
        wsb = wb.create_sheet("Budget Lines")
        banner_row(wsb, "Budget breakdown", req.ref, 7)
        header_row(wsb, ["Description", "Unit", "Budget line", "Quantity", "Frequency",
                          "Unit cost", "Total"])
        write_rows(wsb, [
            [bl.description, bl.unit, bl.budget_line, bl.quantity, bl.frequency,
             bl.unit_cost, bl.line_total]
            for bl in req.budget_lines
        ])
        for col, w in zip("ABCDEFG", [32, 12, 18, 10, 10, 14, 14]):
            wsb.column_dimensions[col].width = w

    # Approvals sheet
    if req.approvals:
        ws3 = wb.create_sheet("Approvals")
        banner_row(ws3, "Approval trail", req.ref, 5)
        header_row(ws3, ["Step", "Actor", "Decision", "Notes", "At"])
        write_rows(ws3, [
            [_humanise(a.step), a.actor, a.decision.value, a.notes, _dt(a.at)]
            for a in req.approvals
        ])
        for col, w in zip("ABCDE", [20, 24, 14, 40, 20]):
            ws3.column_dimensions[col].width = w

    # Compliance sheet
    if req.compliance:
        ws4 = wb.create_sheet("Compliance Check")
        banner_row(ws4, f"Against “{req.compliance.rulebook_name}”",
                   f"{req.compliance.overall_verdict.upper()} — {req.compliance.overall_summary}", 3)
        header_row(ws4, ["Rule", "Verdict", "Reasoning"])
        write_rows(ws4, [
            [f.rule_description, f.verdict, f.reasoning] for f in req.compliance.results
        ])
        for col, w in zip("ABC", [45, 14, 55]):
            ws4.column_dimensions[col].width = w

    # Comments sheet
    if req.comments:
        ws5 = wb.create_sheet("Comments")
        banner_row(ws5, "Comments", req.ref, 4)
        header_row(ws5, ["Author", "Department", "Comment", "At"])
        write_rows(ws5, [
            [c.author, _humanise(c.department), c.text, _dt(c.at)] for c in req.comments
        ])
        for col, w in zip("ABCD", [24, 18, 55, 20]):
            ws5.column_dimensions[col].width = w

    # Attachments sheet
    if req.attachments:
        ws6 = wb.create_sheet("Attachments")
        banner_row(ws6, "Attachments", req.ref, 4)
        header_row(ws6, ["Filename", "Size (bytes)", "Uploaded by", "At"])
        write_rows(ws6, [
            [a.filename, a.size, a.uploaded_by, _dt(a.uploaded_at)] for a in req.attachments
        ])
        for col, w in zip("ABCD", [40, 14, 24, 20]):
            ws6.column_dimensions[col].width = w

    # Audit log sheet
    ws7 = wb.create_sheet("Audit Log")
    banner_row(
        ws7, "Audit log",
        "Hash chain verified" if rq.verify_audit_chain(req) else "HASH CHAIN DOES NOT VERIFY", 5,
    )
    header_row(ws7, ["#", "At", "Actor", "Event", "Detail"])
    write_rows(ws7, [
        [e.seq, _dt(e.at), e.actor, _humanise(e.event), e.detail] for e in req.audit_log
    ])
    for col, w in zip("ABCDE", [6, 20, 24, 20, 55]):
        ws7.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─── period log export (Excel only — see module docstring) ─────────────────


def requisition_log_xlsx(
    reqs: list[rq.Requisition],
    *,
    org_name: str,
    start: str,
    end: str,
    transactions_by_id: Optional[dict[str, rq.TransactionRecord]] = None,
) -> bytes:
    """One row per requisition raised in [start, end] — the weekly/monthly
    audit sweep export. `transactions_by_id` (req.transaction_id -> the
    frozen TransactionRecord) lets paid rows carry bank_reference/paid_at;
    the caller builds it (bounded to just the requisitions in this list,
    so this stays a pure function with no store access of its own)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    transactions_by_id = transactions_by_id or {}

    STATUS_FILL = {
        "paid": PatternFill("solid", start_color="D1FAE5"),
        "declined": PatternFill("solid", start_color="FEE2E2"),
        "on_hold": PatternFill("solid", start_color="F3F4F6"),
    }

    wb = Workbook()
    ws = wb.active
    ws.title = "Requisition Log"

    ws.merge_cells("A1:M1")
    c = ws.cell(row=1, column=1, value=f"{org_name} — Requisition log, {start} to {end}")
    c.font = Font(name="Arial", size=14, bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", start_color="1F3A5F")
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:M2")
    paid_count = sum(1 for r in reqs if r.status == rq.ReqStatus.PAID)
    paid_value = sum(r.amount for r in reqs if r.status == rq.ReqStatus.PAID)
    ws["A2"] = (
        f"{len(reqs)} requisition(s) · {paid_count} paid, {_money(paid_value, reqs[0].currency if reqs else 'NGN')} "
        f"· generated for audit"
    )
    ws["A2"].font = Font(name="Arial", size=9, italic=True, color="666666")

    headers = [
        "Ref", "Raised at", "Vendor", "Amount", "Currency", "Category",
        "Department", "Status", "Current step", "Blocking", "Warnings",
        "Overridden", "Bank reference", "Paid at",
    ]
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=col_idx, value=h)
        c.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="2563EB")
        c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[4].height = 20

    for r_off, r in enumerate(reqs, start=5):
        overridden = sum(1 for c in r.checks if c.overridden)
        warnings = sum(1 for c in r.checks if c.result.value == "warning")
        txn = transactions_by_id.get(r.transaction_id or "")
        values = [
            r.ref, _dt(r.submitted_at), r.vendor_name, r.amount, r.currency,
            r.category, r.department, r.status.value, r.current_step or "",
            len(rq.blocking_checks(r)), warnings, overridden,
            txn.bank_reference if txn else "", _dt(txn.paid_at) if txn else "",
        ]
        fill = STATUS_FILL.get(r.status.value)
        for col_idx, value in enumerate(values, start=1):
            c = ws.cell(row=r_off, column=col_idx, value=value)
            c.font = Font(name="Arial", size=10)
            if fill:
                c.fill = fill
        ws.cell(row=r_off, column=4).number_format = '#,##0.00'

    widths = [12, 20, 26, 14, 10, 16, 16, 12, 16, 10, 10, 12, 20, 20]
    for col, w in zip("ABCDEFGHIJKLMN", widths):
        ws.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
