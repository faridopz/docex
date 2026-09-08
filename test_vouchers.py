"""Checks for vouchers.py: build totals + submit opens a routed transaction.
Run: python test_vouchers.py"""
from __future__ import annotations

import os
import tempfile

import store

# One isolated backend for all three engines, installed BEFORE they are
# imported. Vouchers, transactions and notifications used to be loose files, so
# this suite redirected three module-level directories. Those directories are
# gone — the records now live in the store so they survive a redeploy — and
# leaving the old redirection in place meant the suite quietly read and wrote
# the developer's real data/ directory, counting notifications from every
# previous run.
store.set_store(store.JsonFileStore(tempfile.mkdtemp(prefix="docex_vouch_")))
os.environ["DOCEX_ORG"] = "vouchertest"

import notification_center as nc  # noqa: E402
import transactions as tx  # noqa: E402
import vouchers as vouchers_mod  # noqa: E402
from models import ReceiptItem  # noqa: E402
from per_diem import (  # noqa: E402
    PerDiemPolicy,
    build_participant_payable,
    uniform_days,
)

_fail = 0


def check(name, got, want):
    global _fail
    ok = abs(got - want) < 0.01 if isinstance(got, (int, float)) and isinstance(want, (int, float)) else got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


policy = PerDiemPolicy(rate_per_day=20_000)  # meals 25% default

# Two participants: one clean, one with an unreadable receipt (=> a flag).
p1 = build_participant_payable(
    "Aisha", policy, uniform_days(3, covered=["meals"]),
    [ReceiptItem(filename="taxi", amount=5_000, category="transport")])
p2 = build_participant_payable(
    "Bello", policy, uniform_days(2, covered=["meals"]),
    [ReceiptItem(filename="blurry", amount=None, category="transport")])

# Aisha: 45,000 + 5,000 = 50,000 ; Bello: 30,000 + 0 = 30,000
v = vouchers_mod.build_voucher("Q3 Workshop", [p1, p2],
                               roles=["Facilitator", "Participant"], created_by="finance.bola")
check("voucher total", v.total, 80_000)
check("participant count", v.participant_count, 2)
check("flagged lines (Bello's unreadable receipt)", v.flagged_count, 1)
check("line role stamped", v.lines[0].role, "Facilitator")
check("draft has no transaction yet", v.txn_ref, None)

# Submit → opens transaction, routes to compliance review.
v = vouchers_mod.submit(v.id, created_by="finance.bola")
check("voucher now has a V-ref", v.txn_ref[0], "V")
txn = tx.load(v.txn_id)
check("routed to compliance review", txn.state, "compliance_review")
check("transaction amount matches voucher", txn.amount, 80_000)

# Fire the notification the route would fire, then assert compliance got it.
nc.notify_transition(txn, txn.history[-1])
check("compliance notified", nc.unread_count("compliance"), 1)

# Re-submit is a no-op (no duplicate transaction).
ref_before = v.txn_ref
v2 = vouchers_mod.submit(v.id)
check("re-submit does not open a duplicate", v2.txn_ref, ref_before)

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All voucher checks passed.")
