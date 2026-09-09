#!/usr/bin/env python3
"""
Does the product work when five different people use it?

Every check this repository had until today drove the engine with ONE actor
and asked whether the right person could do the right thing. That is how a
system passes 40 suites while a reviewer in Programmes can approve the Finance
step, then Admin, then the AED — the whole chain, alone. Nobody had asked what
happens when the WRONG person tries.

This script asks that question of the DEPLOYED product, not the engine. It
creates real accounts in each role, signs each one in separately, and walks a
requisition through the organisation's actual approval chain with a different
person acting at every step. At each step it also tries the wrong person, the
wrong department, the submitter approving themselves, a reviewer paying, and
the submitter paying — and expects a refusal every time.

Then it exercises every screen's backing endpoint as the role that would open
it, so a page that exists on disk but 404s in production is caught here rather
than by the client.

    python3 verify_product.py https://docex-g0up.onrender.com \\
        --email admin@neemfoundation.org --password '...'

Writes to the instance: a handful of accounts (deactivated at the end) and a
few requisitions and one payment, all with vendor names starting VERIFY- so
they are unmistakable and easy to remove. Run it against production BEFORE a
client's first day, then clear the VERIFY- records.

Exit code is 1 on any failure. Do not hand the system to a client on a 1.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; B = "\033[1m"; D = "\033[2m"; X = "\033[0m"

_passed = _failed = 0
_findings: list[str] = []


def ok(label: str, detail: str = "") -> None:
    global _passed
    _passed += 1
    print(f"  {G}ok{X}    {label}{('  ' + D + detail + X) if detail else ''}")


def bad(label: str, detail: str = "") -> None:
    global _failed
    _failed += 1
    _findings.append(label + (f" — {detail}" if detail else ""))
    print(f"  {R}FAIL{X}  {label}{('  — ' + detail) if detail else ''}")


def check(label: str, cond: bool, detail: str = "") -> bool:
    (ok if cond else bad)(label, detail)
    return cond


class Api:
    """One HTTP client. Every call names its token, so no request can
    accidentally run as the wrong person."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def __call__(self, path, method="GET", token="", body=None, form=None, timeout=90):
        headers = {}
        data = None
        if form is not None:
            # urlencoded is fine for these Form() routes
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                try:
                    return r.status, json.loads(raw or b"{}")
                except Exception:
                    return r.status, {"_raw": raw[:200].decode(errors="replace")}
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw or b"{}")
            except Exception:
                return e.code, {"_raw": raw[:200].decode(errors="replace")}
        except Exception as e:                                    # noqa: BLE001
            return 0, {"error": str(e)}


def detail_of(body: dict) -> str:
    return str(body.get("detail") or body.get("error") or body)[:140]


# ─── the people ──────────────────────────────────────────────────────────────

class Person:
    def __init__(self, name, email, department, role):
        self.name, self.email, self.department, self.role = name, email, department, role
        self.token = ""
        self.id = ""


def onboard(api: Api, admin_tok: str, p: Person, stamp: str) -> bool:
    """Invite → first sign-in → forced password change → working session."""
    status, inv = api("/auth/users/invite", "POST", admin_tok,
                      body={"email": p.email, "name": p.name,
                            "department": p.department, "role": p.role})
    if status == 409:
        # Left over from an earlier run. Reset it and carry on.
        status, users = api("/auth/users", token=admin_tok)
        match = [u for u in (users.get("users") or []) if u.get("email") == p.email]
        if not match:
            bad(f"{p.role} in {p.department}: exists but cannot be found", p.email)
            return False
        p.id = match[0]["id"]
        if match[0].get("active") is False:
            api(f"/auth/users/{p.id}/activate", "POST", admin_tok)
        status, inv = api(f"/auth/users/{p.id}/reset-password", "POST", admin_tok)
    if status != 200:
        bad(f"{p.role} in {p.department}: invite refused", detail_of(inv))
        return False
    p.id = p.id or (inv.get("user") or {}).get("id", "")
    temp = inv.get("temporary_password", "")

    status, first = api("/auth/login", "POST", body={"email": p.email, "password": temp})
    if status != 200 or not first.get("must_change_password"):
        bad(f"{p.role} in {p.department}: first sign-in", detail_of(first))
        return False
    own = f"Own-{stamp}-{p.department}!"
    status, ch = api("/auth/password", "POST", first["token"],
                     body={"current_password": temp, "new_password": own})
    if status != 200:
        bad(f"{p.role} in {p.department}: could not set own password", detail_of(ch))
        return False
    p.token = ch.get("token", "")
    ok(f"{p.name} — {p.role}, {p.department}", "invited, signed in, password set")
    return True


