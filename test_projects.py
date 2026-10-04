"""
Projects & grants: budget, used, committed, left — and the check that stops a
request spending money a grant no longer has.

What this prevents:
  * a request approved against a grant that is already spent, discovered
    only when the donor's financial report doesn't balance;
  * a budget line quietly overspent while the grant total still looks fine;
  * a figure on the project page that nobody can trace (the competitor's demo
    showed "6429.8% of budget used");
  * a request counted against its own budget when it is re-checked;
  * declined requests and drafts eating budget they will never spend.

Run: python test_projects.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-projects-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import grants  # noqa: E402
import org_config  # noqa: E402
import projects  # noqa: E402
import requisitions as rq  # noqa: E402

PW = "correct-horse-battery"
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
    "departments": [{"key": "program", "name": "Programmes"}, {"key": "finance", "name": "Finance"}],
    "workflow": {"max_amount": 10_000_000, "steps": [
        {"key": "finance", "label": "Finance review", "department": "finance",
         "can_override": True, "override_limit": 10_000_000}]},
}


def _req(amount, *, project="TB-26", grant=None, line=None, submit=True, currency="NGN"):
    lines = [rq.BudgetLine(description="x", budget_line=line, unit_cost=amount)] if line else None
    return rq.create_requisition("acme", submitted_by="amina@acme.org", department="program",
                                 vendor_name="Kano Supplies", amount=amount, project_code=project,
                                 grant_code=grant, budget_lines=lines, submit=submit, currency=currency)


def _pay(r):
    fails = [c.code for c in rq.get_requisition("acme", r.id).checks if c.result == rq.CheckResult.FAIL]
    rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="femi@acme.org", department="finance",
              overrides=fails or None, override_reason="test set-up" if fails else "",
              override_authority="Finance" if fails else "")
    return rq.mark_paid("acme", r.id, actor="femi@acme.org", bank_reference="FT1")


def _checks(r, code):
    return [c for c in rq.get_requisition("acme", r.id).checks if c.code == code]


def test_figures_add_up_from_the_records() -> None:
    print("\nEvery figure comes from a record you can open")
    ag = grants.create_agreement("acme", donor="Global Fund", project_code="TB-26", value=1_000_000,
                                 budget_lines=[grants.BudgetLine(code="L1", label="Outreach", amount=600_000),
                                               grants.BudgetLine(code="L2", label="Supplies", amount=400_000)])
    _pay(_req(200_000, line="L1"))
    _req(300_000)                                   # in review, no line
    _req(50_000, submit=False)                      # a draft
    declined = _req(70_000)
    rq.decide("acme", declined.id, decision=rq.Decision.DECLINED, actor="femi@acme.org",
              department="finance", notes="not needed")
    import payroll
    store.get_store().put("acme", payroll._RUNS, "run1", payroll.PayrollRun(
        id="run1", period="2026-09", status="paid", by_project={"TB-26": 100_000}).model_dump())
    store.get_store().put("acme", payroll._RUNS, "run2", payroll.PayrollRun(
        id="run2", period="2026-10", status="submitted", by_project={"tb-26": 25_000}).model_dump())

    f = projects.figures("acme", ag)
    check("paid is the frozen payment", f.paid == 200_000, str(f.paid))
    check("salary is the paid payroll run's share", f.salary == 100_000, str(f.salary))
    check("committed is the open request plus the unpaid payroll run (not the draft or the declined one)",
          f.committed == 325_000, str(f.committed))
    check("remaining = budget − paid − salary − committed", f.remaining == 375_000, str(f.remaining))
    check("used % counts only money actually out", f.used_percent == 30.0, str(f.used_percent))
    lines = {lf.code: lf for lf in f.lines}
    check("the itemised payment lands on its budget line", lines["L1"].paid == 200_000 and lines["L1"].remaining == 400_000,
          str(lines["L1"]))
    check("the unitemised request is shown as not assigned, not guessed into a line",
          lines[projects.UNASSIGNED].committed == 300_000, str(lines.get(projects.UNASSIGNED)))


def test_the_grant_code_wins() -> None:
    print("\nA request names its grant more precisely than its project")
    grants.create_agreement("acme", donor="FCDO", project_code="MNH", value=500_000)
    r = _req(10_000, project="TB-26", grant="MNH")
    f_tb = projects.figures("acme", grants.find_agreement("acme", "TB-26"))
    f_mnh = projects.figures("acme", grants.find_agreement("acme", "MNH"))
    check("charged to the grant it names", f_mnh.committed == 10_000, str(f_mnh.committed))
    check("…not to the project code beside it", f_tb.committed == 325_000, str(f_tb.committed))
    rq.decide("acme", r.id, decision=rq.Decision.DECLINED, actor="femi@acme.org", department="finance", notes="x")


def test_a_request_cannot_spend_what_isnt_there() -> None:
    print("\nThe funds check")
    big = _req(400_000)
    fail = _checks(big, "FUNDS_AVAILABLE")
    check("₦400,000 against ₦375,000 left fails", fail and fail[0].result == rq.CheckResult.FAIL,
          str([(c.result, c.message) for c in fail]))
    check("…and says exactly what's left and why", fail and "375,000.00" in fail[0].message
          and "salaries" in fail[0].message, fail[0].message if fail else "")
    rq.decide("acme", big.id, decision=rq.Decision.DECLINED, actor="femi@acme.org", department="finance",
              notes="over budget")   # once declined, it stops counting as committed
    small = _req(100_000)
    ok = _checks(small, "FUNDS_AVAILABLE")
    check("a request that fits passes", ok and ok[0].result == rq.CheckResult.PASS, str(ok))
    again = projects.funds_checks("acme", rq.get_requisition("acme", small.id))
    check("re-checking a request doesn't count it against itself",
          again[0].result == rq.CheckResult.PASS, again[0].message)
    line = _req(450_000, line="L1")
    lf = _checks(line, "BUDGET_LINE_AVAILABLE")
    check("a budget line is checked on its own (L1 has ₦400,000 left)",
          lf and lf[0].result == rq.CheckResult.FAIL, str([c.message for c in lf]))
    for r in (small, line):
        rq.decide("acme", r.id, decision=rq.Decision.DECLINED, actor="femi@acme.org", department="finance", notes="x")


def test_an_authority_can_release_it_with_a_reason() -> None:
    print("\nA FAIL, not a wall: budget realignments happen")
    r = _req(390_000)
    check("it fails", _checks(r, "FUNDS_AVAILABLE")[0].result == rq.CheckResult.FAIL)
    rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="femi@acme.org", department="finance",
              overrides=["FUNDS_AVAILABLE"], override_authority="Finance Manager",
              override_reason="Donor approved realignment from L2, letter of 2 Oct")
    after = _checks(r, "FUNDS_AVAILABLE")[0]
    check("Finance releases it with a written reason", after.overridden and "realignment" in (after.override_reason or ""),
          str(after))
    t = rq.mark_paid("acme", r.id, actor="femi@acme.org", bank_reference="FT9")
    ex = projects.exceptions("acme", grants.find_agreement("acme", "TB-26"))
    check("…and it shows on the project's exceptions with the reason", any(
        e["requisition_ref"] == t.requisition_ref and "realignment" in e["reason"] for e in ex), str(ex))


def test_switched_off_and_edge_cases() -> None:
    print("\nNo budget, other currency, or the feature off: no check")
    grants.create_agreement("acme", donor="Unbudgeted", project_code="NOVAL")
    check("a project with no budget isn't checked", _checks(_req(5, project="NOVAL"), "FUNDS_AVAILABLE") == [])
    check("a dollar request isn't measured against a naira budget",
          _checks(_req(5, currency="USD"), "FUNDS_AVAILABLE") == [])
    org_config.set_features("acme", projects=False)
    check("feature off: nothing checked", _checks(_req(9_999_999), "FUNDS_AVAILABLE") == [])
    org_config.set_features("acme", projects=True)


def test_project_details_are_validated() -> None:
    print("\nThe mistakes that would make every figure wrong are refused")
    def refused(**kw):
        try:
            grants.create_agreement("acme", **kw)
            return False
        except grants.AgreementError:
            return True
    check("budget lines adding up to more than the budget", refused(
        donor="X", project_code="P1", value=100,
        budget_lines=[grants.BudgetLine(code="A", amount=80), grants.BudgetLine(code="B", amount=30)]))
    check("two lines with the same code", refused(
        donor="X", project_code="P2", value=100,
        budget_lines=[grants.BudgetLine(code="A", amount=10), grants.BudgetLine(code="a", amount=10)]))
    check("a second project with an existing code", refused(donor="X", project_code="tb-26", value=1))
    check("an end date before the start", refused(donor="X", project_code="P3", start_date="2026-05-01",
                                                  end_date="2026-01-01"))
    check("effort over 100%", refused(donor="X", project_code="P4",
                                      staff=[grants.PlannedStaff(name="Amina", percent=120)]))


def test_the_api(c, h) -> None:
    print("\nThe project page's API: who sees and who changes")
    r = c.get("/projects", headers=h("amina@acme.org"))
    check("a Programmes officer (viewer) can't see grant finances", r.status_code == 403, str(r.status_code))
    r = c.get("/projects/lookup/tb-26", headers=h("amina@acme.org"))
    check("…but can look a code up to pick a budget line", r.status_code == 200 and r.json().get("found")
          and [bl["code"] for bl in r.json()["budget_lines"]] == ["L1", "L2"], r.text[:160])
    check("…and the lookup carries no money", "amount" not in r.text and "value" not in r.json(), r.text[:160])
    r = c.get("/projects", headers=h("pm@acme.org"))
    check("an approver can", r.status_code == 200 and any(p["project_code"] == "TB-26" for p in r.json()["projects"]),
          f"{r.status_code} {r.text[:120]}")
    r = c.get("/projects/TB-26", headers=h("pm@acme.org"))
    body = r.json() if r.status_code == 200 else {}
    check("one project: figures, lines, payments, exceptions together",
          all(k in body for k in ("figures", "agreement", "payments", "exceptions", "approved_time")),
          f"{r.status_code} {list(body)}")
    new = {"donor": "UNICEF", "project_code": "WASH-27", "value": 2_000_000,
           "budget_lines": [{"code": "W1", "label": "Boreholes", "amount": 2_000_000}]}
    r = c.post("/projects", headers=h("pm@acme.org"), json=new)
    check("only Finance approvers and admins create projects", r.status_code == 403, str(r.status_code))
    r = c.post("/projects", headers=h("femi@acme.org"), json=new)
    check("a Finance approver creates one", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    r = c.put("/projects/WASH-27", headers=h("femi@acme.org"), json={"value": 1})
    check("an impossible edit is refused in plain words", r.status_code == 422 and "more than" in r.text,
          f"{r.status_code} {r.text[:160]}")


if __name__ == "__main__":
    print("Projects & grants")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    org_config.set_features("acme", projects=True)
    for email, name, dept, role in [("amina@acme.org", "Amina", "program", "viewer"),
                                    ("pm@acme.org", "PM", "program", "approver"),
                                    ("femi@acme.org", "Femi", "finance", "approver")]:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    test_figures_add_up_from_the_records()
    test_the_grant_code_wins()
    test_a_request_cannot_spend_what_isnt_there()
    test_an_authority_can_release_it_with_a_reason()
    test_switched_off_and_edge_cases()
    test_project_details_are_validated()
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)

    def h(email):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}
    test_the_api(c, h)
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
