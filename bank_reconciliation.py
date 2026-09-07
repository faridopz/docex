"""
Month-end bank reconciliation — does what we say we paid match what the bank
says left the account?

NEEM asked for this by name. It is the last control in the chain: requisitions
prove a payment was authorised, the audit log proves who authorised it, and
reconciliation proves the money that actually moved is the money that was
authorised. Without it, the first three are a story about the account rather
than a description of it.

THE TWO FINDINGS THAT MATTER
----------------------------
1. **A bank debit with no requisition.** Money left the account and no one in
   the system approved it. This is the finding an auditor cares most about and
   the one a spreadsheet reconciliation misses most often, because a person
   ticking off a statement works from the payment list down to the statement —
   never from the statement back to the payment list. This engine matches in
   BOTH directions, always.

2. **A payment recorded as made that never cleared.** Either it failed, or it
   was recorded before it was sent. Near a period boundary that is usually
   timing; well inside the period it is not.

WHY THE MATCHING IS DELIBERATELY CONSERVATIVE
---------------------------------------------
A reconciliation tool that quietly mismatches is worse than no tool, because it
produces a clean report over a wrong pairing and a human stops looking. So:

* Every match is deterministic — amount, date window, bank reference, vendor
  name. No model is consulted anywhere in this file.
* Amounts are compared in integer minor units (kobo). Floats do not decide
  whether two payments are equal.
* A pairing is only accepted when it is unique from BOTH sides in its pass. If
  two payments and two bank lines share an amount and a week, the engine reports
  four ambiguous items rather than pairing them off in file order and being
  right half the time.
* A reference that matches on a DIFFERENT amount is not a match. It is an
  AMOUNT_MISMATCH exception — that pairing is the discovery, not the error.

DATES ARE NOT GUESSED
---------------------
`03/04/2026` is 3 April to a Nigerian bank and 4 March to an American one. The
importer reads the whole column and only accepts a format the data itself
proves (a day > 12 somewhere). Where the column is genuinely ambiguous it
raises and asks for `date_format` to be set, rather than silently reading every
date wrong by up to eleven months.

STATEMENT FORMATS
-----------------
Column names differ by bank. `ColumnMap` is configuration: auto-detection
handles the common Nigerian layouts, an org can pin its own mapping, and every
run records the mapping it used so a human can check the import was read the
way they think it was.

⚠️ Confirm the mapping against a real statement from the client's bank before
   go-live. Auto-detection is a convenience, not a guarantee.

Storage is org-scoped (store.py). A closed run is immutable.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import re
import uuid
from enum import Enum
from typing import Iterable, Optional

from pydantic import BaseModel, Field

import store

_RUNS = "reconciliation_runs"
# Collection names are storage keys: no slashes. The org's statement
# layout is one document in the shared "config" collection, like
# departments and feature flags.
_COLUMN_MAP = "config"
_MAP_ID = "bank_columns"

# How far apart a payment date and a bank value date may be and still pair.
# Nigerian interbank transfers usually clear same-day; cheques and some
# scheduled batches do not. Configurable per run.
DEFAULT_DATE_WINDOW_DAYS = 5

# A payment made within this many days of the period end that has not cleared
# is timing, not a defect. Beyond it, someone should look.
DEFAULT_SETTLEMENT_DAYS = 3

# A bank reference shorter than this is not distinctive enough to match on.
_MIN_REF_LEN = 4


# ─── models ─────────────────────────────────────────────────────────────────


class MatchMethod(str, Enum):
    REFERENCE = "reference"      # bank reference agreed, and so did the amount
    EXACT = "exact"              # amount + date window, unique both sides
    VENDOR = "vendor"            # amount + vendor name in the narration
    MANUAL = "manual"            # a human paired them, with a reason


class ExceptionCode(str, Enum):
    NOT_IN_BANK = "NOT_IN_BANK"                 # we say paid, bank has no line
    NOT_IN_SYSTEM = "NOT_IN_SYSTEM"             # bank debit, no requisition
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"         # same reference, different amount
    AMBIGUOUS = "AMBIGUOUS"                     # several equally good candidates
    DUPLICATE_BANK_LINE = "DUPLICATE_BANK_LINE"  # same debit twice on the statement


class Severity(str, Enum):
    HIGH = "high"        # money is unexplained — resolve before closing
    MEDIUM = "medium"    # explainable, still needs a human
    LOW = "low"          # informational


class ColumnMap(BaseModel):
    """How to read this bank's statement export.

    Either give `amount` (one signed column) or `debit`/`credit` (two columns).
    Header matching is case-insensitive and ignores spaces and punctuation, so
    "Value Date", "VALUE_DATE" and "valuedate" are the same column.
    """
    date: str = ""
    description: str = ""
    reference: str = ""
    debit: str = ""
    credit: str = ""
    amount: str = ""
    date_format: str = ""        # e.g. "%d/%m/%Y". Empty = infer from the data.
    detected: bool = False       # True when auto-detection produced this


class BankLine(BaseModel):
    """One row of the imported statement, normalised."""
    id: str
    row: int                     # 1-based row number in the file, for tracing
    date: str = ""               # ISO
    description: str = ""
    reference: str = ""
    amount_minor: int = 0        # negative = money OUT of the account
    raw: dict = Field(default_factory=dict)

    @property
    def amount(self) -> float:
        return self.amount_minor / 100.0

    @property
    def is_debit(self) -> bool:
        return self.amount_minor < 0


class Match(BaseModel):
    """A payment paired with the bank line that settled it."""
    transaction_id: str = ""
    transaction_ref: str = ""
    bank_line_id: str = ""
    bank_row: int = 0
    method: MatchMethod = MatchMethod.EXACT
    amount: float = 0.0
    paid_at: str = ""
    bank_date: str = ""
    day_gap: int = 0
    vendor_name: str = ""
    matched_by: str = ""         # actor, for MANUAL
    reason: str = ""             # required for MANUAL


class ReconException(BaseModel):
    """Something that did not reconcile. Every one needs a human."""
    code: ExceptionCode
    severity: Severity = Severity.MEDIUM
    amount: float = 0.0
    date: str = ""
    description: str = ""
    transaction_id: str = ""
    transaction_ref: str = ""
    bank_line_id: str = ""
    bank_row: int = 0
    candidates: list[str] = Field(default_factory=list)
    note: str = ""


class ReconciliationRun(BaseModel):
    """The month-end reconciliation, as evidence.

    Once `locked`, nothing in it changes. Re-importing a corrected statement
    produces a NEW run; it never edits this one.
    """
    id: str
    org_id: str = ""
    period: str = ""                 # "2026-08"
    period_start: str = ""
    period_end: str = ""

    statement_name: str = ""
    statement_sha256: str = ""       # proves WHICH file was reconciled
    statement_lines: int = 0
    column_map: ColumnMap = Field(default_factory=ColumnMap)
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS

    matches: list[Match] = Field(default_factory=list)
    exceptions: list[ReconException] = Field(default_factory=list)
    bank_lines: list[BankLine] = Field(default_factory=list)

    total_paid_in_system: float = 0.0
    total_debits_in_bank: float = 0.0
    total_matched: float = 0.0
    variance: float = 0.0

    created_at: str = ""
    created_by: str = ""
    closed_at: str = ""
    closed_by: str = ""
    locked: bool = False

    @property
    def unresolved_high(self) -> int:
        return len([e for e in self.exceptions if e.severity == Severity.HIGH])

    @property
    def reconciled(self) -> bool:
        """Clean means: nothing unexplained, and the totals agree to the kobo."""
        return self.unresolved_high == 0 and abs(self.variance) < 0.005


class ReconciliationError(ValueError):
    """Bad input or an illegal operation — callers map this to HTTP 4xx."""


# ─── small helpers ──────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _minor(x: float) -> int:
    """Money → integer kobo. Rounds half away from zero, like a bank."""
    return int(round(float(x) * 100))


def _norm(s: str) -> str:
    """Fold a header or reference to its comparable core."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _period_bounds(period: str) -> tuple[str, str]:
    """'2026-08' → ('2026-08-01', '2026-08-31')."""
    try:
        year, month = (int(p) for p in period.split("-")[:2])
        start = dt.date(year, month, 1)
    except (ValueError, TypeError) as exc:
        raise ReconciliationError(
            f"Period must look like '2026-08', got '{period}'.") from exc
    end = (dt.date(year + (month == 12), (month % 12) + 1, 1)
           - dt.timedelta(days=1))
    return start.isoformat(), end.isoformat()


