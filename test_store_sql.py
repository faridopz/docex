"""Tests for durable SQL storage.

The point of this suite: prove records SURVIVE a restart (the thing the JSON
file store on an ephemeral container does not do), that org isolation still
holds, and that the existing engines work unchanged on the SQL backend.

Run: python test_store_sql.py
Postgres: set DOCEX_DATABASE_URL to also exercise PostgresStore.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import grants
import payroll
import store
import store_sql

_dir = Path(tempfile.mkdtemp(prefix="docex_sql_"))
_db = _dir / "docex.db"

_fail = 0


def check(name, got, want):
    global _fail
    ok = abs(got - want) < 0.01 if isinstance(got, (int, float)) and isinstance(want, (int, float)) else got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


def expect_err(name, fn):
    global _fail
    try:
        fn()
        print(f"FAIL  {name}: expected an error, none raised")
        _fail += 1
    except Exception:
        print(f"PASS  {name}: raised as expected")


# ── basic CRUD ──
s = store_sql.SqliteStore(_db)
s.put("eva", "testrecs", "agr-1", {"donor": "USAID", "value": 1000})
s.put("eva", "testrecs", "agr-2", {"donor": "Gates", "value": 500})
s.put("neem", "testrecs", "agr-3", {"donor": "EU", "value": 250})

check("get returns the record", s.get("eva", "testrecs", "agr-1")["donor"], "USAID")
check("list is org-scoped", len(s.list("eva", "testrecs")), 2)
check("other org isolated", [r["donor"] for r in s.list("neem", "testrecs")], ["EU"])
check("missing record is None", s.get("eva", "testrecs", "nope"), None)
check("org stamped on record", s.get("neem", "testrecs", "agr-3")["org_id"], "neem")
check("collections listed", s.collections("eva"), ["testrecs"])

# ── upsert, not duplicate ──
s.put("eva", "testrecs", "agr-1", {"donor": "USAID", "value": 9999})
check("upsert overwrites in place", s.get("eva", "testrecs", "agr-1")["value"], 9999)
check("upsert did not duplicate", len(s.list("eva", "testrecs")), 2)

# ── delete ──
check("delete returns True", s.delete("eva", "testrecs", "agr-2"), True)
check("delete of missing returns False", s.delete("eva", "testrecs", "agr-2"), False)
check("record gone", len(s.list("eva", "testrecs")), 1)

# ── validation still enforced ──
expect_err("path traversal rejected", lambda: s.get("../etc", "testrecs", "x"))
expect_err("empty org rejected", lambda: s.list("", "testrecs"))

# ── THE POINT: durability across a "restart" ──
del s
reopened = store_sql.SqliteStore(_db)          # brand-new connection, as after a redeploy
check("data survives restart", reopened.get("eva", "testrecs", "agr-1")["value"], 9999)
check("counts survive restart", reopened.count(), 2)

# ── backup produces a usable copy ──
backup_path = reopened.backup(_dir / "backup.db")
restored = store_sql.SqliteStore(backup_path)
check("backup contains the data", restored.get("eva", "testrecs", "agr-1")["value"], 9999)

# ── engines work unchanged on SQL ──
store.set_store(reopened)
ag = grants.add_agreement("eva", donor="USAID", project_code="P-1", value=1_000_000)
grants.add_tranche("eva", ag.id, "2026-03-01", 400_000, label="Q1")
grants.record_inflow("eva", ag.id, "2026-03-10", 400_000)
rows = grants.monthly_matrix("eva")
check("grants engine works on SQL", rows[0].received, 400_000)

payroll.set_policy("eva", payroll.PayrollPolicy(
    rules=[payroll.DeductionRule(code="PAYE", method="percent", rate_percent=10.0)]))
payroll.add_staff("eva", name="Test Person", gross_salary=100_000,
                  allocations=[payroll.SalaryAllocation(project_code="P-1", donor="USAID", percent=100)])
run = payroll.build_run("eva", "2026-03")
check("payroll engine works on SQL", run.total_net, 90_000)

# Engine data also survives a restart.
store.set_store(store_sql.SqliteStore(_db))
check("agreements persist for the engines", len(grants.list_agreements("eva")), 1)
check("staff persist for the engines", len(payroll.list_staff("eva")), 1)

# ── migration from the JSON store ──
json_root = _dir / "jsondata"
json_store = store.JsonFileStore(json_root)
json_store.put("eva", "legacy", "old-1", {"note": "from files"})
json_store.put("neem", "legacy", "old-2", {"note": "other org"})
target = store_sql.SqliteStore(_dir / "migrated.db")
moved = store_sql.migrate_json_to_sql(json_root, target)
check("migration moved both records", moved, 2)
check("migrated content intact", target.get("eva", "legacy", "old-1")["note"], "from files")
check("migration is idempotent", store_sql.migrate_json_to_sql(json_root, target), 2)
check("no duplicates after re-run", len(target.list("eva", "legacy")), 1)

# ── optional: Postgres, only when a real URL is supplied ──
dsn = os.environ.get("DOCEX_DATABASE_URL")
if dsn:
    pg = store_sql.PostgresStore(dsn)
    pg.put("eva", "smoke", "s-1", {"ok": True})
    check("postgres round-trip", pg.get("eva", "smoke", "s-1")["ok"], True)
    pg.delete("eva", "smoke", "s-1")
else:
    print("SKIP  PostgresStore — set DOCEX_DATABASE_URL to verify it against a real database")

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All SQL storage checks passed.")
