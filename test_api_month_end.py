"""
Month-end, end to end, through the real HTTP API.

The engines have their own suites. This one asks a different question: can a
finance officer actually DO the month using nothing but the API? Every call
below goes through the real FastAPI app — auth middleware, feature gate, form
parsing, serialisers — because an engine nobody can reach is not a feature.

The arc is the client's actual month:

    staff record → timesheet → supervisor approves → payroll charges the grant
    for the hours worked → payment → bank statement → reconciliation → close

It also checks the two gates that protect it: a client without the feature
flags cannot see any of this, and a signed-out caller cannot touch it.

Run: python test_api_month_end.py
"""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-monthend-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as auth_mod  # noqa: E402

auth_mod._SECRET_FILE = Path(_TMP) / ".auth_secret"
auth_mod._secret_cache = None

from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402
import org_config  # noqa: E402
from api.context import default_org  # noqa: E402

client = TestClient(m.app)
ORG = default_org()

_passed = _failed = 0

# Last complete month — a timesheet must be after-the-fact, and payroll for a
# month that has not happened yet is not a thing anyone runs.
_LAST = dt.date.today().replace(day=1) - dt.timedelta(days=1)
PERIOD = _LAST.strftime("%Y-%m")


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def day(n: int) -> str:
    return _LAST.replace(day=n).isoformat()


# ─── setup ──────────────────────────────────────────────────────────────────


def _register(email: str, name: str, role: str, department: str,
              headers: dict | None = None) -> dict:
    """The first user bootstraps the instance; every later one needs an admin."""
    r = client.post("/auth/register", headers=headers or {}, json={
        "email": email, "name": name, "password": "correct-horse-battery",
        "department": department, "role": role})
    if r.status_code >= 400:
        raise AssertionError(f"register {email}: {r.status_code} {r.text[:300]}")
    return r.json()


def _login(email: str) -> dict:
    r = client.post("/auth/login", json={"email": email,
                                         "password": "correct-horse-battery"})
    if r.status_code >= 400:
        raise AssertionError(f"login {email}: {r.status_code} {r.text[:300]}")
    token = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _enable(**flags) -> None:
    """Set feature flags directly — the profile path has its own suite."""
    current = store.get_store().get(ORG, "config", "features") or {}
    features = dict(current.get("features") or {})
    features.update(flags)
    store.get_store().put(ORG, "config", "features", {
        "modules": current.get("modules") or ["compliance"],
        "features": features})


# ─── the gates ──────────────────────────────────────────────────────────────


def test_signed_out_gets_nothing() -> None:
    print("\nA signed-out caller reaches none of it")
    for path in ("/timesheets", "/payroll/runs", "/reconciliation"):
        check(f"{path} → 401", client.get(path).status_code == 401)


def test_feature_flags_hide_what_was_not_bought(admin: dict) -> None:
    print("\nA client without the feature does not see the feature")
    _enable(timesheets=False, payroll=False, bank_reconciliation=False)
    for path in ("/timesheets", "/payroll/runs", "/reconciliation"):
        r = client.get(path, headers=admin)
        check(f"{path} → 404 while flagged off", r.status_code == 404,
              f"got {r.status_code}")
    _enable(timesheets=True, payroll=True, bank_reconciliation=True)
    for path in ("/timesheets", "/payroll/runs", "/reconciliation"):
        check(f"{path} → 200 once enabled",
              client.get(path, headers=admin).status_code == 200)


# ─── effort ─────────────────────────────────────────────────────────────────


def test_timesheet_lifecycle(staff: dict, supervisor: dict) -> str:
    print("\nEmployee fills a timesheet, supervisor signs it")
    entries = ([{"date": day(d), "hours": 8, "project_code": "GF-2026-TB"}
                for d in range(1, 7)]
               + [{"date": day(d), "hours": 8, "project_code": "FCDO-2024"}
                  for d in range(7, 21)])
    r = client.post("/timesheets", headers=staff,
                    data={"period": PERIOD, "staff_name": "Amina Bello",
                          "entries": __import__("json").dumps(entries)})
    check("created", r.status_code == 200, r.text[:200])
    sheet = r.json()
    ts_id = sheet["id"]
    check("160 hours recorded", sheet["total_hours"] == 160)
    check("effort split computed from the hours",
          sheet["effort_allocation"]["GF-2026-TB"] == 30.0)
    check("nothing blocking", sheet["blocking"] == 0)

    r = client.post(f"/timesheets/{ts_id}/approve", headers=supervisor)
    check("cannot be approved before it is submitted", r.status_code == 422)

    r = client.post(f"/timesheets/{ts_id}/submit", headers=staff)
    check("submitted", r.json()["status"] == "submitted")

    # The employee here holds 'reviewer', so the ROLE guard lets the call
    # through and the refusal comes from the engine — which is the control
    # actually being tested. A viewer would have been stopped one layer earlier
    # and proved nothing about self-approval.
    r = client.post(f"/timesheets/{ts_id}/approve", headers=staff)
    check("the employee cannot approve their own", r.status_code == 422,
          f"got {r.status_code}: {r.text[:160]}")

    r = client.get("/timesheets/pending", headers=supervisor)
    check("it is in the supervisor's queue",
          any(t["id"] == ts_id for t in r.json()["timesheets"]))

    r = client.post(f"/timesheets/{ts_id}/approve", headers=supervisor)
    check("supervisor approves", r.json()["status"] == "approved")
    check("and is named on it", r.json()["approved_by"].startswith("supervisor"))

    r = client.get("/timesheets/summary", headers=supervisor,
                   params={"period": PERIOD})
    check("period summary says payroll is safe to run",
          r.json()["ready_for_payroll"] is True, r.text[:200])
    return ts_id