def _days_between(a: str, b: str) -> int:
    try:
        return abs((dt.date.fromisoformat(a[:10]) - dt.date.fromisoformat(b[:10])).days)
    except ValueError:
        return 9999


# ─── amount parsing ─────────────────────────────────────────────────────────

_TRAILING_SIGN = re.compile(r"\b(dr|db|debit|cr|credit)\b\.?$", re.I)


def parse_amount(text: object) -> Optional[int]:
    """Statement amount → integer kobo, or None if the cell is empty.

    Handles the shapes real exports use: '1,500.00', '₦1,500', 'NGN 1500.00',
    '(1,500.00)' for negative, and a trailing 'DR'/'CR' marker.

    Raises rather than returning 0 for a value it cannot read — a silently
    zeroed amount would reconcile as if the payment never happened.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return _minor(text)

    s = str(text).strip()
    if not s:
        return None

    negative = False
    marker = _TRAILING_SIGN.search(s)
    if marker:
        if marker.group(1).lower() in ("dr", "db", "debit"):
            negative = True
        s = _TRAILING_SIGN.sub("", s).strip()
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    if s.startswith("-"):
        negative = True
        s = s[1:]

    s = re.sub(r"[^0-9.]", "", s)          # drop ₦, NGN, spaces, thousands commas
    if not s or s == ".":
        return None
    if s.count(".") > 1:                   # 1.500.00 — European grouping
        head, _, tail = s.rpartition(".")
        s = head.replace(".", "") + "." + tail
    try:
        value = _minor(float(s))
    except ValueError as exc:
        raise ReconciliationError(f"Cannot read '{text}' as an amount.") from exc
    return -value if negative else value


# ─── date parsing ───────────────────────────────────────────────────────────

_UNAMBIGUOUS_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y",
    "%b %d, %Y", "%B %d, %Y",
    "%d-%b-%y", "%d/%b/%Y",
]
_NUMERIC = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\s*$")


def _try_formats(value: str) -> Optional[str]:
    head = value.split(" ")[0] if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", value) else value
    for fmt in _UNAMBIGUOUS_FORMATS:
        try:
            return dt.datetime.strptime(head.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def infer_date_format(values: Iterable[str]) -> str:
    """Work out day-first vs month-first FROM THE DATA, or refuse.

    A statement column where every value could be read either way is not
    something to take a view on: reading 03/04 as 4 March instead of 3 April
    would put payments in the wrong month and quietly break every date window
    in the run. So this returns "%d/%m/%Y", "%m/%d/%Y", "" (no numeric dates
    present — the unambiguous formats will handle them), or raises.
    """
    day_first = month_first = False
    seen_numeric = False

    for raw in values:
        m = _NUMERIC.match(str(raw or ""))
        if not m:
            continue
        seen_numeric = True
        first, second = int(m.group(1)), int(m.group(2))
        if first > 12:
            day_first = True
        if second > 12:
            month_first = True

    if not seen_numeric:
        return ""
    if day_first and month_first:
        raise ReconciliationError(
            "The date column contains values that cannot all be read the same "
            "way — some are day-first and some are month-first. The export is "
            "inconsistent; fix it at source or split the file.")
    if day_first:
        return "%d/%m/%Y"
    if month_first:
        return "%m/%d/%Y"
    raise ReconciliationError(
        "Every date in this statement could be read as either day/month or "
        "month/day (e.g. 03/04/2026). Nothing in the file settles it, and "
        "guessing would move payments between months. Set date_format on the "
        "column map — \"%d/%m/%Y\" for a Nigerian bank.")


def _parse_date(value: object, fmt: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if isinstance(value, (dt.datetime, dt.date)):
        return (value.date() if isinstance(value, dt.datetime) else value).isoformat()

    iso = _try_formats(s)
    if iso:
        return iso
    if fmt:
        for candidate in (fmt, fmt.replace("%Y", "%y")):
            try:
                return dt.datetime.strptime(s.split(" ")[0], candidate).date().isoformat()
            except ValueError:
                continue
    raise ReconciliationError(f"Cannot read '{value}' as a date.")


# ─── column mapping ─────────────────────────────────────────────────────────

_CANDIDATES = {
    "date": ["valuedate", "transactiondate", "postingdate", "date", "trandate",
             "effectivedate", "bookingdate"],
    "description": ["description", "narration", "details", "particulars",
                    "remarks", "transactiondetails", "memo", "narrative"],
    "reference": ["reference", "referenceno", "referencenumber", "transactionref",
                  "transactionreference", "chequeno", "instrumentno", "refno",
                  "transactionid"],
    "debit": ["debit", "withdrawal", "withdrawals", "debitamount", "moneyout",
              "paidout", "dr"],
    "credit": ["credit", "deposit", "deposits", "creditamount", "moneyin",
               "paidin", "cr", "lodgement"],
    "amount": ["amount", "transactionamount", "value"],
}


def detect_columns(headers: list[str]) -> ColumnMap:
    """Recognise a statement layout, or say plainly that it cannot.

    Detection is by longest-candidate-first so "debitamount" wins over "amount"
    and "valuedate" over "date". Where a required column is missing the error
    names the headers actually found, because the usual cause is a file with
    two title rows above the real header.
    """
    lookup: dict[str, str] = {}
    for h in headers:
        key = _norm(h)
        if key and key not in lookup:
            lookup[key] = h

    def pick(field: str) -> str:
        for cand in sorted(_CANDIDATES[field], key=len, reverse=True):
            if cand in lookup:
                return lookup[cand]
        for cand in sorted(_CANDIDATES[field], key=len, reverse=True):
            for key, original in lookup.items():
                if cand in key:
                    return original
        return ""

    cmap = ColumnMap(
        date=pick("date"), description=pick("description"),
        reference=pick("reference"), debit=pick("debit"),
        credit=pick("credit"), detected=True)
    if not (cmap.debit or cmap.credit):
        cmap.amount = pick("amount")

    if not cmap.date:
        raise ReconciliationError(
            "No date column found in the statement. Headers read: "
            + ", ".join(repr(h) for h in headers if str(h).strip())
            + ". If the file has title rows above the headers, remove them, or "
              "set the column map explicitly.")
    if not (cmap.debit or cmap.credit or cmap.amount):
        raise ReconciliationError(
            "No amount column found (looked for debit/credit or a single "
            "amount). Headers read: "
            + ", ".join(repr(h) for h in headers if str(h).strip()))
    return cmap


def set_column_map(org_id: str, cmap: ColumnMap) -> ColumnMap:
    """Pin this org's statement layout so every month imports the same way."""
    org = store.require_org(org_id)
    cmap.detected = False
    store.get_store().put(org, _COLUMN_MAP, _MAP_ID, cmap.model_dump())
    return cmap


