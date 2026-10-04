"""
QuickBooks export — DOCex sits in FRONT of the accounting system, not against it.

THE POSITION THIS FILE ENCODES
NEEM and EVA both run QuickBooks, and QuickBooks already reconciles a bank
account. Building a competing general ledger would be a losing argument and a
waste of their money. The two systems answer different questions:

    QuickBooks   — does my LEDGER match the bank?        (completeness)
    DOCex        — was every payment AUTHORISED, by whom,
                   under which policy, with what evidence? (control)

QuickBooks structurally cannot answer the second one, because approval does not
exist inside it. Someone types an expense in and it is there. There is no
delegation of authority, no policy check, no named approver, no hash-chained
trail. So in QuickBooks an unauthorised transfer looks exactly like a payment
somebody forgot to enter — and the fix for both is the same click:
"Add". That is precisely how an unauthorised payment gets quietly absorbed
into the books.

DOCex is what happens BEFORE QuickBooks. This module is the handoff.

THE TWO EXPORTS, AND WHY THE SECOND ONE IS THE SURPRISE

1. PAYMENT REGISTER — every approved, paid disbursement for the month, already
   coded to an account and a class/project. Today someone re-types those into
   QuickBooks by hand, which is both the largest ongoing time cost and the
   place where the coding drifts from what was actually approved. Exporting it
   removes the re-typing and means the QuickBooks entry says what the approval
   said.

2. A QUICKBOOKS-READY BANK STATEMENT. Nigerian banks are not supported by
   QuickBooks bank feeds — GTBank cannot be connected — so NEEM already
   downloads a CSV and imports it by hand. But QuickBooks rejects exactly what
   Nigerian bank exports contain: currency symbols, comma thousands
   separators, title rows above the headers, and more than four columns. So
   somebody reformats that file in Excel every month.

   DOCex already parses those statements properly, for reconciliation. Emitting
   a clean 3-column file is nearly free for us and deletes a monthly chore
   they have never mentioned because they assume it is just how it is.

WHY CSV BEFORE API
The QuickBooks Online API is the right long-term integration and this module is
shaped so it can become the sink later — the mapping logic is separate from the
writing. But the API needs an Intuit developer app, OAuth, and the client's own
credentials, none of which exist before a contract is signed. A file works on
day one, with no access to anybody's accounting system, which is also an easier
thing for a finance lead to say yes to.

⚠️ COLUMN NAMES MUST BE CONFIRMED. QuickBooks import screens differ by region
   and product tier. The bank format below follows Intuit's published 3/4
   column rules and is safe. The payment register is a well-labelled CSV whose
   columns are MAPPED on QuickBooks' import screen — it is not a magic format,
   and pretending otherwise would produce a failed import in front of a client.
"""
from __future__ import annotations

from sheet_safety import harden_workbook

import csv
import datetime as dt
import io
import re
from typing import Iterable, Optional

from pydantic import BaseModel, Field

import store

_CONFIG = "config"
_MAP_ID = "accounting_map"

# Intuit's documented ceiling for a manual bank CSV upload: roughly 1,000–1,500
# rows / 350KB. We split well below it rather than let an import fail on size.
QBO_ROWS_PER_FILE = 1000


class ExportError(ValueError):
    """Bad mapping or period — callers map this to HTTP 4xx."""


class AccountMap(BaseModel):
    """How DOCex coding becomes QuickBooks coding.

    Configuration, not code. Every organisation's chart of accounts differs,
    and guessing an account name produces entries that import cleanly and are
    posted to the wrong place — worse than an import that fails loudly.
    """
    # DOCex spend category → QuickBooks expense account name.
    accounts: dict[str, str] = Field(default_factory=dict)
    default_account: str = "Uncategorised Expense"

    # Project / grant code → QuickBooks Class (or Customer, for grant tracking).
    classes: dict[str, str] = Field(default_factory=dict)
    # Most donor-funded NGOs track a grant as a Customer/Job so that reports
    # come out per funder. Off by default: it changes the shape of their books.
    grant_as_customer: bool = False

    # Fallback name of the bank account in QuickBooks, for organisations that
    # have not registered their accounts. Each registered bank account carries
    # its own QuickBooks name (bank_accounts.quickbooks_name), which wins.
    bank_account: str = ""

    # Which QuickBooks the organisation runs — it decides what can be imported:
    #   online_international  bank transactions only (Intuit: no journal import
    #                         outside the US) — the coded bank file
    #   online_us             + journal entries (CSV)
    #   desktop               + journal entries (IIF)
    edition: str = "online_international"
    # Where the bank's own charges are posted.
    bank_charges_account: str = "Bank charges"
    # QuickBooks date format on the import screen. Their books, their setting.
    date_format: str = "%d/%m/%Y"