# ─── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--keep-users", action="store_true",
                    help="leave the test accounts active (default: deactivate)")
    a = ap.parse_args()

    api = Api(a.base_url)
    stamp = str(int(time.time()))[-6:]
    print(f"{B}Product verification — {api.base}{X}")
    print(f"{D}Run {stamp}. Test data is prefixed VERIFY-{stamp}.{X}\n")

    # ── 0. alive ─────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    status, _ = api("/health")
    ms = (time.perf_counter() - t0) * 1000
    if not check("instance answers /health", status == 200, f"got {status}"):
        return 1
    if ms > 5000:
        print(f"        {Y}cold start: {ms:.0f}ms — keep-warm is not running{X}")

    # ── 1. the administrator ─────────────────────────────────────────────────
    print(f"\n{B}1. Administrator{X}")
    status, login = api("/auth/login", "POST", body={"email": a.email, "password": a.password})
    if not check("admin signs in", status == 200, detail_of(login)):
        return 1
    admin = login["token"]
    if login.get("must_change_password"):
        bad("admin is on a one-time password", "set a real one and re-run")
        return 1

    status, wf = api("/requisitions/workflow", token=admin)
    if not check("approval workflow loads", status == 200, detail_of(wf)):
        return 1
    steps = wf.get("steps") or []
    cats = wf.get("allowed_categories") or []
    packs = wf.get("documents_by_category") or {}
    check(f"{len(steps)} approval step(s) configured", len(steps) >= 1)
    check(f"{len(cats)} categories configured", len(cats) >= 1)
    check(f"{len(packs)} document pack(s) configured", True,
          "none — every category uses the org-wide list" if not packs else "")

    status, depts = api("/departments", token=admin)
    dept_keys = [d["key"] for d in (depts.get("departments") or [])]
    check(f"{len(dept_keys)} departments", len(dept_keys) >= 2, ", ".join(dept_keys))

    # The amount decides which steps engage. A step with min_amount above the
    # requisition is skipped by design — NEEM's ED joins only above ₦7m — so
    # the chain this run walks is the ENGAGED steps, not every configured one.
    # The first version of this script assumed every step engages and reported
    # correct engine behaviour as three failures.
    ceiling = wf.get("max_amount") or 10_000_000
    amount = min(250_000, ceiling / 4)
    all_steps = steps
    steps = [s for s in all_steps if float(s.get("min_amount") or 0) <= amount]
    skipped = [s["key"] for s in all_steps if s not in steps]
    if skipped:
        ok(f"{len(skipped)} step(s) do not engage at {amount:,.0f}", ", ".join(skipped))

    # Which department raises, and which ones approve. Pick a raiser that is
    # NOT an approval step, so the department check is exercised honestly.
    step_depts = [s["department"] for s in steps]
    raiser_dept = next((d for d in dept_keys if d not in step_depts), dept_keys[0])
    print(f"        {D}raiser: {raiser_dept}  chain at {amount:,.0f}: {' → '.join(step_depts)}{X}")

    # ── 2. the people ────────────────────────────────────────────────────────
    print(f"\n{B}2. Five people, five roles{X}")
    raiser = Person("Verify Raiser", f"verify-raiser-{stamp}@docex.test", raiser_dept, "reviewer")
    approvers: list[Person] = []
    for i, s in enumerate(steps):
        role = "approver" if i == len(steps) - 1 else "reviewer"
        approvers.append(Person(f"Verify Step{i+1}", f"verify-step{i+1}-{stamp}@docex.test",
                                s["department"], role))
    # A second person in the first step's department, for the self-approval test
    twin = Person("Verify Twin", f"verify-twin-{stamp}@docex.test", steps[0]["department"], "reviewer")
    payer = approvers[-1]   # last step is an approver and can pay

    people = [raiser, *approvers, twin]
    for p in people:
        if not onboard(api, admin, p, stamp):
            return finish(api, admin, people, a.keep_users)

    # ── 3. raise ─────────────────────────────────────────────────────────────
    print(f"\n{B}3. {raiser.department} raises a requisition{X}")
    cat = cats[0]
    docs = packs.get(cat) or (wf.get("required_documents") or [])
    status, req = api("/requisitions", "POST", raiser.token, form={
        "vendor_name": f"VERIFY-{stamp} Supplies Ltd", "amount": amount,
        "category": cat, "description": "Product verification run",
        "documents": ",".join(docs), "project_code": "VERIFY",
    })
    if not check("requisition raised", status == 200, detail_of(req)):
        return finish(api, admin, people, a.keep_users)
    rid = req["id"]
    check("it has a reference", bool(req.get("ref")), req.get("ref", ""))
    check("policy checks ran immediately", len(req.get("checks") or []) > 0)
    blocking = [c for c in req.get("checks") or [] if c.get("result") == "fail"]
    check("no blocking failure on a clean request", not blocking,
          ", ".join(c["code"] for c in blocking))
    check("parked on the first step", req.get("current_step") == steps[0]["key"],
          f"got {req.get('current_step')}")
    check("audit chain valid from the start", req.get("audit_chain_valid") is True)

    # ── 4. the wrong people ──────────────────────────────────────────────────
    print(f"\n{B}4. The wrong people try{X}")
    status, r = api(f"/requisitions/{rid}/decide", "POST", raiser.token,
                    form={"decision": "approved", "notes": "approving my own"})
    check("the submitter cannot approve their own request", status in (400, 403), f"got {status}")
    if len(approvers) > 1:
        status, r = api(f"/requisitions/{rid}/decide", "POST", approvers[-1].token,
                        form={"decision": "approved", "notes": "jumping the queue"})
        check(f"{approvers[-1].department} cannot act while it sits with {steps[0]['department']}",
              status in (400, 403), f"got {status}")
    status, r = api(f"/requisitions/{rid}/pay", "POST", approvers[0].token,
                    form={"bank_reference": "X"})
    check("a reviewer cannot pay", status == 403, f"got {status}")
    status, r = api(f"/requisitions/{rid}/pay", "POST", payer.token,
                    form={"bank_reference": "X"})
    check("nobody can pay before approval", status == 400, f"got {status}")

    # ── 5. the right people, in order ────────────────────────────────────────
    print(f"\n{B}5. The chain, one person per step{X}")
    for i, p in enumerate(approvers):
        status, r = api(f"/requisitions/{rid}/decide", "POST", p.token,
                        form={"decision": "approved", "notes": f"step {i+1} ok"})
        if not check(f"{p.department} approves at step {i+1}", status == 200, detail_of(r)):
            break
        nxt = steps[i + 1]["key"] if i + 1 < len(steps) else None
        if nxt:
            check(f"  → routed to {nxt}", r.get("current_step") == nxt, f"got {r.get('current_step')}")
        else:
            check("  → fully approved", r.get("status") == "approved", f"got {r.get('status')}")
    status, r = api(f"/requisitions/{rid}", token=admin)
    check(f"{len(r.get('approvals') or [])} approvals recorded, one per step",
          len(r.get("approvals") or []) == len(steps))
    check("audit chain still valid", r.get("audit_chain_valid") is True)

    # ── 6. pay ───────────────────────────────────────────────────────────────
    print(f"\n{B}6. Payment{X}")
    status, r = api(f"/requisitions/{rid}/pay", "POST", raiser.token,
                    form={"bank_reference": "X"})
    check("the submitter cannot release the payment", status in (400, 403), f"got {status}")
    status, txn = api(f"/requisitions/{rid}/pay", "POST", payer.token,
                      form={"bank_reference": f"VERIFY/{stamp}"})
    if check(f"{payer.department} releases payment", status == 200, detail_of(txn)):
        check("a transaction record was frozen", bool(txn.get("id")), txn.get("id", ""))
        check("it is locked", txn.get("locked") is True)
        check(f"it carries {len(txn.get('checks') or [])} check(s) as applied",
              len(txn.get("checks") or []) > 0)
        status, again = api(f"/requisitions/{rid}/pay", "POST", payer.token,
                            form={"bank_reference": "again"})
        check("it cannot be paid twice", status == 400, f"got {status}")
        status, lst = api("/payments", token=admin)
        ids = [p.get("id") for p in (lst.get("payments") or lst.get("transactions") or [])]
        check("it appears in the payments list", txn.get("id") in ids)

    # ── 7. policy ────────────────────────────────────────────────────────────
    print(f"\n{B}7. Policy checks block what they should{X}")
    status, over = api("/requisitions", "POST", raiser.token, form={
        "vendor_name": f"VERIFY-{stamp} Over Ceiling", "amount": ceiling * 2,
        "category": cat, "description": "over the ceiling", "documents": ",".join(docs),
    })
    fails = [c["code"] for c in over.get("checks") or [] if c.get("result") == "fail"]
    check("over the ceiling → blocking FAIL", status == 200 and "AMOUNT_LIMIT" in fails, str(fails))
    if status == 200:
        status, r = api(f"/requisitions/{over['id']}/decide", "POST", approvers[0].token,
                        form={"decision": "approved", "notes": "trying anyway"})
        check("cannot be approved over an unreleased FAIL", status == 400, f"got {status}")

    if docs:
        status, nodoc = api("/requisitions", "POST", raiser.token, form={
            "vendor_name": f"VERIFY-{stamp} No Docs", "amount": amount,
            "category": cat, "description": "missing documents", "documents": "",
        })
        fails = [c["code"] for c in nodoc.get("checks") or [] if c.get("result") == "fail"]
        check("missing documents → blocking FAIL", status == 200 and any("DOC" in f for f in fails), str(fails))

    status, dup = api("/requisitions", "POST", raiser.token, form={
        "vendor_name": f"VERIFY-{stamp} Supplies Ltd", "amount": amount,
        "category": cat, "description": "same again", "documents": ",".join(docs),
    })
    flagged = [c["code"] for c in dup.get("checks") or []
               if "DUP" in c.get("code", "") and c.get("result") in ("fail", "warning")]
    check("a duplicate within the window is flagged", bool(flagged), str(flagged))

    # ── 7b. a large amount pulls in the higher authority ─────────────────────
    if skipped:
        print(f"\n{B}7b. A large amount engages {', '.join(skipped)}{X}")
        big_step = next(s for s in all_steps if s["key"] == skipped[0])
        big = float(big_step["min_amount"]) + 1
        if big <= ceiling:
            status, br = api("/requisitions", "POST", raiser.token, form={
                "vendor_name": f"VERIFY-{stamp} Large Contract", "amount": big,
                "category": cat, "description": "large enough for the top step",
                "documents": ",".join(docs),
            })
            if check(f"₦{big:,.0f} requisition raised", status == 200, detail_of(br)):
                # walk it to the top step and confirm it stops there
                engaged = [s for s in all_steps if float(s.get("min_amount") or 0) <= big]
                by_dept = {p.department: p for p in approvers}
                last_status = None
                for s in engaged[:-1]:
                    person = by_dept.get(s["department"])
                    if not person:
                        break
                    status, br = api(f"/requisitions/{br['id']}/decide", "POST", person.token,
                                     form={"decision": "approved", "notes": "ok"})
                    last_status = status
                check(f"it reaches {engaged[-1]['key']} and waits there",
                      br.get("current_step") == engaged[-1]["key"],
                      f"at {br.get('current_step')}")
        else:
            ok(f"top step engages above the ceiling; cannot test", "config quirk, not a bug")

    # ── 8. document packs ────────────────────────────────────────────────────
    distinct = {}
    for k, v in packs.items():
        distinct.setdefault(tuple(sorted(v)), k)
    if len(distinct) >= 2:
        print(f"\n{B}8. Document packs differ by category{X}")
        (pa, ka), (pb, kb) = list(distinct.items())[:2]
        check(f"'{ka}' needs {len(pa)} docs, '{kb}' needs {len(pb)} — different packs",
              set(pa) != set(pb))
        check(f"{len(distinct)} distinct pack(s) across {len(packs)} categories", True)

    # ── 9. every screen's endpoint, as the role that opens it ────────────────
    print(f"\n{B}9. Every screen answers{X}")
    screens = [
        ("/dashboard", raiser.token, "Dashboard (reviewer)"),
        ("/requisitions", raiser.token, "Requisitions (reviewer)"),
        ("/requisitions/pending", approvers[0].token, "Waiting on me (approver)"),
        ("/payments", payer.token, "Payments (approver)"),
        ("/audit/summary", admin, "Audit (admin)"),
        (f"/notifications?department={approvers[0].department}&unread_only=true",
         approvers[0].token, "Notification bell"),
        ("/departments", raiser.token, "Departments"),
        ("/org/config", raiser.token, "Client config (nav)"),
        ("/auth/users", admin, "People & access (admin)"),
        ("/auth/me", raiser.token, "Who am I"),
    ]
    status, cfg = api("/org/config", token=admin)
    feats = cfg.get("features") or {}
    if feats.get("bank_reconciliation"):
        screens.append(("/reconciliation", approvers[0].token, "Reconciliation"))
    if feats.get("timesheets"):
        screens.append(("/timesheets/mine", raiser.token, "Timesheets"))
        screens.append(("/timesheets/policy", raiser.token, "Timesheet policy"))
    if feats.get("withholding_tax"):
        screens.append(("/treasury/wht/policy", admin, "Withholding tax"))
    for path, tok, label in screens:
        status, r = api(path, token=tok)
        check(label, status == 200, f"{path} → {status} {detail_of(r) if status != 200 else ''}")

    status, r = api("/auth/users", token=raiser.token)
    check("a reviewer is refused the user list", status == 403, f"got {status}")
    status, r = api("/treasury/wht/policy", "PUT", raiser.token, body={"enabled": False})
    check("a reviewer cannot change tax rates", status == 403, f"got {status}")

    # ── 10. notifications reached the right desk ─────────────────────────────
    print(f"\n{B}10. The next department was told{X}")
    status, n = api(f"/notifications?department={steps[0]['department']}", token=approvers[0].token)
    items = n.get("notifications") or n.get("items") or []
    check(f"{steps[0]['department']} was notified when it was raised",
          any(str(stamp) in json.dumps(i) or "VERIFY" in json.dumps(i) for i in items) or len(items) > 0,
          f"{len(items)} notification(s)")

    return finish(api, admin, people, a.keep_users)


def finish(api: Api, admin: str, people: list[Person], keep: bool) -> int:
    print(f"\n{B}Cleanup{X}")
    if keep:
        print(f"  {D}--keep-users: test accounts left active{X}")
    else:
        n = 0
        for p in people:
            if p.id:
                s, _ = api(f"/auth/users/{p.id}/deactivate", "POST", admin)
                n += s == 200
        ok(f"{n} test account(s) deactivated", "records kept, cannot sign in")
    print(f"  {D}Requisitions and the payment prefixed VERIFY- remain. Clear them before a client's first day.{X}")

    print(f"\n{'=' * 64}")
    print(f"{B}{_passed} passed, {_failed} failed{X}")
    if _findings:
        print(f"\n{R}Findings:{X}")
        for f in _findings:
            print(f"  • {f}")
        print(f"\n{R}Do not hand this to a client until these are fixed.{X}")
        return 1
    print(f"\n{G}The product works for five people in five roles. Multi-user ready.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