def get_column_map(org_id: str) -> Optional[ColumnMap]:
    org = store.require_org(org_id)
    raw = store.get_store().get(org, _COLUMN_MAP, _MAP_ID)
    return ColumnMap.model_validate(raw) if raw else None


# ─── statement import ───────────────────────────────────────────────────────


def _rows_from_csv(data: bytes) -> tuple[list[str], list[dict]]:
    text = data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(str(c).strip() for c in r)]
    if not rows:
        raise ReconciliationError("The statement file is empty.")

    # Banks often put a title and account summary above the real header. Take
    # the first row that looks like headers rather than assuming row 1.
    header_at = 0
    for i, row in enumerate(rows[:15]):
        if sum(1 for c in row if _norm(str(c))) >= 3:
            score = sum(1 for c in row
                        for cands in _CANDIDATES.values()
                        if any(cd in _norm(str(c)) for cd in cands))
            if score >= 2:
                header_at = i
                break
    headers = [str(c).strip() for c in rows[header_at]]
    body = [dict(zip(headers, r)) for r in rows[header_at + 1:]]
    return headers, body


def _rows_from_xlsx(data: bytes) -> tuple[list[str], list[dict]]:
    try:
        import openpyxl
    except ImportError as exc:                       # pragma: no cover
        raise ReconciliationError(
            "Reading .xlsx statements needs openpyxl installed.") from exc
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    grid = [list(r) for r in wb[wb.sheetnames[0]].iter_rows(values_only=True)]
    wb.close()
    rows = [r for r in grid if any(str(c).strip() for c in r if c is not None)]
    if not rows:
        raise ReconciliationError("The statement file is empty.")
    header_at = 0
    for i, row in enumerate(rows[:15]):
        score = sum(1 for c in row if c is not None
                    for cands in _CANDIDATES.values()
                    if any(cd in _norm(str(c)) for cd in cands))
        if score >= 2:
            header_at = i
            break
    headers = [str(c).strip() if c is not None else "" for c in rows[header_at]]
    body = [dict(zip(headers, r)) for r in rows[header_at + 1:]]
    return headers, body


