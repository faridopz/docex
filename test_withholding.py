"""
Withholding tax — and the false alarm it stops.

The bug this prevents is specific and was found in NEEM's own cashbook: WHT at
5% or 10% appears on nearly every vendor payment, remitted separately. So one
approved invoice becomes TWO debits on the bank statement, and reconciliation
reported the tax remittance as "money left the account with no approved
request" — our most serious finding, fired at a statutory payment, on roughly
half the statement.

The last two tests are the ones that matter: reconcile a month containing
withheld payments and prove nothing is falsely accused.

Run: python test_withholding.py
"""
from __future__ import annotations

import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-wht-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import bank_reconciliation as br  # noqa: E402
import disbursements as disb  # noqa: E402
import withholding as wht  # noqa: E402

ORG = "whttest"
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
    except wht.WHTError as exc:
        check(label, not contains or contains.lower() in str(exc).lower(), str(exc))
    except Exception as exc:                                # noqa: BLE001
        check(f"{label} (wrong exception: {type(exc).__name__})", False)
    else:
        check(f"{label} (nothing raised)", False)


def clear() -> None:
    for d in store.get_store().list(ORG, "disbursements"):
        store.get_store().delete(ORG, "disbursements", d["id"])


def configure(**over):
    """A schedule shaped like NEEM's — 5% and 10%, as seen in their cashbook.
    These are TEST values, not rates DOCex ships."""
    policy = wht.WHTPolicy(
        enabled=True,
        rules=[
            wht.WHTRule(category="consultancy", rate_percent=10.0,
                        payee_type="company", description="Professional services"),
            wht.WHTRule(category="consultancy", rate_percent=5.0,
                        payee_type="individual", description="Individual consultant"),
            wht.WHTRule(category="venue", rate_percent=5.0),
            wht.WHTRule(category="rent", rate_percent=10.0),
        ],
        authority_name="Federal Inland Revenue Service",
        remittance_method="RRR", account_code="62010",
        **over)
    return wht.set_policy(ORG, policy)


def statement(rows: list[str]) -> bytes:
    header = "Value Date,Narration,Reference,Debit,Credit"
    return ("\n".join([header] + rows)).encode()


# ─── nothing is invented ────────────────────────────────────────────────────


def test_no_rates_are_shipped() -> None:
    print("\nDOCex ships NO withholding rates — that is deliberate")
    fresh = wht.get_policy("never-configured-org")
    check("a new org has withholding disabled", fresh.enabled is False)
    check("and no rules at all", fresh.rules == [])

    r = wht.compute("never-configured-org", gross=1_000_000, category="consultancy")
    check("so nothing is withheld", r.withheld == 0.0)
    check("and the full amount goes to the payee", r.net_to_payee == 1_000_000)
    check("with the reason stated plainly", "not configured" in r.reason)
    check("the note explains why we ship none",
          "ships no withholding rates" in wht.starter_rules_note())


def test_a_typo_in_a_rate_is_caught() -> None:
    print("\nA tax rate typo becomes a wrong deduction on every invoice")
    raises("a negative rate is refused",
           lambda: wht.set_policy(ORG, wht.WHTPolicy(
               enabled=True, rules=[wht.WHTRule(category="x", rate_percent=-5)])),
           contains="not a withholding rate")
    raises("above 100% is refused",
           lambda: wht.set_policy(ORG, wht.WHTPolicy(
               enabled=True, rules=[wht.WHTRule(category="x", rate_percent=150)])),
           contains="not a withholding rate")
    raises("a rule with no category is refused",
           lambda: wht.set_policy(ORG, wht.WHTPolicy(
               enabled=True, rules=[wht.WHTRule(category=" ", rate_percent=5)])),
           contains="spend category")

    # 50 instead of 5 is legal but almost certainly a typo — flagged, not blocked.
    p = wht.set_policy(ORG, wht.WHTPolicy(
        enabled=True, rules=[wht.WHTRule(category="odd", rate_percent=50)]))
    check("an unusually high rate is allowed but marked",
          "UNUSUALLY HIGH" in p.rules[0].description)


# ─── the arithmetic ─────────────────────────────────────────────────────────


def test_the_split() -> None:
    print("\nOne invoice, split correctly")
    configure()
    r = wht.compute(ORG, gross=1_000_000, category="consultancy", payee_type="company")
    check("10% withheld", r.withheld == 100_000.0)
    check("net to the vendor", r.net_to_payee == 900_000.0)
    check("the two add back to gross", r.withheld + r.net_to_payee == r.gross)
    check("and it says which rule applied", "consultancy" in r.reason)


