"""
WO-47 — reconciliation that is right when an organisation has many bank
accounts, and when a batch leaves the bank as one debit.

Found by running it, not by reading it:
  * payments never recorded which account they left from, so every
    account's reconciliation pulled in every project's payments. A CARE
    statement with one NGN 380,000 debit was compared against CARE's AND
    UNFPA's NGN 380,000 payments, matched nothing, and reported money leaving
    with no approval — the most serious finding the system has, fired at a
    correct payment;
  * a 40-person payment the bank showed as ONE debit produced 0 matches
    and 40 exceptions;
  * the route never passed the chosen account, and "say which account"
    escaped as a 500.

Organisations with one account, or none registered, must see no change.

Run: python test_reconciliation_accounts.py
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile
from collections import Counter
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-recon-acct-")
os.environ["DOCEX_ORG"] = "multi"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import bank_accounts as ba  # noqa: E402
import bank_reconciliation as br  # noqa: E402
import disbursements  # noqa: E402
import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

_passed = _failed = 0
TODAY = dt.date.today()
PERIOD = TODAY.strftime("%Y-%m")
D = TODAY.strftime("%d/%m/%Y")


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def _approved(org, amount, project="", payees=None, vendor="Vendor"):
    r = rq.create_requisition(org, submitted_by="raiser@t", department="program",
                              vendor_name=vendor, amount=amount, project_code=project,
                              payees=payees)
    raw = store.get_store().get(org, "requisitions", r.id)
    raw["status"] = "approved"
    store.get_store().put(org, "requisitions", r.id, raw)
    return r


def _statement(*debits: float) -> bytes:
    rows = "".join(f"{D},TRANSFER,{d:.2f},,1000000\n" for d in debits)
    return f"Date,Narration,Debit,Credit,Balance\n{rows}".encode()


def _codes(run) -> dict:
    return dict(Counter(e.code.value for e in run.exceptions))


def _setup() -> tuple:
    for org in ("multi", "single", "bulkorg", "none"):
        org_config.set_features(org, multi_payee_requisitions=True, bank_reconciliation=True)
    care = ba.add("multi", code="B24", name="CARE / FCDO", account_number="0011223344",
                  bank_name="GTBank", project_code="B24")
    unfpa = ba.add("multi", code="B7", name="UNFPA", account_number="0099887766",
                   bank_name="Zenith", project_code="B7")
    ba.add("multi", code="HQ", name="HQ running", account_number="0055555555",
           bank_name="Access", project_code="")
    ba.add("single", code="MAIN", name="Main account", account_number="0123456789",
           bank_name="GTBank")
    ba.add("bulkorg", code="MAIN", name="Main account", account_number="0123450000",
           bank_name="GTBank")
    return care, unfpa


def test_a_payment_knows_which_account_it_left_from(care, unfpa) -> None:
    print("\nThe account is taken from the project code — no extra step")
    t1 = rq.mark_paid("multi", _approved("multi", 380000, "B24").id, actor="fin@t")
    t2 = rq.mark_paid("multi", _approved("multi", 380000, "B7").id, actor="fin@t")
    check("CARE project ⇒ CARE account", t1.paid_from_account_id == care.id, t1.paid_from_account_id)
    check("UNFPA project ⇒ UNFPA account", t2.paid_from_account_id == unfpa.id, t2.paid_from_account_id)
    check("the audit line names the account",
          any("CARE" in e.detail for e in rq.get_requisition("multi", t1.requisition_id).audit_log
              if e.event == "paid"))


def test_one_accounts_statement_only_sees_its_own_payments(care, unfpa) -> None:
    print("\nA CARE statement is reconciled against CARE's payments only")
    run = br.reconcile("multi", PERIOD, _statement(380000), filename="care.csv",
                       account_id=care.id, actor="fin@t")
    check("the CARE payment matches its CARE debit", len(run.matches) == 1, f"{len(run.matches)} matches")
    check("the UNFPA payment is not dragged in", abs(run.total_paid_in_system - 380000) < 0.01,
          str(run.total_paid_in_system))
    check("no false 'money left with no approval'", "NOT_IN_SYSTEM" not in _codes(run), str(_codes(run)))


def test_an_unclear_account_is_asked_for_not_guessed(care, unfpa) -> None:
    print("\nNo project code and several accounts: Finance is asked, never guessed for")
    r = _approved("multi", 5000, "")
    try:
        rq.mark_paid("multi", r.id, actor="fin@t")
        check("refused", False, "paid without knowing the account")
    except rq.RequisitionError as exc:
        check("refused, and says to choose the account", "account" in str(exc).lower(), str(exc))
    hq = ba.find_by_code("multi", "HQ")
    t = rq.mark_paid("multi", r.id, actor="fin@t", account_id=hq.id)
    check("naming the account works", t.paid_from_account_id == hq.id)


def test_a_single_account_org_never_sees_the_question() -> None:
    print("\nOne account: nothing to choose")
    t = rq.mark_paid("single", _approved("single", 7000).id, actor="fin@t")
    only = ba.list_accounts("single")[0]
    check("paid from the only account, automatically", t.paid_from_account_id == only.id)


def test_an_org_with_no_register_is_unchanged() -> None:
    print("\nNo accounts registered: behaves exactly as before")
    t = rq.mark_paid("none", _approved("none", 9000).id, actor="fin@t")
    check("paid, with no account attached", t.paid_from_account_id == "")


def test_a_bulk_transfer_matches_as_one_debit() -> None:
    print("\nForty people paid as one bank debit reconcile as one line")
    payees = [rq.Payee(name=f"P{i}", account_number=f"01234{i:05d}", bank_name="GTBank",
                       amount=15000.0) for i in range(40)]
    r = _approved("bulkorg", 600000, payees=payees, vendor="Workshop")
    t = rq.mark_paid("bulkorg", r.id, actor="fin@t", settlement="bulk", bank_reference="BULK-0925")
    check("recorded as a bulk settlement", t.settlement == "bulk")
    disb = [d for d in disbursements.list_disbursements("bulkorg") if d.source_id == r.id]
    check("one disbursement of the batch total", len(disb) == 1 and abs(disb[0].amount - 600000) < 0.01,
          f"{len(disb)} × {[d.amount for d in disb][:3]}")
    run = br.reconcile("bulkorg", PERIOD, _statement(600000), filename="s.csv", actor="fin@t")
    check("one match", len(run.matches) == 1, f"{len(run.matches)}")
    check("no exceptions", not run.exceptions, str(_codes(run)))


def test_individual_transfers_still_match_one_by_one() -> None:
    print("\nThe same batch paid person by person matches person by person")
    payees = [rq.Payee(name=f"Q{i}", account_number=f"02234{i:05d}", bank_name="GTBank",
                       amount=1000.0 + i) for i in range(3)]
    r = _approved("single", 3003, payees=payees, vendor="Small batch")
    rq.mark_paid("single", r.id, actor="fin@t")
    disb = [d for d in disbursements.list_disbursements("single") if d.source_id == r.id]
    check("one disbursement per payee (default)", len(disb) == 3, str(len(disb)))


def test_a_bad_settlement_value_is_refused() -> None:
    print("\nSettlement is 'individual' or 'bulk', nothing else")
    r = _approved("single", 10)
    try:
        rq.mark_paid("single", r.id, actor="fin@t", settlement="sometimes")
        check("refused", False)
    except rq.RequisitionError:
        check("refused", True)


def test_the_route_passes_the_account_and_asks_plainly(care, unfpa) -> None:
    print("\nHTTP: account chosen on screen reaches the engine; ambiguity is a 400, not a 500")
    from fastapi.testclient import TestClient
    import api.main as m

    c = TestClient(m.app, raise_server_exceptions=False)
    PW = "correct-horse-battery"
    A.create_user("fin@t", "Finance", PW, "finance", "approver", org_id="multi")
    tok = c.post("/auth/login", json={"email": "fin@t", "password": PW}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    r = c.post("/reconciliation", headers=H, data={"period": PERIOD},
               files={"statement": ("s.csv", _statement(380000), "text/csv")})
    check("several accounts, none named ⇒ 400 with the question",
          r.status_code == 400 and "which one" in r.text.lower(), f"{r.status_code} {r.text[:160]}")
    r = c.post("/reconciliation", headers=H, data={"period": PERIOD, "account_id": unfpa.id},
               files={"statement": ("s.csv", _statement(380000), "text/csv")})
    check("naming UNFPA reconciles UNFPA", r.status_code == 200 and r.json().get("account_id") == unfpa.id,
          f"{r.status_code} {r.text[:160]}")

    r2 = _approved("multi", 2500, "B24", vendor="Paid via API")
    ok = c.post(f"/requisitions/{r2.id}/pay", headers=H,
                data={"bank_reference": "FT1", "settlement": "individual"})
    check("pay route records the account from the project", ok.status_code == 200,
          f"{ok.status_code} {ok.text[:160]}")
    txn = rq.get_transaction("multi", rq.get_requisition("multi", r2.id).transaction_id)
    check("…and it is CARE", txn.paid_from_account_id == care.id, txn.paid_from_account_id)


if __name__ == "__main__":
    print("WO-47 — reconciliation across accounts and bulk transfers")
    care, unfpa = _setup()
    test_a_payment_knows_which_account_it_left_from(care, unfpa)
    test_one_accounts_statement_only_sees_its_own_payments(care, unfpa)
    test_an_unclear_account_is_asked_for_not_guessed(care, unfpa)
    test_a_single_account_org_never_sees_the_question()
    test_an_org_with_no_register_is_unchanged()
    test_a_bulk_transfer_matches_as_one_debit()
    test_individual_transfers_still_match_one_by_one()
    test_a_bad_settlement_value_is_refused()
    test_the_route_passes_the_account_and_asks_plainly(care, unfpa)
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