def parse_statement(
    data: bytes,
    *,
    filename: str = "statement.csv",
    column_map: Optional[ColumnMap] = None,
) -> tuple[list[BankLine], ColumnMap]:
    """Read a bank export into normalised BankLines.

    Returns the lines AND the mapping used, because the mapping is part of the
    evidence: an auditor asking "how did you know that column was the debit"
    gets an answer from the stored run.
    """
    if filename.lower().endswith((".xlsx", ".xlsm")):
        headers, rows = _rows_from_xlsx(data)
    else:
        headers, rows = _rows_from_csv(data)

    # A PARTIAL mapping supplements detection rather than replacing it. The
    # common case is a caller who knows only one thing — usually the date
    # format, because early in a month the file cannot prove day-first — and
    # making them describe every column in order to say that would be a good
    # way to get the columns wrong. So: anything named here wins, anything left
    # blank is detected.
    if column_map is None:
        cmap = detect_columns(headers)
    elif column_map.date or column_map.amount or column_map.debit or column_map.credit:
        cmap = column_map.model_copy(deep=True)
    else:
        cmap = detect_columns(headers)
        for field in ("date", "description", "reference", "debit", "credit", "amount"):
            supplied = getattr(column_map, field)
            if supplied:
                setattr(cmap, field, supplied)
        if column_map.date_format:
            cmap.date_format = column_map.date_format

    for field in ("date", "description", "reference", "debit", "credit", "amount"):
        name = getattr(cmap, field)
        if name and name not in headers:
            match = next((h for h in headers if _norm(h) == _norm(name)), None)
            if match is None:
                raise ReconciliationError(
                    f"Column '{name}' (mapped as {field}) is not in the "
                    f"statement. Headers: {', '.join(repr(h) for h in headers)}")
            setattr(cmap, field, match)

    fmt = cmap.date_format or infer_date_format(r.get(cmap.date) for r in rows)

    lines: list[BankLine] = []
    for i, row in enumerate(rows, start=1):
        iso = _parse_date(row.get(cmap.date), fmt)
        if not iso:
            continue                              # totals row, blank tail row

        if cmap.amount:
            minor = parse_amount(row.get(cmap.amount))
        else:
            debit = parse_amount(row.get(cmap.debit)) if cmap.debit else None
            credit = parse_amount(row.get(cmap.credit)) if cmap.credit else None
            if debit:
                minor = -abs(debit)
            elif credit:
                minor = abs(credit)
            else:
                minor = None
        if not minor:
            continue                              # zero or unparseable → skip row

        lines.append(BankLine(
            id=uuid.uuid4().hex[:12],
            row=i,
            date=iso,
            description=str(row.get(cmap.description) or "").strip(),
            reference=str(row.get(cmap.reference) or "").strip(),
            amount_minor=minor,
            raw={str(k): ("" if v is None else str(v)) for k, v in row.items()},
        ))

    if not lines:
        raise ReconciliationError(
            "No usable transaction rows found. Check that the date and amount "
            "columns were mapped to the right headers.")
    return lines, cmap


