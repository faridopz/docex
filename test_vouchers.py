"""Checks for vouchers.py: build totals + submit opens a routed transaction.
Run: python test_vouchers.py"""
from __future__ import annotations

import tempfile
from pathlib import Path

import notification_center as nc
import transactions as tx
import vouchers as vouchers_mod
from models import ReceiptItem
from per_diem import PerDiemPolicy, build_participant_payable, uniform_days

# Redirect all three stores to temp dirs.
_v = Path(tempfile.mkdtemp(prefix="docex_v_"))
_t = Path(tempfile.mkdtemp(prefix="docex_t_"))
_n = Path(tempfile.mkdtemp(prefix="docex_n_"))
vouchers_mod._VOUCHER_DIR = _v
tx._TXN_DIR = _t
tx._COUNTER_FILE = _t / ".counter"
nc._NOTIF_DIR = _n

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