# ─── configuration ──────────────────────────────────────────────────────────


def set_map(org_id: str, amap: AccountMap) -> AccountMap:
    store.get_store().put(store.require_org(org_id), _CONFIG, _MAP_ID,
                          amap.model_dump())
    return amap


def get_map(org_id: str) -> AccountMap:
    raw = store.get_store().get(store.require_org(org_id), _CONFIG, _MAP_ID)
    return AccountMap.model_validate(raw) if raw else AccountMap()


# ─── helpers ────────────────────────────────────────────────────────────────


def _qbo_amount(value: float) -> str:
    """QuickBooks rejects currency symbols and thousands separators outright.

    So this returns a bare decimal — the single most common cause of a failed
    bank import, and the reason a person sits in Excel every month deleting
    naira signs.
    """
    return f"{float(value or 0):.2f}"


def _qbo_date(iso: str, fmt: str) -> str:
    s = (iso or "")[:10]
    try:
        return dt.date.fromisoformat(s).strftime(fmt)
    except ValueError:
        return s


def _clean_text(s: str) -> str:
    """One line, no control characters, trimmed. QuickBooks truncates long
    descriptions silently, so keep them short enough to survive."""
    out = re.sub(r"\s+", " ", str(s or "")).strip()
    # Text only: a payee or description starting with = + - @ would run as
    # a formula when the CSV is opened in Excel (30 Sep audit, M2).
    from sheet_safety import csv_text
    return csv_text(out[:200])


def _period_bounds(period: str) -> tuple[str, str]:
    try:
        year, month = (int(p) for p in period.split("-")[:2])
        start = dt.date(year, month, 1)
    except (ValueError, TypeError) as exc:
        raise ExportError(f"Period must look like '2026-08', got '{period}'.") from exc
    end = (dt.date(year + (month == 12), (month % 12) + 1, 1)
           - dt.timedelta(days=1))
    return start.isoformat(), end.isoformat()