# ─── matching ───────────────────────────────────────────────────────────────


def _ref_keys(text: str) -> set[str]:
    """Reference-shaped tokens in a narration, normalised for comparison."""
    return {_norm(t) for t in re.split(r"[\s/|,;:]+", text or "")
            if len(_norm(t)) >= _MIN_REF_LEN}


def _vendor_hit(vendor: str, description: str) -> bool:
    """Does the vendor name appear in the bank's narration?

    Requires a distinctive word, not merely any word: "Nigeria Ltd" matching
    every other line on the statement would create false pairs. Words shorter
    than four characters and common company suffixes are ignored.
    """
    stop = {"ltd", "limited", "plc", "nigeria", "nig", "enterprise",
            "enterprises", "services", "service", "company", "and", "the",
            "int", "intl", "global", "resources", "ventures"}
    want = {w for w in re.split(r"[^a-z0-9]+", (vendor or "").lower())
            if len(w) >= 4 and w not in stop}
    if not want:
        return False
    haystack = _norm(description)
    return any(w in haystack for w in want)


def _pair_uniquely(
    candidates: dict[str, list[str]],
) -> dict[str, str]:
    """Accept only pairings that are unique from both sides.

    `candidates` maps a payment id to the bank lines that could settle it. A
    payment with two candidates is not paired; nor is a bank line wanted by two
    payments. What is left is unambiguous, and everything else falls through to
    the next pass and ultimately to a human. This is why the engine never
    depends on row order.
    """
    wanted_by: dict[str, list[str]] = {}
    for txn_id, lines in candidates.items():
        for line_id in lines:
            wanted_by.setdefault(line_id, []).append(txn_id)

    return {txn_id: lines[0]
            for txn_id, lines in candidates.items()
            if len(lines) == 1 and len(wanted_by[lines[0]]) == 1}