def test_company_and_individual_rates_differ() -> None:
    print("\nThe same service, a different payee, a different rate")
    configure()
    company = wht.compute(ORG, gross=500_000, category="consultancy",
                          payee_type="company")
    individual = wht.compute(ORG, gross=500_000, category="consultancy",
                             payee_type="individual")
    check("company withheld at 10%", company.withheld == 50_000.0)
    check("individual withheld at 5%", individual.withheld == 25_000.0)
    check("the specific rule beats a catch-all",
          individual.rate_percent == 5.0)


def test_an_uncovered_category_withholds_nothing_and_says_so() -> None:
    print("\nNo rule means no deduction — and the reason is not silence")
    configure()
    r = wht.compute(ORG, gross=200_000, category="stationery")
    check("nothing withheld", r.withheld == 0.0)
    check("applies is False", r.applies is False)
    check("the message names the missing category",
          "'stationery'" in r.reason and "add the rule" in r.reason)


def test_the_floor() -> None:
    print("\nAn organisation can set a floor below which it does not withhold")
    configure(minimum_amount=50_000)
    small = wht.compute(ORG, gross=10_000, category="venue")
    big = wht.compute(ORG, gross=100_000, category="venue")
    check("below the floor, nothing", small.withheld == 0.0)
    check("and it says why", "floor" in small.reason)
    check("above it, withheld normally", big.withheld == 5_000.0)


def test_rounding_is_to_the_kobo() -> None:
    print("\nWithholding is remitted, so rounding is explicit")
    configure()
    r = wht.compute(ORG, gross=333_333.33, category="venue")   # 5%
    check("rounded to the kobo", r.withheld == 16_666.67, str(r.withheld))
    check("net is the exact remainder",
          round(r.withheld + r.net_to_payee, 2) == 333_333.33)


# ─── the ledger ─────────────────────────────────────────────────────────────


def test_both_halves_are_recorded() -> None:
    print("\nBoth debits are recorded — that is what makes them reconcilable")
    configure(); clear()
    out = wht.record_split_payment(
        ORG, source_kind="requisition", source_id="r1", source_ref="REQ-0001",
        payee_name="Sahel Consulting Ltd", gross=1_000_000, category="consultancy",
        paid_at=f"{PERIOD}-04T10:00:00+00:00",
        vendor_reference="FT26001", tax_reference="RRR99881")

    check("the vendor payment is recorded", bool(out["vendor_disbursement_id"]))
    check("and so is the tax", bool(out["tax_disbursement_id"]))

    items = disb.list_disbursements(ORG, period=PERIOD)
    check("two ledger lines", len(items) == 2)
    vendor = next(d for d in items if "Sahel" in d.payee_name)
    tax = next(d for d in items if "Inland Revenue" in d.payee_name)
    check("vendor gets the net", vendor.amount == 900_000.0)
    check("the authority gets the tax", tax.amount == 100_000.0)
    check("both point at the same approval",
          vendor.source_ref == tax.source_ref == "REQ-0001")
    check("the tax line explains itself", "WHT 10.0%" in tax.memo)
    check("and carries its own bank reference", tax.bank_reference == "RRR99881")


def test_no_tax_line_when_none_applies() -> None:
    print("\nNo phantom remittance when nothing is withheld")
    configure(); clear()
    out = wht.record_split_payment(
        ORG, source_kind="requisition", source_id="r2", source_ref="REQ-0002",
        payee_name="Zenith Stationers", gross=47_500, category="stationery",
        paid_at=f"{PERIOD}-05T10:00:00+00:00", vendor_reference="FT26002")
    check("no tax disbursement", out["tax_disbursement_id"] == "")
    check("one ledger line only", len(disb.list_disbursements(ORG, period=PERIOD)) == 1)
    check("payee got the full amount", out["net_to_payee"] == 47_500)


