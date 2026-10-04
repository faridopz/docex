"""
The demo organisation: a made-up NGO with eight weeks of realistic payments,
for Loom recordings, sales calls and "try it yourself" logins.

Why it exists (29 Sep 2026): every demo so far ran on NEEM's own system or on
a seeder with NEEM's name written into it. A prospect must never see a real
client's payments, and the engine must never carry a client's name. So the
demo is its own organisation, "demo", with a fictional name, and the seeder
refuses to write anywhere else.

What would go wrong without these checks:
  * seeding into a real client's database by running it with the wrong
    DOCEX_ORG set;
  * a password written into the code or profile;
  * an empty screen in the middle of a recording (every state must exist);
  * a seeded audit trail that fails its own tamper check, which is the one
    thing the demo is meant to show off;
  * dates in the future, or everything dated today, which reads as fake.

Run: python test_demo_seed.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-demo-")
os.environ["DOCEX_ORG"] = "demo"
os.environ.pop("DOCEX_DB", None)
os.environ.pop("DOCEX_DATABASE_URL", None)

import store  # noqa: E402

store.set_store(store.JsonFileStore(Path(_TMP) / "store"))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import attachments  # noqa: E402

attachments.set_backend(attachments.LocalDiskAttachmentBackend(Path(_TMP) / "files"))

import demo_seed  # noqa: E402
import requisitions as rq  # noqa: E402

PW = "demo-pass-2026"
_passed = _failed = 0
ROOT = Path(__file__).parent


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def _run_cli(*args: str, org: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DOCEX_ORG": org, "DOCEX_DB": str(Path(_TMP) / "cli.db")}
    env.pop("DEMO_PASSWORD", None)
    return subprocess.run([sys.executable, "demo_seed.py", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def test_it_only_ever_writes_to_the_demo_org() -> None:
    print("\nRun against a client by mistake: refuses, writes nothing")
    r = _run_cli("--password", PW, org="neem")
    check("refused (non-zero exit)", r.returncode != 0, r.stdout[-200:] + r.stderr[-200:])
    check("says why", "demo" in (r.stdout + r.stderr).lower())
    check("nothing written", not (Path(_TMP) / "cli.db").exists()
          or "neem" not in (Path(_TMP) / "cli.db").read_bytes().decode("latin-1"))


def test_no_password_no_seed() -> None:
    print("\nNo password given: refuses rather than inventing one")
    r = _run_cli(org="demo")
    check("refused", r.returncode != 0, r.stdout[-200:] + r.stderr[-200:])
    check("asks for --password or DEMO_PASSWORD", "password" in (r.stdout + r.stderr).lower())


def test_no_secret_or_client_name_in_the_files() -> None:
    print("\nThe demo files carry no password and no real client")
    for name in ("demo_seed.py", "profiles/demo.json"):
        text = (ROOT / name).read_text().lower()
        check(f"{name}: no client name", "neem" not in text and "taconnect" not in text and "eva" not in text.split())
    prof = json.loads((ROOT / "profiles/demo.json").read_text())
    check("profile has no admin password", "password" not in json.dumps(prof.get("admin") or {}).lower())


def test_every_screen_has_something() -> None:
    print("\nSeeded: every state a recording needs exists")
    summary = demo_seed.seed(password=PW, reset=True)
    reqs = rq.list_requisitions("demo")
    by = {}
    for r in reqs:
        by.setdefault(r.status.value if hasattr(r.status, "value") else str(r.status), []).append(r)
    check("about twenty requests", 16 <= len(reqs) <= 30, str(len(reqs)))
    check("several paid", len(by.get("paid", [])) >= 6, str({k: len(v) for k, v in by.items()}))
    check("one returned", len(by.get("returned", [])) >= 1)
    check("one draft", len(by.get("draft", [])) >= 1)
    check("one declined", len(by.get("declined", [])) >= 1)
    check("one on hold", len(by.get("on_hold", [])) >= 1, str(list(by)))
    wf = rq.get_workflow("demo")
    waiting = [r for r in reqs if r.status == rq.ReqStatus.IN_REVIEW]
    steps = {r.current_step for r in waiting}
    check("waiting at every step (budget holder, Finance, ED)",
          {s.key for s in wf.steps} <= steps, str(steps))
    blocked = {c.code for r in waiting for c in rq.blocking_checks(r)}
    check("one blocked for missing quotes", "DOCS_COMPLETE" in blocked, str(blocked))
    check("one blocked for a closed grant", "GRANT_PERIOD" in blocked, str(blocked))
    s = rq.audit_summary("demo")
    check("an explained override for the audit page",
          any(e.get("reason") for e in (s.get("exceptions") or [])), json.dumps(s)[:300])
    check("and the audit is clean (every exception explained)", s.get("audit_ready") is True)
    check("the summary names the logins", len(summary.get("logins") or []) >= 8, str(summary))


def test_the_trail_is_real() -> None:
    print("\nEvery seeded request passes its own tamper check")
    reqs = rq.list_requisitions("demo")
    bad = [r.ref for r in reqs if not rq.verify_audit_chain(r)]
    check("all audit chains verify", not bad, str(bad))


def test_dates_look_like_two_months_of_work() -> None:
    print("\nDates spread over weeks, none in the future")
    reqs = rq.list_requisitions("demo")
    days = sorted({r.created_at[:10] for r in reqs})
    today = dt.date.today()
    oldest = dt.date.fromisoformat(days[0])
    check("oldest is six weeks or more ago", (today - oldest).days >= 42, days[0])
    check("nothing in the future", all(dt.date.fromisoformat(d) <= today for d in days), days[-1])
    check("not all on one day", len(days) >= 10, str(len(days)))
    paid = [r for r in reqs if str(getattr(r.status, "value", r.status)) == "paid"]
    order_ok = all(r.created_at <= (r.updated_at or r.created_at) for r in paid)
    check("each paid request was paid after it was raised", order_ok)
    import audit_findings
    rep = audit_findings.run_audit_tests("demo", tz_offset_minutes=60)   # West Africa Time
    found = {f.code: f.severity for f in rep.findings}
    check("no weekend or night-time approvals flagged by our own audit", not any(
        "HOURS" in c for c in found), str(found))
    check("no medium or high audit findings (a demo is a clean organisation)",
          not any(sev in ("medium", "high") for sev in found.values()), str(found))


def test_an_advance_is_overdue() -> None:
    print("\nAdvances: one retired, one overdue")
    import advances
    advs = advances.list_advances("demo")
    check("two or more advances", len(advs) >= 2, str(len(advs)))
    check("one retired", any(a.retired_at for a in advs))
    overdue = [a for a in advs if not a.retired_at and a.due_at < dt.date.today().isoformat()]
    check("one overdue", len(overdue) >= 1, str([(a.ref, a.due_at, a.retired_at) for a in advs]))


def test_people_can_sign_in_and_see_their_queue() -> None:
    print("\nThe logins work, and each person's queue has their work in it")
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)

    def h(email: str) -> dict:
        r = c.post("/auth/login", json={"email": email, "password": PW})
        return {"Authorization": "Bearer " + r.json().get("token", "")}

    for email, what in [("tunde@riverbend.example", "Programme Manager (budget holder)"),
                        ("ibrahim@riverbend.example", "Finance Manager"),
                        ("amaka@riverbend.example", "Executive Director")]:
        r = c.get("/requisitions/pending", headers=h(email))
        n = len(r.json().get("requisitions", [])) if r.status_code == 200 else -1
        check(f"{what} has something waiting", n >= 1, f"{r.status_code} {n}")
    r = c.get("/requisitions", headers=h("aisha@riverbend.example"))
    check("a programme officer sees her own requests", r.status_code == 200
          and len(r.json()["requisitions"]) >= 2, str(r.status_code))
    paid = next(x for x in rq.list_requisitions("demo") if str(getattr(x.status, "value", x.status)) == "paid")
    r = c.get(f"/requisitions/{paid.id}/voucher.pdf", headers=h("ibrahim@riverbend.example"))
    check("a paid request's voucher prints", r.status_code == 200 and r.content[:4] == b"%PDF",
          f"{r.status_code} {r.text[:120] if r.status_code != 200 else ''}")


def test_the_bank_statement_tells_the_story() -> None:
    print("\nThe latest month's statement: payments match, one transfer nobody approved")
    import bank_reconciliation as br
    import make_demo_statement
    period = max(t.paid_at for t in rq.list_transactions("demo"))[:7]
    csv_text, stats = make_demo_statement.build("demo", period)
    run = br.reconcile("demo", period, csv_text.encode(), filename="statement.csv", actor="ngozi@riverbend.example")
    codes = [str(getattr(e.code, "value", e.code)) for e in run.exceptions]
    check("some payments match", len(run.matches) >= 1, str(len(run.matches)))
    check("exactly one transfer with no request behind it", codes.count("NOT_IN_SYSTEM") == 1, str(codes))


def test_reset_starts_clean() -> None:
    print("\n--reset: the same demo again, references from REQ-0001")
    before = len(rq.list_requisitions("demo"))
    demo_seed.seed(password=PW, reset=True)
    after = rq.list_requisitions("demo")
    check("same number of requests, not doubled", len(after) == before, f"{before} → {len(after)}")
    check("references restart", min(r.ref for r in after).endswith("0001"), min(r.ref for r in after))


def test_projects_time_and_claims_have_something_to_show() -> None:
    print("\nThe four newer screens have something to show")
    import grants
    import projects
    import timesheets as ts
    gf = projects.figures("demo", grants.find_agreement("demo", "GF-TB-26"))
    lines = {lf.code: lf for lf in gf.lines}
    check("the TB grant has money paid on its own budget lines",
          gf.paid > 0 and lines["2.1"].paid > 0 and lines["4.1"].paid > 0, str(gf.lines)[:200])
    check("…and money on its way", gf.committed > 0)
    check("nothing paid on the TB grant is left unassigned to a line",
          not any(lf.code == projects.UNASSIGNED and lf.paid for lf in gf.lines), str(gf.lines)[-200:])
    time_rows = projects.approved_time("demo", grants.find_agreement("demo", "GF-TB-26"))
    check("two months of approved time from two people",
          len({r["period"] for r in time_rows}) == 2 and len({r["staff_id"] for r in time_rows}) == 2, str(time_rows)[:200])
    musa = [t for t in ts.list_timesheets("demo") if t.staff_id.startswith("musa")]
    check("one of them records by week", musa and all(t.span == "week" for t in musa))
    claims = [r for r in rq.list_requisitions("demo") if r.kind == "expense_claim"]
    statuses = sorted(str(getattr(r.status, "value", r.status)) for r in claims)
    check("three claims: two reimbursed, one with Finance", statuses == ["in_review", "paid", "paid"], str(statuses))
    kano = next((r for r in claims if r.advance_id), None)
    check("one settles an advance and pays only the difference",
          kano is not None and kano.claim_total == 92_500 and kano.amount == 12_500)
    import advances
    check("…and that advance is retired", kano is not None and not advances.get("demo", kano.advance_id).open)
    pdf_ok = False
    try:
        import donor_report
        pdf_ok = donor_report.build("demo", grants.find_agreement("demo", "GF-TB-26"))[:4] == b"%PDF"
    except Exception as exc:  # pragma: no cover
        print("   ", exc)
    check("the TB grant's donor report builds", pdf_ok)


if __name__ == "__main__":
    print("Demo organisation (Riverbend Health Foundation)")
    test_it_only_ever_writes_to_the_demo_org()
    test_no_password_no_seed()
    test_no_secret_or_client_name_in_the_files()
    test_every_screen_has_something()
    test_the_trail_is_real()
    test_dates_look_like_two_months_of_work()
    test_an_advance_is_overdue()
    test_people_can_sign_in_and_see_their_queue()
    test_the_bank_statement_tells_the_story()
    test_projects_time_and_claims_have_something_to_show()
    test_reset_starts_clean()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
