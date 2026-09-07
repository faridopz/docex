"""
The payment ledger, and the false alarm it exists to stop.

The bug this prevents: a payroll run that was raised, reviewed and approved
showed up at reconciliation as "money left the account with no approved
request" — the most serious finding the system can produce, fired at a payment
that was entirely correct. Reconciliation could only see requisitions.

So the tests that matter here are the end-to-end ones: pay a payroll run, upload
the statement it produced, and prove it reconciles clean.

Run: python test_disbursements.py
"""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-disb-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import bank_reconciliation as br  # noqa: E402
import disbursements as disb  # noqa: E402

ORG = "disbtest"
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


def raises(label: str, fn, *, contains: str = "") -> None:
    try:
        fn()
    except disb.DisbursementError as exc:
        check(label, not contains or contains.lower() in str(exc).lower(), str(exc))
    except Exception as exc:                               # noqa: BLE001
        check(f"{label} (wrong exception: {type(exc).__name__}: {exc})", False)
    else:
        check(f"{label} (nothing raised)", False)


def statement(rows: list[str]) -> bytes:
    header = "Value Date,Narration,Reference,Debit,Credit"
    return ("\n".join([header] + rows)).encode()


def clear() -> None:
    for d in store.get_store().list(ORG, "disbursements"):
        store.get_store().delete(ORG, "disbursements", d["id"])


# ─── the ledger itself ──────────────────────────────────────────────────────


def test_a_payment_must_say_who_and_how_much() -> None:
    print("\nA ledger line that cannot say who was paid is not evidence")
    raises("an unnamed payee is refused",
           lambda: disb.record(ORG, source_kind="direct", source_id="x",
                               payee_name="  ", amount=1000),
           contains="who was paid")
    raises("a zero amount is refused",
           lambda: disb.record(ORG, source_kind="direct", source_id="x",
                               payee_name="Acme", amount=0),
           contains="positive")
    raises("a negative amount is refused, with a reason",
           lambda: disb.record(ORG, source_kind="direct", source_id="x",
                               payee_name="Acme", amount=-500),
           contains="refund")


def test_individual_payments_share_a_batch() -> None:
    print("\nTwelve staff paid separately = twelve ledger lines, one batch")
    clear()
    lines = [{"payee_name": f"Staff {i}", "amount": 100_000 + i} for i in range(1, 13)]
    made = disb.record_batch(ORG, source_kind="payroll", source_id="run1",
                             source_ref="PR3", lines=lines,
                             paid_at=f"{PERIOD}-28T09:00:00+00:00")
    check("twelve lines", len(made) == 12)
    check("all sharing one batch", len({d.batch_id for d in made}) == 1)
    check("each names its own payee", made[0].payee_name == "Staff 1")
    check("all point back at the run", all(d.source_ref == "PR3" for d in made))
    check("marked individual", made[0].settlement == disb.Settlement.INDIVIDUAL)


def test_a_bulk_transfer_is_one_line() -> None:
    print("\nThe same run paid as one lump sum = one ledger line")
    clear()
    lines = [{"payee_name": f"Staff {i}", "amount": 100_000} for i in range(1, 13)]
    made = disb.record_batch(ORG, source_kind="payroll", source_id="run1",
                             source_ref="PR3", lines=lines,
                             bulk_reference="FTBULK998",
                             bulk_payee="Payroll 2026-08",
                             paid_at=f"{PERIOD}-28T09:00:00+00:00")
    check("one line", len(made) == 1)
    check("for the total", made[0].amount == 1_200_000)
    check("marked bulk", made[0].settlement == disb.Settlement.BULK)
    check("and says what the lump sum covered", "12 payee" in made[0].memo)


def test_requisition_payments_are_derived_not_copied() -> None:
    print("\nRequisition payments are read from the frozen record, never copied")
    clear()

    class FakeTxn:
        id = "TRANS-0001"
        requisition_id = "r1"
        requisition_ref = "REQ-0007"
        vendor_name = "Acme Ltd"
        vendor_account = "0123456789"
        amount = 250_000.0
        currency = "NGN"
        paid_at = f"{PERIOD}-04T10:00:00+00:00"
        paid_by = "finance@org"
        bank_reference = "FT26001"
        category = "supplies"

    import requisitions as rq
    original = rq.list_transactions
    rq.list_transactions = lambda org: [FakeTxn()]
    try:
        items = disb.list_disbursements(ORG, period=PERIOD)
        check("it appears in the ledger", len(items) == 1)
        d = items[0]
        check("as a requisition payment", d.source_kind == disb.SourceKind.REQUISITION)
        check("carrying the bank reference", d.bank_reference == "FT26001")
        check("and the payee", d.payee_name == "Acme Ltd")
        check("with a stable id across calls",
              d.id == disb.list_disbursements(ORG, period=PERIOD)[0].id)
        check("nothing was written to storage",
              len(store.get_store().list(ORG, "disbursements")) == 0)
    finally:
        rq.list_transactions = original


