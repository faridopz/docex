"""
Read a payee list out of a spreadsheet — the file finance already has.

A hundred-line stipend run or a beneficiary payout is prepared in Excel long
before it reaches DOCex. Retyping it is where the errors come from, and
pasting it (which /requisitions/new already supports) demands the columns be
in one exact order. This reads the file as it is: headers in any order,
CSV / TSV / XLSX, and it says per row what it could not understand instead of
failing the whole file on line 87.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
=========================================
It does not create anything. It parses and validates, and hands back rows.
The caller then raises an ordinary multi-payee requisition through
`requisitions.create_requisition()` — the same function a typed batch goes
through, so an imported batch gets the same deterministic policy checks, the
same approval chain, the same compliance check and the same audit log. There
is no bulk-create path, because a second way to create a payment is a second
thing that can drift from the first.

Pure and deterministic — no LLM, no network, no store access. Column
detection follows the longest-candidate-first idiom already proven in
bank_reconciliation.detect_columns().

THE LEADING-ZERO PROBLEM
========================
Nigerian NUBAN account numbers are exactly ten digits and a great many begin
with a zero. Excel stores an account number typed into a General cell as a
NUMBER, which silently drops that zero — 0123456789 comes back as 123456789.
Nine digits is not a valid NUBAN, and quietly prepending a zero to make it fit
would be inventing a bank account to pay money into. So a short numeric
account is reported as an ERROR the human has to fix in the source file, with
an explanation of what Excel did to it. This is the whole reason this module
exists rather than a two-line csv.reader.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Optional

# NUBAN — the Nigerian bank account standard. Exactly ten digits.
_NUBAN_LENGTH = 10

_CANDIDATES: dict[str, list[str]] = {
    "name": ["accountname", "payeename", "beneficiaryname", "fullname", "name",
             "payee", "beneficiary", "staffname", "vendorname", "supplier"],
    "account_number": ["accountnumber", "accountno", "acctnumber", "acctno",
                        "nuban", "bankaccount", "accountnum", "account"],
    "bank_name": ["bankname", "bank", "bankbranch", "institution"],
    "amount": ["amount", "amountngn", "amountpayable", "netamount", "totalamount",
               "value", "total", "sum", "payable"],
    "purpose": ["purpose", "description", "narration", "details", "reason",
                "particulars", "remarks", "memo"],
    "phone_or_email": ["phoneoremail", "phonenumber", "phone", "mobile", "email",
                        "emailaddress", "contact", "telephone", "msisdn"],
    "tin": ["tin", "taxid", "taxidentificationnumber", "taxnumber"],
    "payee_type": ["payeetype", "type", "category", "recipienttype"],
}

_TYPES = ("staff", "vendor", "beneficiary")


def _norm(header: str) -> str:
    """Lowercase, strip everything that isn't a letter or digit. Turns
    'Account Number', 'ACCOUNT_NO' and 'Acct. No.' into comparable keys."""
    return re.sub(r"[^a-z0-9]", "", str(header or "").lower())


@dataclass
class PayeeRow:
    """One parsed line. `errors` empty means it is safe to pay."""
    row_number: int                      # 1-based, as the human sees it in Excel
    name: str = ""
    account_number: str = ""
    bank_name: str = ""
    amount: float = 0.0
    purpose: str = ""
    tin: str = ""
    phone_or_email: str = ""
    payee_type: str = "beneficiary"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_payee_dict(self) -> dict:
        """The shape requisitions.Payee accepts."""
        return {
            "name": self.name, "account_number": self.account_number,
            "bank_name": self.bank_name, "amount": self.amount,
            "purpose": self.purpose, "tin": self.tin,
            "phone_or_email": self.phone_or_email, "payee_type": self.payee_type,
        }


@dataclass
class ImportResult:
    rows: list[PayeeRow] = field(default_factory=list)
    detected_columns: dict[str, str] = field(default_factory=dict)
    headers_found: list[str] = field(default_factory=list)
    file_error: str = ""                 # set when the file itself is unusable

    @property
    def valid_rows(self) -> list[PayeeRow]:
        return [r for r in self.rows if r.ok]

    @property
    def problem_rows(self) -> list[PayeeRow]:
        return [r for r in self.rows if not r.ok]

    @property
    def total_amount(self) -> float:
        return round(sum(r.amount for r in self.valid_rows), 2)


class PayeeImportError(ValueError):
    """The file cannot be read at all — callers map this to HTTP 400."""


# ─── reading the file into rows of cells ────────────────────────────────────


def _read_table(filename: str, content: bytes) -> list[list[str]]:
    """Return the sheet as a grid of strings. XLSX cells keep their displayed
    form where possible, because an account number's leading zero only
    survives if the author formatted the column as text — and we need to be
    able to tell the difference."""
    name = (filename or "").lower()

    if name.endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:                              # pragma: no cover
            raise PayeeImportError("Excel support is not installed on this server.") from exc
        try:
            wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        except Exception as exc:
            raise PayeeImportError(f"That file could not be opened as Excel: {exc}") from exc
        ws = wb[wb.sheetnames[0]]
        grid: list[list[str]] = []
        for row in ws.iter_rows(values_only=True):
            grid.append(["" if c is None else str(c).strip() for c in row])
        return grid

    # CSV / TSV / plain text. Decode defensively — a file exported from a
    # Nigerian bank portal is as likely to be cp1252 as utf-8.
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:                                                       # pragma: no cover
        raise PayeeImportError("That file's text encoding could not be read.")

    sample = text[:4096]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _find_header_row(grid: list[list[str]]) -> int:
    """Which row is the header.

    Not always row 1: exported schedules routinely carry a title and a blank
    line above it. The header is the first row in which at least two cells
    match a known column name — one match is too easy to hit by accident on a
    title like "Payment Schedule".
    """
    for i, row in enumerate(grid[:20]):
        hits = 0
        for cell in row:
            key = _norm(cell)
            if not key:
                continue
            if any(key == cand or cand in key
                   for cands in _CANDIDATES.values() for cand in cands):
                hits += 1
        if hits >= 2:
            return i
    return -1


def detect_columns(headers: list[str]) -> dict[str, str]:
    """Map our field names onto the file's actual headers.

    Longest-candidate-first so "accountname" wins over "name" and
    "accountnumber" over "account" — the same reasoning, and the same failure
    it prevents, as bank_reconciliation.detect_columns().
    """
    lookup: dict[str, str] = {}
    for h in headers:
        key = _norm(h)
        if key and key not in lookup:
            lookup[key] = h

    found: dict[str, str] = {}
    claimed: set[str] = set()
    # Exact matches first, across all fields, so a precise header is never
    # stolen by another field's fuzzy match.
    for field_name, cands in _CANDIDATES.items():
        for cand in sorted(cands, key=len, reverse=True):
            if cand in lookup and lookup[cand] not in claimed:
                found[field_name] = lookup[cand]
                claimed.add(lookup[cand])
                break
    for field_name, cands in _CANDIDATES.items():
        if field_name in found:
            continue
        for cand in sorted(cands, key=len, reverse=True):
            hit = next((orig for key, orig in lookup.items()
                        if cand in key and orig not in claimed), None)
            if hit:
                found[field_name] = hit
                claimed.add(hit)
                break
    return found


# ─── cell parsing ───────────────────────────────────────────────────────────


def parse_amount(raw: str) -> Optional[float]:
    """Read a money cell. Handles '1,500,000', '₦20,000', 'NGN 5000.50',
    '(2,000)' for a negative, and a trailing '.00'. None when unreadable —
    the caller turns that into a row error rather than a zero, because a
    zero-amount payee would pass silently and pay nobody."""
    s = str(raw or "").strip()
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[₦$€£]|NGN|ngn|,|\s|\(|\)", "", s)
    if not s:
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def parse_account_number(raw: str) -> tuple[str, Optional[str]]:
    """Return (account_number, error).

    See the module docstring on leading zeros. A cell Excel turned into a
    number loses any leading zero, and a nine-digit NUBAN is the fingerprint
    of exactly that. We refuse it rather than repairing it: prepending a zero
    would be guessing at a bank account, and the cost of guessing wrong is a
    payment to a stranger.
    """
    s = re.sub(r"[^0-9]", "", str(raw or ""))
    if not s:
        return "", "No account number."
    if len(s) == _NUBAN_LENGTH:
        return s, None
    if len(s) < _NUBAN_LENGTH:
        return s, (
            f"Account number is {len(s)} digits, not {_NUBAN_LENGTH}. If it starts "
            "with a zero, Excel has stripped it — format that column as Text in "
            "the source file and re-export, rather than typing the zero back here."
        )
    return s, f"Account number is {len(s)} digits, longer than a {_NUBAN_LENGTH}-digit account."


def parse_payee_type(raw: str) -> str:
    s = _norm(raw)
    for t in _TYPES:
        if s == t or (s and s.startswith(t[:4])):
            return t
    return "beneficiary"


# ─── the entry point ────────────────────────────────────────────────────────


def parse_payee_file(filename: str, content: bytes) -> ImportResult:
    """Parse a payee schedule. Never raises on a bad ROW — only on a file that
    cannot be read at all.

    Collecting row errors rather than stopping at the first is the point: a
    finance officer fixing a hundred-line schedule should see all eleven
    problems once, not discover them one upload at a time.
    """
    grid = _read_table(filename, content)
    if not grid:
        raise PayeeImportError("That file is empty.")

    header_index = _find_header_row(grid)
    if header_index < 0:
        raise PayeeImportError(
            "No column headings were recognised. The file needs a header row "
            "naming at least a payee and an amount — for example 'Name', "
            "'Account Number', 'Bank', 'Amount'."
        )

    headers = grid[header_index]
    columns = detect_columns(headers)
    result = ImportResult(detected_columns=columns,
                          headers_found=[h for h in headers if str(h).strip()])

    missing = [f for f in ("name", "amount") if f not in columns]
    if missing:
        raise PayeeImportError(
            f"Could not find a column for: {', '.join(missing)}. "
            f"Headings found were: {', '.join(result.headers_found) or '(none)'}."
        )

    index_of = {f: headers.index(h) for f, h in columns.items()}

    def cell(row: list[str], field_name: str) -> str:
        idx = index_of.get(field_name)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx] or "").strip()

    for offset, raw_row in enumerate(grid[header_index + 1:], start=1):
        # Excel's own row number, so "row 14" means row 14 in their file.
        row_number = header_index + 1 + offset
        if not any(str(c).strip() for c in raw_row):
            continue                                  # blank spacer line

        row = PayeeRow(row_number=row_number)
        row.name = cell(raw_row, "name")
        row.bank_name = cell(raw_row, "bank_name")
        row.purpose = cell(raw_row, "purpose")
        row.tin = cell(raw_row, "tin")
        row.phone_or_email = cell(raw_row, "phone_or_email")
        row.payee_type = parse_payee_type(cell(raw_row, "payee_type"))

        if not row.name:
            row.errors.append("No payee name.")

        amount = parse_amount(cell(raw_row, "amount"))
        if amount is None:
            row.errors.append(f"Could not read '{cell(raw_row, 'amount')}' as an amount.")
        elif amount <= 0:
            row.errors.append(f"Amount is {amount:,.2f} — it must be above zero.")
        else:
            row.amount = round(amount, 2)

        if "account_number" in columns:
            account, error = parse_account_number(cell(raw_row, "account_number"))
            row.account_number = account
            if error:
                row.errors.append(error)
        else:
            row.warnings.append("No account-number column in this file.")

        if not row.bank_name and row.account_number:
            row.warnings.append("No bank named.")

        result.rows.append(row)

    if not result.rows:
        raise PayeeImportError("The file has headings but no rows underneath them.")

    # Duplicate account numbers inside one schedule — usually a copy-paste
    # slip, occasionally deliberate (two payments to one person). A warning,
    # not an error, because only the org knows which it is; the deterministic
    # duplicate-payment check on the requisition itself is the hard control.
    seen: dict[str, int] = {}
    for row in result.rows:
        if not row.account_number:
            continue
        first = seen.get(row.account_number)
        if first is not None:
            row.warnings.append(f"Same account number as row {first}.")
        else:
            seen[row.account_number] = row.row_number

    return result
