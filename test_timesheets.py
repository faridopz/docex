"""
Effort reporting tests.

These protect the rule that makes the whole module worth having: salary charged
to a grant comes from hours actually worked, never from a budget. 2 CFR
200.430(i) allows a grant to be charged only for work performed, and time-and-
effort documentation is the largest single source of audit findings — so the
tests here are mostly about refusing things.

Run: python test_timesheets.py
"""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-ts-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import timesheets as ts_mod  # noqa: E402
from timesheets import NON_PROJECT, TimesheetStatus  # noqa: E402

ORG = "effortco"
_passed = _failed = 0

# A period that has definitely finished, so the after-the-fact rule is met.
_LAST = (dt.date.today().replace(day=1) - dt.timedelta(days=1))
PERIOD = _LAST.strftime("%Y-%m")


def check(label: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def expect_error(label: str, fn) -> None:
    try:
        fn()
        check(label, False)
    except ts_mod.TimesheetError:
        check(label, True)


def day(n: int) -> str:
    return _LAST.replace(day=n).isoformat()


def fresh(staff="amina@eva.org", entries=None, period=PERIOD):
    for old in ts_mod.list_timesheets(ORG, period=period, staff_id=staff):
        store.get_store().delete(ORG, "timesheets", old.id)
    return ts_mod.create_timesheet(
        ORG, staff_id=staff, period=period, staff_name="Amina B",
        office="EVA/FCT", entries=entries or [])


def full_month(staff="amina@eva.org"):
    """96h on GF-2026-TB, 64h on FCDO-2024 — 160 total, a clean 60/40."""
    entries = ([{"date": day(d), "hours": 8, "project_code": "GF-2026-TB"} for d in range(1, 13)]
               + [{"date": day(d), "hours": 8, "project_code": "FCDO-2024"} for d in range(13, 21)])
    return fresh(staff, entries)


# ─── the rule that matters ──────────────────────────────────────────────────


def test_allocation_comes_from_actual_hours() -> None:
    print("\nAllocation is derived from hours worked, never supplied")
    t = full_month()
    alloc = ts_mod.effort_allocation(t)
    check(f"GF gets 60% (got {alloc.get('GF-2026-TB')})", alloc["GF-2026-TB"] == 60.0)
    check(f"FCDO gets 40% (got {alloc.get('FCDO-2024')})", alloc["FCDO-2024"] == 40.0)
    check("sums to exactly 100", round(sum(alloc.values()), 6) == 100.0)

    # The API takes no percentages — there is no way to assert a budget figure.
    import inspect
    params = inspect.signature(ts_mod.effort_allocation).parameters
    check("no percentage can be passed in",
          "percent" not in params and "allocation" not in params)


def test_money_splits_and_always_balances() -> None:
    print("\nA salary splits by effort and balances to the naira")
    t = full_month()
    split = ts_mod.allocate_amount(t, 500_000)
    check(f"GF gets 300,000 (got {split.get('GF-2026-TB'):,.2f})", split["GF-2026-TB"] == 300_000.0)
    check(f"FCDO gets 200,000 (got {split.get('FCDO-2024'):,.2f})", split["FCDO-2024"] == 200_000.0)
    check("splits sum to the salary", round(sum(split.values()), 2) == 500_000.0)

    # An awkward number that does not divide cleanly — payroll must still balance.
    odd = fresh("odd@eva.org", [
        {"date": day(1), "hours": 1, "project_code": "A"},
        {"date": day(2), "hours": 1, "project_code": "B"},
        {"date": day(3), "hours": 1, "project_code": "C"},
    ])
    a = ts_mod.effort_allocation(odd)
    check(f"thirds still sum to 100 (got {sum(a.values())})", round(sum(a.values()), 6) == 100.0)
    s = ts_mod.allocate_amount(odd, 100_000.01)
    check(f"an odd salary still balances (got {sum(s.values()):,.2f})",
          round(sum(s.values()), 2) == 100_000.01)


def test_non_project_hours_are_excluded_from_charging() -> None:
    print("\nLeave and admin are recorded, but never charged to a grant")
    t = fresh("mix@eva.org", [
        {"date": day(1), "hours": 60, "project_code": "GF-2026-TB"},
        {"date": day(2), "hours": 20, "project_code": NON_PROJECT, "activity": "Annual leave"},
    ])
    check("total counts everything", t.total_hours == 80)
    check("chargeable excludes leave", t.project_hours == 60)

    charged = ts_mod.effort_allocation(t)
    check("the grant carries 100% of chargeable time", charged["GF-2026-TB"] == 100.0)
    check("leave is not charged anywhere", NON_PROJECT not in charged)

    # The auditor's view: 100% of compensated time must be accounted for.
    honest = ts_mod.effort_allocation(t, chargeable_only=False)
    check("the full view shows leave at 25%", honest[NON_PROJECT] == 25.0)
    check("the full view still sums to 100", round(sum(honest.values()), 6) == 100.0)


# ─── refusals ───────────────────────────────────────────────────────────────


def test_after_the_fact_is_enforced() -> None:
    print("\nEffort is reported after the fact, never forecast")
    future = (dt.date.today().replace(day=1) + dt.timedelta(days=40)).strftime("%Y-%m")
    t = fresh("future@eva.org", period=future, entries=[
        {"date": dt.date.fromisoformat(future + "-01").isoformat(),
         "hours": 8, "project_code": "GF-2026-TB"}])
    issues = ts_mod.validate(ORG, t)
    check("a future period is blocking",
          any(i.code == "NOT_AFTER_THE_FACT" and i.blocking for i in issues))
    expect_error("and cannot be submitted",
                 lambda: ts_mod.submit(ORG, t.id, actor="future@eva.org"))


def test_every_hour_needs_a_job_code() -> None:
    print("\nEvery hour is coded — an unallocatable hour is a finding")
    t = fresh("nocode@eva.org", [{"date": day(1), "hours": 8, "project_code": ""}])
    issues = ts_mod.validate(ORG, t)
    check("missing Customer/Job is blocking",
          any(i.code == "MISSING_PROJECT_CODE" and i.blocking for i in issues))


def test_impossible_and_invalid_hours() -> None:
    print("\nImpossible hours are caught before they become a mischarge")
    t = fresh("long@eva.org", [
        {"date": day(1), "hours": 14, "project_code": "A"},
        {"date": day(1), "hours": 12, "project_code": "B"},   # 26h in one day
    ])
    check("26 hours in a day is blocking",
          any(i.code == "IMPOSSIBLE_DAY" and i.blocking for i in ts_mod.validate(ORG, t)))

    t = fresh("zero@eva.org", [{"date": day(1), "hours": 0, "project_code": "A"}])
    check("zero hours is blocking",
          any(i.code == "NON_POSITIVE_HOURS" and i.blocking for i in ts_mod.validate(ORG, t)))

    t = fresh("stray@eva.org", [{"date": "2020-01-15", "hours": 8, "project_code": "A"}])
    check("a date outside the period is blocking",
          any(i.code == "DATE_OUTSIDE_PERIOD" and i.blocking for i in ts_mod.validate(ORG, t)))

    t = fresh("empty@eva.org", [])
    check("an empty timesheet is blocking",
          any(i.code == "NO_ENTRIES" and i.blocking for i in ts_mod.validate(ORG, t)))


def test_unusual_hours_warn_but_do_not_block() -> None:
    print("\nOvertime and part-time are unusual, not dishonest")
    t = fresh("part@eva.org", [{"date": day(1), "hours": 4, "project_code": "A"}])
    issues = ts_mod.validate(ORG, t)
    drift = [i for i in issues if i.code == "HOURS_OUTSIDE_TOLERANCE"]
    check("a short month is flagged", bool(drift))
    check("but it does not block", drift and not drift[0].blocking)
    check("so it can still be filed",
          ts_mod.submit(ORG, t.id, actor="part@eva.org").status == TimesheetStatus.SUBMITTED)


def test_no_self_approval() -> None:
    print("\nNobody approves their own effort")
    t = full_month("self@eva.org")
    ts_mod.submit(ORG, t.id, actor="self@eva.org")
    expect_error("the submitter cannot approve",
                 lambda: ts_mod.approve(ORG, t.id, supervisor="self@eva.org"))
    try:
        ts_mod.approve(ORG, t.id, supervisor="self@eva.org")
    except ts_mod.TimesheetError as exc:
        check("the refusal says why", "audit finding" in str(exc).lower())
    ok = ts_mod.approve(ORG, t.id, supervisor="supervisor@eva.org")
    check("a supervisor can", ok.status == TimesheetStatus.APPROVED)
    check("the signature is recorded", ok.approved_by == "supervisor@eva.org" and ok.approved_at)


def test_one_timesheet_per_person_per_period() -> None:
    print("\nOne timesheet per person per period — no double charging")
    fresh("dup@eva.org", [{"date": day(1), "hours": 8, "project_code": "A"}])
    expect_error("a second is refused",
                 lambda: ts_mod.create_timesheet(ORG, staff_id="dup@eva.org", period=PERIOD))


def test_lifecycle_and_freezing() -> None:
    print("\nApproved records are evidence, and processed ones are frozen")
    t = full_month("cycle@eva.org")
    check("starts as a draft", t.status == TimesheetStatus.DRAFT)

    t = ts_mod.submit(ORG, t.id, actor="cycle@eva.org")
    check("signature recorded on submit", t.submitted_by == "cycle@eva.org" and t.submitted_at)
    expect_error("a submitted sheet cannot be edited",
                 lambda: ts_mod.set_entries(ORG, t.id, [], actor="cycle@eva.org"))

    t = ts_mod.send_back(ORG, t.id, supervisor="sup@eva.org", reason="Wrong job code on the 12th")
    check("returned", t.status == TimesheetStatus.RETURNED)
    check("the reason is kept", "job code" in t.returned_reason)
    check("and it is editable again",
          ts_mod.set_entries(ORG, t.id, [{"date": day(1), "hours": 8, "project_code": "A"}],
                             actor="cycle@eva.org").status == TimesheetStatus.RETURNED)

    expect_error("returning needs a reason",
                 lambda: ts_mod.send_back(ORG, t.id, supervisor="s", reason="  "))

    ts_mod.submit(ORG, t.id, actor="cycle@eva.org")
    expect_error("payroll cannot process an unapproved sheet",
                 lambda: ts_mod.mark_processed(ORG, t.id))
    ts_mod.approve(ORG, t.id, supervisor="sup@eva.org")
    done = ts_mod.mark_processed(ORG, t.id)
    check("processed", done.status == TimesheetStatus.PROCESSED)
    expect_error("a processed sheet is frozen",
                 lambda: ts_mod.set_entries(ORG, done.id, [], actor="x"))


def test_period_summary_gates_payroll() -> None:
    print("\nFinance can see whether the month is ready to pay")
    period = "2024-03"
    for s in ts_mod.list_timesheets(ORG, period=period):
        store.get_store().delete(ORG, "timesheets", s.id)

    # Spread across days — the engine (correctly) refuses more than 24h in one.
    a = ts_mod.create_timesheet(ORG, staff_id="a@eva.org", period=period, entries=[
        {"date": f"2024-03-{d:02d}", "hours": 10, "project_code": "GF-2026-TB"}
        for d in range(4, 14)])                     # 10 days x 10h = 100
    b = ts_mod.create_timesheet(ORG, staff_id="b@eva.org", period=period, entries=[
        {"date": f"2024-03-{d:02d}", "hours": 10, "project_code": "GF-2026-TB"}
        for d in range(4, 10)])                     # 6 days x 10h = 60

    ts_mod.approve(ORG, ts_mod.submit(ORG, a.id, actor="a@eva.org").id, supervisor="sup@eva.org")
    s = ts_mod.period_summary(ORG, period)
    check("not ready while one is outstanding", s["ready_for_payroll"] is False)
    check("and it names who", "b@eva.org" in s["outstanding_staff"])
    check("approved hours are counted", s["hours_by_project"]["GF-2026-TB"] == 100)

    ts_mod.approve(ORG, ts_mod.submit(ORG, b.id, actor="b@eva.org").id, supervisor="sup@eva.org")
    s = ts_mod.period_summary(ORG, period)
    check("ready once all are approved", s["ready_for_payroll"] is True)
    check("all hours counted", s["hours_by_project"]["GF-2026-TB"] == 160)


def test_org_isolation() -> None:
    print("\nOne client's effort records never reach another")
    ts_mod.create_timesheet("otherco", staff_id="x@other.org", period=PERIOD, entries=[
        {"date": day(1), "hours": 8, "project_code": "SECRET"}])
    ours = {c for t in ts_mod.list_timesheets(ORG) for c in t.hours_by_project()}
    check("their project code is invisible here", "SECRET" not in ours)
    check("and ours is invisible there",
          ts_mod.find_timesheet("otherco", "amina@eva.org", PERIOD) is None)


def main() -> int:
    print("=" * 64)
    print("Effort reporting — salary follows hours worked, not a budget")
    print("=" * 64)
    ts_mod.set_policy(ORG, ts_mod.TimesheetPolicy(standard_hours_per_period=160))
    test_allocation_comes_from_actual_hours()
    test_money_splits_and_always_balances()
    test_non_project_hours_are_excluded_from_charging()
    test_after_the_fact_is_enforced()
    test_every_hour_needs_a_job_code()
    test_impossible_and_invalid_hours()
    test_unusual_hours_warn_but_do_not_block()
    test_no_self_approval()
    test_one_timesheet_per_person_per_period()
    test_lifecycle_and_freezing()
    test_period_summary_gates_payroll()
    test_org_isolation()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