def test_the_window_is_respected() -> None:
    print("\nOnly the month being asked about comes back")
    clear()
    disb.record(ORG, source_kind="direct", source_id="a", payee_name="July Vendor",
                amount=1000, paid_at="2026-07-30T10:00:00+00:00")
    disb.record(ORG, source_kind="direct", source_id="b", payee_name="August Vendor",
                amount=2000, paid_at=f"{PERIOD}-15T10:00:00+00:00")
    items = disb.list_disbursements(ORG, period=PERIOD)
    check("one payment in August", len(items) == 1)
    check("the right one", items[0].payee_name == "August Vendor")


def test_coverage_reports_missing_references() -> None:
    print("\nHow reconcilable the month is, before any statement is uploaded")
    clear()
    disb.record(ORG, source_kind="voucher", source_id="v1", payee_name="A",
                amount=1000, paid_at=f"{PERIOD}-02T10:00:00+00:00",
                bank_reference="FT1")
    disb.record(ORG, source_kind="voucher", source_id="v2", payee_name="B",
                amount=2000, paid_at=f"{PERIOD}-03T10:00:00+00:00")
    c = disb.coverage(ORG, PERIOD)
    check("counts the payments", c["payments"] == 2)
    check("totals them", c["value"] == 3000)
    check("and flags the one with no reference", c["without_bank_reference"] == 1)
    check("broken down by source", c["by_source"]["voucher"]["count"] == 2)


def test_org_scoping() -> None:
    print("\nOne org cannot see another's payments")
    clear()
    disb.record(ORG, source_kind="direct", source_id="a", payee_name="Mine",
                amount=1000, paid_at=f"{PERIOD}-02T10:00:00+00:00")
    disb.record("other-org", source_kind="direct", source_id="b", payee_name="Theirs",
                amount=9999, paid_at=f"{PERIOD}-02T10:00:00+00:00")
    mine = disb.list_disbursements(ORG, period=PERIOD)
    check("only my payment", len(mine) == 1 and mine[0].payee_name == "Mine")


# ─── the point of all of it ─────────────────────────────────────────────────


def test_an_approved_payroll_run_reconciles_clean() -> None:
    print("\nTHE BUG THIS FIXES: approved payroll no longer reads as unapproved")
    clear()
    # Three staff, paid individually on the 28th.
    people = [("Amina Bello", 320_000, "FT26A"),
              ("Chidi Okafor", 285_000, "FT26B"),
              ("Ngozi Eze", 410_000, "FT26C")]
    disb.record_batch(
        ORG, source_kind="payroll", source_id="run-aug", source_ref="PR3",
        paid_at=f"{PERIOD}-28T09:00:00+00:00", paid_by="finance@org",
        lines=[{"payee_name": n, "amount": a, "bank_reference": r}
               for n, a, r in people])

    stmt = statement([
        f"{PERIOD}-28,SALARY TRF AMINA BELLO,FT26A,320000.00,",
        f"{PERIOD}-28,SALARY TRF CHIDI OKAFOR,FT26B,285000.00,",
        f"{PERIOD}-28,SALARY TRF NGOZI EZE,FT26C,410000.00,",
    ])
    run = br.reconcile(ORG, PERIOD, stmt, actor="finance@org")

    check("all three salary payments matched", run.matched == 3 if hasattr(run, "matched")
          else len(run.matches) == 3, f"{len(run.matches)} matched")
    check("NOTHING is reported as unapproved money",
          not [e for e in run.exceptions
               if e.code == br.ExceptionCode.NOT_IN_SYSTEM],
          str([e.code.value for e in run.exceptions]))
    check("the month reconciles", run.reconciled is True)
    check("matched by reference", all(m.method == br.MatchMethod.REFERENCE
                                      for m in run.matches))
    check("and each points back at the payroll run",
          all(m.transaction_ref == "PR3" for m in run.matches))


