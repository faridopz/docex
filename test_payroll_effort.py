"""
Payroll ← timesheet: the link that makes an allocation defensible.

The finding this prevents is the most common one in federal grant audits: a
salary charged to a grant at a BUDGETED percentage rather than the effort
actually worked. 2 CFR 200.430(i) permits charging only for work performed, so
someone budgeted at 50% who worked 30% must cost the grant 30%.

These tests prove the engine prefers recorded hours, says so on the line, and
still runs — loudly disclosed — for an organisation that has not adopted
timesheets yet.

Run: python test_payroll_effort.py
"""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-payeffort-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import payroll  # noqa: E402
import timesheets as ts  # noqa: E402

ORG = "effortpay"
_passed = _failed = 0

_LAST = dt.date.today().replace(day=1) - dt.timedelta(days=1)
PERIOD = _LAST.strftime("%Y-%m")


def check(label: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def day(n: int) -> str:
    return _LAST.replace(day=n).isoformat()


def setup() -> payroll.StaffRecord:
    payroll.set_policy(ORG, payroll.PayrollPolicy(
        rules=[payroll.DeductionRule(code="PAYE", method="percent", rate_percent=10.0)],
        refinancing_sign="negative"))
    # Budgeted 50/50 — the plan.
    return payroll.add_staff(
        ORG, id="amina", name="Amina Bello", gross_salary=400_000,
        allocations=[
            payroll.SalaryAllocation(project_code="GF-2026-TB", donor="Global Fund", percent=50),
            payroll.SalaryAllocation(project_code="FCDO-2024", donor="FCDO", percent=50),
        ])


def approved_timesheet(staff_id: str, gf_days: int, fcdo_days: int):
    for old in ts.list_timesheets(ORG, period=PERIOD, staff_id=staff_id):
        store.get_store().delete(ORG, "timesheets", old.id)
    entries = ([{"date": day(d), "hours": 8, "project_code": "GF-2026-TB"}
                for d in range(1, 1 + gf_days)]
               + [{"date": day(d), "hours": 8, "project_code": "FCDO-2024"}
                  for d in range(1 + gf_days, 1 + gf_days + fcdo_days)])
    sheet = ts.create_timesheet(ORG, staff_id=staff_id, period=PERIOD, entries=entries)
    ts.submit(ORG, sheet.id, actor=staff_id)
    return ts.approve(ORG, sheet.id, supervisor="supervisor@org")


def test_actual_effort_overrides_the_budget() -> None:
    print("\nRecorded hours override the budgeted percentages")
    # Budget says 50/50. She actually worked 6 days GF, 14 days FCDO → 30/70.
    approved_timesheet("amina", gf_days=6, fcdo_days=14)
    run = payroll.build_run(ORG, PERIOD)
    line = run.lines[0]

    alloc = {a.project_code: a.percent for a in line.allocations}
    check(f"GF charged 30%, not the budgeted 50% (got {alloc['GF-2026-TB']})",
          alloc["GF-2026-TB"] == 30.0)
    check(f"FCDO charged 70% (got {alloc['FCDO-2024']})", alloc["FCDO-2024"] == 70.0)
    check("the line says it came from a timesheet", line.allocation_source == "timesheet")
    check("and points at the evidence", bool(line.timesheet_id))
    check("hours are recorded on the line", line.hours_worked == 160)

    # The money must follow the hours, not the plan.
    employer_cost = line.employer_cost
    check(f"GF is charged 30% of cost (₦{run.by_project['GF-2026-TB']:,.0f})",
          abs(run.by_project["GF-2026-TB"] - employer_cost * 0.30) < 0.02)
    check("donor roll-up follows too",
          abs(run.by_donor["FCDO"] - employer_cost * 0.70) < 0.02)


def test_budget_is_used_but_disclosed_when_no_timesheet() -> None:
    print("\nWithout a timesheet payroll still runs — and says so")
    for old in ts.list_timesheets(ORG, period=PERIOD, staff_id="amina"):
        store.get_store().delete(ORG, "timesheets", old.id)

    run = payroll.build_run(ORG, PERIOD)
    line = run.lines[0]
    alloc = {a.project_code: a.percent for a in line.allocations}
    check("falls back to the budgeted 50/50", alloc["GF-2026-TB"] == 50.0)
    check("the line says it is budgeted", line.allocation_source == "budget")
    check("and discloses it as a NOTE, not a defect",
          any("BUDGETED" in n for n in line.notes) and not line.flags)
    check("the run counts unverified lines", run.lines_from_budget == 1)
    check("and warns once, at the top",
          any("BUDGETED percentages" in f for f in run.flags))
    check("effort_verified is False", run.effort_verified is False)


def test_an_unapproved_timesheet_is_not_evidence() -> None:
    print("\nOnly an APPROVED timesheet counts")
    for old in ts.list_timesheets(ORG, period=PERIOD, staff_id="amina"):
        store.get_store().delete(ORG, "timesheets", old.id)
    sheet = ts.create_timesheet(ORG, staff_id="amina", period=PERIOD, entries=[
        {"date": day(d), "hours": 8, "project_code": "GF-2026-TB"} for d in range(1, 21)])
    ts.submit(ORG, sheet.id, actor="amina")          # submitted, NOT approved

    line = payroll.build_run(ORG, PERIOD).lines[0]
    check("submitted-but-unapproved does not override the budget",
          line.allocation_source == "budget")
    check("and the reason is disclosed",
          any("not approved" in n for n in line.notes))

    ts.approve(ORG, sheet.id, supervisor="supervisor@org")
    line = payroll.build_run(ORG, PERIOD).lines[0]
    check("once approved it does override", line.allocation_source == "timesheet")
    check("100% to the one project actually worked",
          line.allocations[0].percent == 100.0)


def test_verified_run_says_so() -> None:
    print("\nA fully evidenced run is stated plainly")
    run = payroll.build_run(ORG, PERIOD)
    check("every line from a timesheet", run.lines_from_timesheet == len(run.lines))
    check("none from budget", run.lines_from_budget == 0)
    check("effort_verified is True", run.effort_verified is True)
    check("the run confirms it",
          any("derive from approved timesheets" in f for f in run.flags))


def test_hours_on_an_uncoded_project_are_disclosed() -> None:
    print("\nHours booked to a project with no donor are flagged, not dropped")
    for old in ts.list_timesheets(ORG, period=PERIOD, staff_id="amina"):
        store.get_store().delete(ORG, "timesheets", old.id)
    sheet = ts.create_timesheet(ORG, staff_id="amina", period=PERIOD, entries=[
        {"date": day(1), "hours": 80, "project_code": "GF-2026-TB"},
        {"date": day(2), "hours": 80, "project_code": "NEW-GRANT-2026"},   # unknown donor
    ] if False else [
        {"date": day(d), "hours": 8, "project_code": "GF-2026-TB"} for d in range(1, 11)
    ] + [
        {"date": day(d), "hours": 8, "project_code": "NEW-GRANT-2026"} for d in range(11, 21)
    ])
    ts.approve(ORG, ts.submit(ORG, sheet.id, actor="amina").id, supervisor="sup@org")

    line = payroll.build_run(ORG, PERIOD).lines[0]
    alloc = {a.project_code: a.percent for a in line.allocations}
    check("the new project still gets its 50%", alloc["NEW-GRANT-2026"] == 50.0)
    check("the missing donor is disclosed",
          any("no donor" in n for n in line.notes))
    check("it is a note, not a defect", not line.flags)


def test_the_switch_can_be_turned_off() -> None:
    print("\nuse_timesheets=False keeps the old behaviour exactly")
    line = payroll.build_run(ORG, PERIOD, use_timesheets=False).lines[0]
    check("budget used", line.allocation_source == "budget")
    check("no timesheet notes at all", not line.notes)


def main() -> int:
    print("=" * 64)
    print("Payroll ← timesheets: charge the grant for work actually done")
    print("=" * 64)
    setup()
    test_actual_effort_overrides_the_budget()
    test_budget_is_used_but_disclosed_when_no_timesheet()
    test_an_unapproved_timesheet_is_not_evidence()
    test_verified_run_says_so()
    test_hours_on_an_uncoded_project_are_disclosed()
    test_the_switch_can_be_turned_off()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
