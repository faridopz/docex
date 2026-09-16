"""
WO-36: importing a payee schedule from a spreadsheet.

The engine-level half — payee_import.py is pure, so it is tested by calling
it with real file bytes and reading the result, no HTTP and no store.

The case this suite exists for is the leading zero. Nigerian NUBAN account
numbers are exactly ten digits and many start with 0. Excel stores an account
number typed into a General cell as a NUMBER and silently drops that zero, so
0123456789 arrives as 123456789. Quietly prepending a zero to make it fit
would be inventing a bank account to send money to, so it must be refused and
explained instead.

Also covers: headers in any order, a title row above the headers, money in
the shapes people actually type, per-row errors collected rather than the
first one stopping the file, blank spacer lines ignored, duplicate accounts
warned about, and a file with no recognisable headings refused with the
headings it did find.

Run: python test_payee_import.py
"""
from __future__ import annotations

import io

import payee_import as pi

_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


def csv_bytes(text: str) -> bytes:
    return text.strip().encode()


# ─── the ordinary case: headers in a sensible order ────────────────────────

result = pi.parse_payee_file("schedule.csv", csv_bytes("""
Name,Account Number,Bank,Amount,Purpose
Aisha Bello,0123456789,GTBank,"20,000",Workshop stipend
Musa Ibrahim,2345678901,Zenith,15000,Workshop stipend
Grace Okon,3456789012,Access,"₦12,500.50",Transport
"""))
check("three rows read", len(result.rows) == 3)
check("all three are valid", len(result.valid_rows) == 3)
check("a ten-digit account starting with zero survives",
      result.rows[0].account_number == "0123456789")
check("a comma-formatted amount parses", result.rows[0].amount == 20000.0)
check("a naira sign and decimals parse", result.rows[2].amount == 12500.50)
check("the total is the sum of the valid rows", result.total_amount == 47500.50)
check("purpose comes through", result.rows[0].purpose == "Workshop stipend")
check("payee type defaults to beneficiary", result.rows[0].payee_type == "beneficiary")

# ─── headers in a different order, and named differently ───────────────────

result = pi.parse_payee_file("odd.csv", csv_bytes("""
AMOUNT PAYABLE,Beneficiary Name,Acct No.,Bank Name,TIN,Phone
5000,Ngozi Eze,9988776655,UBA,TIN-001,08030000000
"""))
check("column order does not matter", len(result.valid_rows) == 1)
row = result.rows[0]
check("amount found under 'AMOUNT PAYABLE'", row.amount == 5000.0)
check("name found under 'Beneficiary Name'", row.name == "Ngozi Eze")
check("account found under 'Acct No.'", row.account_number == "9988776655")
check("TIN found", row.tin == "TIN-001")
check("phone found", row.phone_or_email == "08030000000")

# ─── THE LEADING ZERO — the reason this module exists ──────────────────────

result = pi.parse_payee_file("excel-damaged.csv", csv_bytes("""
Name,Account Number,Bank,Amount
Aisha Bello,123456789,GTBank,20000
"""))
check("a nine-digit account is REFUSED, not silently repaired",
      not result.rows[0].ok)
check("the error explains what Excel did",
      any("Excel" in e for e in result.rows[0].errors))
check("the error says how many digits it found",
      any("9 digits" in e for e in result.rows[0].errors))
check("it is not counted as importable", len(result.valid_rows) == 0)

# An over-long account is refused too — a different mistake, same danger.
result = pi.parse_payee_file("long.csv", csv_bytes("""
Name,Account Number,Amount
Someone,012345678901234,5000
"""))
check("an over-long account number is refused", not result.rows[0].ok)

# ─── every problem reported at once, not one upload at a time ──────────────

result = pi.parse_payee_file("messy.csv", csv_bytes("""
Payment Schedule — September 2026

Name,Account Number,Bank,Amount
Aisha Bello,0123456789,GTBank,20000

,2345678901,Zenith,15000
Musa Ibrahim,3456789012,Access,not-a-number
Grace Okon,456789012,UBA,10000
Ngozi Eze,5678901234,UBA,0
Good Row,6789012345,GTBank,7500
"""))
check("a title row above the headers is skipped — six data rows, not the\n       title or the header", len(result.rows) == 6)
check("the title line never becomes a payee",
      result.rows[0].name == "Aisha Bello")
check("blank spacer lines are ignored — not turned into empty payees",
      all(r.name or r.errors for r in result.rows))