def test_a_bulk_payroll_reconciles_against_one_debit() -> None:
    print("\nThe same run paid in bulk matches the single lump sum")
    clear()
    disb.record_batch(
        ORG, source_kind="payroll", source_id="run-aug", source_ref="PR3",
        paid_at=f"{PERIOD}-28T09:00:00+00:00", bulk_reference="FTBULK77",
        bulk_payee="Payroll 2026-08",
        lines=[{"payee_name": n, "amount": a}
               for n, a in [("Amina", 320_000), ("Chidi", 285_000),
                            ("Ngozi", 410_000)]])

    run = br.reconcile(ORG, PERIOD, statement([
        f"{PERIOD}-28,BULK SALARY UPLOAD AUG,FTBULK77,1015000.00,",
    ]), actor="finance@org")
    check("one payment, one debit, matched", len(run.matches) == 1)
    check("for the full run", run.matches[0].amount == 1_015_000)
    check("clean", run.reconciled is True)


def test_a_genuinely_unapproved_debit_still_fires() -> None:
    print("\nThe control still works — a real one is still caught")
    clear()
    disb.record_batch(
        ORG, source_kind="payroll", source_id="run-aug", source_ref="PR3",
        paid_at=f"{PERIOD}-28T09:00:00+00:00",
        lines=[{"payee_name": "Amina Bello", "amount": 320_000,
                "bank_reference": "FT26A"}])

    run = br.reconcile(ORG, PERIOD, statement([
        f"{PERIOD}-28,SALARY TRF AMINA BELLO,FT26A,320000.00,",
        f"{PERIOD}-11,TRF TO BRIGHTPATH SUPPLIES,FT999,750000.00,",
    ]), actor="finance@org")
    check("payroll matched", len(run.matches) == 1)
    unapproved = [e for e in run.exceptions
                  if e.code == br.ExceptionCode.NOT_IN_SYSTEM]
    check("the unapproved transfer is still caught", len(unapproved) == 1)
    check("at the right amount", unapproved[0].amount == 750_000)
    check("and the month does not reconcile", run.reconciled is False)


def test_payments_from_every_path_reconcile_together() -> None:
    print("\nA month with a requisition, a payroll run and a voucher in it")
    clear()

    class FakeTxn:
        id = "TRANS-0001"
        requisition_id = "r1"
        requisition_ref = "REQ-0007"
        vendor_name = "Acme Ltd"
        vendor_account = ""
        amount = 250_000.0
        currency = "NGN"
        paid_at = f"{PERIOD}-04T10:00:00+00:00"
        paid_by = "finance@org"
        bank_reference = "FTREQ1"
        category = "supplies"

    disb.record_batch(ORG, source_kind="payroll", source_id="run-aug",
                      source_ref="PR3", paid_at=f"{PERIOD}-28T09:00:00+00:00",
                      lines=[{"payee_name": "Amina Bello", "amount": 320_000,
                              "bank_reference": "FTPAY1"}])
    disb.record(ORG, source_kind="voucher", source_id="v1", source_ref="V7",
                payee_name="Workshop participants", amount=96_000,
                paid_at=f"{PERIOD}-12T10:00:00+00:00", bank_reference="FTVOU1")

    import requisitions as rq
    original = rq.list_transactions
    rq.list_transactions = lambda org: [FakeTxn()]
    try:
        run = br.reconcile(ORG, PERIOD, statement([
            f"{PERIOD}-04,TRF TO ACME LTD,FTREQ1,250000.00,",
            f"{PERIOD}-12,VOUCHER V7 WORKSHOP,FTVOU1,96000.00,",
            f"{PERIOD}-28,SALARY TRF AMINA BELLO,FTPAY1,320000.00,",
        ]), actor="finance@org")
        check("all three paths matched", len(run.matches) == 3,
              f"{len(run.matches)}: {[m.transaction_ref for m in run.matches]}")
        refs = {m.transaction_ref for m in run.matches}
        check("requisition, payroll and voucher all present",
              refs == {"REQ-0007", "PR3", "V7"}, str(refs))
        check("no exceptions", len(run.exceptions) == 0)
        check("the whole month reconciles", run.reconciled is True)
    finally:
        rq.list_transactions = original


def main() -> int:
    print("=" * 66)
    print("The payment ledger — every path, one place")
    print("=" * 66)
    for fn in (
        test_a_payment_must_say_who_and_how_much,
        test_individual_payments_share_a_batch,
        test_a_bulk_transfer_is_one_line,
        test_requisition_payments_are_derived_not_copied,
        test_the_window_is_respected,
        test_coverage_reports_missing_references,
        test_org_scoping,
        test_an_approved_payroll_run_reconciles_clean,
        test_a_bulk_payroll_reconciles_against_one_debit,
        test_a_genuinely_unapproved_debit_still_fires,
        test_payments_from_every_path_reconcile_together,
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