def reconcile(
    org_id: str,
    period: str,
    statement: bytes,
    *,
    filename: str = "statement.csv",
    column_map: Optional[ColumnMap] = None,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    settlement_days: int = DEFAULT_SETTLEMENT_DAYS,
    actor: str = "",
    transactions: Optional[list] = None,
) -> ReconciliationRun:
    """Reconcile one month's payments against the bank statement.

    Runs three passes, most-certain first, each accepting only unambiguous
    pairs (see `_pair_uniquely`):

      1. **Reference** — the bank reference recorded at payment appears on the
         statement line. If the amounts differ, that is reported as
         AMOUNT_MISMATCH and neither side is considered settled.
      2. **Amount + date window** — equal to the kobo, within the window.
      3. **Amount + vendor** — for payments that cleared outside the window,
         where the narration names the vendor.

    Everything unpaired afterwards becomes an exception, in both directions.
    """
    org = store.require_org(org_id)
    start, end = _period_bounds(period)

    # EVERY payment path, not just requisitions. Reading only requisitions is
    # what made an approved payroll run appear as "money nobody authorised" —
    # the most serious finding the system produces, fired at a correct payment.
    # disbursements.py is the one place all paths record what actually left.
    import disbursements as _disb
    txns = (transactions if transactions is not None
            else _disb.list_disbursements(org, start=start, end=end))
    txns = [t for t in txns if start <= (t.paid_at or "")[:10] <= end]

    lines, cmap = parse_statement(statement, filename=filename, column_map=column_map)
    debits = [ln for ln in lines if ln.is_debit and start <= ln.date <= end]

    remaining_txns = {t.id: t for t in txns}
    remaining_lines = {ln.id: ln for ln in debits}
    matches: list[Match] = []
    exceptions: list[ReconException] = []

    def take(txn, line, method: MatchMethod) -> None:
        matches.append(Match(
            transaction_id=txn.id, transaction_ref=txn.source_ref or txn.id,
            bank_line_id=line.id, bank_row=line.row, method=method,
            amount=abs(line.amount), paid_at=txn.paid_at, bank_date=line.date,
            day_gap=_days_between(txn.paid_at, line.date),
            vendor_name=txn.payee_name))
        remaining_txns.pop(txn.id, None)
        remaining_lines.pop(line.id, None)

    # ── pass 1: bank reference ──────────────────────────────────────────────
    by_ref: dict[str, list[BankLine]] = {}
    for ln in debits:
        for key in _ref_keys(ln.reference) | _ref_keys(ln.description):
            by_ref.setdefault(key, []).append(ln)

    candidates: dict[str, list[str]] = {}
    for txn in txns:
        key = _norm(txn.bank_reference)
        if len(key) < _MIN_REF_LEN:
            continue
        hits = [ln for ln in by_ref.get(key, []) if ln.id in remaining_lines]
        agreeing = [ln for ln in hits if abs(ln.amount_minor) == _minor(txn.amount)]
        if hits and not agreeing:
            # The reference is the strongest evidence we have that these are the
            # same payment. If the amount then differs, that IS the finding.
            ln = hits[0]
            exceptions.append(ReconException(
                code=ExceptionCode.AMOUNT_MISMATCH, severity=Severity.HIGH,
                amount=txn.amount, date=txn.paid_at[:10],
                description=ln.description,
                transaction_id=txn.id, transaction_ref=txn.source_ref,
                bank_line_id=ln.id, bank_row=ln.row,
                note=(f"Reference {txn.bank_reference} matches, but the system "
                      f"records {txn.amount:,.2f} and the bank shows "
                      f"{abs(ln.amount):,.2f} "
                      f"(difference {abs(abs(ln.amount) - txn.amount):,.2f})."),
            ))
            remaining_txns.pop(txn.id, None)
            remaining_lines.pop(ln.id, None)
            continue
        if agreeing:
            candidates[txn.id] = [ln.id for ln in agreeing]

    for txn_id, line_id in _pair_uniquely(candidates).items():
        take(remaining_txns[txn_id], remaining_lines[line_id], MatchMethod.REFERENCE)

    # ── pass 2: amount + date window ────────────────────────────────────────
    candidates = {}
    for txn in list(remaining_txns.values()):
        hits = [ln.id for ln in remaining_lines.values()
                if abs(ln.amount_minor) == _minor(txn.amount)
                and _days_between(txn.paid_at, ln.date) <= date_window_days]
        if hits:
            candidates[txn.id] = hits
    for txn_id, line_id in _pair_uniquely(candidates).items():
        take(remaining_txns[txn_id], remaining_lines[line_id], MatchMethod.EXACT)

    # ── pass 3: amount + vendor named in the narration ──────────────────────
    candidates = {}
    for txn in list(remaining_txns.values()):
        hits = [ln.id for ln in remaining_lines.values()
                if abs(ln.amount_minor) == _minor(txn.amount)
                and _vendor_hit(txn.payee_name, f"{ln.description} {ln.reference}")]
        if hits:
            candidates[txn.id] = hits
    for txn_id, line_id in _pair_uniquely(candidates).items():
        take(remaining_txns[txn_id], remaining_lines[line_id], MatchMethod.VENDOR)

    # ── what is left ────────────────────────────────────────────────────────
    for txn in remaining_txns.values():
        near = [ln for ln in remaining_lines.values()
                if abs(ln.amount_minor) == _minor(txn.amount)]
        if len(near) > 1:
            exceptions.append(ReconException(
                code=ExceptionCode.AMBIGUOUS, severity=Severity.MEDIUM,
                amount=txn.amount, date=txn.paid_at[:10],
                transaction_id=txn.id, transaction_ref=txn.source_ref,
                description=txn.payee_name,
                candidates=[f"row {ln.row}: {ln.date} {ln.description[:40]}"
                            for ln in near],
                note=(f"{len(near)} bank lines are for exactly this amount and "
                      "nothing distinguishes them. Confirm which one settled "
                      "this payment rather than letting the system choose."),
            ))
            continue

        days_to_end = _days_between(txn.paid_at, end)
        late = txn.paid_at[:10] >= (dt.date.fromisoformat(end)
                                    - dt.timedelta(days=settlement_days)).isoformat()
        exceptions.append(ReconException(
            code=ExceptionCode.NOT_IN_BANK,
            severity=Severity.MEDIUM if late else Severity.HIGH,
            amount=txn.amount, date=txn.paid_at[:10],
            description=txn.payee_name,
            transaction_id=txn.id, transaction_ref=txn.source_ref,
            note=("Recorded as paid within %d days of period end — most likely "
                  "cleared in the next statement. Carry forward and confirm."
                  % days_to_end) if late else
                 ("Recorded as paid, but nothing on the statement settles it. "
                  "Either the transfer failed or it was marked paid before it "
                  "was sent."),
        ))

    seen: dict[tuple, BankLine] = {}
    for ln in sorted(remaining_lines.values(), key=lambda l: l.row):
        fingerprint = (ln.amount_minor, ln.date, _norm(ln.reference or ln.description))
        if fingerprint in seen:
            exceptions.append(ReconException(
                code=ExceptionCode.DUPLICATE_BANK_LINE, severity=Severity.HIGH,
                amount=abs(ln.amount), date=ln.date, description=ln.description,
                bank_line_id=ln.id, bank_row=ln.row,
                note=(f"Identical to row {seen[fingerprint].row}. Either the "
                      "account was debited twice or the export repeats a row — "
                      "both need the bank."),
            ))
            continue
        seen[fingerprint] = ln
        exceptions.append(ReconException(
            code=ExceptionCode.NOT_IN_SYSTEM, severity=Severity.HIGH,
            amount=abs(ln.amount), date=ln.date, description=ln.description,
            bank_line_id=ln.id, bank_row=ln.row,
            note=("Money left the account with no approved requisition behind "
                  "it. Every one of these needs an explanation before the "
                  "month closes."),
        ))

    total_system = round(sum(t.amount for t in txns), 2)
    total_bank = round(sum(abs(ln.amount) for ln in debits), 2)
    total_matched = round(sum(m.amount for m in matches), 2)

    run = ReconciliationRun(
        id=uuid.uuid4().hex[:12], org_id=org, period=period,
        period_start=start, period_end=end,
        statement_name=filename,
        statement_sha256=hashlib.sha256(statement).hexdigest(),
        statement_lines=len(lines),
        column_map=cmap, date_window_days=date_window_days,
        matches=matches, exceptions=exceptions, bank_lines=debits,
        total_paid_in_system=total_system,
        total_debits_in_bank=total_bank,
        total_matched=total_matched,
        variance=round(total_system - total_bank, 2),
        created_at=_now_iso(), created_by=actor,
    )
    return _save(org, run)


