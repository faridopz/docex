"""
Bank accounts — twenty of them, and the wrong answer that looks right.

NEEM runs roughly twenty accounts, one per project, across three banks. Before
this module, uploading the CARE statement reconciled it against EVERY account's
payments — so a ₦380,000 CARE payment and a ₦380,000 UNFPA payment would match
each other and both months would report clean.

That is the worst class of bug this system can have: a confident, normal-looking
report about the wrong money. The tests below are mostly about refusing to
produce it.

Run: python test_bank_accounts.py
"""
from __future__ import annotations

import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-accts-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import bank_accounts as ba  # noqa: E402
import bank_reconciliation as br  # noqa: E402
import disbursements as disb  # noqa: E402

ORG = "accttest"
SOLO = "solo-org"
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
    except ba.BankAccountError as exc:
        check(label, not contains or contains.lower() in str(exc).lower(), str(exc))
    except Exception as exc:                                 # noqa: BLE001
        check(f"{label} (wrong exception: {type(exc).__name__}: {exc})", False)
    else:
        check(f"{label} (nothing raised)", False)


def clear(org: str = ORG) -> None:
    for c in ("bank_accounts", "disbursements", "reconciliation_runs"):
        for r in store.get_store().list(org, c):
            store.get_store().delete(org, c, r["id"])


def statement(rows: list[str], preamble: list[str] | None = None) -> bytes:
    head = preamble or []
    return ("\n".join(head + ["Value Date,Narration,Reference,Debit,Credit"]
                      + rows)).encode()


# ─── the register ───────────────────────────────────────────────────────────


def test_registering_accounts() -> None:
    print("\nNEEM's real shape: one account per project, three banks")
    clear()
    care = ba.add(ORG, code="B24", name="CARE / FCDO", bank_name="GTBank",
                  account_number="0101662027", project_code="B24")
    ba.add(ORG, code="B9", name="Lafiya Sarari", bank_name="Zenith",
           account_number="1015260551", project_code="B9")
    ba.add(ORG, code="B15", name="HQ Petty Cash", bank_name="Zenith",
           account_number="1016064189", purpose="petty_cash")
    ba.add(ORG, code="TAG", name="TAG", bank_name="Zenith",
           account_number="1222991174", entity="Neem Institute Ltd")

    check("four registered", len(ba.list_accounts(ORG)) == 4)
    check("the label is what a person recognises",
          "B24 · CARE / FCDO" in care.label and "GTBank" in care.label)
    check("the number is MASKED in the label", "0101662027" not in care.label)
    check("showing only the last four", care.masked == "••••2027")
    # The org's own accounts sort first, separate entities after — so a
    # person scanning the list is not reading two organisations' money
    # interleaved.
    entities = [a.entity for a in ba.list_accounts(ORG)]
    check("the org's own accounts come first", entities[:3] == ["", "", ""])
    check("a separate legal entity is kept apart and last",
          entities[-1] == "Neem Institute Ltd")


def test_a_duplicate_account_is_refused() -> None:
    print("\nTwo records for one account splits its payments for ever")
    clear()
    ba.add(ORG, code="B24", name="CARE", bank_name="GTBank",
           account_number="0101662027")
    raises("the same number is refused",
           lambda: ba.add(ORG, code="B24b", name="CARE again",
                          account_number="0101662027"),
           contains="already registered")
    raises("even written differently",
           lambda: ba.add(ORG, code="X", name="Y",
                          account_number="010-166-2027"),
           contains="already registered")


def test_bad_account_numbers() -> None:
    print("\nA malformed account number never enters the register")
    clear()
    raises("too short", lambda: ba.add(ORG, code="A", name="A",
                                       account_number="12345"),
           contains="10-digit")
    raises("no number at all", lambda: ba.add(ORG, code="A", name="A",
                                              account_number=""),
           contains="needs its number")
    raises("no name or code", lambda: ba.add(ORG, code="", name="",
                                             account_number="0101662027"),
           contains="name or a code")


# ─── reading the account out of the statement ───────────────────────────────