check("one good row at the top still parses", result.rows[0].ok)
check("the missing name is caught",
      any("No payee name" in e for e in result.rows[1].errors))
check("the unreadable amount is caught",
      any("amount" in e.lower() for e in result.rows[2].errors))
check("the short account is caught", not result.rows[3].ok)
check("a zero amount is caught", any("above zero" in e for e in result.rows[4].errors))
check("the last good row still parses", result.rows[5 - 1].ok or result.rows[-1].ok)
check("four problems found in one pass, not one at a time",
      len(result.problem_rows) == 4)
check("the two good rows are still importable", len(result.valid_rows) == 2)
check("the total counts ONLY the valid rows", result.total_amount == 27500.0)

# ─── duplicates warn, they do not block ────────────────────────────────────

result = pi.parse_payee_file("dupes.csv", csv_bytes("""
Name,Account Number,Amount
Aisha Bello,0123456789,20000
Aisha Bello Again,0123456789,20000
"""))
check("a duplicate account is a WARNING, not an error", result.rows[1].ok)
check("the warning names the first row it saw",
      any("row 2" in w for w in result.rows[1].warnings))

# ─── tab-separated (pasted straight out of Excel) ──────────────────────────

result = pi.parse_payee_file("tabbed.tsv",
                              b"Name\tAccount Number\tAmount\nAisha\t0123456789\t5000")
check("tab-separated files work", len(result.valid_rows) == 1)

# ─── payee type is read when present ───────────────────────────────────────

result = pi.parse_payee_file("typed.csv", csv_bytes("""
Name,Account Number,Amount,Type
A,0123456789,1000,staff
B,2345678901,1000,Vendor
C,3456789012,1000,nonsense
"""))
check("staff type read", result.rows[0].payee_type == "staff")
check("capitalised vendor read", result.rows[1].payee_type == "vendor")
check("an unknown type falls back to beneficiary",
      result.rows[2].payee_type == "beneficiary")

# ─── files that cannot be used at all ──────────────────────────────────────

def expect_file_error(name, filename, content):
    global _fail
    try:
        pi.parse_payee_file(filename, content)
        print(f"FAIL  {name}: expected a refusal, got none")
        _fail += 1
    except pi.PayeeImportError as exc:
        print(f"PASS  {name} ({str(exc)[:55]}…)")


expect_file_error("an empty file is refused", "empty.csv", b"")
expect_file_error("a file with no recognisable headings is refused",
                  "junk.csv", csv_bytes("alpha,beta,gamma\n1,2,3"))
expect_file_error("headings with no rows underneath are refused",
                  "headers-only.csv", csv_bytes("Name,Account Number,Amount"))
expect_file_error("a file with no amount column is refused",
                  "no-amount.csv", csv_bytes("Name,Account Number\nAisha,0123456789"))

# The refusal has to be useful — it should name what it DID find, because the
# usual cause is a title row the person did not think of as data.
try:
    pi.parse_payee_file("nope.csv", csv_bytes("Name,Reference\nAisha,X1"))
except pi.PayeeImportError as exc:
    check("the refusal lists the headings it actually found", "Name" in str(exc))

# ─── a real .xlsx, round-tripped ───────────────────────────────────────────

try:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Account Number", "Bank", "Amount"])
    ws.append(["Aisha Bello", "0123456789", "GTBank", 20000])   # text account
    ws.append(["Musa Ibrahim", 2345678901, "Zenith", 15000])     # numeric account
    buf = io.BytesIO()
    wb.save(buf)
    result = pi.parse_payee_file("sheet.xlsx", buf.getvalue())
    check("xlsx is read", len(result.rows) == 2)
    check("a text-formatted account keeps its leading zero",
          result.rows[0].account_number == "0123456789")
    check("a ten-digit numeric account is still fine",
          result.rows[1].account_number == "2345678901")
except ImportError:                                             # pragma: no cover
    print("SKIP  xlsx test — openpyxl not installed")

# ─── the parsed row is shaped for requisitions.Payee ───────────────────────

result = pi.parse_payee_file("shape.csv", csv_bytes("""
Name,Account Number,Bank,Amount,Purpose
Aisha Bello,0123456789,GTBank,20000,Stipend
"""))
payee = result.rows[0].as_payee_dict()
import requisitions as rq
built = rq.Payee(**payee)
check("the parsed row constructs a real Payee with no translation",
      built.name == "Aisha Bello" and built.amount == 20000.0
      and built.account_number == "0123456789")

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll payee-import checks passed.")
