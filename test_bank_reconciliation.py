"""
Bank reconciliation — the tests that decide whether this is trustworthy.

A reconciliation engine fails dangerously rather than loudly: a wrong pairing
produces a clean report, and a clean report stops a human looking. So most of
what follows is about what the engine REFUSES to do — guess a date format,
pick between two identical amounts, treat a reference match with a different
amount as settled, or let a month close over money nobody can explain.

Run: python test_bank_reconciliation.py
"""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-recon-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import bank_reconciliation as br  # noqa: E402

ORG = "recontest"
PERIOD = "2026-08"
_passed = _failed = 0


def check(label: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def raises(label: str, fn, *, contains: str = "") -> None:
    try:
        fn()
    except br.ReconciliationError as exc:
        if contains and contains.lower() not in str(exc).lower():
            check(f"{label} (wrong message: {exc})", False)
        else:
            check(label, True)
    except Exception as exc:                       # noqa: BLE001
        check(f"{label} (wrong exception type: {type(exc).__name__}: {exc})", False)
    else:
        check(f"{label} (no error raised)", False)


class FakeTxn:
    """Stands in for requisitions.TransactionRecord — same fields we read."""

    def __init__(self, tid, ref, vendor, amount, paid_day, bank_reference=""):
        self.id = tid
        self.requisition_ref = ref
        self.vendor_name = vendor
        self.amount = amount
        self.paid_at = f"2026-08-{paid_day:02d}T10:00:00+00:00"
        self.bank_reference = bank_reference


def statement(rows: list[str], header: str = "Value Date,Narration,Reference,Debit,Credit") -> bytes:
    return ("\n".join([header] + rows)).encode()


# ─── amounts ────────────────────────────────────────────────────────────────


def test_amount_parsing() -> None:
    print("\nAmounts are read the way banks actually write them")
    check("plain", br.parse_amount("1500.00") == 150_000)
    check("thousands separators", br.parse_amount("1,250,000.50") == 125_000_050)
    check("naira symbol", br.parse_amount("₦1,500") == 150_000)
    check("currency code", br.parse_amount("NGN 1500.00") == 150_000)
    check("parentheses mean negative", br.parse_amount("(1,500.00)") == -150_000)
    check("trailing DR means out", br.parse_amount("1,500.00 DR") == -150_000)
    check("trailing CR means in", br.parse_amount("1,500.00 CR") == 150_000)
    check("empty is None, not zero", br.parse_amount("") is None)
    check("a real float survives", br.parse_amount(1500.0) == 150_000)
    # The float trap: 0.1 + 0.2 arithmetic must never decide equality.
    check("kobo are integers", br.parse_amount("0.29") + br.parse_amount("0.01") == 30)


# ─── dates ──────────────────────────────────────────────────────────────────


def test_dates_are_proved_not_guessed() -> None:
    print("\nDate format comes from the data, or the import stops")
    check("a day above 12 proves day-first",
          br.infer_date_format(["03/04/2026", "25/04/2026"]) == "%d/%m/%Y")
    check("a month position above 12 proves month-first",
          br.infer_date_format(["04/25/2026", "03/04/2026"]) == "%m/%d/%Y")
    check("ISO dates need no inference", br.infer_date_format(["2026-08-01"]) == "")

    # THE important one. Every value readable both ways = do not guess.
    raises("an entirely ambiguous column is refused",
           lambda: br.infer_date_format(["03/04/2026", "05/06/2026"]),
           contains="either")
    raises("a column that contradicts itself is refused",
           lambda: br.infer_date_format(["25/04/2026", "04/25/2026"]),
           contains="inconsistent")


def test_a_partial_column_map_supplements_detection() -> None:
    print("\nSaying only the date format must not throw away column detection")
    # Early in a month nothing in the file proves day-first, so the ONLY thing
    # the user can usefully supply is the format. If that answer replaced
    # detection wholesale, the import would find no columns and report "no
    # usable rows" — which reads like a broken file rather than a resolved
    # question. This is the exact bug that shipped and was caught in the demo.
    data = statement(["05/06/2026,TRF TO ACME LTD,FT1,250000.00,",
                      "06/06/2026,TRF TO BETA,FT2,90000.00,"])
    lines, cmap = br.parse_statement(data, column_map=br.ColumnMap(date_format="%d/%m/%Y"))
    check("rows are read", len(lines) == 2)
    check("columns were still detected", cmap.debit == "Debit")
    check("and the supplied format was honoured", lines[0].date == "2026-06-05")

    # A named column still wins outright.
    lines, cmap = br.parse_statement(
        data, column_map=br.ColumnMap(date="Value Date", debit="Debit",
                                      date_format="%d/%m/%Y"))
    check("an explicit mapping is used as given", cmap.date == "Value Date")
    check("and reads the same rows", len(lines) == 2)


def test_ambiguous_dates_stop_the_import() -> None:
    print("\nAn ambiguous statement cannot be imported by accident")
    data = statement(["05/06/2026,PAYMENT ABC,REF1,1500.00,"])
    raises("import refuses rather than reading dates wrong",
           lambda: br.parse_statement(data), contains="date_format")

    cmap = br.ColumnMap(date="Value Date", description="Narration",
                        reference="Reference", debit="Debit", credit="Credit",
                        date_format="%d/%m/%Y")
    lines, _ = br.parse_statement(data, column_map=cmap)
    check("...and imports cleanly once told the format",
          lines[0].date == "2026-06-05")


# ─── column detection ───────────────────────────────────────────────────────


def test_column_detection() -> None:
    print("\nCommon Nigerian statement layouts are recognised")
    lines, cmap = br.parse_statement(statement(
        ["2026-08-04,TRF TO ACME LTD,FT26001,250000.00,",
         "2026-08-05,SALARY CREDIT,SAL01,,900000.00"]))
    check("date column found", cmap.date == "Value Date")
    check("debit column found", cmap.debit == "Debit")
    check("debits are negative", lines[0].amount_minor == -25_000_000)
    check("credits are positive", lines[1].amount_minor == 90_000_000)
    check("row numbers are kept for tracing", lines[0].row == 1)

    lines, cmap = br.parse_statement(statement(
        ["2026-08-04,TRF TO ACME,FT26001,-250000.00"],
        header="Transaction Date,Details,Transaction Ref,Amount"))
    check("a single signed amount column also works", cmap.amount == "Amount")
    check("and its sign is respected", lines[0].is_debit)

    raises("a file with no date column says so",
           lambda: br.parse_statement(statement(["a,b"], header="Foo,Bar")),
           contains="no date column")


def test_preamble_rows_are_skipped() -> None:
    print("\nA statement with bank preamble above the header still imports")
    data = ("FIRST BANK OF NIGERIA PLC\n"
            "Account: 3012345678  Period: 01-Aug-2026 to 31-Aug-2026\n"
            "\n"
            "Value Date,Narration,Reference,Debit,Credit\n"
            "2026-08-04,TRF TO ACME LTD,FT26001,250000.00,\n").encode()
    lines, _ = br.parse_statement(data)
    check("the real header row is found", len(lines) == 1)
    check("and the row parsed", lines[0].amount == -250000.0)


# ─── matching ───────────────────────────────────────────────────────────────


def test_reference_match_is_preferred() -> None:
    print("\nThe bank reference settles it when present")
    txns = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 250000.0, 4, "FT26001")]
    data = statement([
        "2026-08-04,TRF TO SOMEONE ELSE ENTIRELY,FT26001,250000.00,",
        "2026-08-04,ANOTHER PAYMENT,FT99999,250000.00,",
    ])
    run = br.reconcile(ORG, PERIOD, data, transactions=txns, actor="test")
    check("matched", len(run.matches) == 1)
    check("by reference, not by amount coincidence",
          run.matches[0].method == br.MatchMethod.REFERENCE)
    check("the other debit is reported as not in the system",
          any(e.code == br.ExceptionCode.NOT_IN_SYSTEM for e in run.exceptions))