def test_liability_report() -> None:
    print("\nWhat is owed to the authority, from what was withheld")
    configure(); clear()
    for i, (name, gross, cat) in enumerate([
        ("Sahel Consulting Ltd", 1_000_000, "consultancy"),
        ("Kaduna Venue Services", 400_000, "venue"),
        ("Zenith Stationers", 47_500, "stationery"),
    ], start=1):
        wht.record_split_payment(
            ORG, source_kind="requisition", source_id=f"r{i}",
            source_ref=f"REQ-000{i}", payee_name=name, gross=gross,
            category=cat, paid_at=f"{PERIOD}-0{i}T10:00:00+00:00")

    rep = wht.liability(ORG, PERIOD)
    check("two remittances", rep["remittances"] == 2)
    check("totalling 100,000 + 20,000", rep["total_withheld"] == 120_000.0)
    check("broken down per approval", set(rep["by_source"]) == {"REQ-0001", "REQ-0002"})
    check("naming the account code", rep["account_code"] == "62010")
    check("and the method", rep["method"] == "RRR")


# ─── THE POINT ──────────────────────────────────────────────────────────────


def test_a_withheld_month_reconciles_clean() -> None:
    print("\nTHE BUG THIS FIXES: tax remittances are no longer 'unapproved money'")
    configure(); clear()
    wht.record_split_payment(
        ORG, source_kind="requisition", source_id="r1", source_ref="REQ-0001",
        payee_name="Sahel Consulting Ltd", gross=1_000_000, category="consultancy",
        paid_at=f"{PERIOD}-04T10:00:00+00:00",
        vendor_reference="FT26001", tax_reference="RRR99881")
    wht.record_split_payment(
        ORG, source_kind="requisition", source_id="r2", source_ref="REQ-0002",
        payee_name="Kaduna Venue Services", gross=400_000, category="venue",
        paid_at=f"{PERIOD}-06T10:00:00+00:00",
        vendor_reference="FT26002", tax_reference="RRR99882")

    # The statement as the bank actually reports it: four debits, not two.
    run = br.reconcile(ORG, PERIOD, statement([
        f"{PERIOD}-04,TRF TO SAHEL CONSULTING,FT26001,900000.00,",
        f"{PERIOD}-04,REMITA WHT PAYMENT,RRR99881,100000.00,",
        f"{PERIOD}-06,TRF TO KADUNA VENUE SERVICES,FT26002,380000.00,",
        f"{PERIOD}-06,REMITA WHT PAYMENT,RRR99882,20000.00,",
    ]), actor="finance@org")

    check("all four debits matched", len(run.matches) == 4,
          f"{len(run.matches)} matched")
    check("NOTHING reported as unapproved money",
          not [e for e in run.exceptions
               if e.code == br.ExceptionCode.NOT_IN_SYSTEM],
          str([e.code.value for e in run.exceptions]))
    check("the month reconciles", run.reconciled is True)
    check("and the totals agree",
          run.total_paid_in_system == run.total_debits_in_bank == 1_400_000.0)


def test_a_real_unapproved_debit_is_still_caught() -> None:
    print("\nThe control still works — a genuine one is still found")
    configure(); clear()
    wht.record_split_payment(
        ORG, source_kind="requisition", source_id="r1", source_ref="REQ-0001",
        payee_name="Sahel Consulting Ltd", gross=1_000_000, category="consultancy",
        paid_at=f"{PERIOD}-04T10:00:00+00:00",
        vendor_reference="FT26001", tax_reference="RRR99881")

    run = br.reconcile(ORG, PERIOD, statement([
        f"{PERIOD}-04,TRF TO SAHEL CONSULTING,FT26001,900000.00,",
        f"{PERIOD}-04,REMITA WHT PAYMENT,RRR99881,100000.00,",
        f"{PERIOD}-11,TRF TO BRIGHTPATH SUPPLIES,FT999,750000.00,",
    ]), actor="finance@org")
    check("the legitimate pair matched", len(run.matches) == 2)
    unapproved = [e for e in run.exceptions
                  if e.code == br.ExceptionCode.NOT_IN_SYSTEM]
    check("the unapproved transfer is still caught", len(unapproved) == 1)
    check("at the right amount", unapproved[0].amount == 750_000)


def main() -> int:
    print("=" * 68)
    print("Withholding tax — one approval, two debits, both expected")
    print("=" * 68)
    for fn in (
        test_no_rates_are_shipped,
        test_a_typo_in_a_rate_is_caught,
        test_the_split,
        test_company_and_individual_rates_differ,
        test_an_uncovered_category_withholds_nothing_and_says_so,
        test_the_floor,
        test_rounding_is_to_the_kobo,
        test_both_halves_are_recorded,
        test_no_tax_line_when_none_applies,
        test_liability_report,
        test_a_withheld_month_reconciles_clean,
        test_a_real_unapproved_debit_is_still_caught,
    ):
        fn()
    print("\n" + "=" * 68)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 68)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
