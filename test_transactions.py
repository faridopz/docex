"""Deterministic checks for transactions.py. Run: python test_transactions.py"""
from __future__ import annotations

import tempfile
from pathlib import Path

import transactions as tx

# Redirect all persistence to a throwaway temp dir so tests never touch the
# real transactions/ folder or its counter.
_tmp = Path(tempfile.mkdtemp(prefix="docex_txn_test_"))
tx._TXN_DIR = _tmp
tx._COUNTER_FILE = _tmp / ".counter"

_fail = 0


def check(name: str, got, want) -> None:
    global _fail
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


def expect_error(name: str, fn) -> None:
    global _fail
    try:
        fn()
        print(f"FAIL  {name}: expected TransactionError, none raised")
        _fail += 1
    except tx.TransactionError:
        print(f"PASS  {name}: raised as expected")


# ── references are prefixed by kind and monotonic ──
c1 = tx.create("compliance_check", "Voucher batch A", amount=55_000)
p1 = tx.create("payment_run", "March payments")
c2 = tx.create("compliance_check", "Voucher batch B")
check("first compliance ref prefix", c1.ref[0], "C")
check("payment ref prefix", p1.ref[0], "P")
check("counter is monotonic & shared", [c1.ref, p1.ref, c2.ref],
      [f"C{int(c1.ref[1:])}", f"P{int(c1.ref[1:]) + 1}", f"C{int(c1.ref[1:]) + 2}"])

# ── initial state + owner ──
check("starts submitted", c1.state, "submitted")
check("submitted owned by program", c1.owner_department, "program")
check("created event recorded", c1.history[0].type, "created")

# ── legal happy-path transitions move the owner department ──
c1 = tx.transition(c1, "compliance_review", department="program", note="intake done")
check("now compliance_review", c1.state, "compliance_review")
check("owned by compliance", c1.owner_department, "compliance")
c1 = tx.transition(c1, "finance_review", department="compliance")
check("owned by finance", c1.owner_department, "finance")
c1 = tx.transition(c1, "approval", department="finance")
check("approval event type", c1.history[-1].type, "approved")
c1 = tx.transition(c1, "paid", department="management")
check("paid state", c1.state, "paid")
check("paid event type", c1.history[-1].type, "paid")

# ── illegal transitions are rejected, state unchanged ──
expect_error("cannot move out of terminal paid", lambda: tx.transition(c1, "submitted"))
expect_error("cannot skip straight submitted->paid",
             lambda: tx.transition(tx.create("voucher", "V"), "paid"))
check("state preserved after rejected move", tx.load(c1.id).state, "paid")

# ── returned side-state ──
c2 = tx.transition(c2, "compliance_review", department="program")
c2 = tx.transition(c2, "returned", department="compliance", note="missing CAC")
check("returned has no owner", c2.owner_department, None)
check("returned event type", c2.history[-1].type, "returned")
c2 = tx.transition(c2, "compliance_review", department="program", note="CAC supplied")
check("can re-enter pipeline from returned", c2.state, "compliance_review")

# ── views are idempotent per viewer ──
c2 = tx.record_view(c2, department="finance")
c2 = tx.record_view(c2, department="finance")   # dup — no-op
c2 = tx.record_view(c2, department="management")
check("viewed_by deduped", sorted(c2.viewed_by), ["finance", "management"])

# ── lookups + filtered listing ──
check("load_by_ref round-trips", tx.load_by_ref(c1.ref).id, c1.id)
paid_rows = tx.list_all(state="paid")
check("filter by state=paid finds c1", any(r.ref == c1.ref for r in paid_rows), True)
finance_rows = tx.list_all(department="finance")
check("filter by dept excludes non-finance owners",
      all(r.owner_department == "finance" for r in finance_rows), True)

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All transaction checks passed.")