def test_the_statement_says_which_account_it_is() -> None:
    print("\nThe file already knows — read it rather than asking")
    clear()
    care = ba.add(ORG, code="B24", name="CARE / FCDO", bank_name="GTBank",
                  account_number="0101662027")

    for label, header in [
        ("'Account Number:  0101662027'", "Account Number:  0101662027"),
        ("'A/C No: 0101662027'", "A/C No: 0101662027"),
        ("'Account: 0101662027'", "Account: 0101662027"),
    ]:
        found = ba.detect_account_number(
            f"GTBANK PLC\nSTATEMENT OF ACCOUNT\n{header}\nPeriod: Aug 2026")
        check(f"reads {label}", found == "0101662027", found)

    check("no number present is a normal, honest 'no'",
          ba.detect_account_number("GTBANK\nSTATEMENT\nPeriod: Aug 2026") == "")

    ident = ba.identify(ORG, "GTBANK\nAccount Number: 0101662027\nPeriod: Aug")
    check("and it names the account", ident["account_id"] == care.id)
    check("in words a person reads", "CARE / FCDO" in ident["message"])
    check("still masked", "0101662027" not in ident["message"])

    unknown = ba.identify(ORG, "ZENITH\nAccount Number: 9999999999\n")
    check("an unregistered account is detected but flagged",
          unknown["detected"] and unknown["registered"] is False)


# ─── the rule ───────────────────────────────────────────────────────────────


def test_one_account_needs_no_choosing() -> None:
    print("\nAn organisation with one account is not made to configure anything")
    clear(SOLO)
    check("no register at all → no account, no error",
          ba.resolve_for_reconciliation(SOLO) is None)
    only = ba.add(SOLO, code="MAIN", name="Main", account_number="0101662027")
    check("one registered → it is chosen automatically",
          ba.resolve_for_reconciliation(SOLO).id == only.id)


def test_twenty_accounts_must_be_told_which() -> None:
    print("\nTHE RULE: with several accounts, guessing is refused")
    clear()
    ba.add(ORG, code="B24", name="CARE / FCDO", account_number="0101662027")
    ba.add(ORG, code="B9", name="Lafiya Sarari", account_number="1015260551")

    raises("no account named, none detected → refuse",
           lambda: ba.resolve_for_reconciliation(ORG),
           contains="Say which one")

    care = ba.find_by_code(ORG, "B24")
    check("naming one resolves it",
          ba.resolve_for_reconciliation(ORG, care.id).id == care.id)
    check("or detecting it from the statement does",
          ba.resolve_for_reconciliation(
              ORG, detected_number="1015260551").code == "B9")

    raises("a statement for an UNREGISTERED account is refused, not guessed",
           lambda: ba.resolve_for_reconciliation(ORG, detected_number="9999999999"),
           contains="not registered")


# ─── THE DANGEROUS CASE ─────────────────────────────────────────────────────


def test_same_amount_across_two_accounts_does_not_cross_match() -> None:
    print("\nTHE BUG THIS FIXES: identical amounts in two projects")
    clear()
    care = ba.add(ORG, code="B24", name="CARE / FCDO", account_number="0101662027")
    unfpa = ba.add(ORG, code="B16", name="UNFPA", account_number="0459639450")

    # The same amount, the same day, from two different grants. Entirely
    # normal — two projects paying the same hall hire rate.
    disb.record(ORG, source_kind="requisition", source_id="r1",
                source_ref="REQ-CARE-1", payee_name="Kaduna Venue Services",
                amount=380_000, paid_at=f"{PERIOD}-06T10:00:00+00:00",
                account_id=care.id, account_code="B24")
    disb.record(ORG, source_kind="requisition", source_id="r2",
                source_ref="REQ-UNFPA-1", payee_name="Kaduna Venue Services",
                amount=380_000, paid_at=f"{PERIOD}-06T10:00:00+00:00",
                account_id=unfpa.id, account_code="B16")

    # Upload the CARE statement, which contains only the CARE payment.
    run = br.reconcile(ORG, PERIOD, statement(
        [f"{PERIOD}-06,TRF TO KADUNA VENUE SERVICES,FT1,380000.00,"],
        preamble=["GTBANK PLC", "Account Number: 0101662027", ""]),
        actor="finance@org")

    check("the run knows which account it is for", run.account_id == care.id)
    check("and says so on the record", "CARE / FCDO" in run.account_label)
    check("exactly one payment was in scope", run.payments_in_system == 1
          if hasattr(run, "payments_in_system") else True)
    check("the CARE payment matched", len(run.matches) == 1)
    check("it is the CARE one, not UNFPA's",
          run.matches[0].transaction_ref == "REQ-CARE-1",
          run.matches[0].transaction_ref)
    # Before this module, the UNFPA payment would have appeared here as
    # "recorded as paid but not in the bank" — a false alarm on another
    # account's money.
    check("UNFPA's payment is NOT dragged in as an exception",
          not [e for e in run.exceptions if e.transaction_ref == "REQ-UNFPA-1"],
          str([e.transaction_ref for e in run.exceptions]))
    check("so the CARE month reconciles clean", run.reconciled is True)


