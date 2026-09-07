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

    # The bank account these payments left, as named in QuickBooks.
    bank_account: str = ""
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
    return out[:200]


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
        klass = amap.classes.get(d.source_ref, "")
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
