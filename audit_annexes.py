"""
The annexes to the period audit report — everything logged, in the form an
auditor can actually work with.

WHY THIS IS A SEPARATE FILE FROM THE REPORT
===========================================
The report is read by a person: an ED, a board audit committee, a donor's
programme officer. Its value is that it is four pages and they finish it. Bolt
four hundred payments onto the back and it becomes forty pages nobody opens,
including the four that mattered.

But an auditor genuinely wants the whole population, and wants to sort, filter
and pivot it — which is a spreadsheet, not a PDF. Reading four hundred payments
in a PDF is nobody's idea of testing.

So: one pack, two artefacts. The PDF states the verdict and references the
annex; the annex evidences it. That is the shape a real audit deliverable
takes.

Five sheets, of which only the first previously existed anywhere:

  A · Requisitions        every payment request raised in the period
  B · Compliance checks   every rulebook check run — the evidence the policy
                          layer was USED rather than bypassed. Logged nowhere
                          else, and the difference between claiming you check
                          payments against policy and showing a year of it.
  C · Approvals           every decision, with who, when, and what they said
  D · Exceptions          every blocking check released, with reason and
                          authority
  E · Attachments         which supporting documents exist against which
                          payment, so "what do you hold for REQ-0042" is
                          answerable without opening it

PERSONAL DATA
=============
This is a personal-data export. Beneficiary names, account numbers, phone
numbers and tax IDs, hundreds of rows of it, leaving the system as a file that
gets emailed around. Account numbers are therefore MASKED to the last four
digits by default, and unmasking is a deliberate act the caller has to ask for
and which the route records. See mask_account().

No model is involved anywhere in this module. It is a transcription of stored
records.
"""
from __future__ import annotations

import io
from typing import Optional

import requisitions as rq
import store

_MASKED_PREFIX = "•••••• "


def mask_account(account: str, *, full: bool = False) -> str:
    """Last four digits unless the caller explicitly asked for the whole thing.

    An audit annex is usually circulated by email and stored on somebody's
    laptop. The last four digits identify an account well enough to match it
    against a bank statement, which is what the annex is for; the full number
    is what lets someone pay it.
    """
    account = (account or "").strip()
    if not account:
        return ""
    if full:
        return account
    return f"{_MASKED_PREFIX}{account[-4:]}" if len(account) > 4 else _MASKED_PREFIX


def _in_period(iso: str, start: str, end: str) -> bool:
    return bool(iso) and start <= iso[:10] <= end


def _dt(iso: Optional[str]) -> str:
    return iso[:19].replace("T", " ") if iso else ""


def _humanise(key: Optional[str]) -> str:
    if not key:
        return ""
    return " ".join(w.capitalize() for w in str(key).replace("_", " ").split())