# ─── human decisions on a run ───────────────────────────────────────────────


def manual_match(
    org_id: str, run_id: str, *, transaction_id: str, bank_line_id: str,
    actor: str, reason: str,
) -> ReconciliationRun:
    """Pair a payment with a bank line by hand.

    A written reason is required and stored. The engine declined to make this
    pairing itself; the record of who decided otherwise, and why, is the whole
    value of allowing it.
    """
    if not reason.strip():
        raise ReconciliationError(
            "A manual match needs a written reason — it is the only evidence "
            "for a pairing the engine would not make.")
    run = _require_open(org_id, run_id)

    line = next((ln for ln in run.bank_lines if ln.id == bank_line_id), None)
    if line is None:
        raise ReconciliationError(f"Bank line '{bank_line_id}' is not in this run.")
    if any(m.bank_line_id == bank_line_id for m in run.matches):
        raise ReconciliationError(
            f"Bank row {line.row} is already matched. Unmatch it first.")
    if any(m.transaction_id == transaction_id for m in run.matches):
        raise ReconciliationError("That payment is already matched.")

    import disbursements as _disb
    txn = _disb.get(run.org_id, transaction_id)
    if txn is None:
        raise ReconciliationError(f"Payment '{transaction_id}' not found.")

    run.matches.append(Match(
        transaction_id=txn.id, transaction_ref=txn.source_ref or txn.id,
        bank_line_id=line.id, bank_row=line.row, method=MatchMethod.MANUAL,
        amount=abs(line.amount), paid_at=txn.paid_at, bank_date=line.date,
        day_gap=_days_between(txn.paid_at, line.date),
        vendor_name=txn.payee_name, matched_by=actor, reason=reason.strip()))

    run.exceptions = [e for e in run.exceptions
                      if e.transaction_id != transaction_id
                      and e.bank_line_id != bank_line_id]
    run.total_matched = round(sum(m.amount for m in run.matches), 2)
    return _save(run.org_id, run)