def _write(rows: Iterable[list], header: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# ─── 1. bank statement, QuickBooks-ready ────────────────────────────────────


def bank_statement_csv(
    lines: list,
    *,
    date_format: str = "%d/%m/%Y",
    four_column: bool = False,
) -> list[str]:
    """Turn a parsed bank statement into files QuickBooks will actually accept.

    Takes the BankLine objects the reconciliation importer already produces —
    so all the hard work (skipping the bank's title rows, detecting columns,
    proving day-first vs month-first, stripping ₦ and commas) is already done.

    Returns a LIST of CSV strings: QuickBooks caps a manual upload at roughly
    a thousand rows, and a statement that exceeds it fails on upload rather
    than importing the first thousand. Splitting here means the client uploads
    two files instead of discovering the limit themselves.

    `four_column` emits Date/Description/Credit/Debit instead of a single
    signed Amount — some QuickBooks regions prefer it, and it is one flag
    rather than a support conversation.
    """
    header = (["Date", "Description", "Credit", "Debit"] if four_column
              else ["Date", "Description", "Amount"])

    rows: list[list] = []
    for ln in lines:
        date = _qbo_date(getattr(ln, "date", ""), date_format)
        # Keep the bank's own reference in the description: it is what the
        # bookkeeper matches on, and QuickBooks has nowhere else to put it.
        desc = _clean_text(
            f"{getattr(ln, 'description', '')} {getattr(ln, 'reference', '')}")
        amount = float(getattr(ln, "amount", 0.0))
        if four_column:
            out_flow = getattr(ln, "is_debit", amount < 0)
            rows.append([date, desc,
                         "" if out_flow else _qbo_amount(abs(amount)),
                         _qbo_amount(abs(amount)) if out_flow else ""])
        else:
            rows.append([date, desc, _qbo_amount(amount)])

    if not rows:
        raise ExportError("No transactions to export.")

    return [_write(rows[i:i + QBO_ROWS_PER_FILE], header)
            for i in range(0, len(rows), QBO_ROWS_PER_FILE)]


# ─── 2. the coded payment register ──────────────────────────────────────────


def payment_register_csv(org_id: str, period: str,
                         amap: Optional[AccountMap] = None) -> str:
    """Every approved payment for the month, coded and ready to enter.

    This is the export that removes the re-typing. Each row carries what was
    APPROVED — payee, amount, account, class, project, the DOCex reference and
    the bank reference — so the QuickBooks entry says the same thing the
    approval said, rather than whatever the person entering it remembered.

    The DOCex reference column is the important one and is easy to overlook:
    it is what lets somebody standing in QuickBooks six months later ask "who
    approved this?" and get an answer, by looking that reference up.
    """
    org = store.require_org(org_id)
    amap = amap or get_map(org)
    start, end = _period_bounds(period)

    import disbursements as _disb
    payments = sorted(_disb.list_disbursements(org, start=start, end=end),
                      key=lambda d: d.paid_at or "")

    rows = []
    for d in payments:
        category = (d.memo or "").strip().lower()
        account = amap.accounts.get(category, amap.default_account)
        # Classes are keyed by PROJECT/GRANT code (e.g. "B4"), not the
        # requisition reference — using d.source_ref here was a real bug that
        # left the QuickBooks Class column blank on every requisition payment
        # regardless of how the map was configured, silently breaking
        # per-grant/per-donor reporting. Grant code wins when both are set:
        # it is the more specific donor-facing bucket.
        class_key = getattr(d, "grant_code", None) or getattr(d, "project_code", "") or ""
        klass = amap.classes.get(class_key, "") if class_key else ""
        rows.append([
            _qbo_date(d.paid_at, amap.date_format),
            _clean_text(d.payee_name),
            _qbo_amount(d.amount),
            account,
            klass,
            amap.bank_account,
            d.bank_reference,
            d.source_ref,                       # REQ-0007 / PR3 / V7
            d.source_kind.value,
            _clean_text(d.memo),
        ])

    return _write(rows, [
        "Date", "Payee", "Amount", "Account", "Class", "Paid From",
        "Bank Reference", "DOCex Reference", "Source", "Memo",
    ])


def unmapped_categories(org_id: str, period: str,
                        amap: Optional[AccountMap] = None) -> list[str]:
    """Categories in this month's payments with no account mapped.

    Surfaced BEFORE the export is handed over, because the alternative is a
    bookkeeper finding forty rows posted to "Uncategorised Expense" and
    re-coding them by hand — which is the work the export was supposed to
    remove.
    """
    org = store.require_org(org_id)
    amap = amap or get_map(org)
    start, end = _period_bounds(period)

    import disbursements as _disb
    seen = {(d.memo or "").strip().lower()
            for d in _disb.list_disbursements(org, start=start, end=end)}
    return sorted(c for c in seen if c and c not in amap.accounts)


def export_summary(org_id: str, period: str) -> dict:
    """What the export will contain, before anyone downloads it."""
    org = store.require_org(org_id)
    amap = get_map(org)
    start, end = _period_bounds(period)

    import disbursements as _disb
    payments = _disb.list_disbursements(org, start=start, end=end)
    unmapped = unmapped_categories(org, period, amap)

    return {
        "period": period,
        "payments": len(payments),
        "value": round(sum(d.amount for d in payments), 2),
        "bank_account": amap.bank_account,
        "accounts_mapped": len(amap.accounts),
        "unmapped_categories": unmapped,
        "ready": not unmapped and bool(amap.bank_account),
        # Said out loud so nobody discovers it on the QuickBooks import screen.
        "note": ("Column names are mapped on the QuickBooks import screen — "
                 "they differ by region and plan. Confirm the mapping on the "
                 "first import; QuickBooks remembers it afterwards."),
    }


# ─── 3. from a reconciled month: the files QuickBooks can take ──────────────
#
# Research, Sept 2026 (Intuit help centre): the international edition of
# QuickBooks Online — the one Nigerian organisations use — imports bank
# transactions (Date, Description, Amount) and bills, but NOT journal entries
# or expenses ("unavailable in the QuickBooks Online international version",
# Intuit staff). The US edition imports journal entries (Journal No., Journal
# Date, Account Name, Debits, Credits; debits = credits per journal; under
# 1,000 rows). QuickBooks Desktop imports IIF.
#
# So everything here is built FROM A RECONCILIATION RUN: only money the bank
# confirms moved, matched to an approval, reaches the books. The bank file
# works on every edition and replaces the raw statement people upload today;
# the journals are for the editions that can import them, and only from a
# closed month.

EDITIONS = ("online_international", "online_us", "desktop")


def _run_account(org_id: str, run):
    if not getattr(run, "account_id", ""):
        return None
    try:
        import bank_accounts as _ba
        return _ba.get(org_id, run.account_id)
    except Exception:  # noqa: BLE001
        return None


def quickbooks_bank_name(org_id: str, run, amap: "AccountMap") -> str:
    acct = _run_account(org_id, run)
    return ((acct.quickbooks_name if acct else "") or amap.bank_account
            or (acct.label if acct else "")).strip()


def _coding(org_id: str, disbursement_id: str, amap: "AccountMap") -> dict:
    """Account and class for one matched payment, from what was approved."""
    import disbursements as _disb
    d = _disb.get(org_id, disbursement_id)
    if d is None:
        return {"payee": "", "ref": "", "account": amap.default_account, "klass": ""}
    category = (getattr(d, "category", "") or d.memo or "").strip().lower()
    class_key = getattr(d, "grant_code", None) or getattr(d, "project_code", "") or ""
    return {"payee": d.payee_name, "ref": d.source_ref,
            "account": amap.accounts.get(category, amap.default_account),
            "klass": amap.classes.get(class_key, "") if class_key else "",
            "id": d.id}


def _line_labels(org_id: str, run, amap: "AccountMap") -> dict:
    """bank_line_id → the description QuickBooks should show for it."""
    out = {}
    for m in run.matches:
        c = _coding(org_id, m.transaction_id, amap)
        parts = [c["payee"] or m.vendor_name, c["ref"] or m.transaction_ref, c["account"], c["klass"]]
        out[m.bank_line_id] = " · ".join(p for p in parts if p)
    for e in run.exceptions:
        if e.code.value == "BANK_CHARGE" and e.bank_line_id:
            out[e.bank_line_id] = f"{amap.bank_charges_account} · {e.description}"
    return out


def bank_upload_from_run(org_id: str, run, amap: Optional["AccountMap"] = None) -> list[str]:
    """The month's statement as QuickBooks' 3-column bank file, every line
    labelled: matched payments say payee · reference · account · class, bank
    charges say the charges account, everything else keeps the bank's words.

    Upload it INSTEAD of the raw statement (Banking → Upload from file). One
    bank rule per expense account ("Description contains '· Venue costs ·'")
    then files each month's lines by itself."""
    org = store.require_org(org_id)
    amap = amap or get_map(org)
    labels = _line_labels(org, run, amap)
    lines = sorted(list(run.bank_lines) + list(getattr(run, "credit_lines", []) or []),
                   key=lambda ln: (ln.date, ln.row))
    rows = []
    for ln in lines:
        desc = labels.get(ln.id) or f"{ln.description} {ln.reference}"
        rows.append([_qbo_date(ln.date, amap.date_format), _clean_text(desc),
                     _qbo_amount(ln.amount_minor / 100.0)])
    if not rows:
        raise ExportError("This statement has no lines in the month.")
    header = ["Date", "Description", "Amount"]
    return [_write(rows[i:i + QBO_ROWS_PER_FILE], header)
            for i in range(0, len(rows), QBO_ROWS_PER_FILE)]


def _journal_entries(org_id: str, run, amap: "AccountMap") -> list[dict]:
    """Balanced journals for a CLOSED month: one per matched payment (debit
    the expense account + class, credit the bank), one for the month's bank
    charges. Explained-but-unmatched money is never posted: nothing approved
    it, so nothing in DOCex can say which account it belongs to."""
    if not run.locked:
        raise ExportError("Close the month first. Only a closed reconciliation goes to "
                          "QuickBooks, so the books only ever hold money the bank confirmed.")
    bank = quickbooks_bank_name(org_id, run, amap)
    if not bank:
        raise ExportError("Set this bank account's QuickBooks name (Settings → Bank accounts).")
    entries, used = [], {}
    for m in sorted(run.matches, key=lambda m: (m.bank_date, m.transaction_ref, m.transaction_id)):
        c = _coding(org_id, m.transaction_id, amap)
        ref = (c["ref"] or m.transaction_ref or "PAY").replace(" ", "")
        used[ref] = used.get(ref, 0) + 1
        entries.append({"no": f"DX-{ref}" + (f"-{used[ref]}" if used[ref] > 1 else ""),
                        "date": m.bank_date, "debit_account": c["account"], "klass": c["klass"],
                        "credit_account": bank, "amount": m.amount,
                        "description": " · ".join(p for p in (c["payee"] or m.vendor_name, c["ref"]) if p)})
    charges = [e for e in run.exceptions if e.code.value == "BANK_CHARGE"]
    if charges:
        entries.append({"no": f"DX-{run.period}-CHG", "date": run.period_end,
                        "debit_account": amap.bank_charges_account, "klass": "",
                        "credit_account": bank, "amount": round(sum(e.amount for e in charges), 2),
                        "description": f"Bank charges {run.period} ({len(charges)} items)"})
    return entries


def journal_csv_from_run(org_id: str, run, amap: Optional["AccountMap"] = None) -> str:
    """QuickBooks Online (US) journal import: Settings → Import data →
    Journal entries. Journal numbers are stable, so importing the same month
    twice is caught by QuickBooks' duplicate-number warning."""
    org = store.require_org(org_id)
    amap = amap or get_map(org)
    rows = []
    for e in _journal_entries(org, run, amap):
        date = _qbo_date(e["date"], amap.date_format)
        memo = f"DOCex reconciliation {run.period}"
        rows.append([e["no"], date, e["debit_account"], _qbo_amount(e["amount"]), "",
                     _clean_text(e["description"]), e["klass"], memo])
        rows.append([e["no"], date, e["credit_account"], "", _qbo_amount(e["amount"]),
                     _clean_text(e["description"]), e["klass"], memo])
    return _write(rows, ["Journal No.", "Journal Date", "Account Name", "Debits", "Credits",
                         "Description", "Class", "Memo"])


def journal_iif_from_run(org_id: str, run, amap: Optional["AccountMap"] = None) -> str:
    """QuickBooks Desktop: File → Utilities → Import → IIF Files. Tab-
    separated GENERAL JOURNAL transactions; each sums to zero."""
    org = store.require_org(org_id)
    amap = amap or get_map(org)
    out = ["!TRNS\tTRNSID\tTRNSTYPE\tDATE\tACCNT\tCLASS\tAMOUNT\tDOCNUM\tMEMO",
           "!SPL\tSPLID\tTRNSTYPE\tDATE\tACCNT\tCLASS\tAMOUNT\tDOCNUM\tMEMO",
           "!ENDTRNS"]

    def clean(v):
        return _clean_text(v).replace("\t", " ")
    for e in _journal_entries(org, run, amap):
        date = _qbo_date(e["date"], amap.date_format)
        out.append("\t".join(["TRNS", "", "GENERAL JOURNAL", date, clean(e["debit_account"]),
                              clean(e["klass"]), _qbo_amount(e["amount"]), e["no"], clean(e["description"])]))
        out.append("\t".join(["SPL", "", "GENERAL JOURNAL", date, clean(e["credit_account"]),
                              clean(e["klass"]), _qbo_amount(-e["amount"]), e["no"], clean(e["description"])]))
        out.append("ENDTRNS")
    return "\n".join(out) + "\n"


def reconciliation_report_xlsx(org_id: str, run, amap: Optional["AccountMap"] = None) -> bytes:
    """The month, as evidence for an auditor or a donor: what matched, what
    was explained and by whom, the bank's charges, the money in, whether the
    statement was complete, and who closed and who signed it off."""
    import openpyxl
    from openpyxl.styles import Font

    import bank_reconciliation as br
    org = store.require_org(org_id)
    amap = amap or get_map(org)
    s = br.summary(run)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"
    bold = Font(bold=True)

    def money(v):
        return None if v is None else round(float(v), 2)
    complete = {True: "Yes — every running balance agrees", False: "NO — rows missing or altered",
                None: "Not checked (no balance column)"}[s["statement_complete"]]
    rows = [
        ("Bank reconciliation", f"{run.account_label or quickbooks_bank_name(org, run, amap) or 'Account'} — {run.period}"),
        ("Statement file", run.statement_name), ("Statement fingerprint (SHA-256)", run.statement_sha256),
        ("Opening balance", money(s["opening_balance"])), ("Money in", money(s["money_in_total"])),
        ("Money out", money(run.total_debits_in_bank)), ("Closing balance", money(s["closing_balance"])),
        ("Statement complete", complete),
        ("Payments approved in DOCex and confirmed by the bank", f"{s['matched']} ({money(s['matched_value']):,.2f})"),
        ("Bank charges", f"{s['bank_charges_count']} ({money(s['bank_charges_total']):,.2f})"),
        ("Items explained", s["explained"]), ("Items still open", s["open_items"]),
        ("Reconciled", "Yes" if s["reconciled"] else "No"),
        ("Closed by", f"{run.closed_by or '— not closed'} {run.closed_at[:16].replace('T', ' ')}"),
        ("Signed off by", f"{run.reviewed_by or '— not yet signed off'} {run.reviewed_at[:16].replace('T', ' ')}"),
    ]
    for r in rows:
        ws.append(list(r))
    for c in ws["A"]:
        c.font = bold
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 70

    labels = _line_labels(org, run, amap)
    m = wb.create_sheet("Matched")
    m.append(["Bank date", "Amount", "Payee", "DOCex reference", "Account", "Class", "How matched", "Paid in DOCex"])
    for x in run.matches:
        c = _coding(org, x.transaction_id, amap)
        m.append([x.bank_date, money(x.amount), c["payee"] or x.vendor_name, c["ref"] or x.transaction_ref,
                  c["account"], c["klass"], x.method.value, (x.paid_at or "")[:10]])
    o = wb.create_sheet("Explained & open items")
    o.append(["Date", "Amount", "What", "Description", "Status", "Explanation / note"])
    for e in run.exceptions:
        if e.code.value == "BANK_CHARGE":
            continue
        explained = "EXPLAINED by" in (e.note or "")
        o.append([e.date, money(e.amount), e.code.value.replace("_", " ").title(),
                  e.description or e.transaction_ref,
                  "Explained" if explained else ("Open" if e.severity.value == "high" else "Carried forward"),
                  e.note])
    ch = wb.create_sheet("Bank charges")
    ch.append(["Date", "Amount", "Narration"])
    for e in run.exceptions:
        if e.code.value == "BANK_CHARGE":
            ch.append([e.date, money(e.amount), e.description])
    ch.append(["Total", money(s["bank_charges_total"]), ""])
    mi = wb.create_sheet("Money in")
    mi.append(["Date", "Amount", "Narration", "Reference"])
    for ln in getattr(run, "credit_lines", []) or []:
        mi.append([ln.date, money(ln.amount_minor / 100.0), ln.description, ln.reference])
    for sheet in wb.worksheets[1:]:
        for c in sheet[1]:
            c.font = bold
    buf = io.BytesIO()
    harden_workbook(wb)  # staff-typed text must never run as a formula (M2)
    wb.save(buf)
    return buf.getvalue()
