"""
QuickBooks export — the formatting rules QuickBooks enforces, enforced here.

The reason this has tests at all: QuickBooks rejects a bank CSV containing a
currency symbol or a thousands separator, and Nigerian bank exports contain
both. An export that produces a file QuickBooks refuses is worse than no
export, because the client discovers it on the import screen rather than from
us.

Run: python test_accounting_export.py
"""
from __future__ import annotations

import csv
import io
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-qbo-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import accounting_export as ax  # noqa: E402
import disbursements as disb  # noqa: E402

ORG = "qbotest"
PERIOD = "2026-08"
_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def rows_of(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


class Line:
    """Stands in for a parsed BankLine."""

    def __init__(self, date, description, reference, amount):
        self.date, self.description = date, description
        self.reference, self.amount = reference, amount
        self.is_debit = amount < 0


def clear() -> None:
    for d in store.get_store().list(ORG, "disbursements"):
        store.get_store().delete(ORG, "disbursements", d["id"])


# ─── bank statement ─────────────────────────────────────────────────────────


def test_the_output_obeys_quickbooks_rules() -> None:
    print("\nQuickBooks rejects ₦ and commas — so the export contains neither")
    files = ax.bank_statement_csv([
        Line("2026-08-04", "TRF TO ACME LTD", "FT26001", -1_250_000.50),
        Line("2026-08-06", "GRANT RECEIPT", "GF/TR3", 12_400_000.00),
    ])
    check("one file", len(files) == 1)
    text = files[0]
    check("no naira symbol", "₦" not in text)
    check("no thousands separators in amounts", "1,250,000" not in text)

    rows = rows_of(text)
    check("headers first and only three columns",
          rows[0] == ["Date", "Description", "Amount"])
    check("amount is a bare decimal", rows[1][2] == "-1250000.50", rows[1][2])
    check("money in stays positive", rows[2][2] == "12400000.00")
    check("dates are day-first by default", rows[1][0] == "04/08/2026")
    check("the bank's reference is kept in the description",
          "FT26001" in rows[1][1])


def test_four_column_variant() -> None:
    print("\nSome QuickBooks regions want Credit and Debit instead")
    rows = rows_of(ax.bank_statement_csv([
        Line("2026-08-04", "TRF OUT", "F1", -50_000.00),
        Line("2026-08-05", "MONEY IN", "F2", 20_000.00),
    ], four_column=True)[0])
    check("four columns",
          rows[0] == ["Date", "Description", "Credit", "Debit"])
    check("money out lands in Debit", rows[1][3] == "50000.00" and rows[1][2] == "")
    check("money in lands in Credit", rows[2][2] == "20000.00" and rows[2][3] == "")


def test_large_statements_are_split() -> None:
    print("\nA statement over QuickBooks' row cap is split, not truncated")
    many = [Line("2026-08-04", f"TRF {i}", f"F{i}", -1000.0)
            for i in range(2_500)]
    files = ax.bank_statement_csv(many)
    check("three files", len(files) == 3, str(len(files)))
    check("each under the cap",
          all(len(rows_of(f)) - 1 <= ax.QBO_ROWS_PER_FILE for f in files))
    check("every row survives",
          sum(len(rows_of(f)) - 1 for f in files) == 2_500)
    check("each file carries its own header",
          all(rows_of(f)[0][0] == "Date" for f in files))


def test_an_empty_export_says_so() -> None:
    print("\nNothing to export is an error, not an empty file")
    try:
        ax.bank_statement_csv([])
    except ax.ExportError as exc:
        check("refused with a message", "No transactions" in str(exc))
    else:
        check("refused", False)


def test_date_format_follows_their_books() -> None:
    print("\nThe date format is their QuickBooks setting, not our guess")
    rows = rows_of(ax.bank_statement_csv(
        [Line("2026-08-04", "TRF", "F1", -100.0)],
        date_format="%m/%d/%Y")[0])
    check("month-first when asked", rows[1][0] == "08/04/2026")


# ─── payment register ───────────────────────────────────────────────────────


def seed_payments() -> None:
    clear()
    disb.record(ORG, source_kind="requisition", source_id="r1",
                source_ref="REQ-0007", payee_name="Acme Ltd", amount=250_000,
                paid_at=f"{PERIOD}-04T10:00:00+00:00", bank_reference="FT26001",
                memo="supplies")
    disb.record(ORG, source_kind="payroll", source_id="p1", source_ref="PR3",
                payee_name="Amina Bello", amount=320_000,
                paid_at=f"{PERIOD}-28T10:00:00+00:00", bank_reference="FTPAY1",
                memo="salary")


def test_the_register_carries_the_approval_coding() -> None:
    print("\nEvery paid item, coded the way it was approved")
    seed_payments()
    ax.set_map(ORG, ax.AccountMap(
        accounts={"supplies": "Office Supplies", "salary": "Salaries & Wages"},
        classes={"REQ-0007": "GF-2026-TB", "PR3": "Core"},
        bank_account="GTBank Current 3012345678"))

    rows = rows_of(ax.payment_register_csv(ORG, PERIOD))
    check("header names every field a bookkeeper needs",
          rows[0] == ["Date", "Payee", "Amount", "Account", "Class",
                      "Paid From", "Bank Reference", "DOCex Reference",
                      "Source", "Memo"])
    check("two payments", len(rows) == 3)

    acme = rows[1]
    check("oldest first", acme[1] == "Acme Ltd")
    check("mapped to the right account", acme[3] == "Office Supplies")
    check("and the right class", acme[4] == "GF-2026-TB")
    check("bank account named", acme[5] == "GTBank Current 3012345678")
    check("amount is clean", acme[2] == "250000.00")

    payroll = rows[2]
    check("payroll appears too — not just requisitions", payroll[1] == "Amina Bello")
    check("coded to salaries", payroll[3] == "Salaries & Wages")
    check("and marked as payroll in origin", payroll[8] == "payroll")

    # The column that answers "who approved this?" months later.
    check("the DOCex reference travels into QuickBooks",
          {r[7] for r in rows[1:]} == {"REQ-0007", "PR3"})


def test_unmapped_categories_are_surfaced_before_export() -> None:
    print("\nUnmapped spend is reported up front, not discovered in QuickBooks")
    seed_payments()
    ax.set_map(ORG, ax.AccountMap(accounts={"supplies": "Office Supplies"},
                                  bank_account="GTBank Current"))
    missing = ax.unmapped_categories(ORG, PERIOD)
    check("the unmapped category is named", missing == ["salary"], str(missing))

    s = ax.export_summary(ORG, PERIOD)
    check("the summary is not ready", s["ready"] is False)
    check("and says which category is missing", s["unmapped_categories"] == ["salary"])
    check("it counts the payments", s["payments"] == 2)
    check("and their value", s["value"] == 570_000)

    ax.set_map(ORG, ax.AccountMap(
        accounts={"supplies": "Office Supplies", "salary": "Salaries & Wages"},
        bank_account="GTBank Current"))
    check("ready once everything is mapped",
          ax.export_summary(ORG, PERIOD)["ready"] is True)


def test_an_unmapped_payment_still_exports_somewhere_visible() -> None:
    print("\nUnmapped spend lands in an obvious account, never silently dropped")
    seed_payments()
    ax.set_map(ORG, ax.AccountMap(accounts={}, bank_account="GTBank Current"))
    rows = rows_of(ax.payment_register_csv(ORG, PERIOD))
    check("both payments still exported", len(rows) == 3)
    check("posted somewhere a bookkeeper will notice",
          all(r[3] == "Uncategorised Expense" for r in rows[1:]))


def test_the_summary_warns_about_column_mapping() -> None:
    print("\nThe export does not pretend to be a magic QuickBooks format")
    s = ax.export_summary(ORG, PERIOD)
    check("it says columns are mapped on import",
          "mapped on the QuickBooks import screen" in s["note"])


def test_org_scoping() -> None:
    print("\nOne org cannot export another's payments")
    seed_payments()
    disb.record("other-org", source_kind="direct", source_id="x",
                source_ref="X1", payee_name="Someone Else", amount=999_999,
                paid_at=f"{PERIOD}-10T10:00:00+00:00")
    text = ax.payment_register_csv(ORG, PERIOD)
    check("their payment is absent", "Someone Else" not in text)


def main() -> int:
    print("=" * 66)
    print("QuickBooks export — hand off cleanly, don't compete")
    print("=" * 66)
    for fn in (
        test_the_output_obeys_quickbooks_rules,
        test_four_column_variant,
        test_large_statements_are_split,
        test_an_empty_export_says_so,
        test_date_format_follows_their_books,
        test_the_register_carries_the_approval_coding,
        test_unmapped_categories_are_surfaced_before_export,
        test_an_unmapped_payment_still_exports_somewhere_visible,
        test_the_summary_warns_about_column_mapping,
        test_org_scoping,
    ):
        fn()
    print("\n" + "=" * 66)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 66)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
