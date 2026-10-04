"""
Timesheets people actually fill in, on time.

What this prevents:
  * staff typing project codes (and mistyping them) instead of picking
    from the projects they work on;
  * a timesheet that takes twenty minutes when it should take seconds;
  * time logged for tomorrow — a forecast dressed as a record;
  * "fill my month" inventing future days or overwriting what was recorded;
  * Finance not knowing who hasn't even started their timesheet;
  * staff quietly rewriting last quarter's hours after payroll used them;
  * a second sign-off by the same supervisor, or skipped altogether when the
    organisation asked for two.

Run: python test_timesheet_easy.py
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-tseasy-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import grants  # noqa: E402
import org_config  # noqa: E402
import timesheets as ts  # noqa: E402

PW = "correct-horse-battery"
_passed = _failed = 0
TODAY = dt.date.today()
LAST_MONTH = (TODAY.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")


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
                    {"key": "hr", "name": "HR"}],
    "workflow": {"max_amount": 10_000_000, "steps": [
        {"key": "finance", "label": "Finance review", "department": "finance"}]},
}
USERS = [("amina@acme.org", "Amina Bello", "program", "reviewer"),
         ("bola@acme.org", "Bola Ade", "program", "reviewer"),
         ("chidi@acme.org", "Chidi Eze", "hr", "reviewer"),
         ("pm@acme.org", "PM", "program", "approver"),
         ("femi@acme.org", "Femi", "finance", "approver"),
         ("root@acme.org", "Root", "finance", "admin")]


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)

    def h(email):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}
    return c, h


def _workday(back: int = 0) -> str:
    d = TODAY - dt.timedelta(days=back)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def test_my_projects(c, h) -> None:
    print("\nStaff pick from their own projects")
    r = c.get("/timesheets/my-projects", headers=h("amina@acme.org"))
    codes = [p["project_code"] for p in r.json().get("projects", [])]
    check("the projects that name her, biggest share first", codes[:2] == ["TB-26", "MNH-26"], str(r.json())[:200])
    check("…not a project she isn't on", "WASH-27" not in codes)
    check("leave/admin is always available", r.json().get("non_project") == "NON_PROJECT")


def test_log_today(c, h) -> None:
    print("\nLog today in one step")
    day = _workday()
    r = c.post("/timesheets/quick-log", headers=h("amina@acme.org"),
               data={"project_code": "TB-26", "portion": "full", "date": day})
    body = r.json()
    check("a full day opens the month's sheet and records it", r.status_code == 200
          and any(e["date"] == day and e["project_code"] == "TB-26" for e in body.get("entries", [])),
          f"{r.status_code} {r.text[:160]}")
    full = body.get("hours_per_day")
    check("a full day is the organisation's own standard, not an assumed 8",
          any(e["hours"] == full for e in body.get("entries", []))
          and full == ts.hours_per_day("acme", day[:7]), str(full))
    r = c.post("/timesheets/quick-log", headers=h("amina@acme.org"),
               data={"project_code": "TB-26", "portion": "half", "date": day})
    entries = [e for e in r.json()["entries"] if e["date"] == day and e["project_code"] == "TB-26"]
    check("logging the same day and project again corrects it, not doubles it",
          len(entries) == 1 and entries[0]["hours"] == round(full / 2, 2), str(entries))
    tomorrow = (TODAY + dt.timedelta(days=1)).isoformat()
    r = c.post("/timesheets/quick-log", headers=h("amina@acme.org"),
               data={"project_code": "TB-26", "portion": "full", "date": tomorrow})
    check("tomorrow can't be logged", r.status_code == 422 and "after it is worked" in r.text, r.text[:120])


def test_fill_my_month(c, h) -> None:
    print("\nFill my month from my usual split")
    sheet = ts.find_timesheet("acme", "amina@acme.org", TODAY.strftime("%Y-%m"))
    r = c.post(f"/timesheets/{sheet.id}/fill-from-plan", headers=h("amina@acme.org"))
    check("it fills", r.status_code == 200, r.text[:160])
    entries = r.json().get("entries", [])
    check("never a day after today", all(e["date"] <= TODAY.isoformat() for e in entries))
    check("never a weekend", all(dt.date.fromisoformat(e["date"]).weekday() < 5 for e in entries))
    day = _workday()
    on_day = [e for e in entries if e["date"] == day]
    check("the day she already logged is left exactly as she logged it",
          len(on_day) == 1 and on_day[0]["project_code"] == "TB-26", str(on_day))
    other = [e for e in entries if e["date"] != day]
    if other:
        codes = {e["project_code"] for e in entries if e["date"] == other[0]["date"]}
        check("a filled day follows her split: 60% TB, 30% MNH, the rest leave/admin",
              codes == {"TB-26", "MNH-26", "NON_PROJECT"}, str(codes))
    r = c.post(f"/timesheets/{sheet.id}/fill-from-plan", headers=h("pm@acme.org"))
    check("nobody else can fill her month", r.status_code == 403, str(r.status_code))
    r = c.post("/timesheets/quick-log", headers=h("bola@acme.org"),
               data={"project_code": "TB-26", "portion": "full", "date": _workday()})
    bola = ts.find_timesheet("acme", "bola@acme.org", TODAY.strftime("%Y-%m"))
    r = c.post(f"/timesheets/{bola.id}/fill-from-plan", headers=h("bola@acme.org"))
    check("someone with no planned split is told why, in plain words",
          r.status_code == 422 and "aren't named" in r.text, r.text[:160])


def test_who_hasnt_started(c, h) -> None:
    print("\nFinance sees who hasn't even started")
    r = c.get(f"/timesheets/summary?period={TODAY.strftime('%Y-%m')}", headers=h("femi@acme.org"))
    body = r.json()
    names = [p["name"] for p in body.get("not_started", [])]
    check("everyone expected who has no sheet is listed", "Chidi Eze" in names and "PM" in names, str(names))
    check("…but not people who have started", "Amina Bello" not in names)
    check("…and not the admin account", "Root" not in names)
    check("drafts are listed as not sent", any(p["name"] == "Amina Bello" for p in body.get("not_submitted", [])))
    ts.set_policy("acme", ts.TimesheetPolicy(who_records="project_staff"))
    names = [p["name"] for p in c.get(f"/timesheets/summary?period={TODAY.strftime('%Y-%m')}",
                                      headers=h("femi@acme.org")).json()["not_started"]]
    check("set to project staff only, Chidi (on no project) isn't chased", "Chidi Eze" not in names, str(names))
    ts.set_policy("acme", ts.TimesheetPolicy())
    r = c.post("/timesheets/remind", headers=h("femi@acme.org"), data={"period": TODAY.strftime("%Y-%m")})
    check("one click reminds them all", r.status_code == 200 and r.json()["reminded"] >= 3, r.text[:160])
    inbox = c.get("/notifications", headers=h("chidi@acme.org")).json()
    check("…and it lands in their own inbox", any("timesheet isn't in" in n["title"] for n in inbox["notifications"]),
          str(inbox)[:200])
    r = c.post("/timesheets/remind", headers=h("pm@acme.org"), data={"period": TODAY.strftime("%Y-%m")})
    check("a department approver reminds only their own team",
          r.status_code == 200 and "Chidi Eze" not in r.json()["people"], r.text[:200])
    r = c.post("/timesheets/remind", headers=h("amina@acme.org"), data={"period": TODAY.strftime("%Y-%m")})
    check("staff can't send reminders", r.status_code == 403)


def test_grace_period(c, h) -> None:
    print("\nAfter the grace period, last month is closed to changes")
    old = ts.create_timesheet("acme", staff_id="bola@acme.org", staff_name="Bola Ade", period="2026-01",
                              entries=[{"date": "2026-01-05", "hours": 8, "project_code": "TB-26"}])
    ts.set_policy("acme", ts.TimesheetPolicy(grace_days=5))
    r = c.put(f"/timesheets/{old.id}/entries", headers=h("bola@acme.org"),
              data={"entries": '[{"date": "2026-01-06", "hours": 8, "project_code": "TB-26"}]'})
    check("Bola can't change January any more", r.status_code == 422 and "closed for changes" in r.text, r.text[:160])
    r = c.post("/timesheets/quick-log", headers=h("bola@acme.org"),
               data={"project_code": "TB-26", "portion": "full", "date": "2026-01-07"})
    check("…not even through log-today", r.status_code == 422, r.text[:120])
    r = c.post(f"/timesheets/{old.id}/reopen", headers=h("pm@acme.org"))
    check("his manager can't reopen it; Finance does", r.status_code == 403)
    r = c.post(f"/timesheets/{old.id}/reopen", headers=h("femi@acme.org"), data={"days": "3"})
    check("Finance reopens it for a few days", r.status_code == 200 and not r.json()["locked"], r.text[:160])
    r = c.put(f"/timesheets/{old.id}/entries", headers=h("bola@acme.org"),
              data={"entries": '[{"date": "2026-01-06", "hours": 8, "project_code": "TB-26"}]'})
    check("…and he can correct it", r.status_code == 200, r.text[:120])
    ts.set_policy("acme", ts.TimesheetPolicy())


def test_two_signatures(c, h) -> None:
    print("\nAn organisation that wants Finance to sign after the supervisor")
    ts.set_policy("acme", ts.TimesheetPolicy(second_approval="finance"))
    sheet = ts.create_timesheet("acme", staff_id="bola@acme.org", staff_name="Bola Ade", period=LAST_MONTH,
                                entries=[{"date": f"{LAST_MONTH}-0{d}", "hours": 8, "project_code": "TB-26"}
                                         for d in range(1, 8)])
    c.post(f"/timesheets/{sheet.id}/submit", headers=h("bola@acme.org"))
    r = c.post(f"/timesheets/{sheet.id}/approve", headers=h("femi@acme.org"))
    check("Finance can't sign before the supervisor", r.status_code == 403, str(r.status_code))
    r = c.post(f"/timesheets/{sheet.id}/approve", headers=h("pm@acme.org"))
    check("the supervisor signs first; it is not yet approved",
          r.status_code == 200 and r.json()["status"] == "submitted" and r.json()["stage"] == "second", r.text[:200])
    q = c.get("/timesheets/pending", headers=h("femi@acme.org")).json()
    check("it now waits in Finance's queue", any(t["id"] == sheet.id for t in q["timesheets"]))
    r = c.post(f"/timesheets/{sheet.id}/approve", headers=h("pm@acme.org"))
    check("the supervisor can't sign twice", r.status_code == 403, str(r.status_code))
    r = c.post(f"/timesheets/{sheet.id}/approve", headers=h("femi@acme.org"))
    check("Finance's signature approves it", r.status_code == 200 and r.json()["status"] == "approved"
          and r.json()["supervisor_approved_by"] == "pm@acme.org" and r.json()["approved_by"] == "femi@acme.org",
          r.text[:200])
    ts.set_policy("acme", ts.TimesheetPolicy())


def test_the_wizard_question() -> None:
    print("\nSetup wizard: 'Do your staff charge time to donor projects?'")
    import setup_wizard as sw
    a = sw.load_answers("acme")
    check("it reads back the current setting", a["staff_time"] is True, str(a["staff_time"]))
    a["org_name"] = "Acme Health"
    a["staff_time"] = False
    sw.apply("acme", a, actor="root@acme.org")
    check("answering no switches timesheets off", not org_config.feature_enabled("acme", "timesheets"))
    a["staff_time"] = True
    sw.apply("acme", a, actor="root@acme.org")
    check("answering yes switches them on", org_config.feature_enabled("acme", "timesheets"))
    a["staff_time"] = None
    sw.apply("acme", a, actor="root@acme.org")
    check("not answering leaves it as it was", org_config.feature_enabled("acme", "timesheets"))


if __name__ == "__main__":
    print("Timesheets people fill in")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    org_config.set_features("acme", timesheets=True, projects=True)
    for email, name, dept, role in USERS:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    grants.create_agreement("acme", donor="Global Fund", project_code="TB-26", value=1_000_000,
                            staff=[grants.PlannedStaff(name="Amina Bello", staff_id="amina@acme.org", percent=60)])
    grants.create_agreement("acme", donor="FCDO", project_code="MNH-26", value=500_000,
                            staff=[grants.PlannedStaff(name="Amina Bello", staff_id="amina@acme.org", percent=30)])
    grants.create_agreement("acme", donor="UNICEF", project_code="WASH-27", value=100)
    c, h = _client()
    test_my_projects(c, h)
    test_log_today(c, h)
    test_fill_my_month(c, h)
    test_who_hasnt_started(c, h)
    test_grace_period(c, h)
    test_two_signatures(c, h)
    test_the_wizard_question()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