def test_reference_match_with_wrong_amount_is_a_finding() -> None:
    print("\nSame reference, different amount → the discovery, not a match")
    txns = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 250000.0, 4, "FT26001")]
    data = statement(["2026-08-04,TRF TO ACME LTD,FT26001,255000.00,"])
    run = br.reconcile(ORG, PERIOD, data, transactions=txns, actor="test")
    check("not treated as settled", len(run.matches) == 0)
    exc = run.exceptions[0]
    check("raised as AMOUNT_MISMATCH", exc.code == br.ExceptionCode.AMOUNT_MISMATCH)
    check("at high severity", exc.severity == br.Severity.HIGH)
    check("and the difference is stated", "5,000.00" in exc.note)


def test_amount_and_date_window() -> None:
    print("\nWithout a reference: amount + date window")
    txns = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 250000.0, 4)]
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-06,TRF 0034,,250000.00,"]), transactions=txns, actor="test")
    check("cleared two days later still matches",
          run.matches and run.matches[0].method == br.MatchMethod.EXACT)
    check("the gap is recorded", run.matches[0].day_gap == 2)

    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-20,TRF 0034,,250000.00,"]), transactions=txns, actor="test")
    check("sixteen days later does not silently match", len(run.matches) == 0)


def test_two_identical_amounts_are_not_guessed() -> None:
    print("\nTwo payments, two identical debits — the engine refuses to pair")
    txns = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 100000.0, 4),
            FakeTxn("T2", "REQ-0002", "Beta Ltd", 100000.0, 4)]
    data = statement(["2026-08-04,TRANSFER,,100000.00,",
                      "2026-08-04,TRANSFER,,100000.00,"])
    run = br.reconcile(ORG, PERIOD, data, transactions=txns, actor="test")
    check("nothing is paired on a coin flip", len(run.matches) == 0)
    ambiguous = [e for e in run.exceptions if e.code == br.ExceptionCode.AMBIGUOUS]
    check("both payments are flagged ambiguous", len(ambiguous) == 2)
    check("with the candidates listed", len(ambiguous[0].candidates) == 2)

    # Same setup, but the narration names one vendor → that one resolves.
    data = statement(["2026-08-04,TRF TO ACME LTD LAGOS,,100000.00,",
                      "2026-08-04,TRANSFER,,100000.00,"])
    run = br.reconcile(ORG, PERIOD, data, transactions=txns, actor="test")
    check("a named vendor breaks the tie",
          any(m.transaction_id == "T1" for m in run.matches))


