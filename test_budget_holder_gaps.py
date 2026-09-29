"""
Two gaps in the budget-holder step, found building the demo organisation
(29 Sep 2026). Both would hit every organisation that uses "the requester's
own manager approves first", which is the common NGO flow.

1. The manager raises a request themselves. The first step belongs to their
   own department and nobody may approve their own request, so it sat there
   with no one able to move it. In practice the manager raising it IS the
   budget holder's confirmation: it should go straight on to Finance, and
   the trail should say why. (If the budget-holder step is the ONLY step, it
   must not be skipped: that would be a self-approved payment.)

2. A request fails a check the manager cannot release (missing quotes, a
   closed grant). The only way on was "Pass to Finance", which recorded no
   decision from the manager, so the voucher and the audit showed nobody had
   confirmed the need. The manager should be able to approve the need while
   the failing check travels on to the step that holds the authority to
   release it. The last step can never approve over an open failure.

Run: python test_budget_holder_gaps.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-bhgaps-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


PROFILE = {
    "org_id": "acme", "currency": "NGN",
    "departments": [{"key": "program", "name": "Programmes"}, {"key": "finance", "name": "Finance"},
                    {"key": "ed", "name": "Executive Director", "is_final_authority": True}],
    "workflow": {"max_amount": 50_000_000, "required_documents": ["memo", "invoice"], "steps": [
        {"key": "budget", "label": "Budget holder approval", "requester_department": True},
        {"key": "finance", "label": "Finance review", "department": "finance",
         "can_override": True, "override_limit": 250_000},
        {"key": "ed", "label": "ED approval", "department": "ed", "min_amount": 1_000_000},
    ]},
}


def _raise(who: str, dept: str, amount: float, docs=("memo", "invoice")) -> rq.Requisition:
    return rq.create_requisition("acme", submitted_by=who, department=dept, vendor_name="Kano Printers",
                                 amount=amount, documents=list(docs))


def test_manager_raises_their_own_request() -> None:
    print("\nThe Programme Manager raises a request: it goes straight to Finance")
    r = _raise("pm@acme.org", "program", 80_000)
    check("with Finance, not stuck with the manager", r.current_step == "finance", str(r.current_step))
    line = next((e for e in r.audit_log if e.event == "budget_holder_raised"), None)
    check("the trail says why the first step was passed", line is not None
          and "budget holder" in line.detail.lower(), str([e.event for e in r.audit_log]))
    r = _raise("amina@acme.org", "program", 80_000)
    check("an officer's request still goes to the manager first", r.current_step == "budget", str(r.current_step))


def test_never_skipped_when_it_is_the_only_approval() -> None:
    print("\nIf the budget holder is the only approver, their own request is not waved through")
    solo = copy.deepcopy(PROFILE)
    solo["org_id"] = "solo"
    solo["workflow"]["steps"] = [solo["workflow"]["steps"][0]]
    org_config.apply_profile(solo)
    A.create_user("boss@solo.org", "Boss", "correct-horse-battery", "program", "approver", org_id="solo")
    r = rq.create_requisition("solo", submitted_by="boss@solo.org", department="program",
                              vendor_name="X", amount=10_000, documents=["memo", "invoice"])
    check("not approved automatically", r.status != rq.ReqStatus.APPROVED, r.status.value)


def test_manager_confirms_the_need_and_finance_decides_the_exception() -> None:
    print("\nMissing invoice: the manager confirms the need, Finance decides the exception")
    r = _raise("amina@acme.org", "program", 120_000, docs=("memo",))
    check("blocked", bool(rq.blocking_checks(r)))
    r = rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="pm@acme.org", department="program",
                  notes="Needed for the Kano training")
    check("manager's approval recorded", any(a.step == "budget" and a.actor == "pm@acme.org"
                                             and a.decision == rq.Decision.APPROVED for a in r.approvals))
    check("now with Finance", r.current_step == "finance", str(r.current_step))
    check("the failing check is still open", bool(rq.blocking_checks(r)))
    check("the trail says who must decide it",
          any(e.event == "passed_with_open_checks" and "Finance" in e.detail for e in r.audit_log),
          str([(e.event, e.detail) for e in r.audit_log][-3:]))
    try:
        rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="femi@acme.org", department="finance")
        check("Finance cannot just approve over it (it's the last step at this amount)", False)
    except rq.RequisitionError:
        check("Finance cannot just approve over it (it's the last step at this amount)", True)
    r = rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="femi@acme.org", department="finance",
                  overrides=["DOCS_COMPLETE"], override_reason="Invoice copy on file, original lost in transit")
    check("Finance releases it with a reason, and it is approved", r.status == rq.ReqStatus.APPROVED, r.status.value)


def test_no_one_later_can_release_it() -> None:
    print("\nAbove every override limit: the manager can't send it on, it must be returned")
    r = _raise("amina@acme.org", "program", 600_000, docs=("memo",))   # finance limit 250k; ED can't override
    try:
        rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="pm@acme.org", department="program")
        check("refused", False, "approved a request nobody can release")
    except rq.RequisitionError as exc:
        check("refused, and says to return it", "return" in str(exc).lower(), str(exc))


if __name__ == "__main__":
    print("Budget-holder step: the manager's own requests, and checks only Finance can release")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    for email, name, dept, role in [("amina@acme.org", "Amina", "program", "reviewer"),
                                    ("pm@acme.org", "Programme Manager", "program", "approver"),
                                    ("femi@acme.org", "Femi", "finance", "approver")]:
        A.create_user(email, name, "correct-horse-battery", dept, role, org_id="acme")
    test_manager_raises_their_own_request()
    test_never_skipped_when_it_is_the_only_approval()
    test_manager_confirms_the_need_and_finance_decides_the_exception()
    test_no_one_later_can_release_it()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