def build_annexes_xlsx(
    org_id: str, start: str, end: str, *,
    org_name: str = "", full_account_numbers: bool = False,
) -> bytes:
    """Every record in the period, five sheets, ready to filter."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    org = store.require_org(org_id)
    reqs = [r for r in rq.list_requisitions(org) if _in_period(r.submitted_at, start, end)]
    txns = {t.requisition_id: t for t in rq.list_transactions(org)}

    HEADER = PatternFill("solid", start_color="2563EB")
    BANNER = PatternFill("solid", start_color="1F3A5F")

    wb = Workbook()

    def sheet(title: str, subtitle: str, headers: list[str], rows: list[list],
              widths: list[int], first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        span = max(len(headers), 1)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
        c = ws.cell(row=1, column=1, value=f"{org_name or org} — {title}")
        c.font = Font(name="Arial", size=13, bold=True, color="FFFFFF")
        c.fill = BANNER
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 26

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
        ws.cell(row=2, column=1, value=f"{subtitle} · {start} to {end}").font = Font(
            name="Arial", size=9, italic=True, color="666666")

        for i, h in enumerate(headers, start=1):
            hc = ws.cell(row=4, column=i, value=h)
            hc.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            hc.fill = HEADER
            hc.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[4].height = 20

        for r_off, row in enumerate(rows, start=5):
            for c_idx, value in enumerate(row, start=1):
                cell = ws.cell(row=r_off, column=c_idx, value=value)
                cell.font = Font(name="Arial", size=10)
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(row=4, column=i).column_letter].width = w

        # Filters on every sheet — the annex exists to be filtered, and an
        # auditor should not have to switch them on themselves.
        if rows:
            ws.auto_filter.ref = (
                f"A4:{ws.cell(row=4, column=len(headers)).column_letter}{4 + len(rows)}"
            )
        ws.freeze_panes = "A5"
        return ws

    # ─── A · Requisitions ───────────────────────────────────────────────────
    rows_a = []
    for r in reqs:
        txn = txns.get(r.id)
        rows_a.append([
            r.ref, _dt(r.submitted_at), r.vendor_name,
            mask_account(r.vendor_account, full=full_account_numbers),
            r.vendor_bank_name, r.amount, r.currency,
            _humanise(r.category), _humanise(r.payment_type),
            r.project_code, r.grant_code or "", _humanise(r.department),
            r.submitted_by, _humanise(r.status.value),
            _humanise(r.current_step) if r.current_step else "",
            len(r.payees), len(r.attachments), len(rq.blocking_checks(r)),
            sum(1 for c in r.checks if c.overridden),
            txn.bank_reference if txn else "", _dt(txn.paid_at) if txn else "",
            r.description,
        ])
    sheet("A Requisitions", "Every payment request raised in the period",
          ["Ref", "Raised", "Payee", "Account", "Bank", "Amount", "Ccy",
           "Category", "Payment type", "Project", "Grant", "Department",
           "Raised by", "Status", "With", "Payees", "Documents", "Blocking",
           "Overrides", "Bank reference", "Paid", "Description"],
          rows_a,
          [12, 18, 26, 16, 16, 14, 7, 18, 14, 12, 12, 16, 24, 13, 18, 9, 11,
           10, 10, 18, 18, 40],
          first=True)

    # ─── B · Compliance checks ──────────────────────────────────────────────
    # The evidence that the policy layer was used. Nothing else in the system
    # exports this, which means today an org cannot show an auditor a year of
    # policy checking even though it did it.
    rows_b = []
    for r in reqs:
        c = r.compliance
        if not c:
            continue
        rows_b.append([
            r.ref, c.rulebook_name, c.rulebook_id,
            _humanise(c.overall_verdict), c.document_count,
            c.checked_by, _dt(c.checked_at), len(c.results),
            sum(1 for f in c.results if f.verdict == "block"),
            sum(1 for f in c.results if f.verdict == "flag"),
            c.overall_summary,
        ])
    sheet("B Compliance checks",
          "Every policy-rulebook check run against a payment in the period",
          ["Ref", "Rulebook", "Rulebook ID", "Verdict", "Documents read",
           "Checked by", "Checked at", "Rules", "Blocking", "Flagged", "Summary"],
          rows_b, [12, 28, 20, 14, 14, 24, 18, 8, 10, 10, 60])

    # ─── C · Approvals ──────────────────────────────────────────────────────
    rows_c = []
    for r in reqs:
        for a in r.approvals:
            rows_c.append([
                r.ref, _humanise(a.step), _humanise(a.department), a.actor,
                _humanise(a.decision.value), _dt(a.at),
                ", ".join(a.overrides), a.notes,
            ])
    sheet("C Approvals", "Every decision recorded against a payment",
          ["Ref", "Stage", "Department", "Decided by", "Decision", "At",
           "Checks released", "Notes"],
          rows_c, [12, 22, 18, 26, 12, 18, 22, 50])

    # ─── D · Exceptions ─────────────────────────────────────────────────────
    rows_d = []
    for r in reqs:
        for c in r.checks:
            if not c.overridden:
                continue
            rows_d.append([
                r.ref, c.code, c.name, c.policy_value, c.actual_value,
                c.override_by or "", c.override_authority or "",
                c.override_reason or "NO REASON RECORDED", r.amount,
            ])
    sheet("D Exceptions", "Every blocking policy check released, and on whose authority",
          ["Ref", "Check", "Name", "Policy", "Actual", "Released by",
           "Authority", "Reason", "Amount"],
          rows_d, [12, 18, 26, 18, 18, 24, 22, 55, 14])

    # ─── E · Attachments ────────────────────────────────────────────────────
    rows_e = []
    for r in reqs:
        for a in r.attachments:
            rows_e.append([
                r.ref, a.filename, a.content_type, a.size,
                a.uploaded_by, _dt(a.uploaded_at),
            ])
    sheet("E Attachments", "Supporting documents held against each payment",
          ["Ref", "Filename", "Type", "Size (bytes)", "Uploaded by", "Uploaded at"],
          rows_e, [12, 44, 24, 14, 26, 18])

    # A note on the pack itself, so the file explains its own scope and its
    # own redactions to whoever opens it six months from now.
    ws = wb.create_sheet("About")
    notes = [
        ("Organisation", org_name or org),
        ("Period", f"{start} to {end}"),
        ("Requisitions in period", len(reqs)),
        ("Compliance checks recorded", len(rows_b)),
        ("Approval decisions", len(rows_c)),
        ("Exceptions released", len(rows_d)),
        ("Supporting documents", len(rows_e)),
        ("Account numbers",
         "Shown in full" if full_account_numbers else "Masked to the last four digits"),
        ("Basis", "Transcribed from stored records. No figure is estimated and "
                  "no part of this pack was generated by a language model."),
        ("Completeness", "Every requisition whose submission date falls in the "
                         "period is listed in Annex A, including drafts and "
                         "declined requests."),
    ]
    ws.cell(row=1, column=1, value="About this pack").font = Font(
        name="Arial", size=13, bold=True)
    for i, (label, value) in enumerate(notes, start=3):
        ws.cell(row=i, column=1, value=label).font = Font(name="Arial", size=10, bold=True)
        ws.cell(row=i, column=2, value=value).font = Font(name="Arial", size=10)
        ws.cell(row=i, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 78

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