def test_vendor_matching_needs_a_distinctive_word() -> None:
    print("\nVendor matching ignores words that match everything")
    check("'Nigeria Ltd' alone is not a match",
          br._vendor_hit("Nigeria Ltd", "TRF TO SOMETHING NIGERIA LIMITED") is False)
    check("a real name is", br._vendor_hit("Acme Ltd", "TRF TO ACME LTD"))
    check("case and punctuation do not matter",
          br._vendor_hit("Acme-Global", "trf/acme/inv"))


# ─── the findings that matter ───────────────────────────────────────────────


def test_a_bank_debit_with_no_requisition_is_the_top_finding() -> None:
    print("\nMoney out with no approval behind it")
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-11,TRF TO UNKNOWN VENDOR,X1,750000.00,"]),
        transactions=[], actor="test")
    exc = run.exceptions[0]
    check("reported", exc.code == br.ExceptionCode.NOT_IN_SYSTEM)
    check("at high severity", exc.severity == br.Severity.HIGH)
    check("the amount is stated", exc.amount == 750000.0)
    check("the run is not reconciled", run.reconciled is False)
    check("and the variance shows the money", run.variance == -750000.0)


def test_a_payment_that_never_cleared() -> None:
    print("\nRecorded as paid, nothing in the bank")
    mid = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 90000.0, 10)]
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-04,UNRELATED,Z9,1000.00,"]), transactions=mid, actor="test")
    exc = next(e for e in run.exceptions if e.code == br.ExceptionCode.NOT_IN_BANK)
    check("mid-month non-clearance is high severity", exc.severity == br.Severity.HIGH)

    end = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 90000.0, 30)]
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-04,UNRELATED,Z9,1000.00,"]), transactions=end, actor="test")
    exc = next(e for e in run.exceptions if e.code == br.ExceptionCode.NOT_IN_BANK)
    check("near period end it is timing, not a defect",
          exc.severity == br.Severity.MEDIUM)
    check("and says so", "next statement" in exc.note)


def test_a_duplicated_debit() -> None:
    print("\nThe same debit twice")
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-04,TRF TO ACME,FT1,50000.00,",
         "2026-08-04,TRF TO ACME,FT1,50000.00,"]),
        transactions=[], actor="test")
    dup = [e for e in run.exceptions if e.code == br.ExceptionCode.DUPLICATE_BANK_LINE]
    check("flagged once, not twice", len(dup) == 1)
    check("pointing at the first occurrence", "row 1" in dup[0].note)


def test_credits_are_not_reconciled_as_payments() -> None:
    print("\nMoney IN is not a payment")
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-04,GRANT RECEIPT FROM DONOR,GR1,,5000000.00"]),
        transactions=[], actor="test")
    check("a credit raises no payment exception", len(run.exceptions) == 0)
    check("and does not touch the debit total", run.total_debits_in_bank == 0.0)


