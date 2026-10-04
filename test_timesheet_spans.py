"""
Recording time by day, by week, or as a monthly total.

What this prevents:
  * staff inventing daily figures to fill a grid when what they honestly know
    is "this week was on the TB project" — a guess dressed as a measurement;
  * the same hours counted twice, once in a weekly line and again day by day;
  * a "week" that starts on a Wednesday overlapping the next one;
  * a weekly or monthly total tripping the 24-hours-in-a-day check, or a week
    claiming more hours than it has;
  * an organisation whose donor demands daily records receiving weekly ones.

Run: python test_timesheet_spans.py
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile

os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(tempfile.mkdtemp(prefix="docex-spans-")))

import timesheets as ts  # noqa: E402

_passed = _failed = 0
AFTER = dt.date(2026, 10, 5)      # September is over, so it can be reported


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


_n = 0


def codes(entries) -> set[str]:
    global _n
    _n += 1
    sheet = ts.create_timesheet("acme", staff_id=f"s{_n}@x", period="2026-09", entries=entries)
    return {i.code for i in ts.validate("acme", sheet, at=AFTER) if i.blocking}


def test_weeks() -> None:
    print("\nBy week")
    # September 2026: the 1st is a Tuesday, so the weeks start 1, 7, 14, 21, 28.
    weeks = [{"date": d, "hours": 40, "project_code": "TB-26", "span": "week"}
             for d in ("2026-09-07", "2026-09-14", "2026-09-21")]
    weeks.append({"date": "2026-09-01", "hours": 32, "project_code": "TB-26", "span": "week"})
    check("a month recorded by week is valid", codes(weeks) == set(), str(codes(weeks)))
    sheet = ts.create_timesheet("acme", staff_id="w@x", period="2026-09", entries=weeks)
    check("…and its hours go to the project like any others",
          ts.effort_allocation(sheet) == {"TB-26": 100.0} and sheet.total_hours == 152)
    check("a week must start on its Monday (or the 1st)",
          "WEEK_START" in codes([{"date": "2026-09-09", "hours": 8, "project_code": "TB-26", "span": "week"}]))
    check("a week can't hold more hours than it has (the 28th–30th is 3 days, 72 h)",
          "IMPOSSIBLE_SPAN" in codes([{"date": "2026-09-28", "hours": 80, "project_code": "TB-26", "span": "week"}]))
    check("a 40-hour week doesn't trip the 24-hours-a-day check",
          "IMPOSSIBLE_DAY" not in codes([{"date": "2026-09-14", "hours": 40, "project_code": "TB-26", "span": "week"}]))


def test_month() -> None:
    print("\nAs one monthly total")
    entries = [{"date": "2026-09-01", "hours": 120, "project_code": "TB-26", "span": "month"},
               {"date": "2026-09-01", "hours": 40, "project_code": "NON_PROJECT", "span": "month"}]
    check("a monthly split is valid", codes(entries) == set(), str(codes(entries)))
    sheet = ts.create_timesheet("acme", staff_id="m@x", period="2026-09", entries=entries)
    check("…and allocates exactly like daily hours would", ts.effort_allocation(sheet) == {"TB-26": 100.0})
    check("a monthly total is dated the 1st",
          "MONTH_START" in codes([{"date": "2026-09-15", "hours": 100, "project_code": "TB-26", "span": "month"}]))


def test_no_mixing() -> None:
    print("\nOne way per month, so nothing is counted twice")
    mixed = [{"date": "2026-09-07", "hours": 40, "project_code": "TB-26", "span": "week"},
             {"date": "2026-09-08", "hours": 8, "project_code": "TB-26"}]
    check("a weekly line plus daily lines is refused", "MIXED_SPANS" in codes(mixed))


def test_an_org_can_require_daily() -> None:
    print("\nAn organisation whose donor wants daily records")
    ts.set_policy("acme", ts.TimesheetPolicy(allowed_spans=["day"]))
    check("a weekly line is refused, saying how to record instead",
          "SPAN_NOT_ALLOWED" in codes([{"date": "2026-09-07", "hours": 40, "project_code": "TB-26", "span": "week"}]))
    check("daily entries are fine",
          codes([{"date": "2026-09-07", "hours": 8, "project_code": "TB-26"}]) == set())
    ts.set_policy("acme", ts.TimesheetPolicy())


def test_old_records_still_read() -> None:
    print("\nSheets saved before spans existed")
    raw = ts.create_timesheet("acme", staff_id="old@x", period="2026-08",
                              entries=[{"date": "2026-08-03", "hours": 8, "project_code": "TB-26"}]).model_dump()
    for e in raw["entries"]:
        e.pop("span", None)
    check("an entry with no span is a day", ts.Timesheet.model_validate(raw).entries[0].span == "day")


if __name__ == "__main__":
    print("Recording time by day, week or month")
    test_weeks()
    test_month()
    test_no_mixing()
    test_an_org_can_require_daily()
    test_old_records_still_read()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
