#!/usr/bin/env python3
"""
Pre-demo smoke test — prove the whole path works before you are in the room.

    python3 demo_check.py

Setup has broken in four different ways so far, and every one of them was
invisible until a screen was already on a projector:

  * the seeder waiting silently at a password prompt
  * the seeder and the API pointed at different stores, so a login that had
    just been created returned 401
  * a stale .next cache serving an unstyled page
  * an old uvicorn holding port 8000 without DOCEX_DB, so the app loaded and
    showed nothing

This checks all of it in about ten seconds. Run it the night before, and again
an hour before. A green run means the demo path works end to end.

It talks to the app in-process, so it does NOT need uvicorn running — it tests
the system, not your terminals. The last section checks your terminals too.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DB = os.environ.get("DOCEX_DB", "./demo.db")
ORG = os.environ.get("DOCEX_ORG", "default")
EMAIL = "demo@neem.org"

_fail: list[str] = []
_warn: list[str] = []


def ok(label: str) -> None:
    print(f"  \033[32m✓\033[0m {label}")


def bad(label: str, fix: str) -> None:
    print(f"  \033[31m✗\033[0m {label}\n      → {fix}")
    _fail.append(label)


def warn(label: str, fix: str) -> None:
    print(f"  \033[33m!\033[0m {label}\n      → {fix}")
    _warn.append(label)


def main() -> int:  # noqa: C901 - a checklist reads better flat
    print("\nDOCex pre-demo check")
    print("─" * 58)

    # ── 1. OCR ───────────────────────────────────────────────────────────
    print("\nOCR")
    try:
        import fast_extract
        if fast_extract.ocr_available():
            ok("tesseract installed — photographed receipts will read")
        else:
            bad("tesseract MISSING — the photo receipt will show nothing",
                "brew install tesseract, then restart the API")
    except Exception as exc:
        bad(f"could not check OCR ({exc})", "pip3 install -r requirements.txt")

    # ── 2. Storage ───────────────────────────────────────────────────────
    print("\nStorage")
    if not DB:
        bad("DOCEX_DB is not set",
            "export DOCEX_DB=./demo.db — without it the seeder and the API "
            "use different stores and login returns 401")
        return report()

    import store
    import store_sql
    store.set_store(store_sql.SqliteStore(DB))
    ok(f"SQLite at {DB}")

    # ── 3. Demo data ─────────────────────────────────────────────────────
    print("\nDemo data")
    import auth
    user = auth.get_by_email(EMAIL, ORG)
    if user is None:
        bad(f"no {EMAIL} in org '{ORG}'",
            f"DOCEX_DB={DB} DOCEX_ORG={ORG} python3 demo_seed.py "
            "--reset --password 'DemoPass2026'")
        return report()
    ok(f"login exists — {EMAIL} ({user.role})")

    import requisitions as rq
    reqs = rq.list_requisitions(ORG)
    if not reqs:
        bad("no requisitions seeded", "re-run demo_seed.py --reset")
        return report()
    ok(f"{len(reqs)} requisitions")

    # The blocked one is the demo. Without it there is no story.
    blocked = [
        r for r in reqs
        if r.status == rq.ReqStatus.IN_REVIEW
        and any(c.result == rq.CheckResult.FAIL and not c.overridden for c in r.checks)
    ]
    if blocked:
        b = blocked[0]
        fail = next(c for c in b.checks
                    if c.result == rq.CheckResult.FAIL and not c.overridden)
        ok(f"BLOCKED payment ready — {b.ref} {b.currency} {b.amount:,.0f}")
        print(f"      ↳ {fail.message[:78]}")
    else:
        bad("no blocked payment — the override moment will not work",
            "python3 demo_seed.py --reset --password 'DemoPass2026'")

    paid = [r for r in reqs if r.status == rq.ReqStatus.PAID]
    ok(f"{len(paid)} paid, for the Payments screen") if paid else warn(
        "no paid payments", "the Payments screen will be empty")

    try:
        import field_receipts as fr
        rec = fr.list_receipts(ORG)
        ok(f"{len(rec)} field receipts") if rec else warn(
            "no field receipts", "the receipts screen will be empty")
    except Exception:
        warn("could not read field receipts", "not fatal — check the screen manually")

    summary = rq.audit_summary(ORG)
    ok(f"audit: {summary['exceptions_total']} exception(s), "
       f"audit_ready={summary['audit_ready']}")

    # ── 4. The app answers ───────────────────────────────────────────────
    print("\nApplication")
    try:
        from fastapi.testclient import TestClient
        import api.main as m
        client = TestClient(m.app)

        if client.get("/health").status_code == 200:
            ok("app boots")
        else:
            bad("app does not answer /health", "check the API terminal for errors")

        r = client.post("/auth/login",
                        json={"email": EMAIL, "password": "DemoPass2026"})
        if r.status_code != 200:
            bad(f"login failed ({r.status_code})",
                "re-run demo_seed.py --reset --password 'DemoPass2026'")
            return report()
        ok("login works")
        h = {"Authorization": f"Bearer {r.json()['token']}"}

        for path, label in [
            ("/org/config", "org config"),
            ("/departments", "departments"),
            ("/requisitions", "Requisitions screen"),
            ("/field-receipts", "Field receipts screen"),
            ("/payments", "Payments screen"),
            ("/audit/summary", "Audit screen"),
            ("/dashboard", "Dashboard"),
            ("/reconciliation", "Reconciliation screen"),
            ("/timesheets", "Timesheets screen"),
            ("/timesheets/mine", "My timesheets"),
        ]:
            code = client.get(path, headers=h).status_code
            ok(f"{label} ({code})") if code == 200 else bad(
                f"{label} returned {code}", "check the API terminal")

        if client.get("/requisitions").status_code == 401:
            ok("auth is closed — unauthenticated requests rejected")
        else:
            bad("API answers without credentials",
                "auth middleware is not active — do NOT use real client data")
        # Reconciliation is the newest thing in the demo and has the most
        # moving parts: a feature flag, a statement file, column detection and
        # a date format the file may not settle on its own. Prove the whole
        # import path here rather than discovering it live.
        try:
            import datetime as _dt

            import make_demo_statement as _mds

            csv_text, stats = _mds.build(ORG)
            if stats["matched_payments"] == 0:
                warn("demo statement has no payments to match",
                     "re-run demo_seed.py, then make_demo_statement.py")
            else:
                ok(f"demo statement built — {stats['matched_payments']} payment(s) "
                   "should match")

            files = {"statement": ("demo_bank_statement.csv",
                                   csv_text.encode(), "text/csv")}
            period = _dt.date.today().strftime("%Y-%m")
            r = client.post("/reconciliation/preview", headers=h, files=files)
            if r.status_code == 422 and "date_format" in r.text:
                # Expected early in a month: the file cannot prove day-first.
                # The screen asks; here we answer, and the retry must work.
                r = client.post("/reconciliation/preview", headers=h, files=files,
                                data={"date_format": "%d/%m/%Y"})
                ok("statement dates are ambiguous — the day/month prompt is "
                   "expected in the UI") if r.status_code == 200 else bad(
                    f"preview still fails after choosing a date format ({r.status_code})",
                    "check api/reconciliation_routes.py")
            if r.status_code == 200:
                ok(f"statement reads — {r.json()['debits']} payments out")
                rr = client.post("/reconciliation", headers=h, files=files,
                                 data={"period": period, "date_format": "%d/%m/%Y"})
                if rr.status_code == 200:
                    run = rr.json()
                    planted = [e for e in run["exceptions"]
                               if e["code"] == "NOT_IN_SYSTEM" and e["amount"] >= 500_000]
                    ok(f"reconciles — {run['matched']} matched, "
                       f"{len(run['exceptions'])} exception(s)")
                    ok("the unapproved ₦750,000 transfer is caught") if planted else bad(
                        "the planted unapproved transfer was NOT flagged",
                        "the demo's main finding is missing — check the matcher")
                else:
                    bad(f"reconcile failed ({rr.status_code})", rr.text[:120])
            else:
                bad(f"statement preview failed ({r.status_code})", r.text[:120])
        except Exception as exc:
            warn(f"reconciliation path not checked: {exc}",
                 "is bank_reconciliation enabled in the org profile?")

    except Exception as exc:
        bad(f"app failed to start: {exc}", "check the API terminal for a traceback")

    # ── 5. Demo documents ────────────────────────────────────────────────
    print("\nDemo documents")
    docs = Path(__file__).parent / "demo_docs"
    files = sorted(docs.glob("*")) if docs.is_dir() else []
    if len(files) >= 7:
        ok(f"{len(files)} documents ready to drag in")
    else:
        warn(f"only {len(files)} demo documents", "python3 make_demo_docs.py")

    # ── 6. Your terminals ────────────────────────────────────────────────
    # Everything above tests the system in-process. This tests what is
    # actually serving, which is the thing that was wrong twice today.
    print("\nRunning servers")
    for url, label, fix in [
        ("http://localhost:8000/health", "API on :8000",
         f"cd ~/Desktop/docex && DOCEX_DB={DB} DOCEX_ORG={ORG} "
         "uvicorn api.main:app --reload --port 8000"),
        ("http://localhost:3000", "Frontend on :3000",
         "cd ~/Desktop/docex/web && npm run dev"),
    ]:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                ok(f"{label} responding ({resp.status})")
        except urllib.error.HTTPError as exc:
            ok(f"{label} responding ({exc.code})")
        except Exception:
            warn(f"{label} not running", fix)

    return report()


def report() -> int:
    print("\n" + "─" * 58)
    if _fail:
        print(f"\033[31m{len(_fail)} BLOCKING issue(s)\033[0m — fix before the demo:")
        for f in _fail:
            print(f"  · {f}")
        return 1
    if _warn:
        print(f"\033[33mReady, with {len(_warn)} warning(s).\033[0m")
        for w in _warn:
            print(f"  · {w}")
    else:
        print("\033[32mAll green. The demo path works.\033[0m")
    print("\n  http://localhost:3000/login   demo@neem.org / DemoPass2026")
    print("  Receipts → Requisitions → the BLOCKED one → Audit")
    print("  Keep demo amounts under ₦250,000.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