def test_a_clean_month_reads_clean() -> None:
    print("\nA month that actually reconciles")
    txns = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 250000.0, 4, "FT26001"),
            FakeTxn("T2", "REQ-0002", "Beta Services", 90000.0, 12)]
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-04,TRF ACME,FT26001,250000.00,",
         "2026-08-13,TRF TO BETA SERVICES,,90000.00,"]),
        transactions=txns, actor="finance@org")
    check("everything matched", len(run.matches) == 2)
    check("no exceptions", len(run.exceptions) == 0)
    check("variance is zero", run.variance == 0.0)
    check("reconciled", run.reconciled is True)
    check("totals agree", run.total_paid_in_system == run.total_debits_in_bank)
    s = br.summary(run)
    check("summary is honest about it", s["reconciled"] and s["matched"] == 2)


def test_out_of_period_lines_are_ignored() -> None:
    print("\nOnly the period being reconciled is in scope")
    txns = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 250000.0, 4, "FT26001")]
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-07-30,PRIOR MONTH,OLD1,999999.00,",
         "2026-08-04,TRF ACME,FT26001,250000.00,",
         "2026-09-02,NEXT MONTH,NEW1,888888.00,"]),
        transactions=txns, actor="test")
    check("July and September are out of scope", len(run.exceptions) == 0)
    check("only August debits are totalled", run.total_debits_in_bank == 250000.0)


# ─── the run as evidence ────────────────────────────────────────────────────


def test_the_statement_is_fingerprinted() -> None:
    print("\nWhich file was reconciled is provable")
    data = statement(["2026-08-04,TRF,FT1,1000.00,"])
    a = br.reconcile(ORG, PERIOD, data, transactions=[], actor="test")
    b = br.reconcile(ORG, PERIOD, data, transactions=[], actor="test")
    c = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-04,TRF,FT1,1000.01,"]), transactions=[], actor="test")
    check("same file, same hash", a.statement_sha256 == b.statement_sha256)
    check("one kobo different, different hash",
          a.statement_sha256 != c.statement_sha256)
    check("the column mapping used is stored", a.column_map.date == "Value Date")


def test_manual_match_requires_a_reason() -> None:
    print("\nA human override is recorded, never silent")
    txns = [FakeTxn("T1", "REQ-0001", "Acme Ltd", 100000.0, 4),
            FakeTxn("T2", "REQ-0002", "Beta Ltd", 100000.0, 4)]
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-04,TRANSFER,,100000.00,",
         "2026-08-04,TRANSFER,,100000.00,"]), transactions=txns, actor="test")
    line_id = run.bank_lines[0].id

    raises("a blank reason is refused",
           lambda: br.manual_match(ORG, run.id, transaction_id="T1",
                                   bank_line_id=line_id, actor="a@org", reason="  "),
           contains="written reason")

    class Stub:
        id, requisition_ref, vendor_name = "T1", "REQ-0001", "Acme Ltd"
        amount, paid_at, bank_reference = 100000.0, "2026-08-04T10:00:00+00:00", ""

    import requisitions as _req
    original = _req.get_transaction
    _req.get_transaction = lambda org, tid: Stub() if tid == "T1" else None
    try:
        run = br.manual_match(ORG, run.id, transaction_id="T1",
                              bank_line_id=line_id, actor="a@org",
                              reason="Confirmed with GTBank: FT26001 is REQ-0001.")
        check("the match is made", len(run.matches) == 1)
        check("marked as manual", run.matches[0].method == br.MatchMethod.MANUAL)
        check("the reason is kept", "GTBank" in run.matches[0].reason)
        check("and who decided", run.matches[0].matched_by == "a@org")
        check("the ambiguity for that payment is cleared",
              not any(e.transaction_id == "T1" for e in run.exceptions))
        raises("the same bank line cannot be used twice",
               lambda: br.manual_match(ORG, run.id, transaction_id="T2",
                                       bank_line_id=line_id, actor="a@org",
                                       reason="also this one"),
               contains="already matched")
    finally:
        _req.get_transaction = original


