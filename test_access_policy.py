"""
Who may open which area — and who may hand their sign-off to someone else.

Found in the 30 Sep 2026 security audit. Before this, being signed in was
enough to reach most of the system:
  * C1  anyone who could see a request could email themselves a sign-off link
        for every step and approve their own payment end to end;
  * C2  a viewer could read every salary and bank account on /payroll;
  * H2  accounting exports, reconciliation and treasury were open to viewers;
  * H3  any viewer could rewrite the policy rulebooks;
  * H4  bank-account verification and rate cards (what people are paid) were
        open to anyone;
  * H5  the old transactions pipeline stayed reachable even where the org had
        switched it off.

Each check below names the failure it prevents. Run: python test_access_policy.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-access-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

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
    "departments": [{"key": "program", "name": "Programmes"},
                    {"key": "finance", "name": "Finance"},
                    {"key": "ed", "name": "Executive Director"}],
    "workflow": {"max_amount": 10_000_000, "steps": [
        {"key": "budget", "label": "Budget holder", "requester_department": True},
        {"key": "finance", "label": "Finance review", "department": "finance"},
        {"key": "ed", "label": "ED approval", "department": "ed"}]},
}

USERS = [("amina@acme.org", "Amina", "program", "viewer"),
         ("pm@acme.org", "PM", "program", "approver"),
         ("ngozi@acme.org", "Ngozi", "finance", "reviewer"),
         ("femi@acme.org", "Femi", "finance", "approver"),
         ("ed@acme.org", "ED", "ed", "approver"),
         ("root@acme.org", "Root", "ed", "admin")]


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)
    tokens: dict[str, dict] = {}

    def h(email: str) -> dict:
        if email not in tokens:
            r = c.post("/auth/login", json={"email": email, "password": PW})
            tokens[email] = {"Authorization": "Bearer " + r.json()["token"]}
        return tokens[email]
    return c, h


def test_finance_areas_are_finance_only(c, h) -> None:
    print("\nSalaries, ledgers, statements and bank checks are Finance's")
    areas = [("GET", "/payroll/staff", "C2: a viewer reads every salary"),
             ("GET", "/accounting/export/payments?period=2026-09", "H2: a viewer exports the ledger"),
             ("GET", "/reconciliation", "H2: a viewer reads bank statements"),
             ("GET", "/treasury/accounts", "H2: a viewer reads treasury"),
             ("GET", "/verify/batches", "H4: a viewer runs bank-account checks")]
    for method, path, failure in areas:
        r = c.request(method, path, headers=h("amina@acme.org"))
        check(f"refused to a Programmes viewer ({failure})", r.status_code == 403, f"{path} {r.status_code}")
        r = c.request(method, path, headers=h("pm@acme.org"))
        check(f"refused to a Programmes approver too ({path})", r.status_code == 403, f"{r.status_code}")
        r = c.request(method, path, headers=h("ngozi@acme.org"))
        check(f"Finance still gets in ({path})", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
        r = c.request(method, path, headers=h("root@acme.org"))
        check(f"an administrator still gets in ({path})", r.status_code == 200, f"{r.status_code}")
    r = c.get("/treasury/wht/policy", headers=h("amina@acme.org"))
    check("withholding-tax guidance stays readable to staff raising requests", r.status_code == 200, str(r.status_code))


def test_rates_and_rules_are_admin_writes(c, h) -> None:
    print("\nWhat people are paid, and the policy itself, change only by an admin")
    r = c.post("/rate-cards", headers=h("ngozi@acme.org"), json={})
    check("H4: Finance staff cannot rewrite a rate card", r.status_code == 403, str(r.status_code))
    r = c.get("/rate-cards", headers=h("amina@acme.org"))
    check("…but anyone may read the rates", r.status_code == 200, str(r.status_code))
    r = c.put("/compliance/org-profile", headers=h("femi@acme.org"), json={})
    check("H3: even a Finance approver cannot rewrite the org's policy profile", r.status_code == 403, str(r.status_code))
    r = c.get("/compliance/org-profile", headers=h("femi@acme.org"))
    check("…but the approval chain can read it", r.status_code == 200, str(r.status_code))
    r = c.get("/compliance/org-profile", headers=h("amina@acme.org"))
    check("…and a Programmes viewer cannot", r.status_code == 403, str(r.status_code))
    r = c.post("/compliance/checks/xyz/approve", headers=h("ngozi@acme.org"))
    check("H3: a Finance reviewer cannot approve a policy check", r.status_code == 403, str(r.status_code))


def test_switched_off_pipeline_is_absent(c, h) -> None:
    print("\nAn area the organisation switched off is not there at all")
    for who in ("amina@acme.org", "root@acme.org"):
        r = c.get("/transactions", headers=h(who))
        check(f"H5: /transactions is 404 for {who.split('@')[0]}", r.status_code == 404, str(r.status_code))
        r = c.get("/vouchers", headers=h(who))
        check(f"…and so is /vouchers for {who.split('@')[0]}", r.status_code == 404, str(r.status_code))
    org_config.set_features("acme", attendance_payments=True)
    r = c.get("/vouchers", headers=h("amina@acme.org"))
    check("switched on, vouchers are still Finance's, not a viewer's", r.status_code == 403, str(r.status_code))
    r = c.get("/vouchers", headers=h("ngozi@acme.org"))
    check("…and Finance gets in", r.status_code == 200, str(r.status_code))
    org_config.set_features("acme", attendance_payments=False)


def test_signoff_links_belong_to_the_decider(c, h) -> None:
    print("\nC1: only the step's own approver may hand their sign-off to someone else")
    r = rq.create_requisition("acme", submitted_by="amina@acme.org", department="program",
                              vendor_name="Kano Printers", amount=2_000_000)
    url = f"/requisitions/{r.id}/request-signoff"
    res = c.post(url, headers=h("amina@acme.org"), json={"step": "budget", "approver_email": "me@gmail.com"})
    check("the submitter cannot mint a link for their own request", res.status_code == 403, f"{res.status_code} {res.text[:120]}")
    res = c.post(url, headers=h("pm@acme.org"), json={"step": "ed", "approver_email": "x@gmail.com"})
    check("no one can mint a link for a later step in advance", res.status_code == 400, f"{res.status_code}")
    res = c.post(url, headers=h("femi@acme.org"), json={"step": "budget", "approver_email": "x@gmail.com"})
    check("an approver from another department cannot", res.status_code == 403, f"{res.status_code}")
    res = c.post(url, headers=h("pm@acme.org"), json={"step": "budget", "approver_email": "amina@acme.org"})
    check("the step's approver cannot send it to the person who raised it", res.status_code == 422, f"{res.status_code}")
    res = c.post(url, headers=h("pm@acme.org"), json={"step": "budget", "approver_email": "deputy@acme.org"})
    check("the step's own approver can delegate to someone else", res.status_code == 200, f"{res.status_code} {res.text[:160]}")
    rq.decide("acme", r.id, decision=rq.Decision.APPROVED, actor="pm@acme.org", department="program")
    res = c.post(url, headers=h("femi@acme.org"), json={"step": "finance", "approver_email": "pm@acme.org"})
    check("…but not to someone who already approved an earlier step", res.status_code == 422, f"{res.status_code}")
    res = c.post(url, headers=h("root@acme.org"), json={"step": "finance", "approver_email": "auditor@acme.org"})
    check("an administrator can delegate the current step", res.status_code == 200, f"{res.status_code}")


if __name__ == "__main__":
    print("Who may open which area")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    org_config.set_features("acme", bank_reconciliation=True, withholding_tax=True, payroll=True,
                            accounting_export=True)
    for email, name, dept, role in USERS:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    c, h = _client()
    test_finance_areas_are_finance_only(c, h)
    test_rates_and_rules_are_admin_writes(c, h)
    test_switched_off_pipeline_is_absent(c, h)
    test_signoff_links_belong_to_the_decider(c, h)
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