def test_returning_a_timesheet_needs_a_reason(staff: dict, supervisor: dict) -> None:
    print("\nSending a timesheet back requires feedback")
    import json as _json
    r = client.post("/timesheets", headers=staff, data={
        "period": PERIOD, "staff_id": "bola", "staff_name": "Bola A",
        "entries": _json.dumps([{"date": day(1), "hours": 8,
                                 "project_code": "GF-2026-TB"}])})
    # staff_id != caller, so this needs elevation — proves the guard works.
    check("filling one in for someone else is refused for staff",
          r.status_code == 403, f"got {r.status_code}")

    r = client.post("/timesheets", headers=supervisor, data={
        "period": PERIOD, "staff_id": "bola", "staff_name": "Bola A",
        "entries": _json.dumps([{"date": day(1), "hours": 8,
                                 "project_code": "GF-2026-TB"}])})
    check("but allowed for an approver", r.status_code == 200, r.text[:200])
    ts_id = r.json()["id"]
    client.post(f"/timesheets/{ts_id}/submit", headers=supervisor)

    r = client.post(f"/timesheets/{ts_id}/return", headers=supervisor,
                    data={"reason": ""})
    check("a blank reason is refused", r.status_code == 422)
    r = client.post(f"/timesheets/{ts_id}/return", headers=supervisor,
                    data={"reason": "Friday is missing."})
    check("returned with the reason kept",
          r.json()["returned_reason"] == "Friday is missing.")


# ─── payroll ────────────────────────────────────────────────────────────────


def test_payroll_uses_the_approved_hours(admin: dict, ts_id: str) -> None:
    print("\nPayroll charges the grant for the hours actually worked")
    r = client.put("/payroll/policy", headers=admin, json={
        "rules": [{"code": "PAYE", "method": "percent", "rate_percent": 10.0}],
        "refinancing_sign": "negative"})
    check("deduction policy set", r.status_code == 200, r.text[:200])

    # Budgeted 50/50 — deliberately NOT what she worked.
    r = client.post("/payroll/staff", headers=admin, json={
        "id": "amina", "email": "staff@org",
        "name": "Amina Bello", "gross_salary": 400000,
        "allocations": [
            {"project_code": "GF-2026-TB", "donor": "Global Fund", "percent": 50},
            {"project_code": "FCDO-2024", "donor": "FCDO", "percent": 50}]})
    check("staff record added", r.status_code == 200, r.text[:200])

    r = client.post("/payroll/runs", headers=admin, data={"period": PERIOD})
    check("run built", r.status_code == 200, r.text[:300])
    run = r.json()
    line = run["lines"][0]
    alloc = {a["project_code"]: a["percent"] for a in line["allocations"]}
    check("the grant is charged 30%, not the budgeted 50%",
          alloc["GF-2026-TB"] == 30.0, str(alloc))
    check("the line says where that came from",
          line["allocation_source"] == "timesheet")
    check("and points at the timesheet", line["timesheet_id"] == ts_id)
    check("hours are on the line", line["hours_worked"] == 160)
    check("the sheet was found even though it is filed under an email "
          "and the staff record under a storage id",
          line["timesheet_id"] == ts_id)
    check("the run reports effort as verified", run["effort_verified"] is True)
    check("with no unverified lines", run["lines_from_budget"] == 0)


def test_payroll_without_a_timesheet_is_disclosed(admin: dict) -> None:
    print("\nA person with no timesheet still gets paid — and it is disclosed")
    client.post("/payroll/staff", headers=admin, json={
        "id": "chidi", "email": "chidi@org",
        "name": "Chidi O", "gross_salary": 250000,
        "allocations": [{"project_code": "FCDO-2024", "donor": "FCDO",
                         "percent": 100}]})
    run = client.post("/payroll/runs", headers=admin,
                      data={"period": PERIOD}).json()
    chidi = next(l for l in run["lines"] if l["staff_id"] == "chidi")
    check("he is paid", chidi["net"] > 0)
    check("from the budget", chidi["allocation_source"] == "budget")
    check("disclosed as a note, not a defect",
          chidi["notes"] and not chidi["flags"])
    check("the run counts it", run["lines_from_budget"] == 1)
    check("and no longer claims verified effort",
          run["effort_verified"] is False)


# ─── reconciliation ─────────────────────────────────────────────────────────


def _statement(rows: list[str]) -> bytes:
    return ("\n".join(["Value Date,Narration,Reference,Debit,Credit"] + rows)).encode()