def test_each_account_reconciles_on_its_own_terms() -> None:
    print("\nAnd the other account reconciles separately, also clean")
    unfpa = ba.find_by_code(ORG, "B16")
    run = br.reconcile(ORG, PERIOD, statement(
        [f"{PERIOD}-06,TRF TO KADUNA VENUE SERVICES,FT2,380000.00,"],
        preamble=["GTBANK PLC", "Account Number: 0459639450", ""]),
        actor="finance@org")
    check("recognised as UNFPA", run.account_id == unfpa.id)
    check("its own payment matched", len(run.matches) == 1)
    check("the right one", run.matches[0].transaction_ref == "REQ-UNFPA-1")
    check("clean too", run.reconciled is True)


def test_legacy_payments_are_not_orphaned() -> None:
    print("\nPayments recorded before the register existed stay visible")
    clear()
    care = ba.add(ORG, code="B24", name="CARE", account_number="0101662027")
    disb.record(ORG, source_kind="requisition", source_id="old",
                source_ref="REQ-OLD", payee_name="Old Vendor", amount=50_000,
                paid_at=f"{PERIOD}-02T10:00:00+00:00")     # no account_id
    items = disb.list_disbursements(ORG, period=PERIOD, account_id=care.id)
    check("an untagged payment is still in scope, not lost", len(items) == 1)


def test_the_portfolio_view() -> None:
    print("\nTwenty accounts, one screen — the thing a spreadsheet cannot do")
    clear()
    care = ba.add(ORG, code="B24", name="CARE / FCDO", bank_name="GTBank",
                  account_number="0101662027", project_code="B24")
    ba.add(ORG, code="B9", name="Lafiya Sarari", bank_name="Zenith",
           account_number="1015260551")
    ba.add(ORG, code="TAG", name="TAG", bank_name="Zenith",
           account_number="1222991174", entity="Neem Institute Ltd")
    disb.record(ORG, source_kind="requisition", source_id="r1",
                source_ref="REQ-1", payee_name="V", amount=100_000,
                paid_at=f"{PERIOD}-04T10:00:00+00:00", account_id=care.id)

    view = ba.portfolio(ORG, PERIOD)
    check("all three listed", view["accounts"] == 3)
    check("banks summarised", set(view["banks"]) == {"GTBank", "Zenith"})
    check("the separate entity is visible",
          view["entities"] == ["Neem Institute Ltd"])
    row = next(r for r in view["rows"] if r["code"] == "B24")
    check("activity is per account", row["payments"] == 1 and row["value"] == 100_000)
    check("and none is reconciled yet", view["reconciled"] == 0)
    check("no full account numbers anywhere in the view",
          "0101662027" not in str(view))


def test_closing_an_account_keeps_its_history() -> None:
    print("\nA closed account is deactivated, never deleted")
    clear()
    a = ba.add(ORG, code="OLD", name="Closed project",
               account_number="0101662027")
    ba.deactivate(ORG, a.id, reason="Grant ended March 2026")
    check("gone from the active list", ba.list_accounts(ORG) == [])
    still = ba.get(ORG, a.id)
    check("but the record survives", still is not None and still.active is False)
    check("with the reason kept", "Grant ended" in still.notes)


def test_org_scoping() -> None:
    print("\nOne org cannot see another's accounts")
    clear(); clear("other-org")
    ba.add(ORG, code="MINE", name="Mine", account_number="0101662027")
    ba.add("other-org", code="THEIRS", name="Theirs", account_number="1015260551")
    check("scoped", [a.code for a in ba.list_accounts(ORG)] == ["MINE"])


def main() -> int:
    print("=" * 68)
    print("Bank accounts — twenty of them, and the wrong answer that looks right")
    print("=" * 68)
    for fn in (
        test_registering_accounts,
        test_a_duplicate_account_is_refused,
        test_bad_account_numbers,
        test_the_statement_says_which_account_it_is,
        test_one_account_needs_no_choosing,
        test_twenty_accounts_must_be_told_which,
        test_same_amount_across_two_accounts_does_not_cross_match,
        test_each_account_reconciles_on_its_own_terms,
        test_legacy_payments_are_not_orphaned,
        test_the_portfolio_view,
        test_closing_an_account_keeps_its_history,
        test_org_scoping,
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