def test_closing_is_blocked_over_unexplained_money() -> None:
    print("\nA month cannot quietly close over money nobody explained")
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-11,TRF TO UNKNOWN,X1,750000.00,",
         "2026-08-12,MONTHLY BANK CHARGE,CHG,2500.00,"]),
        transactions=[], actor="test")
    check("two high-severity items", run.unresolved_high == 2)
    raises("close is refused",
           lambda: br.close_period(ORG, run.id, actor="fin@org"),
           contains="unexplained")

    run = br.explain_exception(ORG, run.id,
                               bank_line_id=run.bank_lines[1].id,
                               actor="fin@org", reason="Standard bank charge")
    check("an explained item is downgraded, not deleted",
          len(run.exceptions) == 2 and run.unresolved_high == 1)
    check("and the explanation names who gave it",
          any("fin@org" in e.note for e in run.exceptions))

    run = br.explain_exception(ORG, run.id,
                               bank_line_id=run.bank_lines[0].id,
                               actor="fin@org",
                               reason="Duplicate of July payment, refund requested")
    run = br.close_period(ORG, run.id, actor="fin@org")
    check("now it closes", run.locked is True)
    check("with who and when", run.closed_by == "fin@org" and bool(run.closed_at))


def test_forcing_a_close_is_allowed_but_named() -> None:
    print("\nForcing a close is a decision that carries a name")
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-11,TRF TO UNKNOWN,X1,750000.00,"]),
        transactions=[], actor="test")
    run = br.close_period(ORG, run.id, actor="ed@org",
                          force_reason="Bank investigating; audit informed.")
    check("closed", run.locked is True)
    check("the override is written into the run",
          any("CLOSED WITH" in e.note and "ed@org" in e.note for e in run.exceptions))


def test_a_closed_run_is_immutable() -> None:
    print("\nClosed means closed")
    run = br.reconcile(ORG, PERIOD, statement(
        ["2026-08-11,TRF,X1,1000.00,"]), transactions=[], actor="test")
    br.close_period(ORG, run.id, actor="fin@org", force_reason="accepted")
    raises("no further explanations",
           lambda: br.explain_exception(ORG, run.id,
                                        bank_line_id=run.bank_lines[0].id,
                                        actor="x@org", reason="changed my mind"),
           contains="cannot be edited")
    raises("no re-closing",
           lambda: br.close_period(ORG, run.id, actor="x@org", force_reason="again"),
           contains="closed")


def test_runs_are_org_scoped() -> None:
    print("\nOne org cannot see another's reconciliation")
    a = br.reconcile("org-a", PERIOD, statement(
        ["2026-08-04,TRF,A1,1000.00,"]), transactions=[], actor="test")
    br.reconcile("org-b", PERIOD, statement(
        ["2026-08-04,TRF,B1,2000.00,"]), transactions=[], actor="test")
    check("get is scoped", br.get_run("org-b", a.id) is None)
    check("list is scoped", len(br.list_runs("org-a")) == 1)


def test_period_parsing() -> None:
    print("\nPeriod bounds, including the ones people get wrong")
    check("August ends on the 31st", br._period_bounds("2026-08")[1] == "2026-08-31")
    check("February 2026", br._period_bounds("2026-02")[1] == "2026-02-28")
    check("leap February", br._period_bounds("2028-02")[1] == "2028-02-29")
    check("December rolls the year", br._period_bounds("2026-12")[1] == "2026-12-31")
    raises("a malformed period is refused",
           lambda: br._period_bounds("August 2026"), contains="2026-08")


def main() -> int:
    print("=" * 66)
    print("Bank reconciliation — what the engine refuses to guess")
    print("=" * 66)
    for fn in (
        test_amount_parsing,
        test_dates_are_proved_not_guessed,
        test_ambiguous_dates_stop_the_import,
        test_a_partial_column_map_supplements_detection,
        test_column_detection,
        test_preamble_rows_are_skipped,
        test_reference_match_is_preferred,
        test_reference_match_with_wrong_amount_is_a_finding,
        test_amount_and_date_window,
        test_two_identical_amounts_are_not_guessed,
        test_vendor_matching_needs_a_distinctive_word,
        test_a_bank_debit_with_no_requisition_is_the_top_finding,
        test_a_payment_that_never_cleared,
        test_a_duplicated_debit,
        test_credits_are_not_reconciled_as_payments,
        test_a_clean_month_reads_clean,
        test_out_of_period_lines_are_ignored,
        test_the_statement_is_fingerprinted,
        test_manual_match_requires_a_reason,
        test_closing_is_blocked_over_unexplained_money,
        test_forcing_a_close_is_allowed_but_named,
        test_a_closed_run_is_immutable,
        test_runs_are_org_scoped,
        test_period_parsing,
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
