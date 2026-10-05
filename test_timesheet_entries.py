"""
Timesheets as a list of entries, each one reviewed.

What this prevents:
  * a supervisor having to send back a whole month over one wrong day;
  * a rejection with no reason, or by the person whose time it is;
  * an approved entry being quietly changed or deleted afterwards;
  * a sheet going back up with a rejected entry still on it;
  * the month grid wiping out entries a supervisor already approved;
  * old timesheets (no entry ids) breaking, or reading as unapproved;
  * a supervisor seeing another department's people in their team view.

Run: python test_timesheet_entries.py
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-tsentries-")
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
         ("hrboss@acme.org", "HR Lead", "hr", "approver"),
         ("femi@acme.org", "Femi", "finance", "approver"),
         ("root@acme.org", "Root", "finance", "admin")]


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)

    def h(email):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}
    return c, h


def _day(n: int) -> str:
    return f"{LAST_MONTH}-{n:02d}"


def test_adding_entries(c, h) -> dict:
    print("\nStaff add entries one at a time")
    r = c.post("/timesheets", headers=h("amina@acme.org"), data={"period": LAST_MONTH})
    sid = r.json()["id"]
    ids = {}
    for n, code, hours, ot in [(1, "TB-26", 8, False), (2, "TB-26", 6, False), (2, "MNH-26", 4, True),
                               (3, "MNH-26", 8, False)]:
        r = c.post(f"/timesheets/{sid}/items", headers=h("amina@acme.org"),
                   data={"date": _day(n), "project_code": code, "hours": hours,
                         "activity": f"Work on {code}", "overtime": "true" if ot else "false"})
        check(f"{_day(n)} {code} {hours}h is added", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
        e = [x for x in r.json().get("entries", []) if x["date"] == _day(n) and x["project_code"] == code]
        ids[(n, code)] = e[0]["id"] if e else ""
    body = r.json()
    check("every entry has an id and starts pending",
          all(e["id"] and e["status"] == "pending" for e in body["entries"]), str(body["entries"])[:200])
    check("overtime is kept as a flag", any(e["overtime"] for e in body["entries"]))
    check("counts by status are on the sheet", body.get("entry_counts") == {"pending": 4, "approved": 0, "rejected": 0},
          str(body.get("entry_counts")))
    check("project names come with it, so nobody reads codes",
          body.get("project_names", {}).get("TB-26", {}).get("donor") == "Global Fund", str(body.get("project_names")))

    r = c.post(f"/timesheets/{sid}/items", headers=h("amina@acme.org"),
               data={"date": (TODAY + dt.timedelta(days=1)).isoformat(), "project_code": "TB-26", "hours": 8})
    check("tomorrow can't be added", r.status_code == 422, r.text[:120])
    r = c.post(f"/timesheets/{sid}/items", headers=h("amina@acme.org"),
               data={"date": TODAY.replace(day=1).isoformat() if TODAY.day > 1 else "2000-01-01",
                     "project_code": "TB-26", "hours": 8})
    check("a day outside this month can't be added", r.status_code == 422, r.text[:120])
    r = c.post(f"/timesheets/{sid}/items", headers=h("amina@acme.org"),
               data={"date": _day(4), "project_code": "TB-26", "hours": 25})
    check("more than 24 hours can't be added", r.status_code == 422, r.text[:120])
    r = c.post(f"/timesheets/{sid}/items", headers=h("amina@acme.org"),
               data={"date": _day(4), "project_code": "", "hours": 8})
    check("an entry needs a project", r.status_code == 422, r.text[:120])
    r = c.post(f"/timesheets/{sid}/items", headers=h("bola@acme.org"),
               data={"date": _day(4), "project_code": "TB-26", "hours": 8})
    check("a colleague can't add to her sheet", r.status_code in (403, 404), str(r.status_code))

    eid = ids[(3, "MNH-26")]
    r = c.put(f"/timesheets/{sid}/items/{eid}", headers=h("amina@acme.org"),
              data={"date": _day(3), "project_code": "MNH-26", "hours": 7, "activity": "Corrected"})
    e = [x for x in r.json().get("entries", []) if x["id"] == eid]
    check("she can edit an entry", r.status_code == 200 and e and e[0]["hours"] == 7, r.text[:160])
    r = c.post(f"/timesheets/{sid}/items", headers=h("amina@acme.org"),
               data={"date": _day(6), "project_code": "TB-26", "hours": 2})
    extra = [x["id"] for x in r.json()["entries"] if x["date"] == _day(6)][0]
    r = c.delete(f"/timesheets/{sid}/items/{extra}", headers=h("amina@acme.org"))
    check("she can remove an entry", r.status_code == 200 and all(x["id"] != extra for x in r.json()["entries"]),
          r.text[:160])
    return {"sid": sid, **{f"{n}-{c_}": v for (n, c_), v in ids.items()}}


def test_reviewing_entries(c, h, s: dict) -> None:
    print("\nThe supervisor reviews each entry")
    sid = s["sid"]
    r = c.post(f"/timesheets/{sid}/submit", headers=h("amina@acme.org"))
    check("she sends it", r.status_code == 200, r.text[:200])
    bad = s["2-MNH-26"]
    r = c.post(f"/timesheets/{sid}/items/{bad}/reject", headers=h("pm@acme.org"), data={"reason": ""})
    check("a rejection needs a reason", r.status_code == 422, r.text[:120])
    r = c.post(f"/timesheets/{sid}/items/{bad}/reject", headers=h("hrboss@acme.org"), data={"reason": "x"})
    check("another department's approver can't reject it", r.status_code in (403, 404), str(r.status_code))
    r = c.post(f"/timesheets/{sid}/items/{bad}/reject", headers=h("amina@acme.org"), data={"reason": "x"})
    check("she can't review her own entry", r.status_code in (403, 404), str(r.status_code))
    r = c.post(f"/timesheets/{sid}/items/{s['1-TB-26']}/reject", headers=h("pm@acme.org"),
               data={"reason": "Wrong project"})
    r = c.post(f"/timesheets/{sid}/items/{s['1-TB-26']}/clear", headers=h("pm@acme.org"))
    e = [x for x in r.json().get("entries", []) if x["id"] == s["1-TB-26"]]
    check("a rejection can be undone before approving", r.status_code == 200 and e and e[0]["status"] == "pending",
          r.text[:160])
    r = c.post(f"/timesheets/{sid}/items/{bad}/reject", headers=h("pm@acme.org"),
               data={"reason": "Overtime wasn't agreed for this day"})
    e = [x for x in r.json().get("entries", []) if x["id"] == bad]
    check("the supervisor rejects one entry with a reason",
          r.status_code == 200 and e and e[0]["status"] == "rejected"
          and e[0]["reject_reason"] == "Overtime wasn't agreed for this day", r.text[:200])
    q = c.get("/timesheets/pending", headers=h("pm@acme.org")).json()
    check("it is still in his queue until he finishes", any(t["id"] == sid for t in q["timesheets"]))

    r = c.post(f"/timesheets/{sid}/approve", headers=h("pm@acme.org"))
    body = r.json()
    by_id = {x["id"]: x for x in body.get("entries", [])}
    check("approving the rest sends the sheet back, because one was rejected",
          r.status_code == 200 and body["status"] == "returned", r.text[:200])
    check("…the others are approved", all(x["status"] == "approved" for i, x in by_id.items() if i != bad),
          str(body.get("entry_counts")))
    check("…and the reason names the rejected entry", _day(2) in body.get("returned_reason", ""),
          body.get("returned_reason", ""))

    r = c.post(f"/timesheets/{sid}/submit", headers=h("amina@acme.org"))
    check("she can't send it again while the rejected entry is still there", r.status_code == 422
          and "rejected" in r.text.lower(), r.text[:200])
    ok = s["1-TB-26"]
    r = c.put(f"/timesheets/{sid}/items/{ok}", headers=h("amina@acme.org"),
              data={"date": _day(1), "project_code": "TB-26", "hours": 1})
    check("an approved entry can't be edited", r.status_code == 422, r.text[:160])
    r = c.delete(f"/timesheets/{sid}/items/{ok}", headers=h("amina@acme.org"))
    check("…or removed", r.status_code == 422, r.text[:160])
    r = c.put(f"/timesheets/{sid}/entries", headers=h("amina@acme.org"),
              data={"entries": f'[{{"date": "{_day(1)}", "hours": 8, "project_code": "TB-26"}}]'})
    check("the month grid can't overwrite approved entries", r.status_code == 422, r.text[:160])

    r = c.put(f"/timesheets/{sid}/items/{bad}", headers=h("amina@acme.org"),
              data={"date": _day(2), "project_code": "MNH-26", "hours": 2, "activity": "Agreed with PM",
                    "overtime": "false"})
    e = [x for x in r.json().get("entries", []) if x["id"] == bad]
    check("fixing the rejected entry puts it back to pending and clears the reason",
          r.status_code == 200 and e and e[0]["status"] == "pending" and not e[0]["reject_reason"], r.text[:200])
    r = c.post(f"/timesheets/{sid}/submit", headers=h("amina@acme.org"))
    check("now she can send it", r.status_code == 200, r.text[:200])
    r = c.post(f"/timesheets/{sid}/approve", headers=h("pm@acme.org"))
    body = r.json()
    check("approving with nothing rejected approves the sheet and every entry",
          body.get("status") == "approved" and all(x["status"] == "approved" for x in body["entries"]),
          r.text[:200])
    r = c.post(f"/timesheets/{sid}/items/{bad}/reject", headers=h("pm@acme.org"), data={"reason": "late"})
    check("nothing can be rejected on an approved sheet", r.status_code == 422, r.text[:120])


def test_old_records(c, h) -> None:
    print("\nTimesheets saved before entries had ids")
    import uuid
    sid = uuid.uuid4().hex
    raw = {"id": sid, "org_id": "acme", "staff_id": "bola@acme.org", "staff_name": "Bola Ade",
           "period": LAST_MONTH, "status": "approved", "approved_by": "pm@acme.org",
           "entries": [{"date": _day(1), "hours": 8, "project_code": "TB-26"},
                       {"date": _day(2), "hours": 8, "project_code": "TB-26"}]}
    store.get_store().put("acme", "timesheets", sid, raw)
    t = ts.get_timesheet("acme", sid)
    check("each old entry gets an id", all(e.id for e in t.entries), str([e.id for e in t.entries]))
    check("…that stays the same next time", [e.id for e in ts.get_timesheet("acme", sid).entries]
          == [e.id for e in t.entries])
    check("on an approved sheet they read as approved", all(e.status == "approved" for e in t.entries))
    sid2 = uuid.uuid4().hex
    store.get_store().put("acme", "timesheets", sid2, {**raw, "id": sid2, "status": "draft",
                                                     "staff_id": "chidi@acme.org", "approved_by": ""})
    check("on a draft they read as pending",
          all(e.status == "pending" for e in ts.get_timesheet("acme", sid2).entries))
    total = sum(ts.allocate_amount(t, 1000).values())
    check("payroll still allocates from it", abs(total - 1000) < 0.01, str(total))


def test_team_view(c, h) -> None:
    print("\nThe team view")
    r = c.get(f"/timesheets/team?period={LAST_MONTH}", headers=h("pm@acme.org"))
    body = r.json()
    names = {row["staff_id"] for row in body.get("rows", [])}
    check("the supervisor sees his department", r.status_code == 200
          and {"amina@acme.org", "bola@acme.org"} <= names, r.text[:200])
    check("…not HR's people", "chidi@acme.org" not in names, str(names))
    row = next((x for x in body.get("rows", []) if x["staff_id"] == "amina@acme.org"), {})
    check("each row has entries by status", row.get("entry_counts", {}).get("approved", 0) >= 4, str(row))
    check("counters are there", set(body.get("counters", {})) >= {"needs_review", "approved", "has_rejections",
                                                                  "not_started"}, str(body.get("counters")))
    r = c.get(f"/timesheets/team?period={LAST_MONTH}", headers=h("femi@acme.org"))
    names = {row["staff_id"] for row in r.json().get("rows", [])}
    check("Finance sees everyone", "chidi@acme.org" in names and "amina@acme.org" in names, str(names))
    r = c.get(f"/timesheets/team?period={LAST_MONTH}", headers=h("bola@acme.org"))
    check("a staff member doesn't get the team view", r.status_code == 403, str(r.status_code))


if __name__ == "__main__":
    print("Timesheets as entries")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    org_config.set_features("acme", timesheets=True, projects=True)
    for email, name, dept, role in USERS:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    grants.create_agreement("acme", donor="Global Fund", project_code="TB-26", value=1_000_000,
                            title="TB case finding",
                            staff=[grants.PlannedStaff(name="Amina Bello", staff_id="amina@acme.org", percent=60)])
    grants.create_agreement("acme", donor="FCDO", project_code="MNH-26", value=500_000,
                            staff=[grants.PlannedStaff(name="Amina Bello", staff_id="amina@acme.org", percent=30)])
    c, h = _client()
    s = test_adding_entries(c, h)
    test_reviewing_entries(c, h, s)
    test_old_records(c, h)
    test_team_view(c, h)
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