def explain_exception(
    org_id: str, run_id: str, *, bank_line_id: str = "", transaction_id: str = "",
    actor: str, reason: str,
) -> ReconciliationRun:
    """Record why an unmatched item is acceptable, and downgrade it.

    Bank charges, interest, and a reversal that nets to nothing are all real
    reasons a line has no requisition. The item stays in the run — it is never
    deleted — but it stops blocking the close once someone has put their name
    to an explanation.
    """
    if not reason.strip():
        raise ReconciliationError("An explanation cannot be blank.")
    run = _require_open(org_id, run_id)

    hit = False
    for e in run.exceptions:
        if ((bank_line_id and e.bank_line_id == bank_line_id)
                or (transaction_id and e.transaction_id == transaction_id)):
            e.severity = Severity.LOW
            e.note = f"{e.note} — EXPLAINED by {actor}: {reason.strip()}"
            hit = True
    if not hit:
        raise ReconciliationError("No matching exception in this run.")
    return _save(run.org_id, run)


def close_period(org_id: str, run_id: str, *, actor: str,
                 force_reason: str = "") -> ReconciliationRun:
    """Lock the month. After this the run is evidence and never changes.

    Closing with unexplained high-severity exceptions is refused unless a
    written reason is supplied — a month closed over unexplained money is a
    decision someone made, and it should carry their name.
    """
    run = _require_open(org_id, run_id)
    if run.unresolved_high and not force_reason.strip():
        codes = sorted({e.code.value for e in run.exceptions
                        if e.severity == Severity.HIGH})
        raise ReconciliationError(
            f"{run.unresolved_high} unexplained exception(s) remain "
            f"({', '.join(codes)}). Explain each one, or close with a written "
            "reason that will be recorded against your name.")

    run.closed_at = _now_iso()
    run.closed_by = actor
    run.locked = True
    if force_reason.strip():
        run.exceptions.append(ReconException(
            code=ExceptionCode.NOT_IN_SYSTEM, severity=Severity.LOW,
            note=(f"CLOSED WITH {run.unresolved_high} UNRESOLVED EXCEPTION(S) "
                  f"by {actor}: {force_reason.strip()}")))
    return _save(run.org_id, run)


# ─── persistence + reporting ────────────────────────────────────────────────


def _save(org_id: str, run: ReconciliationRun) -> ReconciliationRun:
    store.get_store().put(org_id, _RUNS, run.id, run.model_dump())
    return run


def _require_open(org_id: str, run_id: str) -> ReconciliationRun:
    run = get_run(org_id, run_id)
    if run is None:
        raise ReconciliationError(f"Reconciliation '{run_id}' not found.")
    if run.locked:
        raise ReconciliationError(
            f"{run.period} was closed by {run.closed_by} on "
            f"{run.closed_at[:10]}. A closed reconciliation is evidence and "
            "cannot be edited — import the corrected statement as a new run.")
    return run


def get_run(org_id: str, run_id: str) -> Optional[ReconciliationRun]:
    raw = store.get_store().get(store.require_org(org_id), _RUNS, run_id)
    return ReconciliationRun.model_validate(raw) if raw else None


def list_runs(org_id: str, *, period: Optional[str] = None) -> list[ReconciliationRun]:
    org = store.require_org(org_id)
    out = []
    for raw in store.get_store().list(org, _RUNS):
        try:
            run = ReconciliationRun.model_validate(raw)
        except Exception:
            continue
        if period and run.period != period:
            continue
        out.append(run)
    out.sort(key=lambda r: (r.period, r.created_at), reverse=True)
    return out


def summary(run: ReconciliationRun) -> dict:
    """The one screen a finance officer reads at month end."""
    by_code: dict[str, int] = {}
    for e in run.exceptions:
        by_code[e.code.value] = by_code.get(e.code.value, 0) + 1
    return {
        "run_id": run.id,
        "period": run.period,
        "statement": run.statement_name,
        "statement_sha256": run.statement_sha256[:16],
        "payments_in_system": len(run.matches) + len(
            [e for e in run.exceptions if e.transaction_id]),
        "debits_in_bank": len(run.bank_lines),
        "matched": len(run.matches),
        "matched_value": run.total_matched,
        "total_paid_in_system": run.total_paid_in_system,
        "total_debits_in_bank": run.total_debits_in_bank,
        "variance": run.variance,
        "exceptions_by_code": by_code,
        "unresolved_high": run.unresolved_high,
        "reconciled": run.reconciled,
        "locked": run.locked,
        "closed_by": run.closed_by,
    }
