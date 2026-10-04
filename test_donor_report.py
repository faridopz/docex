"""
The donor report: one click, one project, one period.

What this prevents:
  * a report that leaves out a payment, or includes one from another period;
  * an exception reported without the reason someone gave for releasing it;
  * unapproved hours presented to a donor as evidence;
  * a salary charged on a budgeted split passed off as recorded effort;
  * a bank account number printed into a document that leaves the building;
  * a report that someone outside Finance and the approvers can download.

Reads the PDF's text back with pdftotext, so it checks what a donor sees.
Run: python test_donor_report.py
"""
from __future__ import annotations

import copy
import os
import subprocess
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-donor-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import grants  # noqa: E402
import org_config  # noqa: E402
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


def _paid(amount, vendor, *, when, line=None, override=False, account="0123456789"):
    rq._now_iso = lambda: f"{when}T10:00:00+00:00"
    lines = [rq.BudgetLine(description="x", budget_line=line, unit_cost=amount)] if line else None
    r = rq.create_requisition("acme", submitted_by="amina@acme.org", department="program",
                              vendor_name=vendor, vendor_account=account, amount=amount,
                              grant_code="TB-26", project_code="TB-26", budget_lines=lines)
    fails = [c.code for c in r.checks if c.result == rq.CheckResult.FAIL]
    rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="femi@acme.org", department="finance",
              overrides=fails or None,
              override_reason="Donor approved the realignment by letter, 2 Sep" if fails else "",
              override_authority="Finance Manager" if fails else "")
    return rq.mark_paid("acme", r.id, actor="femi@acme.org", bank_reference=f"FT-{vendor[:4].upper()}")


def _text(pdf: bytes) -> str:
    p = Path(_TMP) / "r.pdf"
    p.write_bytes(pdf)
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout


def setup() -> None:
    org_config.apply_profile(copy.deepcopy(PROFILE))
    org_config.set_features("acme", projects=True, timesheets=True)
    for email, name, dept, role in [("amina@acme.org", "Amina Bello", "program", "viewer"),
                                    ("pm@acme.org", "PM", "program", "approver"),
                                    ("femi@acme.org", "Femi", "finance", "approver")]:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    grants.create_agreement("acme", donor="Global Fund", project_code="TB-26", title="TB case finding",
                            value=1_000_000, start_date="2026-01-01", end_date="2026-12-31",
                            budget_lines=[grants.BudgetLine(code="L1", label="Outreach", amount=600_000),
                                          grants.BudgetLine(code="L2", label="Supplies", amount=100_000)],
                            staff=[grants.PlannedStaff(name="Amina Bello", role="Field officer", percent=50)])
    _paid(80_000, "Zaria Motors", when="2026-08-20", line="L1")
    _paid(150_000, "Harbour Medical Stores", when="2026-09-10", line="L2", override=True,
          account="9988776655")    # over L2's ₦100,000: released with a reason
    _paid(40_000, "Kaduna Printers", when="2026-09-22")
    import timesheets as ts
    t = ts.create_timesheet("acme", staff_id="amina@acme.org", staff_name="Amina Bello", period="2026-09",
                            entries=[{"date": "2026-09-07", "hours": 30, "project_code": "TB-26", "span": "week"},
                                     {"date": "2026-09-14", "hours": 10, "project_code": "NON_PROJECT", "span": "week"}])
    raw = t.model_dump()
    raw.update(status="approved", approved_by="pm@acme.org", approved_at="2026-10-02T09:00:00+00:00")
    store.get_store().put("acme", ts._TIMESHEETS, t.id, raw)
    unapproved = ts.create_timesheet("acme", staff_id="ghost@acme.org", staff_name="Unapproved Person",
                                     period="2026-09", entries=[{"date": "2026-09-08", "hours": 8, "project_code": "TB-26"}])
    assert unapproved
    import payroll
    run = payroll.PayrollRun(id="run-sep", period="2026-09", status="paid", by_project={"TB-26": 120_000}, lines=[
        payroll.PayrollLine(staff_id="amina@acme.org", name="Amina Bello", employer_cost=240_000,
                            allocation_source="timesheet",
                            allocations=[payroll.SalaryAllocation(project_code="TB-26", donor="Global Fund", percent=50)]),
        payroll.PayrollLine(staff_id="musa@acme.org", name="Musa Danjuma", employer_cost=100_000,
                            allocation_source="budget",
                            allocations=[payroll.SalaryAllocation(project_code="TB-26", donor="Global Fund", percent=30)])])
    store.get_store().put("acme", payroll._RUNS, run.id, run.model_dump())


def test_the_report(c, h) -> None:
    print("\nSeptember's report for TB-26")
    r = c.get("/projects/TB-26/report.pdf?date_from=2026-09-01&date_to=2026-09-30", headers=h("pm@acme.org"))
    check("an approver downloads it", r.status_code == 200 and r.content[:4] == b"%PDF",
          f"{r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
    text = _text(r.content)
    check("it names the donor, project and period", "Global Fund" in text and "TB-26" in text
          and "01 Sep 2026 to 30 Sep 2026" in text, text[:300])
    check("September's two payments are in", "Harbour Medical Stores" in text and "Kaduna Printers" in text)
    check("August's payment is not", "Zaria Motors" not in text)
    check("the period's payments total ₦190,000", "190,000.00" in text)
    check("project to date shows all three (₦270,000)", "270,000.00" in text)
    check("budget against actual names the lines", "L1 · Outreach" in text and "L2 · Supplies" in text)
    check("the overspent line shows negative", "-" in text.split("L2 · Supplies")[1].split("\n")[0], text.split("L2 · Supplies")[1][:120])
    check("the exception carries its reason and who released it",
          "realignment" in text and "femi@acme.org" in text and "Finance Manager" in text)
    check("approved time is reported, with who signed", "Amina Bello" in text and "pm@acme.org" in text
          and "30" in text)
    check("unapproved time is not", "Unapproved Person" not in text)
    check("a salary on a budgeted split is labelled as such", "Budgeted split" in text and "Approved hours" in text)
    check("no bank account number appears", "0123456789" not in text and "9988776655" not in text)


def test_who_and_what(c, h) -> None:
    print("\nAccess and inputs")
    r = c.get("/projects/TB-26/report.pdf", headers=h("amina@acme.org"))
    check("a Programmes viewer can't download it", r.status_code == 403, str(r.status_code))
    r = c.get("/projects/TB-26/report.pdf?date_from=2026-09-30&date_to=2026-09-01", headers=h("femi@acme.org"))
    check("an end date before the start is refused in plain words", r.status_code == 422, str(r.status_code))
    r = c.get("/projects/TB-26/report.pdf", headers=h("femi@acme.org"))
    check("no dates: the whole project to date", r.status_code == 200 and "Zaria Motors" in _text(r.content))
    check("the file is named for the project", "TB-26-donor-report" in r.headers.get("content-disposition", ""))


if __name__ == "__main__":
    print("Donor report")
    setup()
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)

    def h(email):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}
    test_the_report(c, h)
    test_who_and_what(c, h)
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