def test_preview_before_committing(admin: dict) -> None:
    print("\nThe importer shows its reading before anything is stored")
    data = _statement([f"{day(4)},TRF TO ACME LTD,FT26001,250000.00,"])
    r = client.post("/reconciliation/preview", headers=admin,
                    files={"statement": ("gtb.csv", data, "text/csv")})
    check("preview works", r.status_code == 200, r.text[:300])
    body = r.json()
    check("columns auto-detected", body["auto_detected"] is True)
    check("the debit was read", body["debits"] == 1)
    check("with the right value", body["debit_value"] == 250000.0)
    check("and it says to check before trusting it", "Check the sample" in body["confirm"])
    check("nothing was stored",
          client.get("/reconciliation", headers=admin).json()["total"] == 0)


def test_an_ambiguous_statement_is_refused(admin: dict) -> None:
    print("\nA statement whose dates cannot be read is refused, not guessed")
    data = _statement(["05/06/2026,TRF TO ACME,FT1,250000.00,"])
    r = client.post("/reconciliation/preview", headers=admin,
                    files={"statement": ("odd.csv", data, "text/csv")})
    check("refused with 422", r.status_code == 422, f"got {r.status_code}")
    check("and the message says how to fix it",
          "date_format" in r.json()["detail"], r.text[:200])


def test_the_month_reconciles_and_closes(admin: dict) -> None:
    print("\nReconcile the month, explain the exceptions, close it")
    data = _statement([
        f"{day(4)},TRF TO ACME LTD,FT26001,250000.00,",
        f"{day(12)},MONTHLY ACCOUNT MAINTENANCE,CHG,2500.00,",
        f"{day(15)},GRANT RECEIPT,GR1,,5000000.00",
    ])
    r = client.post("/reconciliation", headers=admin,
                    data={"period": PERIOD},
                    files={"statement": ("gtb.csv", data, "text/csv")})
    check("run created", r.status_code == 200, r.text[:300])
    run = r.json()
    run_id = run["run_id"]

    codes = [e["code"] for e in run["exceptions"]]
    check("the unapproved debit is flagged", "NOT_IN_SYSTEM" in codes)
    check("the credit is not treated as a payment", len(run["exceptions"]) == 2)
    check("high severity first in the response",
          run["exceptions"][0]["severity"] == "high")
    check("not reconciled yet", run["reconciled"] is False)

    r = client.post(f"/reconciliation/{run_id}/close", headers=admin, data={})
    check("close is refused over unexplained money", r.status_code == 422)
    check("and says how many", "2 unexplained" in r.json()["detail"], r.text[:200])

    for exc in run["exceptions"]:
        r = client.post(f"/reconciliation/{run_id}/explain", headers=admin, data={
            "bank_line_id": exc["bank_line_id"],
            "reason": "Bank charge / prior-month payment, confirmed with GTBank."})
        check(f"explained {exc['code']}", r.status_code == 200, r.text[:200])

    r = client.post(f"/reconciliation/{run_id}/close", headers=admin, data={})
    check("now it closes", r.status_code == 200, r.text[:200])
    closed = r.json()
    check("locked", closed["locked"] is True)
    check("with the closer's name", closed["closed_by"].startswith("admin"))
    check("the statement is fingerprinted", len(closed["statement_sha256"]) == 16)

    r = client.post(f"/reconciliation/{run_id}/explain", headers=admin, data={
        "bank_line_id": run["exceptions"][0]["bank_line_id"], "reason": "later thought"})
    check("a closed month cannot be edited", r.status_code == 422)
    check("and the message explains why",
          "cannot be edited" in r.json()["detail"], r.text[:200])


def test_explain_needs_a_target(admin: dict) -> None:
    print("\nAn explanation must name what it explains")
    run_id = client.get("/reconciliation", headers=admin).json()["runs"][0]["run_id"]
    r = client.post(f"/reconciliation/{run_id}/explain", headers=admin,
                    data={"reason": "because"})
    check("refused without an id", r.status_code == 422)


def main() -> int:
    print("=" * 68)
    print(f"Month end through the API — period {PERIOD}")
    print("=" * 68)

    _register("admin@org", "Admin", "admin", "finance")   # bootstraps the instance
    admin = _login("admin@org")
    _register("staff@org", "Amina Bello", "reviewer", "program", headers=admin)
    staff = _login("staff@org")
    _register("supervisor@org", "Supervisor", "approver", "program", headers=admin)
    supervisor = _login("supervisor@org")

    test_signed_out_gets_nothing()
    test_feature_flags_hide_what_was_not_bought(admin)
    ts_id = test_timesheet_lifecycle(staff, supervisor)
    test_returning_a_timesheet_needs_a_reason(staff, supervisor)
    test_payroll_uses_the_approved_hours(admin, ts_id)
    test_payroll_without_a_timesheet_is_disclosed(admin)
    test_preview_before_committing(admin)
    test_an_ambiguous_statement_is_refused(admin)
    test_the_month_reconciles_and_closes(admin)
    test_explain_needs_a_target(admin)

    print("\n" + "=" * 68)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 68)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
